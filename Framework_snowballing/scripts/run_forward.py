import sys
import json
import traceback
import re
import hashlib
import requests


REQUEST_TIMEOUT = 10
USER_AGENT = "forward-snowballing-app/1.0"

OPENALEX_CACHE = {}
CROSSREF_CACHE = {}


def slugify(text):
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", text)[:50]


def generate_paper_id(title):
    if not title:
        return "id-desconhecido"
    slug = slugify(title)
    return slug or hashlib.md5(title.encode()).hexdigest()[:10]


def normalize_doi(doi):
    if not doi:
        return None

    doi = str(doi).strip().lower()

    if doi in {"", "-", "none", "null"}:
        return None

    doi = doi.replace("https://doi.org/", "")
    doi = doi.replace("http://doi.org/", "")
    doi = doi.replace("doi.org/", "")
    doi = doi.replace("doi:", "")
    doi = doi.strip()

    if doi in {"", "-", "none", "null"}:
        return None

    return doi


def normalize_title(title):
    if not title:
        return ""

    title = str(title).strip().lower()
    title = re.sub(r"[^\w\s]", "", title)
    title = re.sub(r"\s+", " ", title)
    return title


def is_missing(value):
    return value in (None, "", "-", "null", "None")


def safe_get(url):
    headers = {"User-Agent": USER_AGENT}
    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception:
        return None


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


def fallback_via_requests(doi):
    fields = (
        "title,year,venue,abstract,authors,externalIds,citationCount,"
        "citations.title,citations.authors,citations.year,citations.venue,"
        "citations.externalIds,citations.abstract,citations.citationCount"
    )
    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields={fields}"

    data = safe_get(url)
    if not data:
        return None

    data["api"] = "semantic"
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

    result = {
        "title": data.get("title", "-"),
        "year": data.get("publication_year", "-"),
        "venue": source.get("display_name", "-"),
        "abstract": abstract,
        "doi": normalize_doi(data.get("doi")) or normalized_doi,
        "authors": authors,
        "citations_count": data.get("cited_by_count", 0),
        "api": "openalex",
    }

    OPENALEX_CACHE[cache_key] = result
    return result


def fallback_openalex_by_title(title):
    normalized_title = normalize_title(title)
    if not normalized_title:
        return None

    cache_key = f"title:{normalized_title}"
    if cache_key in OPENALEX_CACHE:
        return OPENALEX_CACHE[cache_key]

    query = requests.utils.quote(title)
    url = f"https://api.openalex.org/works?search={query}&per-page=5"
    data = safe_get(url)
    if not data:
        OPENALEX_CACHE[cache_key] = None
        return None

    results = data.get("results") or []
    if not results:
        OPENALEX_CACHE[cache_key] = None
        return None

    best = None
    for item in results:
        candidate_title = item.get("title", "")
        if normalize_title(candidate_title) == normalized_title:
            best = item
            break

    if not best:
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

        url = f"https://api.crossref.org/works/{normalized_doi}"
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
        url = f"https://api.crossref.org/works?query.title={query}&rows=5"
        data = safe_get(url)
        if not data:
            CROSSREF_CACHE[cache_key] = None
            return None

        items = data.get("message", {}).get("items", [])
        if not items:
            CROSSREF_CACHE[cache_key] = None
            return None

        item = None
        for candidate in items:
            titles = candidate.get("title", [])
            candidate_title = titles[0] if titles else ""
            if normalize_title(candidate_title) == normalized_title:
                item = candidate
                break

        if not item:
            CROSSREF_CACHE[cache_key] = None
            return None
    else:
        return None

    title_list = item.get("title", [])
    abstract = item.get("abstract", "-")

    year = "-"
    issued = item.get("issued", {}).get("date-parts", [])
    if issued and issued[0]:
        year = issued[0][0]

    venue_list = item.get("container-title", [])
    authors = []
    for a in item.get("author", []):
        full_name = f"{a.get('given', '')} {a.get('family', '')}".strip()
        authors.append({"name": full_name or "-"})

    result = {
        "title": title_list[0] if title_list else "-",
        "year": year,
        "venue": venue_list[0] if venue_list else "-",
        "abstract": abstract if abstract else "-",
        "doi": normalize_doi(item.get("DOI")) or "-",
        "authors": authors,
        "citations_count": 0,
        "api": "crossref",
    }

    if doi:
        CROSSREF_CACHE[f"doi:{normalize_doi(doi)}"] = result
    elif title:
        CROSSREF_CACHE[f"title:{normalize_title(title)}"] = result

    return result


