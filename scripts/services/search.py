import os
import re
import sys
import time
import json
import threading
import requests
from difflib import SequenceMatcher
from pathlib import Path

from services.normalize import (
    normalize_doi,
    normalize_title,
    fuzzy_match,
    token_overlap_score,
    is_missing,
    generate_paper_id,
)
from services.matching import merge_prefer_filled
from services.settings import cache_enabled

REQUEST_TIMEOUT = 12
USER_AGENT = "forward-snowballing-app/1.0"
# Teto de páginas ao paginar citações no OpenAlex (200 por página).
# Evita que um artigo com dezenas de milhares de citações trave a busca.
MAX_CITATION_PAGES = 10
# Similaridade mínima para aceitar um match do Crossref resolvido por título.
# Alinhado com fallback_semantic_by_title (0.85); fallback_openalex_by_title
# usa 0.80 porque só escolhe o paper-semente, não escreve metadado em cima
# de referências já coletadas.
CROSSREF_TITLE_MATCH_THRESHOLD = 0.85

# A chave da Semantic Scholar permite 1 requisição por segundo. Estourar isso
# devolve 429 e o pipeline degrada para OpenAlex-only, o que fazia a MESMA
# busca devolver contagens diferentes a cada execução. O intervalo é aplicado
# por processo e vale para todas as threads: run_forward dispara
# search_combined e a busca de referências em paralelo, e enrich_semantic_records
# faz uma chamada por registro incompleto — sem serializar, essas chamadas
# competem entre si e estouram o limite sozinhas.
SEMANTIC_HOST = "api.semanticscholar.org"
SEMANTIC_MIN_INTERVAL_SECONDS = 1.0
_semantic_rate_lock = threading.Lock()
_semantic_last_request_at = 0.0


def _throttle_semantic_scholar(url):
    """
    Segura a thread até que tenha se passado 1s desde a última chamada à
    Semantic Scholar. Só afeta a S2 — OpenAlex e Crossref têm limites bem mais
    folgados e serializá-los deixaria a busca ordens de grandeza mais lenta
    sem necessidade.

    O sleep acontece DENTRO do lock de propósito: se cada thread apenas
    consultasse o relógio e dormisse por fora, duas delas poderiam ler o mesmo
    "última chamada" e acordar juntas, disparando duas requisições no mesmo
    instante. Segurando o lock, as threads formam fila e cada uma só marca o
    relógio quando de fato vai emitir a sua.
    """
    if SEMANTIC_HOST not in url:
        return

    global _semantic_last_request_at

    with _semantic_rate_lock:
        espera = SEMANTIC_MIN_INTERVAL_SECONDS - (time.monotonic() - _semantic_last_request_at)
        if espera > 0:
            time.sleep(espera)
        _semantic_last_request_at = time.monotonic()


OPENALEX_CACHE = {}
CROSSREF_CACHE = {}
SEMANTIC_CACHE = {}
REQUEST_CACHE = {}
COMPLETE_CACHE_VERSION = 2


def load_project_env():
    if os.getenv("SEMANTIC_API_KEY"):
        return


    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return


    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue


            key, value = line.split("=", 1)
            key = key.strip()
            if key != "SEMANTIC_API_KEY" or os.getenv(key):
                continue


            os.environ[key] = value.strip().strip('"').strip("'")
    except Exception:
        return


def semantic_headers():
    load_project_env()
    api_key = os.getenv("SEMANTIC_API_KEY")
    return {"x-api-key": api_key} if api_key else None


def safe_get(url, headers=None):


    if url in REQUEST_CACHE:
        return REQUEST_CACHE[url]


    headers = dict(headers or {})
    headers.update({"User-Agent": USER_AGENT})


    # Sem SEMANTIC_API_KEY, 429 é o caso comum (rate limit não-autenticado da
    # Semantic Scholar), não uma falha excepcional — por isso ele leva mais
    # tentativas e espera de verdade o Retry-After, ao contrário de erro de
    # rede/5xx, que é retry curto, e 4xx que não é 429, que não é retryable.
    # Medido: a Semantic Scholar devolve 429 já na segunda requisição pesada
    # (references + citations com abstract), mesmo com chave, e só libera após
    # ~5 s. Com 3 tentativas (1 s + 2 s de espera) o pipeline desistia antes
    # disso e caía para "só OpenAlex" — origem da variação entre execuções do
    # mesmo artigo. 6 tentativas esperam até 1+2+4+8+8 = 23 s.
    max_attempts_429 = 6
    max_attempts_other = 2
    max_wait_seconds = 8

    attempt_429 = 0
    attempt_other = 0

    # Laço incondicional, com cada orçamento checado no ponto em que é
    # consumido. A condição anterior era `attempt_429 < max_429 AND
    # attempt_other < max_other`, que encerrava o laço assim que QUALQUER um
    # dos dois se esgotasse: dois erros de rede descartavam as três tentativas
    # de 429 ainda não usadas, e vice-versa. Trocar o AND por OR não resolve —
    # com 429 contínuo, attempt_other ficaria parado em 0 e o laço nunca
    # terminaria. Os orçamentos só são independentes de verdade se cada
    # categoria decidir a própria parada.
    while True:
        try:
            # Dentro do laço, não antes dele: cada nova tentativa também é uma
            # requisição e precisa respeitar o mesmo 1 req/s. O cache-hit lá em
            # cima já retornou sem passar por aqui, então requisição servida do
            # cache não consome o intervalo.
            _throttle_semantic_scholar(url)
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)


            if response.status_code == 200:
                data = response.json()


                REQUEST_CACHE[url] = data


                return data


            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                try:
                    wait_time = min(int(retry_after), max_wait_seconds) if retry_after else min(2 ** attempt_429, max_wait_seconds)
                except (TypeError, ValueError):
                    # Retry-After às vezes vem como data HTTP em vez de segundos.
                    wait_time = min(2 ** attempt_429, max_wait_seconds)
                attempt_429 += 1
                if attempt_429 >= max_attempts_429:
                    # Desiste sem dormir: a espera antes de sair só atrasava a
                    # busca inteira sem nunca ser aproveitada por uma tentativa.
                    return None
                time.sleep(wait_time)
                continue

            if response.status_code >= 500:
                # Erro do lado do servidor: pode ser transitório, vale tentar
                # de novo (mesmo orçamento de tentativas do erro de rede).
                attempt_other += 1
                if attempt_other >= max_attempts_other:
                    return None
                time.sleep(attempt_other)
                continue

            # 4xx que não é 429 (401/403/404/...) não é retryable: a resposta
            # não muda tentando de novo.
            return None

        except Exception:
            attempt_other += 1
            if attempt_other >= max_attempts_other:
                return None
            time.sleep(attempt_other)
            continue


