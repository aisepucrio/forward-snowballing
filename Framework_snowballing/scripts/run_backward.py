import sys
import json
import traceback
import requests

from services.normalize import normalize_doi
from services.search import search_combined, enrich_incomplete_citations, clear_caches
from services.deduplication import deduplicate_citations
from services.cache import init_db, save_to_cache


#Funçãp de references via OpenAlex
def get_references_openalex(doi):
    try:
        url_work = f"https://api.openalex.org/works/https://doi.org/{doi}"
        resp_work = requests.get(url_work)
        
        if resp_work.status_code != 200:
            return [], 0
            
        data = resp_work.json()
        total_references = data.get("referenced_works_count", 0)
        refs_ids = data.get("referenced_works", [])

        if not refs_ids:
            return [], total_references

        references = []
        # Busca em blocos de 50 para não estourar o limite da URL da API
        chunk_size = 50
        for i in range(0, len(refs_ids), chunk_size):
            chunk = refs_ids[i:i + chunk_size]
            target_ids = "|".join(chunk) 
            url_batch = f"https://api.openalex.org/works?filter=openalex_id:{target_ids}"
            
            resp_batch = requests.get(url_batch)
            if resp_batch.status_code == 200:
                results = resp_batch.json().get("results", [])
                for ref in results:
                    primary_loc = ref.get("primary_location") or {}
                    source = primary_loc.get("source") or {}
                    references.append({
                        "title": ref.get("title") or "Untitled",
                        "year": ref.get("publication_year", "-"),
                        "venue": source.get("display_name", "-"),
                        "doi": normalize_doi(ref.get("doi")) if ref.get("doi") else "-",
                        "authors": [{"name": a.get("author", {}).get("display_name", "-")} for a in (ref.get("authorships") or [])],
                        "citationCount": ref.get("cited_by_count", 0),
                    })
            print(f"[DEBUG] Recuperadas {len(references)} de {total_references} referências...", file=sys.stderr)

        return references, total_references

    except Exception as e:
        print(f"[ERROR OPENALEX] {e}", file=sys.stderr)
        return [], 0


def main():
    try:
        doi = sys.argv[1].strip() if len(sys.argv) > 1 else None
        title = sys.argv[2].strip() if len(sys.argv) > 2 else None

        doi = None if doi in {None, "", "-", "null", "None"} else doi
        title = None if title in {None, "", "-", "null", "None"} else title

        if not doi and not title:
            print(json.dumps({"error": "DOI ou título devem ser informados"}))
            sys.exit(1)

        doi = normalize_doi(doi) if doi else None

        init_db()
        clear_caches()

        
        paper = search_combined(doi=doi, title=title)

        # Tenta references do próprio paper
        raw_references = paper.get("references", [])
        total_refs_count = len(raw_references)

        # fallback se vazio
        if not raw_references and doi:
            print("[DEBUG] usando OpenAlex para references...", file=sys.stderr)
            # AQUI: captura os dois retornos da função atualizada
            raw_references, total_refs_count = get_references_openalex(doi)

        deduped_references = deduplicate_citations(raw_references)
        final_references = enrich_incomplete_citations(deduped_references)

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
            "references_count": total_refs_count,  # O total real citado pelo paper
            "references_retrieved": len(final_references),
            "references": final_references,
        }

        print("[SALVANDO NO CACHE]", result.get("resolved_doi"), file=sys.stderr)
        save_to_cache(
            doi=result.get("resolved_doi"),
            title=result.get("title"),
            data=result
        )

        with open("output.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(json.dumps(result, ensure_ascii=False, indent=2))

    except Exception:
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"error": "Erro inesperado ao processar o artigo."}))
        sys.exit(1)


if __name__ == "__main__":
    main()