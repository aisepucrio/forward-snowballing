import os
import re
import sys
import time
import json
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from services.normalize import (
    normalize_doi,
    normalize_title,
    fuzzy_match,
    token_overlap_score,
    is_missing,
    generate_paper_id,
)
from services.matching import merge_prefer_filled

REQUEST_TIMEOUT = 12
USER_AGENT = "forward-snowballing-app/1.0"
OPENALEX_CACHE = {}
CROSSREF_CACHE = {}
SEMANTIC_CACHE = {}
REQUEST_CACHE = {}


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


    for attempt in range(4):
        try:
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)


            if response.status_code == 200:
                data = response.json()


                REQUEST_CACHE[url] = data


                return data


            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                wait_time = int(retry_after) if retry_after else 15 * (attempt + 1)
                time.sleep(wait_time)
                continue

            return None
            
        except Exception as e:
            wait_time = 3 * (attempt + 1)
            time.sleep(wait_time)
            continue


    return None


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
        "citations.referenceCount"
    ])


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

    data["api"] = "semantic_doi_lookup"
    if "open_access" not in data:
        data["open_access"] = data.get("isOpenAccess")

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

    citations = []
    cursor = "*"

    for _ in range(5):  # max 1000 citations (5 pages × 200)
        url = f"https://api.openalex.org/works?filter=cites:{openalex_id}&per-page=200&cursor={cursor}"
        data = safe_get(url)

        if not data:
            break

        results = data.get("results", [])
        if not results:
            break

        for item in results:
            biblio = item.get("biblio") or {}
            pages = build_pages(biblio.get("first_page"), biblio.get("last_page"))
            abstract = reconstruct_abstract_from_inverted_index(item.get("abstract_inverted_index"))
            primary_location = item.get("primary_location") or {}
            source = primary_location.get("source") or {}
            openalex_work_id = item.get("id", "").replace("https://openalex.org/", "")
            citations.append({
                "paperId": openalex_work_id or generate_paper_id(item.get("title", "-")),
                "title": item.get("title"),
                "year": item.get("publication_year"),
                "abstract": abstract,
                "doi": normalize_doi(item.get("doi")),
                "url": primary_location.get("landing_page_url"),
                "venue": source.get("display_name") or "-",
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

        next_cursor = data.get("meta", {}).get("next_cursor")
        if not next_cursor:
            break
        cursor = next_cursor

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

    biblio = best.get("biblio") or {}
    pages = build_pages(biblio.get("first_page"), biblio.get("last_page"))

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
        "pages": pages,
        "numpages": extract_npages(pages),


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


        if not item:
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

def load_complete_cache(doi):
    path = cache_path_for_doi(doi)
    if not path.exists():
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_complete_cache(doi, data):
    path = cache_path_for_doi(doi)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)



def merge_citations(openalex_citations, semantic_citations):
    """Use OpenAlex citations (complete) as primary; add Semantic Scholar ones not covered by OpenAlex."""
    if not openalex_citations:
        return semantic_citations or []

    openalex_dois = {c["doi"] for c in openalex_citations if c.get("doi") and c["doi"] != "-"}
    openalex_titles = {normalize_title(c["title"]) for c in openalex_citations if c.get("title")}

    extras = []
    for c in (semantic_citations or []):
        doi = normalize_doi(c.get("doi") or c.get("externalIds", {}).get("DOI", ""))
        title = normalize_title(c.get("title", ""))
        if doi and doi in openalex_dois:
            continue
        if title and title in openalex_titles:
            continue
        extras.append(c)

    return openalex_citations + extras


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

        with ThreadPoolExecutor(max_workers=2) as executor:
            fut_semantic = executor.submit(fallback_via_requests, cleaned_doi)
            fut_openalex = executor.submit(fallback_openalex_by_doi, cleaned_doi)
            paper_data = fut_semantic.result()
            openalex_data = fut_openalex.result()

        if paper_data:
            semantic_doi = None
            if isinstance(paper_data.get("externalIds"), dict):
                semantic_doi = normalize_doi(paper_data["externalIds"].get("DOI"))


            paper_data["doi"] = semantic_doi or cleaned_doi


            openalex_citations = []
            if openalex_data and openalex_data.get("openalex_id"):
                openalex_citations = get_openalex_citations(openalex_data["openalex_id"])

            all_citations = (paper_data.get("citations", []) or []) + openalex_citations


            merged = openalex_data.copy() if openalex_data else {}
            merged = merge_prefer_filled(merged, paper_data)


            merged["doi"] = semantic_doi or cleaned_doi
            merged["citations"] = all_citations
            merged["api"] = "semantic+openalex"
            merged["partial_result"] = False

            save_complete_cache(cleaned_doi, merged)

            return merged


        if openalex_data:

            for retry in range(3):
                time.sleep(2 ** retry)
                paper_data = fallback_via_requests(cleaned_doi)

                if paper_data:
                    REQUEST_CACHE.clear()
                    SEMANTIC_CACHE.clear()
                    return search_combined(doi=cleaned_doi, title=None)

            cached = load_complete_cache(cleaned_doi)
            if cached:
                cached["from_cache"] = True
                cached["warning"] = (
                    f"Semantic Scholar falhou para o DOI {cleaned_doi}; "
                    "usando último resultado completo salvo."
                )
                return cached

            return {
    "error": (
        f"Semantic Scholar falhou para o DOI {cleaned_doi} "
        "e ainda não existe cache completo salvo."
    ),
    "partial_result": True,
    "citationCount": None,
    "citations": [],
}

        crossref_data = fallback_crossref(doi=cleaned_doi)
        if crossref_data:
            return crossref_data


    if cleaned_title and not openalex_data and not paper_data and not crossref_data:
        paper_data = fallback_semantic_by_title(title)


        if paper_data:
            semantic_doi = None
            if isinstance(paper_data.get("externalIds"), dict):
                semantic_doi = normalize_doi(paper_data["externalIds"].get("DOI"))


            resolved_doi = semantic_doi or normalize_doi(paper_data.get("doi"))


            if resolved_doi:
                return search_combined(doi=resolved_doi, title=None)


            paper_data["citationCount"] = len(paper_data.get("citations", []))
            return paper_data


        openalex_data = fallback_openalex_by_title(title)


        openalex_doi = normalize_doi(openalex_data.get("doi")) if openalex_data else None
        if openalex_doi:
            return search_combined(doi=openalex_doi, title=None)


        if openalex_data:
            return attach_openalex_citations(openalex_data)


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
        openalex_citations = []
        if openalex_data and openalex_data.get("openalex_id"):
            openalex_citations = get_openalex_citations(openalex_data["openalex_id"])

        all_citations = (paper_data.get("citations", []) if paper_data else []) + openalex_citations




        merged["citations"] = all_citations

        merged["api"] = f'{openalex_data.get("api", "openalex")}+{paper_data.get("api", "semantic")}'




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




    print(json.dumps({
        "error": f"Artigo não encontrado. DOI='{doi}' | title='{title}'"
    }))
    sys.exit(1)








def needs_enrichment(citation):
    return (
        is_missing(citation.get("doi")) or
        is_missing(citation.get("year")) or
        is_missing(citation.get("venue")) or
        is_missing(citation.get("abstract")) or
        not citation.get("authors") or
        is_missing(citation.get("url")) or
        is_missing(citation.get("language")) or
        is_missing(citation.get("pages")) or
        is_missing(citation.get("numpages")) or
        is_missing(citation.get("open_access")) or
        is_missing(citation.get("keywords")) or
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

        if needs_enrichment(enriched):
            oa = fallback_openalex_by_doi(doi)
            if oa:
                enriched = merge_prefer_filled(enriched, oa)


    elif title and normalize_title(title):
        if needs_enrichment(enriched):
            cr = fallback_crossref(title=title)
            if cr:
                enriched = merge_prefer_filled(enriched, cr)

        resolved_doi = get_citation_doi(enriched)
        if resolved_doi and needs_enrichment(enriched):
            oa = fallback_openalex_by_doi(resolved_doi)
            if oa:
                enriched = merge_prefer_filled(enriched, oa)


    enriched["paperId"] = generate_paper_id(enriched.get("title", "-"))
    enriched["doi"] = normalize_doi(enriched.get("doi")) or "-"


    if (not enriched.get("url") or enriched.get("url") in ["", "-"]) and enriched.get("doi") not in ["", "-"]:
        enriched["url"] = f"https://doi.org/{enriched['doi']}"


    return enriched


def enrich_incomplete_citations(citations):
    enriched_citations = [dict(citation) for citation in citations]

    indices_to_enrich = [
        i for i, c in enumerate(enriched_citations)
        if needs_enrichment(c)
    ]

    dois_to_fetch = []
    for i in indices_to_enrich:
        citation = enriched_citations[i]
        doi = get_citation_doi(citation)
        if doi:
            citation["doi"] = doi
            dois_to_fetch.append(doi)

    crossref_by_doi = fallback_crossref_batch_by_doi(dois_to_fetch)

    # Apply batch results; collect what still needs individual enrichment.
    individual_tasks = []
    for i in indices_to_enrich:
        citation = enriched_citations[i]
        doi = get_citation_doi(citation)
        title = citation.get("title")
        if doi:
            cr = crossref_by_doi.get(doi)
            if cr:
                enriched_citations[i] = merge_prefer_filled(citation, cr)
            if needs_enrichment(enriched_citations[i]):
                individual_tasks.append((i, "doi", doi))
        elif title and normalize_title(title):
            individual_tasks.append((i, "title", title))

    # Parallelize remaining individual calls to avoid serial API waits.
    if individual_tasks:
        def _fetch(task):
            index, kind, value = task
            result = dict(enriched_citations[index])

            if kind == "doi":
                cr = fallback_crossref(doi=value)
                if cr:
                    result = merge_prefer_filled(result, cr)
                if needs_enrichment(result):
                    oa = fallback_openalex_by_doi(value)
                    if oa:
                        result = merge_prefer_filled(result, oa)
            else:
                cr = fallback_crossref(title=value)
                if cr:
                    result = merge_prefer_filled(result, cr)
                resolved_doi = get_citation_doi(result)
                if resolved_doi and needs_enrichment(result):
                    oa = fallback_openalex_by_doi(resolved_doi)
                    if oa:
                        result = merge_prefer_filled(result, oa)

            return index, result

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(_fetch, task): task for task in individual_tasks}
            for fut in as_completed(futures):
                try:
                    index, enriched = fut.result()
                    enriched_citations[index] = enriched
                except Exception:
                    pass

    for index, citation in enumerate(enriched_citations):
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