def extract_npages(pages):
    if not pages:
        return None
    if "-" in pages:
        try:
            start, end = pages.split("-", 1)
            return int(end) - int(start) + 1
        except:
            return None
    return None


def build_pages(first_page, last_page):
    if first_page and last_page:
        return f"{first_page}-{last_page}"
    return str(first_page) if first_page else None


def strip_html_tags(text):
    if not text or not isinstance(text, str):
        return text
    return re.sub(r"<[^>]+>", " ", text).strip()

def crossref_item_to_result(item):
    title_list = item.get("title", [])
    abstract = strip_html_tags(item.get("abstract")) or "-"

    year = "-"
    issued = item.get("issued", {}).get("date-parts", [])
    if issued and issued[0]:
        year = issued[0][0]


    venue_list = item.get("container-title", [])


    authors = []
    for a in item.get("author", []):
        full_name = f"{a.get('given', '')} {a.get('family', '')}".strip()
        authors.append({"name": full_name or "-"})


    return {
        "title": title_list[0] if title_list else "-",
        "year": year,
        "venue": venue_list[0] if venue_list else "-",
        "abstract": abstract if abstract else "-",
        "doi": normalize_doi(item.get("DOI")) or "-",
        "authors": authors,
        "citations_count": item.get("is-referenced-by-count"),
        "citationCount": item.get("is-referenced-by-count"),
        "api": "crossref",
        "language": item.get("language"),
        "url": item.get("URL"),
        "pages": item.get("page"),
        "numpages": extract_npages(item.get("page")),
    }




def reconstruct_abstract_from_inverted_index(inverted_index):
    if not inverted_index or not isinstance(inverted_index, dict):
        return "-"




    position_to_word = {}
    for word, positions in inverted_index.items():
        for pos in positions:
            position_to_word[pos] = word

    if not position_to_word:
        return "-"

    ordered_positions = sorted(position_to_word.keys())
    words = [position_to_word[pos] for pos in ordered_positions]
    return " ".join(words)


def semantic_fields():
    return ",".join([
        "paperId",
        "externalIds",
        "url",
        "title",
        "abstract",
        "venue",
        "year",
        "referenceCount",
        "citationCount",
        "influentialCitationCount",
        "isOpenAccess",
        "openAccessPdf",
        "fieldsOfStudy",
        "s2FieldsOfStudy",
        "publicationTypes",
        "publicationDate",
        "journal",
        "authors",
        "citations",
        "citations.title",
        "citations.authors",
        "citations.year",
        "citations.venue",
        "citations.externalIds",
        "citations.abstract",
        "citations.citationCount",
        "citations.referenceCount",
        "references",
        "references.title",
        "references.authors",
        "references.year",
        "references.venue",
        "references.externalIds",
        "references.abstract",
        "references.citationCount",
        "references.referenceCount"
    ])


def enrich_semantic_records(data):
    if not data:
        return data

    for relation in ("citations", "references"):
        records = data.get(relation) or []
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                continue

            record["source"] = "semantic"
            has_title = not is_missing(record.get("title"))
            has_doi = bool(get_citation_doi(record))
            if has_title or has_doi or not record.get("paperId"):
                continue

            paper_url = (
                f"https://api.semanticscholar.org/graph/v1/paper/"
                f"{record['paperId']}?fields="
                "paperId,title,externalIds,year,venue,abstract,authors,"
                "citationCount,referenceCount"
            )
            detailed = safe_get(paper_url, headers=semantic_headers())
            if detailed:
                for field, value in detailed.items():
                    if is_missing(record.get(field)) and not is_missing(value):
                        record[field] = value
                record["source"] = "semantic"

            records[index] = record

    return data


def is_semantic_reference_noise(record):
    """
    Referência que a Semantic Scholar extraiu do PDF sem casar com paper algum
    e sem ano nem DOI. Medido em dois artigos: as 6 que caíam nesse caso eram
    frases do corpo do texto ("We identified six main different application
    areas...", "A6 Evolution", "RQ3 - What is the performance..."), não
    referências — e entravam na contagem do backward.
    """
    return (
        not record.get("paperId")
        and is_missing(record.get("year"))
        and not get_citation_doi(record)
    )


def tag_source(records, source):
    tagged = []
    for record in records or []:
        item = dict(record)
        item["source"] = item.get("source") or source
        tagged.append(item)
    return tagged


def fallback_via_requests(doi):
    normalized_doi = normalize_doi(doi)
    if not normalized_doi:
        return None


    encoded_doi = requests.utils.quote(normalized_doi, safe="")
    fields = semantic_fields()

    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{encoded_doi}?fields={fields}"


    data = safe_get(url, headers=semantic_headers())
    if not data:
        return None

    data = enrich_semantic_records(data)
    data["api"] = "semantic_doi_lookup"

    return data

def fallback_semantic_by_title(title):
    normalized_title = normalize_title(title)
    if not normalized_title:
        return None

    cache_key = f"title:{normalized_title}"
    if cache_key in SEMANTIC_CACHE:
        cached = SEMANTIC_CACHE[cache_key]
        return cached

    query = requests.utils.quote(title)

    search_url = (
        "https://api.semanticscholar.org/graph/v1/paper/search"
        f"?query={query}&limit=10&fields=paperId,title,externalIds,year,venue,abstract,authors,citationCount"
    )
    search_data = safe_get(search_url, headers=semantic_headers())
    if not search_data:
        return None

    results = search_data.get("data") or []
    if not results:
        return None

    best = None
    best_score = 0

    for item in results:
        candidate_title = item.get("title", "")
        fuzzy = fuzzy_match(title, candidate_title)
        overlap = token_overlap_score(title, candidate_title)

        if overlap < 0.7:
            continue

        score = (0.6 * fuzzy) + (0.4 * overlap)

        if score > best_score:
            best_score = score
            best = item

    if not best or best_score < 0.85:
        return None

    semantic_doi = None
    if isinstance(best.get("externalIds"), dict):
        semantic_doi = normalize_doi(best["externalIds"].get("DOI"))

    if semantic_doi:
        doi_data = fallback_via_requests(semantic_doi)
        if doi_data:
            doi_data["api"] = "semantic_title_to_doi"
            SEMANTIC_CACHE[cache_key] = doi_data
            return doi_data

    paper_id = best.get("paperId")
    if not paper_id:
        return None

    paper_url = (
        f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}"
        f"?fields={semantic_fields()}"
    )
    data = safe_get(paper_url, headers=semantic_headers())
    if not data:
        return None


    data = enrich_semantic_records(data)
    data["api"] = "semantic_title_paperid_fallback"

    SEMANTIC_CACHE[cache_key] = data
    return data

