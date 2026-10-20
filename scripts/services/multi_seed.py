"""
Snowballing a partir de várias seeds numa única busca.

Cada seed passa pelo mesmo SnowballingPipeline.run_forward da busca de uma seed
só — citations e references, as mesmas fontes, a mesma deduplicação interna.
Este módulo só acrescenta o que existe por haver mais de uma seed:

- validação da lista de entrada (tipo DOI/título escolhido pelo usuário);
- seeds repetidas, antes da busca (mesmo DOI ou mesmo título) e depois dela
  (um título que resolve para o DOI de outra seed);
- falha isolada: uma seed que não é encontrada ou dá erro não derruba as
  outras — ela volta com status, e a busca só falha se nenhuma der certo;
- a união deduplicada das listas de todas as seeds, com a origem de cada
  estudo (found_via_seeds).

As seeds rodam em sequência, no mesmo processo, de propósito: o throttle do
Semantic Scholar (services/search.py) é um lock por processo, e os caches em
memória das fontes são reaproveitados entre seeds que se citam.

Formato de saída (só o necessário para a interface): a união vem completa em
`citations` / `references`; cada seed carrega apenas as chaves dos seus
estudos (`citation_keys` / `reference_keys`). Repetir os registros por seed
dobraria o payload — com 20 seeds ele passaria do limite do PythonRunner.
"""
import os
import re
import sys
import traceback

from services.normalize import normalize_doi, normalize_title
from services.matching import merge_prefer_filled
from services.search import ArticleNotFoundError, get_record_key
from services.snowballing_pipeline import SearchInput, SnowballingPipeline

MULTI_SEED_FORMAT_VERSION = 1
DEFAULT_MAX_SEEDS = 20
SEED_TYPES = ("doi", "title")
DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)

STATUS_OK = "ok"
STATUS_PARTIAL = "partial"
STATUS_NOT_FOUND = "not_found"
STATUS_ERROR = "error"
STATUS_DUPLICATE = "duplicate"
SUCCESS_STATUSES = {STATUS_OK, STATUS_PARTIAL}

# Campos do resultado de uma seed que a interface usa no card da aba.
SEED_FIELDS = (
    "input_doi", "input_title", "resolved_doi", "data_source", "title", "authors",
    "year", "venue", "abstract", "open_access", "url", "keywords", "language",
    "pages", "numpages", "warning", "partial_result", "citationCount",
)


def max_seeds():
    try:
        value = int(os.getenv("SNOWMAP_MAX_SEEDS", DEFAULT_MAX_SEEDS))
    except ValueError:
        return DEFAULT_MAX_SEEDS
    return value if value > 0 else DEFAULT_MAX_SEEDS


def parse_seeds(raw_seeds):
    """
    Valida a lista [{type, value}] vinda da interface e devolve seeds limpas.

    O tipo é o que o usuário escolheu no seletor — não há adivinhação. Um DOI
    sem formato de DOI é erro de entrada, não "tentar como título".
    Levanta ValueError com mensagem para o usuário.
    """
    if not isinstance(raw_seeds, list) or not raw_seeds:
        raise ValueError("Informe ao menos uma seed.")

    limit = max_seeds()
    if len(raw_seeds) > limit:
        raise ValueError(f"Máximo de {limit} seeds por busca.")

    seeds = []
    for position, raw in enumerate(raw_seeds, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"Seed {position}: formato inválido.")

        seed_type = str(raw.get("type") or "").strip().lower()
        value = str(raw.get("value") or "").strip()

        if seed_type not in SEED_TYPES:
            raise ValueError(f"Seed {position}: tipo deve ser 'doi' ou 'title'.")
        if not value:
            raise ValueError(f"Seed {position}: valor vazio.")

        if seed_type == "doi":
            doi = normalize_doi(value)
            if not doi or not DOI_PATTERN.match(doi):
                raise ValueError(f"Seed {position}: '{value}' não é um DOI válido.")
            value = doi

        seeds.append({"index": len(seeds), "input_type": seed_type, "input_value": value})

    return seeds


def _input_key(seed):
    if seed["input_type"] == "doi":
        return f"doi:{normalize_doi(seed['input_value'])}"
    return f"title:{normalize_title(seed['input_value'])}"


def _resolved_key(result):
    doi = normalize_doi(result.get("resolved_doi"))
    if doi:
        return f"doi:{doi}"
    title = normalize_title(result.get("title"))
    return f"title:{title}" if title else None


def _study_key(record, fallback):
    return get_record_key(record) or fallback


def _progress(message):
    print(message, file=sys.stderr, flush=True)


