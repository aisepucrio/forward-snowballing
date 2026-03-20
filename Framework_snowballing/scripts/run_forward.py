import sys
import json
import traceback

from services.normalize import normalize_doi
from services.search import search_combined, enrich_incomplete_citations, clear_caches
from services.deduplication import deduplicate_citations


def main():
    try:
        doi = sys.argv[1].strip() if len(sys.argv) > 1 else None
        title = sys.argv[2].strip() if len(sys.argv) > 2 else None

        doi = None if doi in {None, "", "-", "null", "None"} else doi
        title = None if title in {None, "", "-", "null", "None"} else title

        if not doi and not title:
            print(json.dumps({"error": "DOI ou título devem ser informados"}))
            sys.exit(1)

        clear_caches()

        paper = search_combined(doi=doi, title=title)

        raw_citations = paper.get("citations", [])
        deduped_citations = deduplicate_citations(raw_citations)
        final_citations = enrich_incomplete_citations(deduped_citations)

        result = {
            "input_doi": normalize_doi(doi) or "-",
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
        }

        with open("output.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(json.dumps(result, ensure_ascii=False, indent=2))

    except Exception:
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"error": "Erro inesperado ao processar o artigo."}))
        sys.exit(1)


if __name__ == "__main__":
    main()