def fallback_openalex_by_doi(doi):
    normalized_doi = normalize_doi(doi)
    if not normalized_doi:
        return None


    cache_key = f"doi:{normalized_doi}"
    if cache_key in OPENALEX_CACHE:
        return OPENALEX_CACHE[cache_key]


    url = f"https://api.openalex.org/works/https://doi.org/{normalized_doi}"
    data = safe_get(url)
    if not data:
        OPENALEX_CACHE[cache_key] = None
        return None


    abstract = reconstruct_abstract_from_inverted_index(
        data.get("abstract_inverted_index")
    )


    primary_location = data.get("primary_location") or {}
    source = primary_location.get("source") or {}


    authorships = data.get("authorships") or []
    authors = []
    for a in authorships:
        author = a.get("author") or {}
        authors.append({"name": author.get("display_name", "-")})


    biblio = data.get("biblio") or {}
    pages = build_pages(biblio.get("first_page"), biblio.get("last_page"))

    result = {
        "title": data.get("title", "-"),
        "year": data.get("publication_year", "-"),
        "venue": source.get("display_name", "-"),
        "abstract": abstract,
        "doi": normalize_doi(data.get("doi")) or normalized_doi,
        "authors": authors,
        "citations_count": data.get("cited_by_count", 0),
        "api": "openalex",
        "openalex_id": data.get("id"),
        "open_access": data.get("open_access", {}).get("is_oa"),
        "url": primary_location.get("landing_page_url"),
        "keywords": [
            c.get("display_name")
            for c in data.get("concepts", [])
            if c.get("display_name")
        ][:10],
        "language": data.get("language"),
        "pages": pages,
        "numpages": extract_npages(pages),
    }


    OPENALEX_CACHE[cache_key] = result
    return result

def extract_opencitations_doi(value):
    """
    Extrai o DOI de um campo "cited"/"citing" da OpenCitations.

    A API v1 devolve o DOI puro ("10.5753/wei.2017.3556"); a v2 devolve todos
    os identificadores separados por espaço ("omid:br/0616 doi:10.5753/wei...
    openalex:W300..."). Aceitar os dois formatos protege contra mudança na
    ordem dos tokens da v2 e permite voltar para a v1 se preciso.
    """
    if not value:
        return None

    text = str(value).strip()

    for token in text.split():
        if token.lower().startswith("doi:"):
            return normalize_doi(token[4:])

    # Formato da v1: o valor inteiro é o DOI. Reconhecido pelo prefixo "10."
    # (todo DOI começa assim), e não pela ausência de ":" — DOIs no padrão
    # SICI, comuns em periódicos antigos, contêm dois-pontos no sufixo
    # ("10.1002/(SICI)1097-4571(199806)49:8<693::AID-ASI4>3.0.CO;2-O") e
    # seriam descartados em silêncio.
    if text.startswith("10.") and not any(ch.isspace() for ch in text):
        return normalize_doi(text)

    return None


def fallback_opencitations_by_doi(doi):
    """
    Busca na OpenCitations os DOIs referenciados por `doi`.

    A OpenCitations devolve só pares citing/cited, sem título, ano, autores etc.
    Por isso o retorno sai no formato de "referência incompleta" (doi presente,
    título "-") que enrich_incomplete_citations sabe completar via Crossref —
    sem isso, get_record_key/merge_records_across_sources não teriam como casar
    esses registros com os de outras fontes.

    Quem decide QUANDO consultar é o pipeline (run_forward), não esta função:
    só lá as referências do OpenAlex já estão disponíveis, e sem elas não há
    como saber o que a OpenCitations acrescenta de fato.
    """
    normalized_doi = normalize_doi(doi)
    if not normalized_doi:
        return []

    url = f"https://api.opencitations.net/index/v2/references/doi:{normalized_doi}"
    data = safe_get(url)

    # safe_get devolve None em erro de rede/limite/etc. Sem essa guarda o
    # "for item in data" quebra com TypeError e derruba o pipeline inteiro
    # por causa de uma fonte que é só complementar.
    if not data or not isinstance(data, list):
        return []

    references = []
    seen_dois = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        cited_doi = extract_opencitations_doi(item.get("cited"))
        if not cited_doi or cited_doi in seen_dois:
            continue
        seen_dois.add(cited_doi)
        references.append({
            "doi": cited_doi,
            "title": "-",
            "api": "opencitations",
            "source": "opencitations",
        })

    return references


def attach_openalex_citations(paper):
    merged = dict(paper)

    if merged.get("openalex_id"):
        citations = get_openalex_citations(merged["openalex_id"])
        merged["citations"] = citations
        merged["citationCount"] = len(merged["citations"])
    else:
        merged.setdefault("citations", [])
        merged.setdefault(
            "citationCount",
            merged.get("citationCount", merged.get("citations_count", 0)),
        )

    return merged


