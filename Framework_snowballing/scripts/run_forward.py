import sys
import json
import traceback


from services.normalize import normalize_doi
from services.search import search_combined, enrich_incomplete_citations, clear_caches
from services.deduplication import deduplicate_citations
from services.cache import init_db, get_cached, save_to_cache
from run_backward import get_references_openalex


#em caso de erro com charmap.
sys.stdout.reconfigure(encoding='utf-8')


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
        cached = get_cached(doi=doi, title=title)
        if (cached and cached.get("mode") == "forward" and cached.get("citations") and len(cached.get("citations")) > 0):
            print("[CACHE HIT]", file=sys.stderr)
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


        # 1. deduplica primeiro
        deduped = deduplicate_citations(raw_citations)


        # 2. depois enriquece
        final_citations = enrich_incomplete_citations(deduped)


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
            "mode": "backward",
            "references_count": len(references),
            "references_retrieved": len(references),
        }


        # salva no cache
        print("[SALVANDO NO CACHE]", result.get("resolved_doi"), file=sys.stderr)
        save_to_cache(
            doi=doi,
            title=result.get("title"),
            data=result
        )


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
