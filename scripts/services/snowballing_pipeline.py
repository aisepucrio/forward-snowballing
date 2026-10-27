import json
import os
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor

import requests

from services.cache import get_cached, init_db, save_to_cache
from services.deduplication import deduplicate_citations
from services.normalize import normalize_doi
from services.settings import cache_enabled, database_enabled
from services.search import (
    build_pages,
    collapse_duplicates_by_key,
    enrich_incomplete_citations,
    get_record_key,
    is_semantic_reference_noise,
    merge_records_across_sources,
    tag_source,
    extract_npages,
    fallback_openalex_by_title,
    fallback_opencitations_by_doi,
    reconstruct_abstract_from_inverted_index,
    search_combined,
)


NULL_INPUTS = {None, "", "-", "null", "None"}
# Versão 3: o payload passou a carregar search_id / seed_id / paper_id_map.
# Entradas antigas precisam ser refeitas, senão voltam sem os ids do banco.
RESULT_CACHE_VERSION = 3

# Usado enquanto não existe login. Quando houver autenticação, trocar pelo id do
# usuário logado.
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"


def _load_database_layer():
    """
    Importa a camada de banco sob demanda.

    Mantém o Postgres opcional: quem só quer rodar o snowballing (o caso dos
    artefatos de reprodução do paper) não precisa de psycopg2 nem de um banco
    no ar. Levanta ImportError se a stack não estiver instalada.
    """
    from dotenv import load_dotenv
    load_dotenv()

    from services.snowmap_bd import save_full_result

    return save_full_result, os.getenv("TEMP_USER_ID", DEFAULT_USER_ID)


class SearchInput:
    def __init__(self, doi=None, title=None):
        self.doi = normalize_doi(doi) if doi not in NULL_INPUTS else None
        self.title = title.strip() if isinstance(title, str) and title.strip() not in NULL_INPUTS else None

    @classmethod
    def from_argv(cls, argv):
        doi = argv[1].strip() if len(argv) > 1 else None
        title = argv[2].strip() if len(argv) > 2 else None
        return cls(doi=doi, title=title)

    def validate(self):
        if self.doi or self.title:
            return
        raise ValueError("DOI ou título devem ser informados")


class CitationNormalizer:
    @staticmethod
    def normalize_counts(citations):
        normalized = []

        for citation in citations:
            item = dict(citation)
            count = (
                item.get("citations_count")
                if item.get("citations_count") is not None
                else item.get("citationCount")
                if item.get("citationCount") is not None
                else item.get("cited_by_count")
            )

            if count is None:
                count = 0

            item["citations_count"] = count
            item["citationCount"] = count
            normalized.append(item)

        return normalized