def get_openalex_citations(openalex_id):
    if not openalex_id:
        return []


    # O OpenAlex devolve no máximo 200 itens por página. Sem paginar, artigos
    # com mais citações eram truncados silenciosamente em 200.
    results = []
    cursor = "*"

    for _ in range(MAX_CITATION_PAGES):
        url = (
            f"https://api.openalex.org/works?filter=cites:{openalex_id}"
            f"&per-page=200&cursor={cursor}"
        )
        data = safe_get(url)

        if not data:
            break

        page_results = data.get("results", [])
        results.extend(page_results)

        cursor = (data.get("meta") or {}).get("next_cursor")
        if not cursor or not page_results:
            break

    if not results:
        return []

    data = {"results": results}

    citations = []


    for item in data.get("results", []):
        biblio = item.get("biblio") or {}
        pages = build_pages(biblio.get("first_page"), biblio.get("last_page"))
        abstract = reconstruct_abstract_from_inverted_index(item.get("abstract_inverted_index"))
        citations.append({
            "title": item.get("title"),
            "year": item.get("publication_year"),
            "abstract": abstract,
            "doi": normalize_doi(item.get("doi")),
            "url": item.get("primary_location", {}).get("landing_page_url"),
            "open_access": item.get("open_access", {}).get("is_oa"),
            "citations_count": item.get("cited_by_count", 0),
            "citationCount": item.get("cited_by_count", 0),
            "keywords": [
                c.get("display_name") for c in item.get("concepts", [])
            ],
            "language": item.get("language"),
            "pages": pages,
            "numpages": extract_npages(pages),
            "authors": [
                {"name": a.get("author", {}).get("display_name", "-")}
                for a in item.get("authorships", [])
            ],
            "source": "openalex"
        })




    return citations




def fallback_openalex_by_title(title):
    normalized_title = normalize_title(title)
    if not normalized_title:
        return None


    cache_key = f"title:{normalized_title}"
    if cache_key in OPENALEX_CACHE:
        return OPENALEX_CACHE[cache_key]


    query = requests.utils.quote(title)
    url = f"https://api.openalex.org/works?search={query}&per-page=10"
    data = safe_get(url)
    if not data:
        OPENALEX_CACHE[cache_key] = None
        return None


    results = data.get("results") or []
    if not results:
        OPENALEX_CACHE[cache_key] = None
        return None


    best = None
    best_score = 0


    for item in results:
        candidate_title = item.get("title", "")
        score = fuzzy_match(title, candidate_title)
        if score > best_score:
            best_score = score
            best = item


    if not best or best_score < 0.80:
        OPENALEX_CACHE[cache_key] = None
        return None


    abstract = reconstruct_abstract_from_inverted_index(
        best.get("abstract_inverted_index")
    )


    primary_location = best.get("primary_location") or {}
    source = primary_location.get("source") or {}


    authorships = best.get("authorships") or []
    authors = []
    for a in authorships:
        author = a.get("author") or {}
        authors.append({"name": author.get("display_name", "-")})


    result = {
        "title": best.get("title", "-"),
        "year": best.get("publication_year", "-"),
        "venue": source.get("display_name", "-"),
        "abstract": abstract,
        "doi": normalize_doi(best.get("doi")) or "-",
        "authors": authors,
        "citations_count": best.get("cited_by_count", 0),
        "api": "openalex",
        "openalex_id": best.get("id"),
        "open_access": best.get("open_access", {}).get("is_oa"),
        "url": primary_location.get("landing_page_url"),
        "keywords": [
            c.get("display_name")
            for c in best.get("concepts", [])
            if c.get("display_name")
        ][:10],
        "language": best.get("language"),


    }


    OPENALEX_CACHE[cache_key] = result
    return result




def fallback_crossref(doi=None, title=None):
    if doi:
        normalized_doi = normalize_doi(doi)
        if not normalized_doi:
            return None


        cache_key = f"doi:{normalized_doi}"
        if cache_key in CROSSREF_CACHE:
            return CROSSREF_CACHE[cache_key]


        encoded_doi = requests.utils.quote(normalized_doi, safe="")
        url = f"https://api.crossref.org/works/{encoded_doi}"
        data = safe_get(url)
        if not data:
            CROSSREF_CACHE[cache_key] = None
            return None


        item = data.get("message", {})
    elif title:
        normalized_title = normalize_title(title)
        if not normalized_title:
            return None


        cache_key = f"title:{normalized_title}"
        if cache_key in CROSSREF_CACHE:
            return CROSSREF_CACHE[cache_key]


        query = requests.utils.quote(title)
        url = f"https://api.crossref.org/works?query.title={query}&rows=10"
        data = safe_get(url)
        if not data:
            CROSSREF_CACHE[cache_key] = None
            return None


        items = data.get("message", {}).get("items", [])
        if not items:
            CROSSREF_CACHE[cache_key] = None
            return None


        item = None
        best_score = 0


        for candidate in items:
            titles = candidate.get("title", [])
            candidate_title = titles[0] if titles else ""
            score = fuzzy_match(title, candidate_title)
            if score > best_score:
                best_score = score
                item = candidate


        # Sem limiar, o "melhor" candidato do Crossref era aceito mesmo com
        # similaridade baixíssima — a busca por título devolve 10 itens e
        # sempre havia um com score > 0. Isso colava DOI/ano/venue de um
        # artigo alheio na referência (ex.: "ε-PAL: An Active Learning
        # Approach..." de 2013 recebia o DOI de "A Neurodynamic Approach to
        # Multi-Objective Fuzzy Optimization Problem" de 2025, score 0.727).
        # Metadado errado numa revisão sistemática é pior que metadado
        # ausente, e o ano contaminado ainda alimenta o filtro determinístico
        # de ano da triagem por LLM. Mesmo limiar do fallback do Semantic
        # Scholar, que também resolve identidade por título.
        if not item or best_score < CROSSREF_TITLE_MATCH_THRESHOLD:
            CROSSREF_CACHE[cache_key] = None
            return None
    else:
        return None


    result = crossref_item_to_result(item)



    if doi:
        CROSSREF_CACHE[f"doi:{normalize_doi(doi)}"] = result
    elif title:
        CROSSREF_CACHE[f"title:{normalize_title(title)}"] = result


    return result

