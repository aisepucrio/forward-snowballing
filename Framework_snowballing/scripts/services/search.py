import os
import sys
import time
import json
import requests


from services.normalize import (
    normalize_doi,
    normalize_title,
    fuzzy_match,
    token_overlap_score,
    is_missing,
    generate_paper_id,
)
from services.matching import merge_prefer_filled




REQUEST_TIMEOUT = 10
USER_AGENT = "forward-snowballing-app/1.0"


OPENALEX_CACHE = {}
CROSSREF_CACHE = {}
SEMANTIC_CACHE = {}




def safe_get(url, headers=None):
    headers = headers or {}
    headers.update({"User-Agent": USER_AGENT})


    for attempt in range(3):
        try:
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            print(f"[DEBUG] GET {url} -> {response.status_code}", file=sys.stderr)


            if response.status_code == 200:
                return response.json()


            if response.status_code == 429:
                wait_time = 3 * (attempt + 1)
                print(f"[DEBUG] 429 recebido. Esperando {wait_time}s...", file=sys.stderr)
                time.sleep(wait_time)
                continue


            print(f"[DEBUG] BODY: {response.text[:500]}", file=sys.stderr)
            return None


        except Exception as e:
            print(f"[DEBUG] EXCEPTION GET {url}: {e}", file=sys.stderr)
            return None


    return None

def extract_npages(pages):
    if not pages:
        return None
    if "-" in pages:
        try:
            start, end = pages.split("-")
            return int(end) - int(start) + 1
        except:
            return None
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




def semantic_fields():
    return (
        "title,year,venue,abstract,authors,externalIds,citationCount,"
        "citations.title,citations.authors,citations.year,citations.venue,"
        "citations.externalIds,citations.abstract,citations.citationCount"
    )






def fallback_via_requests(doi):
    normalized_doi = normalize_doi(doi)
    if not normalized_doi:
        return None


    encoded_doi = requests.utils.quote(normalized_doi, safe="")
    fields = semantic_fields()


    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{encoded_doi}?fields={fields}"


    API_KEY = os.getenv("SEMANTIC_API_KEY")
    headers = {
        "x-api-key": API_KEY
    }


    data = safe_get(url, headers=headers)
    if not data:
        return None


    data["api"] = "semantic_doi_lookup"
    data["_debug_doi_lookup"] = {
        "stage": "doi_lookup_success",
        "normalized_doi": normalized_doi,
    }


    return data




def fallback_semantic_by_title(title):
    normalized_title = normalize_title(title)
    if not normalized_title:
        return None


    cache_key = f"title:{normalized_title}"
    if cache_key in SEMANTIC_CACHE:
        cached = SEMANTIC_CACHE[cache_key]
        if cached and isinstance(cached, dict):
            cached["_debug_title_flow"] = {
                "stage": "cache_hit_title",
                "cache_key": cache_key,
            }
        return cached


    query = requests.utils.quote(title)


    search_url = (
        "https://api.semanticscholar.org/graph/v1/paper/search"
        f"?query={query}&limit=10&fields=paperId,title,externalIds"
    )
    search_data = safe_get(search_url)
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
            doi_data["_debug_title_flow"] = {
                "stage": "title_to_doi_success",
                "best_title": best.get("title"),
                "best_score": best_score,
                "paperId": best.get("paperId"),
                "semantic_doi": semantic_doi,
            }
            SEMANTIC_CACHE[cache_key] = doi_data
            return doi_data


    paper_id = best.get("paperId")
    if not paper_id:
        return None


    paper_url = (
        f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}"
        f"?fields={semantic_fields()}"
    )
    data = safe_get(paper_url)
    if not data:
        return None


    data["api"] = "semantic_title_paperid_fallback"
    data["_debug_title_flow"] = {
        "stage": "title_to_paperid_fallback",
        "best_title": best.get("title"),
        "best_score": best_score,
        "paperId": paper_id,
        "semantic_doi": semantic_doi,
    }


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

    }


    OPENALEX_CACHE[cache_key] = result
    return result