class OpenAlexReferenceProvider:
    def __init__(self):
        # Setado a cada get_references(): quantos dos referenced_works
        # listados pelo OpenAlex de fato resolveram para um work de verdade.
        # Um provider é criado por processo e usado uma única vez por busca
        # então guardar isso na instância é seguro apesar de não ser thread-safe
        # em geral.
        self.last_warning = None

    def get_references(self, doi=None, openalex_id=None):
        self.last_warning = None
        try:
            # As referências vêm do campo referenced_works do work no OpenAlex.
            # O work pode ser localizado pelo DOI OU pelo openalex_id — este
            # último é essencial para artigos sem DOI, que senão ficariam sem
            # referências mesmo o OpenAlex tendo-as.
            work_url = self._work_url(doi, openalex_id)
            if not work_url:
                return []

            resp = requests.get(work_url, timeout=30)
            if resp.status_code != 200:
                return []

            refs_ids = resp.json().get("referenced_works", [])
            if not refs_ids:
                return []

            references = []
            resolved_ids = set()
            chunk_size = 50
            failed_batches = 0
            for index in range(0, len(refs_ids), chunk_size):
                chunk = refs_ids[index:index + chunk_size]
                # per-page é obrigatório: sem ele o OpenAlex devolve apenas 25
                # resultados por página, truncando lotes maiores em silêncio.
                batch_url = (
                    f"https://api.openalex.org/works"
                    f"?filter=openalex_id:{'|'.join(chunk)}&per-page={chunk_size}"
                )
                resp_batch = requests.get(batch_url, timeout=30)
                if resp_batch.status_code != 200:
                    failed_batches += 1
                    continue

                batch_results = resp_batch.json().get("results", [])
                references.extend(self._map_reference(ref) for ref in batch_results)
                resolved_ids.update(
                    str(ref.get("id", "")).rstrip("/").rsplit("/", 1)[-1]
                    for ref in batch_results
                    if ref.get("id")
                )

            # Alguns IDs não aparecem no filtro em lote, embora ainda possam
            # retornar metadados quando consultados individualmente.
            recovered_individually = 0
            for reference_id in refs_ids:
                short_id = str(reference_id).rstrip("/").rsplit("/", 1)[-1]
                if short_id in resolved_ids:
                    continue

                individual = requests.get(
                    f"https://api.openalex.org/works/{short_id}",
                    timeout=30,
                )
                if individual.status_code != 200:
                    continue

                reference_data = individual.json()
                if reference_data.get("title") or reference_data.get("doi"):
                    mapped_reference = self._map_reference(reference_data)
                    mapped_reference["openalex_id"] = reference_data.get("id")
                    references.append(mapped_reference)
                    recovered_individually += 1

            # O OpenAlex às vezes lista, no work original, referenced_works que
            # não resolvem mais em /works (work deletado/mesclado do lado
            # deles) — os IDs somem em silêncio do batch fetch e a contagem
            # final vem menor do que os referenced_works prometiam, parecendo
            # perda de dado nossa. Não tem como recuperar isso; só dá pra
            # avisar.
            missing = len(refs_ids) - len(references)
            print(
                f"[OPENALEX REFERENCES] listed={len(refs_ids)}, "
                f"resolved={len(references)}, missing={missing}, "
                f"recovered_individually={recovered_individually}, "
                f"failed_batches={failed_batches}",
                file=sys.stderr,
            )
            if missing > 0:
                self.last_warning = (
                    f"OpenAlex lista {len(refs_ids)} referências para este paper, mas "
                    f"{missing} desses work IDs não resolveram mais (removidos/mesclados "
                    "no lado do OpenAlex). Contagem final não inclui essas."
                )

            return references

        except Exception as exc:
            print(f"[ERROR OPENALEX] {exc}", file=sys.stderr)
            return []

    def _work_url(self, doi, openalex_id):
        if openalex_id:
            # aceita tanto a URL completa quanto só o id (W123...)
            short_id = str(openalex_id).rstrip("/").rsplit("/", 1)[-1]
            if short_id:
                return f"https://api.openalex.org/works/{short_id}"

        clean_doi = normalize_doi(doi)
        if clean_doi:
            return f"https://api.openalex.org/works/https://doi.org/{clean_doi}"

        return None

    def _map_reference(self, ref):
        primary_loc = ref.get("primary_location") or {}
        source = primary_loc.get("source") or {}
        biblio = ref.get("biblio") or {}
        pages = build_pages(biblio.get("first_page"), biblio.get("last_page"))

        return {
            "title": ref.get("title") or "Untitled",
            "year": ref.get("publication_year", "-"),
            "venue": source.get("display_name", "-"),
            "abstract": reconstruct_abstract_from_inverted_index(ref.get("abstract_inverted_index")),
            "doi": normalize_doi(ref.get("doi")) if ref.get("doi") else "-",
            "authors": [
                {"name": a.get("author", {}).get("display_name", "-")}
                for a in (ref.get("authorships") or [])
            ],
            "citationCount": ref.get("cited_by_count", 0),
            "citations_count": ref.get("cited_by_count", 0),
            "open_access": ref.get("open_access", {}).get("is_oa"),
            "url": primary_loc.get("landing_page_url"),
            "keywords": [
                c.get("display_name")
                for c in ref.get("concepts", [])
                if c.get("display_name")
            ][:10],
            "language": ref.get("language"),
            "pages": pages,
            "numpages": extract_npages(pages),
            "source": "openalex",
            # "paratext" é volume de anais/front matter: o OpenAlex às vezes
            # resolve a referência ao volume em vez do artigo dentro dele.
            "openalex_type": ref.get("type"),
        }