def fallback_crossref_batch_by_doi(dois, batch_size=20):
    normalized_dois = []

    for doi in dois:
        normalized_doi = normalize_doi(doi)
        if normalized_doi and normalized_doi not in normalized_dois:
            normalized_dois.append(normalized_doi)


    results_by_doi = {}


    missing_dois = [
        doi for doi in normalized_dois
        if f"doi:{doi}" not in CROSSREF_CACHE
    ]


    for doi in normalized_dois:
        cache_key = f"doi:{doi}"
        if cache_key in CROSSREF_CACHE and CROSSREF_CACHE[cache_key]:
            results_by_doi[doi] = CROSSREF_CACHE[cache_key]


    for i in range(0, len(missing_dois), batch_size):
        batch = missing_dois[i:i + batch_size]


        filter_value = ",".join([f"doi:{doi}" for doi in batch])


        params = {
            "filter": filter_value,
            "rows": len(batch),
        }


        request = requests.Request(
            "GET",
            "https://api.crossref.org/works",
            params=params,
        ).prepare()


        data = safe_get(request.url)


        if not data:
            for doi in batch:
                CROSSREF_CACHE[f"doi:{doi}"] = None
            continue


        items = data.get("message", {}).get("items", [])


        found = set()


        for item in items:
            result = crossref_item_to_result(item)
            result_doi = normalize_doi(result.get("doi"))


            if result_doi:
                CROSSREF_CACHE[f"doi:{result_doi}"] = result
                results_by_doi[result_doi] = result
                found.add(result_doi)


        for doi in batch:
            if doi not in found:
                CROSSREF_CACHE[f"doi:{doi}"] = None


    return results_by_doi






def is_crossref_reference_fragment(ref):
    """
    Pedaço de citação que a editora depositou como entrada própria: só a lista
    de autores, terminada em vírgula ("Ashouri, A.H., Killian, W., ...,
    Silvano, C.,"). Medido: 6 dos 139 itens do Crossref de um artigo da JSS;
    sem eles a contagem fecha com a lista do PDF. "Sem ano" não serve de
    critério: há referências legítimas sem ano e anos como "1988a".
    """
    if ref.get("DOI") or ref.get("year"):
        return False
    if ref.get("article-title") or ref.get("volume-title") or ref.get("series-title"):
        return False
    return (ref.get("unstructured") or "").rstrip().endswith(",")


def crossref_reference_to_record(ref):
    # article-title é o trabalho citado; volume-title/series-title é o livro
    # ou anais onde ele saiu (ou o próprio livro, quando não há article-title).
    container = ref.get("journal-title") or ref.get("volume-title") or ref.get("series-title")
    title = ref.get("article-title") or ref.get("volume-title") or ref.get("series-title")
    if title == container and not ref.get("article-title"):
        container = ref.get("journal-title")
        # Capítulo de livro sem título próprio: a editora deposita o título
        # do LIVRO em volume-title e a página inicial do capítulo. Usá-lo como
        # título dava o mesmo título a todos os capítulos do livro (4 num
        # artigo), que o collapse por chave fundia num só — e o enriquecimento
        # por título colava neles o DOI de outra obra homônima.
        if ref.get("first-page"):
            title = None
            container = ref.get("volume-title") or ref.get("series-title")

    return {
        # Sem título estruturado fica "-": o texto livre da citação vai em
        # "unstructured", onde merge_records_across_sources procura o título
        # vindo das outras fontes. Usar o texto livre como título aqui faria
        # enrich_incomplete_citations buscá-lo no Crossref por título.
        "title": title or "-",
        "unstructured": ref.get("unstructured"),
        "year": ref.get("year") or "-",
        "venue": container or "-",
        "doi": normalize_doi(ref.get("DOI")) or "-",
        "authors": [{"name": ref["author"]}] if ref.get("author") else [],
        "source": "crossref",
    }


def fetch_crossref_references(doi):
    """
    Lista de referências que a editora depositou no Crossref para `doi`.

    É a fonte mais próxima da lista impressa no artigo: nos artigos medidos
    bateu exatamente com a contagem do PDF (77, 28, 83), inclusive quando a
    Semantic Scholar bloqueia a lista e o OpenAlex só conhece as referências
    com DOI (capítulos de livro, resumos de congresso e "in press" ficavam de
    fora). Usa a mesma URL de fallback_crossref, então a requisição é
    reaproveitada pelo cache de safe_get.
    """
    normalized_doi = normalize_doi(doi)
    if not normalized_doi:
        return []

    encoded_doi = requests.utils.quote(normalized_doi, safe="")
    data = safe_get(f"https://api.crossref.org/works/{encoded_doi}")
    if not data:
        return []

    refs = (data.get("message") or {}).get("reference") or []
    return [
        crossref_reference_to_record(ref)
        for ref in refs
        if isinstance(ref, dict) and not is_crossref_reference_fragment(ref)
    ]


def semantic_references_blocked_warning(paper_data):
    """
    A Semantic Scholar às vezes sabe QUANTAS referências um paper tem
    (referenceCount, metadado público) mas não libera a LISTA em si
    (references vem null) — bloqueio da editora, não erro de request.
    Sem isso sinalizado, o backward parecia ter perdido dado silenciosamente
    quando na real não havia nada a mais pra recuperar da S2 nesse paper.
    """
    if not paper_data:
        return None

    has_reference_list = bool(paper_data.get("references"))
    reported_count = paper_data.get("referenceCount")

    if not has_reference_list and reported_count:
        return (
            f"Semantic Scholar reporta {reported_count} referências para este "
            "paper, mas não disponibiliza a lista (bloqueio da editora). "
            "As referências exibidas vêm das demais fontes."
        )

    return None


def merge_semantic_with_openalex(semantic_data, openalex_data):
    semantic_data = semantic_data or {}
    openalex_data = openalex_data or {}

    merged = semantic_data.copy()
    merged = merge_prefer_filled(merged, openalex_data)

    semantic_citations = tag_source(semantic_data.get("citations"), "semantic")
    openalex_citations = tag_source(openalex_data.get("citations"), "openalex")
    merged["citations"] = merge_records_across_sources(
        semantic_citations,
        openalex_citations,
    )

    semantic_references = tag_source(semantic_data.get("references"), "semantic")
    openalex_references = tag_source(openalex_data.get("references"), "openalex")
    merged["references"] = merge_records_across_sources(
        semantic_references,
        openalex_references,
    )

    merged["api"] = "semantic+openalex"
    merged["partial_result"] = False
    merged["semantic_citation_count"] = semantic_data.get("citationCount")
    merged["semantic_reference_count"] = semantic_data.get("referenceCount")
    merged["openalex_citation_count"] = openalex_data.get("citations_count")
    return merged


