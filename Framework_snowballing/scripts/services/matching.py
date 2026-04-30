from services.normalize import normalize_doi, normalize_title, is_missing


def build_dedup_key(title, doi):
    normalized_doi = normalize_doi(doi)
    if normalized_doi:
        return f"doi:{normalized_doi}"
    return f"title:{normalize_title(title)}"


def score_citation(citation):
    score = 0

    if not is_missing(citation.get("title")):
        score += 2
    if not is_missing(citation.get("year")):
        score += 3
    if not is_missing(citation.get("abstract")):
        score += 4
    if not is_missing(citation.get("venue")):
        score += 2
    if citation.get("authors"):
        score += 1
    if not is_missing(citation.get("doi")):
        score += 4
    if not is_missing(citation.get("language")):
        score += 2
    if not is_missing(citation.get("url")):
        score += 2
    if not is_missing(citation.get("pages")):
        score += 2
    if not is_missing(citation.get("numpages")):
        score += 2
    if not is_missing(citation.get("open_access")):
        score += 2
    if not is_missing(citation.get("keywords")):
        score += 2

    return score


def merge_prefer_filled(base, extra):
    merged = dict(base)

    for field in ["title", "year", "venue", "abstract", "doi","language","pages","numpages","open_access","keywords"]:
        if is_missing(merged.get(field)) and not is_missing(extra.get(field)):
            merged[field] = extra[field]

    if (not merged.get("authors")) and extra.get("authors"):
        merged["authors"] = extra["authors"]

    base_count = merged.get("citations_count", 0)
    extra_count = extra.get("citations_count", 0)
    if (not base_count) and extra_count:
        merged["citations_count"] = extra_count

    return merged