class SnowballingResultBuilder:
    def build_base(self, search_input, paper, mode):
        return {
            "_cache_version": RESULT_CACHE_VERSION,
            "input_doi": search_input.doi or "-",
            "input_title": search_input.title or "-",
            "resolved_doi": normalize_doi(paper.get("doi")) or search_input.doi or "-",
            "data_source": paper.get("api", "-"),
            "title": paper.get("title", "-"),
            "authors": [
                {"name": author.get("name", "-")}
                for author in paper.get("authors", [])
            ] if isinstance(paper.get("authors"), list) else [],
            "year": paper.get("year", "-"),
            "venue": paper.get("venue", "-"),
            "abstract": paper.get("abstract", "-"),
            "mode": mode,
            "open_access": paper.get("open_access", None),
            "url": paper.get("url", None),
            "keywords": paper.get("keywords", []),
            "language": paper.get("language", None),
            "pages": paper.get("pages", None),
            "numpages": paper.get("numpages", None),
            # search_combined seta isso quando uma fonte falha e o resultado
            # vem só da outra (ex.: Semantic Scholar indisponível) — sem
            # propagar aqui, a falha fica invisível: a contagem de
            # referências/citações sai menor e nada no resultado explica por quê.
            "warning": paper.get("warning"),
            "partial_result": paper.get("partial_result", False),
            "semantic_citation_count": paper.get("semantic_citation_count"),
            "semantic_reference_count": paper.get("semantic_reference_count"),
            "openalex_citation_count": paper.get("openalex_citation_count"),
        }

    def build_forward(self, search_input, paper, citations, references):
        result = self.build_base(search_input, paper, "forward")
        result.update({
            "citationCount": paper.get("citationCount", paper.get("citations_count", 0)),
            "citations_retrieved": len(citations),
            "citations": citations,
            "references_count": len(references),
            "references_retrieved": len(references),
            "references": references,
        })
        return result