def merge_records_across_sources(
    primary_records,
    secondary_records,
    match_titles=False,
    keep_unmatched=True,
):
    """
    Remove only records that overlap between two different sources.

    match_titles=True também casa por título quando a chave (DOI, ou título se
    não houver DOI) não bate. Medido no backward: o mesmo trabalho chega com
    DOI de um lado e sem DOI do outro (a chave vira doi:... vs title:...), ou
    com DOIs diferentes (preprint arXiv vs versão publicada, edição de livro),
    e era contado duas vezes — 18 de 131 referências do OpenAlex num artigo.
    Dentro da lista de referências de UM paper, dois títulos praticamente
    iguais são o mesmo trabalho citado; por isso a opção é só para referências.
    Também casa o título da secundária dentro do texto livre da citação
    ("unstructured") de uma primária sem título — o caso do Crossref.

    keep_unmatched=False usa a secundária só para completar campos da
    primária, sem acrescentar registros: é o modo em que a lista primária
    (a depositada pela editora no Crossref) define o conjunto.
    """
    primary_records = [dict(record) for record in (primary_records or [])]
    secondary_records = [dict(record) for record in (secondary_records or [])]

    primary_by_key = {}
    primary_by_title = {}
    primary_by_citation_text = {}
    for record in primary_records:
        key = get_record_key(record)
        if key and key not in primary_by_key:
            primary_by_key[key] = record
        title = normalize_title(record.get("title"))
        if title and title not in primary_by_title:
            primary_by_title[title] = record
        citation_text = normalize_title(record.get("unstructured"))
        if not title and citation_text:
            primary_by_citation_text.setdefault(citation_text, record)

    merged = primary_records[:]
    for record in secondary_records:
        key = get_record_key(record)
        match = primary_by_key.get(key) if key else None
        if match is None and match_titles:
            match = find_record_by_title(record.get("title"), primary_by_title)
        if match is None and match_titles:
            match = find_record_in_citation_text(record.get("title"), primary_by_citation_text)
        if match is not None:
            match.update({
                field: value
                for field, value in record.items()
                if field_missing(match.get(field))
                and not field_missing(value)
            })
            continue
        if keep_unmatched:
            merged.append(record)

    return merged


def find_record_in_citation_text(title, records_by_citation_text):
    """
    Só aceita quando o título aparece no texto de UMA citação. O título de um
    livro aparece em todos os capítulos citados dele ("Membranes, Metabolism
    and Dry Organisms" em 4 citações de um artigo): casar com o primeiro
    colava o livro no capítulo, e o collapse por chave depois fundia os 4
    capítulos num só.
    """
    normalized = normalize_title(title)
    if len(normalized) < REFERENCE_TITLE_MIN_LENGTH:
        return None
    matches = [
        record
        for citation_text, record in records_by_citation_text.items()
        if normalized in citation_text
    ]
    return matches[0] if len(matches) == 1 else None


REFERENCE_TITLE_MATCH_THRESHOLD = 0.90
# Abaixo disso a similaridade de sequência não é confiável: "Action research"
# casaria com qualquer título curto parecido.
REFERENCE_TITLE_MIN_LENGTH = 20


def find_record_by_title(title, records_by_title):
    normalized = normalize_title(title)
    if not normalized:
        return None

    exact = records_by_title.get(normalized)
    if exact is not None:
        return exact

    if len(normalized) < REFERENCE_TITLE_MIN_LENGTH:
        return None

    best, best_score = None, 0.0
    for candidate_title, candidate in records_by_title.items():
        if len(candidate_title) < REFERENCE_TITLE_MIN_LENGTH:
            continue
        # Um título prefixo do outro é a mesma obra com sufixo de edição ou
        # subtítulo ("Modern Information Retrieval, 1st ed"), que derruba a
        # similaridade de sequência abaixo do limiar.
        if normalized.startswith(candidate_title) or candidate_title.startswith(normalized):
            return candidate
        score = SequenceMatcher(None, normalized, candidate_title).ratio()
        if score > best_score:
            best, best_score = candidate, score

    return best if best_score >= REFERENCE_TITLE_MATCH_THRESHOLD else None


def collapse_duplicates_by_key(records):
    """
    Funde, dentro de uma mesma lista, registros que compartilham a chave de
    identidade (DOI, ou título normalizado quando não há DOI).

    Existe por causa da ordem do pipeline: merge_records_across_sources roda
    ANTES de enrich_incomplete_citations, então um registro cujo DOI só
    aparece no enriquecimento via Crossref nunca chega a ser comparado por
    DOI com o seu par da outra fonte — os dois sobrevivem como se fossem
    referências distintas e a contagem final sai inflada. Rodar esta passada
    depois do enriquecimento fecha essa janela sem refazer requisição alguma.

    Preserva a ordem de primeira ocorrência e só preenche campo vazio com
    valor da duplicata, nunca sobrescreve valor já presente — mesma política
    de merge_records_across_sources.
    """
    collapsed = []
    by_key = {}

    for record in records or []:
        item = dict(record)
        key = get_record_key(item)

        if not key or key not in by_key:
            if key:
                by_key[key] = item
            collapsed.append(item)
            continue

        existing = by_key[key]
        existing.update({
            field: value
            for field, value in item.items()
            if field_missing(existing.get(field)) and not field_missing(value)
        })

        sources = {
            source
            for source in (existing.get("source"), item.get("source"))
            if source
        }
        if sources:
            existing["sources"] = sorted(sources)

    return collapsed


def get_record_key(record):
    doi = get_citation_doi(record)
    if doi:
        return f"doi:{doi}"

    title = normalize_title(record.get("title"))
    return f"title:{title}" if title else None


def get_citation_doi(citation):
    doi = normalize_doi(citation.get("doi"))
    if doi:
        return doi


    external_ids = citation.get("externalIds")
    if isinstance(external_ids, dict):
        return normalize_doi(external_ids.get("DOI"))


    return None




def field_missing(value):
    return value in [None, "", "-", []]


def get_citation_count_value(citation):
    if citation.get("citations_count") not in [None, "", "-"]:
        return citation.get("citations_count")


    if citation.get("citationCount") not in [None, "", "-"]:
        return citation.get("citationCount")


    if citation.get("cited_by_count") not in [None, "", "-"]:
        return citation.get("cited_by_count")


    return None