def search_combined(doi):
    cleaned_doi = normalize_doi(doi)
    if not cleaned_doi:
        print(json.dumps({"error": f"DOI inválido: {doi}"}))
        sys.exit(1)

    openalex_data = fallback_openalex_by_doi(cleaned_doi)
    paper_data = fallback_via_requests(cleaned_doi)

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

        if not merged.get("authors") and paper_data.get("authors"):
            merged["authors"] = [
                {"name": a.get("name", "-")} for a in paper_data.get("authors", [])
            ]

        merged["citations"] = paper_data.get("citations", [])
        merged["api"] = "openalex+semantic"
        return merged

    if openalex_data:
        return openalex_data

    if paper_data:
        return paper_data

    print(json.dumps({"error": f"Artigo com DOI {doi} não encontrado."}))
    sys.exit(1)


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

    return score


def merge_prefer_filled(base, extra):
    merged = dict(base)

    for field in ["title", "year", "venue", "abstract", "doi"]:
        if is_missing(merged.get(field)) and not is_missing(extra.get(field)):
            merged[field] = extra[field]

    if (not merged.get("authors")) and extra.get("authors"):
        merged["authors"] = extra["authors"]

    base_count = merged.get("citations_count", 0)
    extra_count = extra.get("citations_count", 0)
    if (not base_count) and extra_count:
        merged["citations_count"] = extra_count

    return merged


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
            best_by_key[dedup_key] = citation_obj
        else:
            best_by_key[dedup_key] = merge_prefer_filled(current_best, citation_obj)

    return list(best_by_key.values())


def needs_enrichment(citation):
    return (
        is_missing(citation.get("abstract")) or
        is_missing(citation.get("doi")) or
        is_missing(citation.get("year")) or
        is_missing(citation.get("venue")) or
        not citation.get("authors")
    )


def enrich_citation(citation):
    enriched = dict(citation)
    doi = normalize_doi(enriched.get("doi"))
    title = enriched.get("title")

    if doi:
        oa = fallback_openalex_by_doi(doi)
        if oa:
            enriched = merge_prefer_filled(enriched, oa)

        if needs_enrichment(enriched):
            cr = fallback_crossref(doi=doi)
            if cr:
                enriched = merge_prefer_filled(enriched, cr)
    else:
        if title and normalize_title(title):
            oa = fallback_openalex_by_title(title)
            if oa:
                enriched = merge_prefer_filled(enriched, oa)

        if needs_enrichment(enriched) and title and normalize_title(title):
            cr = fallback_crossref(title=title)
            if cr:
                enriched = merge_prefer_filled(enriched, cr)

    enriched["paperId"] = generate_paper_id(enriched.get("title", "-"))
    enriched["doi"] = normalize_doi(enriched.get("doi")) or "-"

    return enriched


def enrich_incomplete_citations(citations):
    enriched_citations = []

    for citation in citations:
        if needs_enrichment(citation):
            citation = enrich_citation(citation)
        enriched_citations.append(citation)

    return enriched_citations


def main():
    try:
        if len(sys.argv) < 2:
            print(json.dumps({"error": "Uso: python run_forward.py <DOI>"}))
            sys.exit(1)

        doi = sys.argv[1].strip()
        paper = search_combined(doi)

        raw_citations = paper.get("citations", [])
        deduped_citations = deduplicate_citations(raw_citations)
        final_citations = enrich_incomplete_citations(deduped_citations)

        result = {
                "input_doi": normalize_doi(paper.get("doi", doi)) or doi,
                "title": paper.get("title", "-"),
                "authors": [
                    {"name": a.get("name", "-")} for a in paper.get("authors", [])
                ] if isinstance(paper.get("authors"), list) else [],
                "year": paper.get("year", "-"),
                "venue": paper.get("venue", "-"),
                "abstract": paper.get("abstract", "-"),
                "citations_count": len(final_citations),
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