class MultiSeedSnowballing:
    def __init__(self, pipeline=None):
        self.pipeline = pipeline or SnowballingPipeline(write_debug_output=False)

    def run(self, raw_seeds):
        seeds = parse_seeds(raw_seeds)
        total = len(seeds)

        seen_inputs = {}
        seen_resolved = {}
        results = {}

        for seed in seeds:
            position = seed["index"] + 1
            input_key = _input_key(seed)

            if input_key in seen_inputs:
                self._mark_duplicate(seed, seen_inputs[input_key])
                _progress(f"[SEED DONE] {position}/{total} status=duplicate citations=0 references=0")
                continue
            seen_inputs[input_key] = seed["index"]

            _progress(f"[SEED START] {position}/{total} {seed['input_type']}={seed['input_value']}")
            result = self._run_one(seed)

            if result is not None:
                resolved_key = _resolved_key(result)
                if resolved_key and resolved_key in seen_resolved:
                    self._mark_duplicate(seed, seen_resolved[resolved_key])
                    result = None
                else:
                    if resolved_key:
                        seen_resolved[resolved_key] = seed["index"]
                    results[seed["index"]] = result
                    self._fill_seed(seed, result)

            _progress(
                f"[SEED DONE] {position}/{total} status={seed['status']} "
                f"citations={len((result or {}).get('citations') or [])} "
                f"references={len((result or {}).get('references') or [])}"
            )

        if not results:
            reasons = "; ".join(
                f"{s['input_value']}: {s.get('error') or s['status']}" for s in seeds
            )
            raise ValueError(f"Nenhuma seed retornou resultado ({reasons}).")

        return self._build_output(seeds, results)

    def _run_one(self, seed):
        search_input = (
            SearchInput(doi=seed["input_value"])
            if seed["input_type"] == "doi"
            else SearchInput(title=seed["input_value"])
        )
        try:
            result = self.pipeline.run_forward(search_input)
        except ArticleNotFoundError as exc:
            seed.update(status=STATUS_NOT_FOUND, error=str(exc))
            return None
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            seed.update(status=STATUS_ERROR, error=str(exc) or exc.__class__.__name__)
            return None

        if not result or not result.get("title") or result.get("error"):
            seed.update(status=STATUS_NOT_FOUND, error=(result or {}).get("error"))
            return None

        seed["status"] = STATUS_PARTIAL if result.get("partial_result") else STATUS_OK
        seed["error"] = None
        return result

    @staticmethod
    def _mark_duplicate(seed, original_index):
        seed.update(status=STATUS_DUPLICATE, duplicate_of=original_index,
                    error=f"Mesmo artigo da seed {original_index + 1}.")

    @staticmethod
    def _fill_seed(seed, result):
        for field in SEED_FIELDS:
            seed[field] = result.get(field)

    def _build_output(self, seeds, results):
        # Uma seed que aparece na lista de outra (A cita B) já está no
        # conjunto de partida: listá-la como candidata a triagem é ruído.
        seed_keys = {
            key for key in (_resolved_key(result) for result in results.values()) if key
        }

        unions = {}
        removed_seed_hits = 0
        for direction, keys_field in (("citations", "citation_keys"), ("references", "reference_keys")):
            union = {}
            for seed in seeds:
                result = results.get(seed["index"])
                seed[keys_field] = []
                seen_in_seed = set()
                if result is None:
                    continue

                for position, record in enumerate(result.get(direction) or []):
                    key = _study_key(record, f"seed{seed['index']}:{direction}:{position}")
                    if key in seed_keys:
                        removed_seed_hits += 1
                        continue
                    if key in seen_in_seed:
                        continue
                    seen_in_seed.add(key)
                    seed[keys_field].append(key)

                    if key in union:
                        merged = merge_prefer_filled(union[key], record)
                        merged["found_via_seeds"] = union[key]["found_via_seeds"] + [seed["index"]]
                        union[key] = merged
                    else:
                        union[key] = {**record, "study_key": key, "found_via_seeds": [seed["index"]]}

            unions[direction] = list(union.values())

        for seed in seeds:
            seed.setdefault("status", STATUS_ERROR)
            seed.setdefault("error", None)
            seed.setdefault("duplicate_of", None)
            seed["citations_retrieved"] = len(seed.get("citation_keys") or [])
            seed["references_retrieved"] = len(seed.get("reference_keys") or [])

        succeeded = [s for s in seeds if s["status"] in SUCCESS_STATUSES]
        failed = [s for s in seeds if s["status"] in (STATUS_NOT_FOUND, STATUS_ERROR)]

        print(
            f"[MULTI SEED] seeds={len(seeds)} ok={len(succeeded)} failed={len(failed)} "
            f"citations={len(unions['citations'])} references={len(unions['references'])} "
            f"seed_hits_removed={removed_seed_hits}",
            file=sys.stderr,
        )

        return {
            "multi_seed": True,
            "_format_version": MULTI_SEED_FORMAT_VERSION,
            "seeds": seeds,
            "citations": unions["citations"],
            "references": unions["references"],
            "citations_retrieved": len(unions["citations"]),
            "references_retrieved": len(unions["references"]),
            "seeds_succeeded": len(succeeded),
            "seeds_failed": len(failed),
            "partial_result": bool(failed) or any(s["status"] == STATUS_PARTIAL for s in seeds),
            "seed_hits_removed": removed_seed_hits,
            # Sem banco (SNOWMAP_ENABLE_DB desligado) não há search_id; a
            # interface usa isso para esconder o "Save Research State".
            "search_id": None,
            "search_id_backward": None,
            "paper_id_map": {},
        }