def deduplicate_citations(citations):
    unique = {}


    for citation in citations:
        c = dict(citation)


        doi = get_citation_doi(c)
        title = normalize_title(c.get("title"))


        if doi:
            key = f"doi:{doi}"
            c["doi"] = doi
        elif title:
            key = f"title:{title}"
        else:
            continue


        count = get_citation_count_value(c)
        if count is not None:
            c["citations_count"] = count
            c["citationCount"] = count


        if key not in unique:
            unique[key] = c
            continue


        existing = unique[key]


        for field, value in c.items():
            if field_missing(existing.get(field)) and not field_missing(value):
                existing[field] = value


        existing_count = get_citation_count_value(existing)
        incoming_count = get_citation_count_value(c)


        if existing_count in [None, "", "-", 0, "0"] and incoming_count not in [None, "", "-"]:
            existing["citations_count"] = incoming_count
            existing["citationCount"] = incoming_count
        elif existing_count not in [None, "", "-"]:
            existing["citations_count"] = existing_count
            existing["citationCount"] = existing_count


        sources = set()


        if existing.get("source"):
            sources.add(existing.get("source"))
        if c.get("source"):
            sources.add(c.get("source"))


        if sources:
            existing["sources"] = sorted(sources)


        if existing.get("doi"):
            existing["doi"] = normalize_doi(existing.get("doi"))


    return list(unique.values())

def cache_path_for_doi(doi):
    normalized = normalize_doi(doi)
    if not normalized:
        return None

    safe_doi = normalized.replace("/", "_")
    cache_dir = Path(__file__).resolve().parents[1] / "cache"
    cache_dir.mkdir(exist_ok=True)

    return cache_dir / f"cache_complete_{safe_doi}.json"

class ArticleNotFoundError(ValueError):
    """Nenhuma fonte encontrou o artigo pedido.

    Antes search_combined imprimia o erro e chamava sys.exit(1) — o que, numa
    busca com várias seeds no mesmo processo, derrubava todas por causa de uma.
    É ValueError para que run_cli continue respondendo {"error": ...} com
    exit 1, exatamente como antes.
    """


def load_complete_cache(doi):
    if not cache_enabled():
        return None

    path = cache_path_for_doi(doi)
    if not path.exists():
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        if cached.get("_cache_version") != COMPLETE_CACHE_VERSION:
            return None
        return cached
    except Exception:
        return None


def save_complete_cache(doi, data):
    if not cache_enabled():
        return

    path = cache_path_for_doi(doi)
    data = {**data, "_cache_version": COMPLETE_CACHE_VERSION}

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)



def search_combined(doi=None, title=None):
    cleaned_doi = normalize_doi(doi) if doi else None
    cleaned_title = normalize_title(title) if title else ""




    openalex_data = None
    paper_data = None
    crossref_data = None


    if cleaned_doi:
        cached = load_complete_cache(cleaned_doi)
        if cached:
            cached["from_cache"] = True
            return cached

        # Semantic Scholar é a fonte prioritária; OpenAlex complementa a resposta.
        paper_data = fallback_via_requests(cleaned_doi)
        openalex_data = fallback_openalex_by_doi(cleaned_doi)

        if paper_data:
            semantic_doi = None
            if isinstance(paper_data.get("externalIds"), dict):
                semantic_doi = normalize_doi(paper_data["externalIds"].get("DOI"))


            paper_data["doi"] = semantic_doi or cleaned_doi


            if openalex_data and openalex_data.get("openalex_id"):
                openalex_data["citations"] = get_openalex_citations(
                    openalex_data["openalex_id"]
                )

            print(
                f"[SOURCE COUNTS] Semantic: citations={len(paper_data.get('citations', []) or [])}, "
                f"references={len(paper_data.get('references', []) or [])}; "
                f"OpenAlex: citations={len(openalex_data.get('citations', []) or []) if openalex_data else 0}, "
                f"references={len(openalex_data.get('references', []) or []) if openalex_data else 0}",
                file=sys.stderr,
            )

            merged = merge_semantic_with_openalex(paper_data, openalex_data)


            merged["doi"] = semantic_doi or cleaned_doi
            semantic_block_warning = semantic_references_blocked_warning(paper_data)
            if semantic_block_warning:
                merged["warning"] = semantic_block_warning
                merged["partial_result"] = True

            save_complete_cache(cleaned_doi, merged)

            return merged


        if openalex_data:
            result = attach_openalex_citations(openalex_data)
            result["warning"] = "Semantic Scholar indisponível; resultado obtido pelo OpenAlex."
            result["partial_result"] = True
            save_complete_cache(cleaned_doi, result)
            return result

        crossref_data = fallback_crossref(doi=cleaned_doi)
        if crossref_data:
            return crossref_data


    if cleaned_title and not openalex_data and not paper_data and not crossref_data:
        # Semantic Scholar é tentado primeiro. Se resolver um DOI, o ramo de DOI
        # consulta as duas fontes e faz a fusão.
        paper_data = fallback_semantic_by_title(title)


        if paper_data:
            semantic_doi = None
            if isinstance(paper_data.get("externalIds"), dict):
                semantic_doi = normalize_doi(paper_data["externalIds"].get("DOI"))


            resolved_doi = semantic_doi or normalize_doi(paper_data.get("doi"))


            if resolved_doi:
                return search_combined(doi=resolved_doi, title=None)

        openalex_data = fallback_openalex_by_title(title)

        openalex_doi = normalize_doi(openalex_data.get("doi")) if openalex_data else None
        if openalex_doi:
            return search_combined(doi=openalex_doi, title=None)


        # Nenhuma das duas resolveu DOI. O OpenAlex ainda é preferido por trazer
        # o openalex_id, que permite recuperar citações adicionais.
        if openalex_data:
            return attach_openalex_citations(openalex_data)


        if paper_data:
            paper_data["citationCount"] = len(paper_data.get("citations", []))
            return paper_data


        crossref_data = fallback_crossref(title=title)


        if crossref_data and crossref_data.get("doi"):
            return search_combined(doi=crossref_data.get("doi"), title=None)


        if not paper_data:
            resolved_doi = None


            if openalex_data:
                resolved_doi = normalize_doi(openalex_data.get("doi"))


            if not resolved_doi and crossref_data:
                resolved_doi = normalize_doi(crossref_data.get("doi"))


            if resolved_doi:
                paper_data = fallback_via_requests(resolved_doi)
                if paper_data:
                    paper_data["api"] = "semantic_resolved_from_title_doi"


    if openalex_data and paper_data:
        merged = openalex_data.copy()


        if is_missing(merged.get("abstract")) and not is_missing(paper_data.get("abstract")):
            merged["abstract"] = paper_data.get("abstract")


        if is_missing(merged.get("venue")) and not is_missing(paper_data.get("venue")):
            merged["venue"] = paper_data.get("venue")


        if is_missing(merged.get("year")) and not is_missing(paper_data.get("year")):
            merged["year"] = paper_data.get("year")


        if is_missing(merged.get("title")) and not is_missing(paper_data.get("title")):
            merged["title"] = paper_data.get("title")

        semantic_doi = None
        if isinstance(paper_data.get("externalIds"), dict):
            semantic_doi = normalize_doi(paper_data["externalIds"].get("DOI"))
        if not semantic_doi:
            semantic_doi = normalize_doi(paper_data.get("doi"))

        if is_missing(merged.get("doi")) and semantic_doi:
            merged["doi"] = semantic_doi

        if not merged.get("authors") and paper_data.get("authors"):
            merged["authors"] = [
                {"name": a.get("name", "-")} for a in paper_data.get("authors", [])
            ]

        merged["citationCount"] = paper_data.get("citationCount", merged.get("citationCount", 0))
        # --- SEMANTIC ---
        semantic_citations = paper_data.get("citations", []) if paper_data else []


        # --- OPENALEX ---
        openalex_citations = []
        if openalex_data and openalex_data.get("openalex_id"):
            openalex_citations = get_openalex_citations(openalex_data["openalex_id"])




        all_citations = deduplicate_citations(
            semantic_citations + openalex_citations
        )




        merged["citations"] = all_citations
        # ver comentário equivalente acima: merge_prefer_filled não propaga
        # "references" sozinho.
        merged["references"] = merge_records_across_sources(
            paper_data.get("references", []) if paper_data else [],
            openalex_data.get("references", []) if openalex_data else [],
        )

        merged["api"] = f'{openalex_data.get("api", "openalex")}+{paper_data.get("api", "semantic")}'

        if paper_data:
            semantic_block_warning = semantic_references_blocked_warning(paper_data)
            if semantic_block_warning:
                merged["warning"] = semantic_block_warning
                merged["partial_result"] = True




        if crossref_data:
            merged = merge_prefer_filled(merged, crossref_data)
            merged["api"] += "+crossref"




        return merged




    if openalex_data:
        if cleaned_doi:
            cached = load_complete_cache(cleaned_doi)
            if cached:
                cached["from_cache"] = True
                return cached

        merged = dict(openalex_data)
        openalex_citations = []
        if openalex_data.get("openalex_id"):
            openalex_citations = get_openalex_citations(openalex_data["openalex_id"])

        merged["citations"] = openalex_citations
        merged["citationCount"] = len(openalex_citations)
        merged["partial_result"] = True
        merged["warning"] = "Resultado parcial: apenas OpenAlex."
        return merged



    if paper_data:
        merged = dict(paper_data)




        semantic_doi = None
        if isinstance(paper_data.get("externalIds"), dict):
            semantic_doi = normalize_doi(paper_data["externalIds"].get("DOI"))
        if not semantic_doi:
            semantic_doi = normalize_doi(paper_data.get("doi"))
        if semantic_doi:
            merged["doi"] = semantic_doi




        if crossref_data:
            merged = merge_prefer_filled(merged, crossref_data)
            merged["api"] = f'{paper_data.get("api", "semantic")}+crossref'
        else:
            merged["api"] = paper_data.get("api", "semantic")




        return merged




    if crossref_data:
        return crossref_data




    raise ArticleNotFoundError(f"Artigo não encontrado. DOI='{doi}' | title='{title}'")








