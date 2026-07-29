import sys
import json
import traceback
import os

from dotenv import load_dotenv
load_dotenv()

from services.normalize import normalize_doi
from services.search import search_combined, enrich_incomplete_citations, clear_caches
from services.cache import init_db, get_cached, save_to_cache
from services.snowmap_bd import save_full_result
from run_backward import get_references_openalex

# em caso de erro com charmap.
sys.stdout.reconfigure(encoding='utf-8')

# ID fixo temporário até ter sistema de login
# Quando tiver autenticação, substituir pelo id do usuário logado
TEMP_USER_ID = os.getenv("TEMP_USER_ID", "00000000-0000-0000-0000-000000000001")


def normalize_citation_counts(citations):
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


def main():
    try:
        doi = sys.argv[1].strip() if len(sys.argv) > 1 else None
        title = sys.argv[2].strip() if len(sys.argv) > 2 else None

        doi = None if doi in {None, "", "-", "null", "None"} else doi
        title = None if title in {None, "", "-", "null", "None"} else title

        if not doi and not title:
            print(json.dumps({"error": "DOI ou título devem ser informados"}))
            sys.exit(1)

        # normaliza DOI
        doi = normalize_doi(doi) if doi else None

        # inicializa banco
        init_db()

        # CHECA CACHE ANTES DE TUDO
        cached = get_cached(doi=doi, title=title, mode="forward")
        if cached and cached.get("citations") and len(cached.get("citations")) > 0:
            print("[CACHE HIT - FORWARD]", file=sys.stderr) #testando o ccache e o novo BD
            print(json.dumps(cached, ensure_ascii=False, indent=2))
            return

        # limpa cache das APIs
        # clear_caches()

        # chama APIs
        paper = search_combined(doi=doi, title=title)
        references = []
        if paper.get("doi"):
            references = get_references_openalex(paper.get("doi"))

        raw_citations = paper.get("citations", [])

        # search_combined ja soma Semantic + OpenAlex e deduplica
        final_citations = enrich_incomplete_citations(raw_citations)
        final_citations = normalize_citation_counts(final_citations)

        result = {
            "input_doi": doi or "-",
            "input_title": title or "-",
            "resolved_doi": normalize_doi(paper.get("doi")) or "-",
            "data_source": paper.get("api", "-"),
            "title": paper.get("title", "-"),
            "authors": [
                {"name": a.get("name", "-")} for a in paper.get("authors", [])
            ] if isinstance(paper.get("authors"), list) else [],
            "year": paper.get("year", "-"),
            "venue": paper.get("venue", "-"),
            "abstract": paper.get("abstract", "-"),
            "citationCount": paper.get("citationCount", paper.get("citations_count", 0)),
            "citations_retrieved": len(final_citations),
            "citations": final_citations,
            "mode": "forward",
            "references_count": len(references),
            "references_retrieved": len(references),
            "open_access": paper.get("open_access", None),
            "url": paper.get("url", None),
            "keywords": paper.get("keywords", []),
            "language": paper.get("language", None),
            "pages": paper.get("pages", None),
            "numpages": paper.get("numpages", None),
        }

        # salva no cache
        print("[SALVANDO NO CACHE]", result.get("resolved_doi"), file=sys.stderr)
        save_to_cache(
            doi=doi,
            title=result.get("title"),
            data=result
        )

        # salva no BD novo
        try:
            ids = save_full_result(output_json=result, user_id=TEMP_USER_ID)
            result["search_id"] = ids["search_id"]
            result["seed_id"] = ids["seed_id"]
        except Exception as db_err:
            result["search_id"] = None
            result["seed_id"] = None

        # salva arquivo local
        with open("output.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(json.dumps(result, ensure_ascii=False, indent=2))

    except Exception:
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"error": "Erro inesperado ao processar o artigo."}))
        sys.exit(1)

if __name__ == "__main__":
    main()