class SnowballingPipeline:
    def __init__(self, reference_provider=None, result_builder=None, write_debug_output=True):
        self.reference_provider = reference_provider or OpenAlexReferenceProvider()
        self.result_builder = result_builder or SnowballingResultBuilder()
        self.write_debug_output = write_debug_output

    def run_forward(self, search_input):
        search_input.validate()

        cached = None
        if cache_enabled():
            init_db()
            cached = get_cached(doi=search_input.doi, title=search_input.title, mode="forward")
        if (
            cached
            and cached.get("citations")
            and cached.get("references")
            and cached.get("_cache_version") == RESULT_CACHE_VERSION
        ):
            return cached

        if search_input.doi:
            # DOI conhecido de início: busca o paper e as referências em paralelo.
            with ThreadPoolExecutor(max_workers=2) as executor:
                fut_paper = executor.submit(search_combined, search_input.doi, search_input.title)
                fut_refs = executor.submit(self.reference_provider.get_references, search_input.doi)
                paper = fut_paper.result()
                openalex_references = fut_refs.result()
            seed_doi = search_input.doi
        else:
            # Busca por título: os identificadores só são conhecidos depois de
            # resolver o paper. Sem isso as referências sairiam sempre vazias.
            paper = search_combined(search_input.doi, search_input.title)
            resolved_doi = normalize_doi(paper.get("doi"))
            openalex_id = paper.get("openalex_id")

            # Artigos sem DOI (comuns em anais e periódicos regionais) ainda têm
            # referências no OpenAlex, acessíveis pelo openalex_id. Se o paper
            # resolvido não trouxe nenhum identificador, resolve o openalex_id
            # pelo título antes de desistir das referências.
            if not resolved_doi and not openalex_id:
                openalex_match = fallback_openalex_by_title(search_input.title)
                if openalex_match:
                    openalex_id = openalex_match.get("openalex_id")
                    resolved_doi = normalize_doi(openalex_match.get("doi")) or resolved_doi

            openalex_references = self.reference_provider.get_references(
                doi=resolved_doi, openalex_id=openalex_id
            )
            seed_doi = resolved_doi

        # O Semantic Scholar também contribui
        # referências (via paper.get("references"), que search_combined já
        # traz de search_input.doi ou do título resolvido) — sem somar as
        # duas fontes aqui, o forward ficava com o "References" contando só o
        # que o OpenAlex resolveu, bem menor do que a busca backward do mesmo
        # paper (que já fazia o merge desde o commit anterior).
        semantic_references = [
            record
            for record in tag_source(paper.get("references"), "semantic")
            if not is_semantic_reference_noise(record)
        ]
        paper["citations"] = tag_source(paper.get("citations"), "semantic")

        # OpenCitations entra quando o Semantic Scholar não entregou lista de
        # referências — seja por bloqueio da editora, seja porque não respondeu
        # (sem chave de API, 429 é o caso comum). Depender só do bloqueio
        # confirmado deixava a fonte complementar presa justamente à fonte que
        # mais falha. Quando o Semantic entrega a lista, ela é a mais completa
        # e a chamada extra não compensa.
        #
        # Fica aqui, e não em search_combined: só neste ponto as referências do
        # OpenAlex já existem, e sem elas não há como saber o que é novo.
        opencitations_references = []
        if not semantic_references and seed_doi:
            opencitations_references = fallback_opencitations_by_doi(seed_doi)
        semantic_citations = paper.get("citations", []) or []

        # Com a lista do Semantic disponível, o OpenAlex só complementa. Um
        # registro "paratext" (volume de anais) é a mesma referência que o
        # Semantic já resolveu para o artigo certo, mas não casa por DOI nem
        # por título e entrava como referência extra. Sem o Semantic, ele é a
        # única pista de que a referência existe, então fica.
        if semantic_references:
            openalex_complement = [
                record for record in openalex_references
                if record.get("openalex_type") != "paratext"
            ]
        else:
            openalex_complement = openalex_references

        print(
            f"[SOURCE COUNTS] Semantic: references={len(semantic_references)}; "
            f"OpenAlex: references={len(openalex_references)}",
            file=sys.stderr,
        )
        print(
            f"[SEED COUNTS] Semantic: citations={paper.get('semantic_citation_count')}, "
            f"references={paper.get('semantic_reference_count')}; "
            f"OpenAlex: citations={paper.get('openalex_citation_count')}, "
            f"references_listed={len(openalex_references)}",
            file=sys.stderr,
        )

        # collapse_duplicates_by_key roda DEPOIS do enriquecimento: é ele que
        # descobre o DOI de registros que chegaram só com título, e sem uma
        # segunda passada esses pares nunca são reconhecidos como o mesmo
        # trabalho.
        citations = CitationNormalizer.normalize_counts(
            collapse_duplicates_by_key(
                enrich_incomplete_citations(
                    paper.get("citations", [])
                )
            )
        )
        references = CitationNormalizer.normalize_counts(
            collapse_duplicates_by_key(
                enrich_incomplete_citations(
                    merge_records_across_sources(
                        merge_records_across_sources(
                            semantic_references,
                            openalex_complement,
                            match_titles=True,
                        ),
                        opencitations_references,
                    )
                )
            )
        )

        semantic_reference_keys = {
            get_record_key(item) for item in semantic_references
        }
        cross_source_matches = sum(
            1 for record in openalex_references
            if get_record_key(record) in semantic_reference_keys
        )

        print(
            f"[DEDUP COUNTS] References: semantic={len(semantic_references)}, "
            f"openalex={len(openalex_references)}, "
            f"cross_source_matches={cross_source_matches}, "
            f"final_after_merge={len(references)}",
            file=sys.stderr,
        )

        print(
            f"[SOURCE COUNTS] Final forward: citations={len(citations)}, "
            f"references={len(references)}",
            file=sys.stderr,
        )

        # Conta o que a OpenCitations trouxe e nenhuma outra fonte trouxe.
        # merge_records_across_sources e collapse_duplicates_by_key preservam o
        # registro da primeira fonte em que ele aparece, então o que chega ao
        # resultado com source == "opencitations" não casou com nada das outras
        # fontes pela chave de identidade do pipeline (get_record_key).
        #
        # Limite conhecido: essa chave usa o DOI quando existe e só cai para o
        # título quando não existe, então um registro com DOI nunca é comparado
        # por título com outro sem DOI. Se o OpenAlex trouxer uma referência sem
        # DOI (cerca de 10% nos artigos medidos) e a OpenCitations trouxer a
        # mesma com DOI, as duas sobrevivem e esta contagem inclui a duplicata.
        opencitations_added = sum(
            1 for record in references if record.get("source") == "opencitations"
        )
        if opencitations_references:
            print(
                f"[OPENCITATIONS] listed={len(opencitations_references)}, "
                f"added={opencitations_added}",
                file=sys.stderr,
            )
        if opencitations_added:
            opencitations_note = (
                f"OpenCitations acrescentou {opencitations_added} "
                f"{'referência' if opencitations_added == 1 else 'referências'} "
                "que não vieram das outras fontes."
            )
            existing_warning = paper.get("warning")
            paper["warning"] = (
                f"{existing_warning} | {opencitations_note}" if existing_warning else opencitations_note
            )

        openalex_warning = self.reference_provider.last_warning
        if openalex_warning:
            existing_warning = paper.get("warning")
            paper["warning"] = (
                f"{existing_warning} | {openalex_warning}" if existing_warning else openalex_warning
            )
            paper["partial_result"] = True

        result = self.result_builder.build_forward(search_input, paper, citations, references)
        self._save(result, search_input.doi)
        return result

    def _persist_to_database(self, result):
        """
        Grava o resultado no PostgreSQL como DUAS searches: uma 'forward' com as
        citations e outra 'backward' com as references.

        O schema guarda a direção em searches.direction, ou seja, por busca e não
        por resultado — então cada lista precisa da sua própria linha. Falha aqui
        nunca derruba a busca: o snowballing continua funcionando sem banco.

        Desligado por padrão (SNOWMAP_ENABLE_DB): sem a chave, nem tenta
        conectar e os ids saem como None.
        """
        save_full_result = None
        if database_enabled():
            try:
                save_full_result, user_id = _load_database_layer()
            except ImportError as import_error:
                print(f"[BD INDISPONIVEL] {import_error}", file=sys.stderr)

        paper_id_map = {}

        if save_full_result:
            directions = (
                ("forward", "search_id", result.get("citations") or []),
                ("backward", "search_id_backward", result.get("references") or []),
            )

            for direction, result_key, papers in directions:
                if not papers:
                    result[result_key] = None
                    continue

                try:
                    ids = save_full_result(
                        output_json={**result, "mode": direction, "citations": papers},
                        user_id=user_id,
                    )
                    result[result_key] = ids["search_id"]
                    result["seed_id"] = ids["seed_id"]
                    # save_paper deduplica por doi/semantic_paper_id/título, então
                    # um paper presente nas duas listas devolve o mesmo uuid nos
                    # dois mapas e a fusão não perde nada.
                    paper_id_map.update(ids["paper_id_map"])
                except Exception as db_error:
                    print(f"[ERRO CRITICO BD - {direction}] {db_error}", file=sys.stderr)
                    traceback.print_exc(file=sys.stderr)
                    result[result_key] = None

        result["paper_id_map"] = paper_id_map
        result.setdefault("search_id", None)
        result.setdefault("search_id_backward", None)
        result.setdefault("seed_id", None)

    def _save(self, result, doi):
        # Persiste ANTES de cachear: os ids do banco precisam entrar no payload
        # cacheado, senão uma busca repetida volta sem search_id/paper_id_map e o
        # frontend perde a capacidade de atualizar flags.
        self._persist_to_database(result)

        if cache_enabled():
            print("[SALVANDO NO CACHE]", result.get("resolved_doi"), file=sys.stderr)
            save_to_cache(doi=doi, title=result.get("title"), data=result)

        # output.json é cópia de depuração da última busca de uma seed só;
        # numa busca com várias seeds cada uma sobrescreveria a anterior.
        if self.write_debug_output:
            with open("output.json", "w", encoding="utf-8") as output_file:
                json.dump(result, output_file, ensure_ascii=False, indent=2)


def run_cli():
    """
    Entrada única do snowballing.

    Existia um run_backward separado, de quando ele era o único caminho que
    fundia as referências do Semantic Scholar com as do OpenAlex. Depois que o
    pipeline foi unificado, run_forward passou a coletar as duas listas — as
    referências pelo mesmo encadeamento, mais as citações — e o backward virou
    um subconjunto estrito, que nem a interface chamava (ela faz uma busca só,
    forward, e o toggle "Citations/References" apenas alterna entre as duas
    listas da mesma resposta).
    """
    sys.stdout.reconfigure(encoding="utf-8")

    try:
        search_input = SearchInput.from_argv(sys.argv)
        result = SnowballingPipeline().run_forward(search_input)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"error": "Erro inesperado ao processar o artigo."}, ensure_ascii=False))
        sys.exit(1)
