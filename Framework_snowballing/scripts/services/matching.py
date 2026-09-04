from services.normalize import normalize_doi, normalize_title, is_missing


def build_dedup_key(title, doi, unique_id=None):
    # A busca só funde automaticamente quando o DOI bate exato — é o único
    # critério seguro pra dizer "é com certeza o mesmo artigo" sem checar com
    # o usuário. Sem DOI, cada item fica com uma chave única (unique_id) e
    # nunca funde com nada aqui, nem com outro item de título igual: esse
    # caso (mesmo artigo sem DOI em um dos lados, ou títulos iguais com DOIs
    # diferentes) fica pro botão de duplicatas, que é revisão manual.
    normalized_doi = normalize_doi(doi)
    if normalized_doi:
        return f"doi:{normalized_doi}"
    return f"unique:{unique_id}"


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

    base_count = merged.get("citations_count") if merged.get("citations_count") is not None else merged.get("citationCount")
    extra_count = extra.get("citations_count") if extra.get("citations_count") is not None else extra.get("citationCount")

    if base_count is None and extra_count is not None:
        merged["citations_count"] = extra_count
        merged["citationCount"] = extra_count
    elif base_count is not None:
        merged["citations_count"] = base_count
        merged["citationCount"] = base_count

    return merged