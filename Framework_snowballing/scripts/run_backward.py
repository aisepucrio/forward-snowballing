import sys
import json
import traceback
import requests


from services.normalize import normalize_doi
from services.search import search_combined, enrich_incomplete_citations, clear_caches
from services.deduplication import deduplicate_citations
from services.cache import init_db, get_cached, save_to_cache


def get_references_openalex(doi):
   try:
       clean_doi = normalize_doi(doi)
       url = f"https://api.openalex.org/works/https://doi.org/{clean_doi}"


       resp = requests.get(url)
       if resp.status_code != 200:
           return []


       data = resp.json()
       refs_ids = data.get("referenced_works", [])


       if not refs_ids:
           return []


       references = []
       chunk_size = 50


       for i in range(0, len(refs_ids), chunk_size):
           chunk = refs_ids[i:i + chunk_size]
           ids = "|".join(chunk)


           batch_url = f"https://api.openalex.org/works?filter=openalex_id:{ids}"
           resp_batch = requests.get(batch_url)


           if resp_batch.status_code != 200:
               continue


           results = resp_batch.json().get("results", [])


           for ref in results:
               primary_loc = ref.get("primary_location") or {}
               source = primary_loc.get("source") or {}


               references.append({
                   "title": ref.get("title") or "Untitled",
                   "year": ref.get("publication_year", "-"),
                   "venue": source.get("display_name", "-"),
                   "doi": normalize_doi(ref.get("doi")) if ref.get("doi") else "-",
                   "authors": [
                       {"name": a.get("author", {}).get("display_name", "-")}
                       for a in (ref.get("authorships") or [])
                   ],
                   "citationCount": ref.get("cited_by_count", 0),
               })


       return references


   except Exception as e:
       print(f"[ERROR OPENALEX] {e}", file=sys.stderr)
       return []




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


       cached = get_cached(doi=doi, title=title)
       if (cached and cached.get("mode") == "backward" and cached.get("references") and len(cached.get("references")) > 0):         
        print("[CACHE HIT - BACKWARD]", file=sys.stderr)
        print(json.dumps(cached, ensure_ascii=False, indent=2))
        return


       #clear_caches()


       # busca principal
       paper = search_combined(doi=doi, title=title)


       references = paper.get("references", []) or []


       if not references and doi:
           print("[DEBUG] Fallback OpenAlex...", file=sys.stderr)
           references = get_references_openalex(doi)


       # processamento
       references = deduplicate_citations(references)
       references = enrich_incomplete_citations(references)


       result = {
           "input_doi": doi or "-",
           "input_title": title or "-",
           "resolved_doi": normalize_doi(paper.get("doi")) or doi or "-",
           "data_source": paper.get("api", "-"),
           "title": paper.get("title", "-"),
           "authors": [
               {"name": a.get("name", "-")}
               for a in paper.get("authors", [])
           ] if isinstance(paper.get("authors"), list) else [],
           "year": paper.get("year", "-"),
           "venue": paper.get("venue", "-"),
           "abstract": paper.get("abstract", "-"),
           "citations_count": paper.get("citationCount", paper.get("citations_count", 0)),
           "references_count": len(references),
           "references_retrieved": len(references),
           "references": references,
           "citations": [],
           "mode": "forward",
       }


       # salva cache
       print("[SALVANDO NO CACHE]", result.get("resolved_doi"), file=sys.stderr)
       save_to_cache(
           doi=doi,
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

