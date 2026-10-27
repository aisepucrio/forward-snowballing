"""
Diagnóstico do backward: explica, artigo a artigo, de onde vem a diferença
entre o total de referências do pipeline e o valor real.

Para cada DOI, compara as listas brutas de cada fonte (Semantic Scholar,
OpenAlex, OpenCitations) com o resultado final do pipeline e classifica as
referências do OpenAlex que não casaram com o Semantic:
  - doi_match: casou por DOI (esperado);
  - title_dup: não casou pela chave do pipeline, mas o título é praticamente
    igual ao de uma referência do Semantic -> duplicata que infla a contagem;
  - new: referência que só o OpenAlex tem.

Uso:
    python -X utf8 tests_csvs/diagnose_backward.py [DOI ...]
Sem argumentos, roda os 5 artigos problemáticos de PROBLEMATICOS.
Detalhes por artigo vão para tests_csvs/diagnostics/<doi>.json.
"""
import csv
import json
import os
import sys
from difflib import SequenceMatcher

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "scripts")
sys.path.insert(0, SCRIPTS_DIR)
os.environ.setdefault("SNOWMAP_DISABLE_CACHE", "1")

from services import search  # noqa: E402
from services.normalize import normalize_doi, normalize_title  # noqa: E402
from services.snowballing_pipeline import (  # noqa: E402
    OpenAlexReferenceProvider,
    SearchInput,
    SnowballingPipeline,
)

# Máximo de 5 por rodada: cada artigo faz dezenas de requisições.
PROBLEMATICOS = [
    "10.1016/j.jss.2021.111044",     # sobra: 160 vs 110
    "10.5277/e-Inf180103",           # falta: 5 vs 75 (Semantic bloqueado)
    "10.1016/j.infsof.2016.07.006",  # instável: 75 / 30 vs 77
    "10.1016/j.infsof.2020.106294",  # sobra: 37 vs 28
    "10.1049/ic.2011.0001",          # falta: 12 vs 23 (Semantic bloqueado)
]

TITLE_DUP_MIN = 0.90
OUT_DIR = os.path.join(SCRIPT_DIR, "diagnostics")


def load_reais():
    path = os.path.join(SCRIPT_DIR, "valores_reais_artigos.csv")
    with open(path, encoding="utf-8-sig") as f:
        return {
            (row["DOI"] or "").strip().lower(): int(row["Backward Real do Artigo"])
            for row in csv.DictReader(f)
        }


def title_similarity(a, b):
    return SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio()


def best_title_match(title, candidates):
    best, best_score = None, 0.0
    for candidate in candidates:
        score = title_similarity(title, candidate.get("title"))
        if score > best_score:
            best, best_score = candidate, score
    return best, best_score


def resumo(record):
    return {
        "title": record.get("title"),
        "doi": search.get_citation_doi(record),
        "year": record.get("year"),
        "source": record.get("source"),
    }


def run_pipeline(doi):
    pipeline = SnowballingPipeline(write_debug_output=False)
    pipeline._save = lambda result, doi: None  # não grava banco/cache
    search.clear_caches()
    return pipeline.run_forward(SearchInput(doi=doi, title=None))


def diagnose(doi, reais):
    doi = normalize_doi(doi)
    semantic = search.fallback_via_requests(doi)
    s2_refs = (semantic or {}).get("references") or []
    s2_reported = (semantic or {}).get("referenceCount")

    provider = OpenAlexReferenceProvider()
    oa_refs = provider.get_references(doi=doi)

    oc_refs = search.fallback_opencitations_by_doi(doi)

    s2_keys = {search.get_record_key(r) for r in s2_refs}
    s2_dois = {search.get_citation_doi(r) for r in s2_refs} - {None}

    oa_doi_match, oa_title_dup, oa_new = [], [], []
    for record in oa_refs:
        if search.get_record_key(record) in s2_keys:
            oa_doi_match.append(record)
            continue
        match, score = best_title_match(record.get("title"), s2_refs)
        if score >= TITLE_DUP_MIN:
            oa_title_dup.append({**resumo(record), "s2_match": resumo(match), "score": round(score, 3)})
        else:
            oa_new.append({**resumo(record), "best_s2_score": round(score, 3)})

    oc_dois = {r["doi"] for r in oc_refs}
    oa_dois = {search.get_citation_doi(r) for r in oa_refs} - {None}

    result = run_pipeline(doi)
    final_refs = result.get("references") or []
    by_source = {}
    for record in final_refs:
        by_source[record.get("source") or "?"] = by_source.get(record.get("source") or "?", 0) + 1

    # Duplicatas que sobreviveram no resultado final (título quase igual)
    final_dups = []
    for i, a in enumerate(final_refs):
        for b in final_refs[i + 1:]:
            if title_similarity(a.get("title"), b.get("title")) >= TITLE_DUP_MIN:
                final_dups.append([resumo(a), resumo(b)])

    report = {
        "doi": doi,
        "real": reais.get(doi.lower()),
        "pipeline_final": len(final_refs),
        "pipeline_by_source": by_source,
        "pipeline_warning": result.get("warning"),
        "semantic_ok": semantic is not None,
        "semantic_reported": s2_reported,
        "semantic_listed": len(s2_refs),
        "semantic_without_doi": sum(1 for r in s2_refs if not search.get_citation_doi(r)),
        "semantic_without_title": sum(1 for r in s2_refs if not normalize_title(r.get("title"))),
        "openalex_listed": len(oa_refs),
        "openalex_without_doi": sum(1 for r in oa_refs if not search.get_citation_doi(r)),
        "openalex_doi_match": len(oa_doi_match),
        "openalex_title_dup": len(oa_title_dup),
        "openalex_new": len(oa_new),
        "openalex_paratext": sum(1 for r in oa_refs if r.get("openalex_type") == "paratext"),
        "opencitations_listed": len(oc_refs),
        "opencitations_not_in_s2_or_oa": len(oc_dois - s2_dois - oa_dois),
        "final_title_duplicates": len(final_dups),
        "details": {
            "openalex_title_dup": oa_title_dup,
            "openalex_new": oa_new,
            "final_title_duplicates": final_dups,
            "semantic_refs": [resumo(r) for r in s2_refs],
        },
    }
    return report


def main():
    dois = sys.argv[1:] or PROBLEMATICOS
    if len(dois) > 5:
        print("(AVISO) Limitando a 5 artigos por rodada.")
        dois = dois[:5]

    reais = load_reais()
    os.makedirs(OUT_DIR, exist_ok=True)

    cols = [
        "real", "pipeline_final", "semantic_reported", "semantic_listed",
        "semantic_without_doi", "openalex_listed", "openalex_without_doi",
        "openalex_doi_match", "openalex_title_dup", "openalex_new", "openalex_paratext",
        "opencitations_listed", "opencitations_not_in_s2_or_oa",
        "final_title_duplicates",
    ]
    rows = []
    for doi in dois:
        print(f"\n== {doi}", flush=True)
        report = diagnose(doi, reais)
        rows.append(report)
        with open(os.path.join(OUT_DIR, doi.replace("/", "_") + ".json"), "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        for col in cols + ["pipeline_by_source"]:
            print(f"   {col:32} {report[col]}")

    summary_path = os.path.join(OUT_DIR, "summary.csv")
    with open(summary_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["doi"] + cols)
        writer.writeheader()
        for report in rows:
            writer.writerow({k: report[k] for k in ["doi"] + cols})
    print(f"\nResumo em {summary_path}")


if __name__ == "__main__":
    main()