def get_openalex_citations(openalex_id):
    if not openalex_id:
        return []


    url = f"https://api.openalex.org/works?filter=cites:{openalex_id}&per-page=200"
    data = safe_get(url)


    if not data:
        return []


    citations = []


    for item in data.get("results", []):
        citations.append({
            "title": item.get("title"),
            "year": item.get("publication_year"),
            "doi": normalize_doi(item.get("doi")),

            "url": item.get("primary_location", {}).get("landing_page_url"),

            "open_access": item.get("open_access", {}).get("is_oa"),

            "keywords": [
                c.get("display_name") for c in item.get("concepts", [])
            ],

            "language": item.get("language"),

            "pages": item.get("biblio", {}).get("first_page"),
            "numpages": item.get("biblio", {}).get("last_page"),

            "authors": [
                {"name": a.get("author", {}).get("display_name", "-")}
                for a in item.get("authorships", [])
            ],

            "source": "openalex"
        })


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
        "open_access": data.get("open_access", {}).get("is_oa"),
        "url": primary_location.get("landing_page_url"),
        "keywords": [
            c.get("display_name")
            for c in data.get("concepts", [])
            if c.get("display_name")
        ][:10],
        "language": data.get("language"),


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
        "language": item.get("language"),
        "url": item.get("URL"),
        "pages": item.get("page"),
        "numpages": extract_npages(item.get("page")),
    }


    if doi:
        CROSSREF_CACHE[f"doi:{normalize_doi(doi)}"] = result
    elif title:
        CROSSREF_CACHE[f"title:{normalize_title(title)}"] = result


    return result


def deduplicate_citations(citations):
    unique = {}


    for c in citations:
        doi = normalize_doi(c.get("doi"))
        title = normalize_title(c.get("title"))


        key = None


        if doi:
            key = f"doi:{doi}"
        elif title:
            key = f"title:{title}"
        else:
            continue




        if key not in unique:
            unique[key] = c


        else:
            existing = unique[key]


            # preenche campos faltantes
            for field in ["year", "doi", "venue"]:
                if not existing.get(field) and c.get(field):
                    existing[field] = c.get(field)


            # merge de autores
            if not existing.get("authors") and c.get("authors"):
                existing["authors"] = c.get("authors")


    return list(unique.values())


def search_combined(doi=None, title=None):
    cleaned_doi = normalize_doi(doi) if doi else None
    cleaned_title = normalize_title(title) if title else ""


    openalex_data = None
    paper_data = None
    crossref_data = None


    if cleaned_doi:
        openalex_data = fallback_openalex_by_doi(cleaned_doi)
        paper_data = fallback_via_requests(cleaned_doi)
        crossref_data = fallback_crossref(doi=cleaned_doi)


    if cleaned_title:
        if not paper_data:
            paper_data = fallback_semantic_by_title(title)


        if not openalex_data:
            openalex_data = fallback_openalex_by_title(title)


        if not crossref_data:
            crossref_data = fallback_crossref(title=title)


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
        # --- SEMANTIC ---
        semantic_citations = paper_data.get("citations", []) if paper_data else []


        # --- OPENALEX ---
        openalex_citations = []
        if openalex_data and openalex_data.get("openalex_id"):
            openalex_citations = get_openalex_citations(openalex_data["openalex_id"])


        all_citations = semantic_citations + openalex_citations


        # REMOVE DUPLICATAS
        deduped_citations = deduplicate_citations(all_citations)


        merged["citations"] = deduped_citations
        merged["citationCount"] = len(deduped_citations)




        merged["api"] = f'{openalex_data.get("api", "openalex")}+{paper_data.get("api", "semantic")}'


        if crossref_data:
            merged = merge_prefer_filled(merged, crossref_data)
            merged["api"] += "+crossref"


        return merged


    if openalex_data:
        merged = dict(openalex_data)
        if crossref_data:
            merged = merge_prefer_filled(merged, crossref_data)
            merged["api"] = "openalex+crossref"
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
    
    print("[DEBUG enriched keys]", enriched.keys(), file=sys.stderr)

    return enriched




def enrich_incomplete_citations(citations):
    enriched_citations = []


    for citation in citations:
        if needs_enrichment(citation):
            citation = enrich_citation(citation)
        enriched_citations.append(citation)


    return enriched_citations




def clear_caches():
    OPENALEX_CACHE.clear()
    CROSSREF_CACHE.clear()
    SEMANTIC_CACHE.clear()