def needs_enrichment(citation):
    return (
        is_missing(citation.get("doi")) or
        is_missing(citation.get("year")) or
        is_missing(citation.get("venue")) or
        not citation.get("authors") or
        is_missing(citation.get("citationCount")) or
        is_missing(citation.get("citations_count"))
    )








def enrich_citation(citation):
    enriched = dict(citation)
    doi = get_citation_doi(enriched)
    title = enriched.get("title")


    if doi:
        enriched["doi"] = doi


        if needs_enrichment(enriched):
            cr = fallback_crossref(doi=doi)
            if cr:
                enriched = merge_prefer_filled(enriched, cr)


    elif title and normalize_title(title):
        if needs_enrichment(enriched):
            cr = fallback_crossref(title=title)
            if cr:
                enriched = merge_prefer_filled(enriched, cr)


    enriched["paperId"] = generate_paper_id(enriched.get("title", "-"))
    enriched["doi"] = normalize_doi(enriched.get("doi")) or "-"


    if (not enriched.get("url") or enriched.get("url") in ["", "-"]) and enriched.get("doi") not in ["", "-"]:
        enriched["url"] = f"https://doi.org/{enriched['doi']}"


    return enriched


def enrich_incomplete_citations(citations):
    enriched_citations = [dict(citation) for citation in citations]


    dois_to_fetch = []


    for citation in enriched_citations:
        if needs_enrichment(citation):
            doi = get_citation_doi(citation)
            if doi:
                citation["doi"] = doi
                dois_to_fetch.append(doi)


    crossref_by_doi = fallback_crossref_batch_by_doi(dois_to_fetch)


    for index, citation in enumerate(enriched_citations):
        if needs_enrichment(citation):
            doi = get_citation_doi(citation)
            title = citation.get("title")


            if doi:
                cr = crossref_by_doi.get(doi)


                if not cr:
                    cr = fallback_crossref(doi=doi)


                if cr:
                    citation = merge_prefer_filled(citation, cr)


            elif title and normalize_title(title):
                cr = fallback_crossref(title=title)
                if cr:
                    citation = merge_prefer_filled(citation, cr)


        citation["paperId"] = generate_paper_id(citation.get("title", "-"))
        citation["doi"] = normalize_doi(citation.get("doi")) or "-"


        if (
            not citation.get("url")
            and citation.get("doi") not in [None, "-", ""]
        ):
            citation["url"] = f"https://doi.org/{citation['doi']}"


        enriched_citations[index] = citation


    return enriched_citations








def clear_caches():
    OPENALEX_CACHE.clear()
    CROSSREF_CACHE.clear()
    SEMANTIC_CACHE.clear()
    REQUEST_CACHE.clear()
