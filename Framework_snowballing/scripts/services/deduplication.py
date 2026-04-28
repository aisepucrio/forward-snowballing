from services.normalize import normalize_doi, generate_paper_id
from services.matching import build_dedup_key, score_citation, merge_prefer_filled


def parse_single_citation(c):
    title = c.get("title", "-")
    year = c.get("year", "-")
    venue = c.get("venue", "-")

    raw_doi = None
    if isinstance(c.get("externalIds"), dict):
        raw_doi = c["externalIds"].get("DOI")
    if not raw_doi:
        raw_doi = c.get("doi")

    normalized_doi = normalize_doi(raw_doi)
    doi = normalized_doi or "-"

    abstract = c.get("abstract", "-")
    authors = c.get("authors", [])
    autores = [{"name": a.get("name", "-")} for a in authors]
    total_citations_received = c.get("citationCount", 0)

    return {
        "paperId": generate_paper_id(title),
        "title": title,
        "authors": autores,
        "year": year,
        "venue": venue,
        "doi": doi,
        "abstract": abstract,
        "citations_count": total_citations_received,
    }


def deduplicate_citations(raw_citations):
    best_by_key = {}

    for c in raw_citations:
        citation_obj = parse_single_citation(c)
        dedup_key = build_dedup_key(
            citation_obj.get("title"),
            citation_obj.get("doi")
        )

        if dedup_key not in best_by_key:
            best_by_key[dedup_key] = citation_obj
            continue

        current_best = best_by_key[dedup_key]
        if score_citation(citation_obj) > score_citation(current_best):
            best_by_key[dedup_key] = merge_prefer_filled(citation_obj, current_best)
        else:
            best_by_key[dedup_key] = merge_prefer_filled(current_best, citation_obj)

    return list(best_by_key.values())