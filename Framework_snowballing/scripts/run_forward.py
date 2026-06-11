import sys
import json
import traceback
from concurrent.futures import ThreadPoolExecutor

from services.normalize import normalize_doi
from services.search import search_combined, enrich_incomplete_citations, clear_caches
from services.cache import init_db, get_cached, save_to_cache
from run_backward import get_references_openalex




#em caso de erro com charmap.
sys.stdout.reconfigure(encoding='utf-8')

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
            print(json.dumps(cached, ensure_ascii=False, indent=2))
            return


        # limpa cache das APIs
        # clear_caches()


        # chama APIs em paralelo
        with ThreadPoolExecutor(max_workers=2) as executor:
            fut_paper = executor.submit(search_combined, doi, title)
            fut_refs = executor.submit(get_references_openalex, doi) if doi else None
            paper = fut_paper.result()
            references = fut_refs.result() if fut_refs else []


        raw_citations = paper.get("citations", [])

        from_openalex = raw_citations and all(c.get("source") == "openalex" for c in raw_citations)
        if from_openalex:
            final_citations = raw_citations
        else:
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
