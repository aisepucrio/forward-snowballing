import json
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor

import requests

from services.cache import get_cached, init_db, save_to_cache
from services.deduplication import deduplicate_citations
from services.normalize import normalize_doi
from services.search import (
    build_pages,
    enrich_incomplete_citations,
    extract_npages,
    reconstruct_abstract_from_inverted_index,
    search_combined,
)


NULL_INPUTS = {None, "", "-", "null", "None"}


class SearchInput:
    def __init__(self, doi=None, title=None):
        self.doi = normalize_doi(doi) if doi not in NULL_INPUTS else None
        self.title = title.strip() if isinstance(title, str) and title.strip() not in NULL_INPUTS else None

    @classmethod
    def from_argv(cls, argv):
        doi = argv[1].strip() if len(argv) > 1 else None
        title = argv[2].strip() if len(argv) > 2 else None
        return cls(doi=doi, title=title)

    def validate(self):
        if self.doi or self.title:
            return
        raise ValueError("DOI ou título devem ser informados")


class CitationNormalizer:
    @staticmethod
    def normalize_counts(citations):
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


class OpenAlexReferenceProvider:
    def get_references(self, doi):
        try:
            clean_doi = normalize_doi(doi)
            url = f"https://api.openalex.org/works/https://doi.org/{clean_doi}"
            resp = requests.get(url, timeout=30)
            if resp.status_code != 200:
                return []

            refs_ids = resp.json().get("referenced_works", [])
            if not refs_ids:
                return []

            references = []
            chunk_size = 50
            for index in range(0, len(refs_ids), chunk_size):
                chunk = refs_ids[index:index + chunk_size]
                batch_url = f"https://api.openalex.org/works?filter=openalex_id:{'|'.join(chunk)}"
                resp_batch = requests.get(batch_url, timeout=30)
                if resp_batch.status_code != 200:
                    continue

                references.extend(self._map_reference(ref) for ref in resp_batch.json().get("results", []))

            return references

        except Exception as exc:
            print(f"[ERROR OPENALEX] {exc}", file=sys.stderr)
            return []

    def _map_reference(self, ref):
        primary_loc = ref.get("primary_location") or {}
        source = primary_loc.get("source") or {}
        biblio = ref.get("biblio") or {}
        pages = build_pages(biblio.get("first_page"), biblio.get("last_page"))

        return {
            "title": ref.get("title") or "Untitled",
            "year": ref.get("publication_year", "-"),
            "venue": source.get("display_name", "-"),
            "abstract": reconstruct_abstract_from_inverted_index(ref.get("abstract_inverted_index")),
            "doi": normalize_doi(ref.get("doi")) if ref.get("doi") else "-",
            "authors": [
                {"name": a.get("author", {}).get("display_name", "-")}
                for a in (ref.get("authorships") or [])
            ],
            "citationCount": ref.get("cited_by_count", 0),
            "citations_count": ref.get("cited_by_count", 0),
            "open_access": ref.get("open_access", {}).get("is_oa"),
            "url": primary_loc.get("landing_page_url"),
            "keywords": [
                c.get("display_name")
                for c in ref.get("concepts", [])
                if c.get("display_name")
            ][:10],
            "language": ref.get("language"),
            "pages": pages,
            "numpages": extract_npages(pages),
            "source": "openalex",
        }


class SnowballingResultBuilder:
    def build_base(self, search_input, paper, mode):
        return {
            "input_doi": search_input.doi or "-",
            "input_title": search_input.title or "-",
            "resolved_doi": normalize_doi(paper.get("doi")) or search_input.doi or "-",
            "data_source": paper.get("api", "-"),
            "title": paper.get("title", "-"),
            "authors": [
                {"name": author.get("name", "-")}
                for author in paper.get("authors", [])
            ] if isinstance(paper.get("authors"), list) else [],
            "year": paper.get("year", "-"),
            "venue": paper.get("venue", "-"),
            "abstract": paper.get("abstract", "-"),
            "mode": mode,
            "open_access": paper.get("open_access", None),
            "url": paper.get("url", None),
            "keywords": paper.get("keywords", []),
            "language": paper.get("language", None),
            "pages": paper.get("pages", None),
            "numpages": paper.get("numpages", None),
        }

    def build_forward(self, search_input, paper, citations, references):
        result = self.build_base(search_input, paper, "forward")
        result.update({
            "citationCount": paper.get("citationCount", paper.get("citations_count", 0)),
            "citations_retrieved": len(citations),
            "citations": citations,
            "references_count": len(references),
            "references_retrieved": len(references),
        })
        return result

    def build_backward(self, search_input, paper, references):
        result = self.build_base(search_input, paper, "backward")
        result.update({
            "citations_count": paper.get("citationCount", paper.get("citations_count", 0)),
            "references_count": len(references),
            "references_retrieved": len(references),
            "references": references,
            "citations": [],
        })
        return result


class SnowballingPipeline:
    def __init__(self, reference_provider=None, result_builder=None):
        self.reference_provider = reference_provider or OpenAlexReferenceProvider()
        self.result_builder = result_builder or SnowballingResultBuilder()

    def run_forward(self, search_input):
        search_input.validate()
        init_db()

        cached = get_cached(doi=search_input.doi, title=search_input.title, mode="forward")
        if cached and cached.get("citations"):
            return cached

        with ThreadPoolExecutor(max_workers=2) as executor:
            fut_paper = executor.submit(search_combined, search_input.doi, search_input.title)
            fut_refs = executor.submit(self.reference_provider.get_references, search_input.doi) if search_input.doi else None
            paper = fut_paper.result()
            references = fut_refs.result() if fut_refs else []

        citations = CitationNormalizer.normalize_counts(
            enrich_incomplete_citations(paper.get("citations", []))
        )
        result = self.result_builder.build_forward(search_input, paper, citations, references)
        self._save(result, search_input.doi)
        return result

    def run_backward(self, search_input):
        search_input.validate()
        init_db()

        cached = get_cached(doi=search_input.doi, title=search_input.title, mode="backward")
        if cached and cached.get("references"):
            print("[CACHE HIT - BACKWARD]", file=sys.stderr)
            return cached

        paper = search_combined(doi=search_input.doi, title=search_input.title)
        references = paper.get("references", []) or []

        if not references and search_input.doi:
            print("[DEBUG] Fallback OpenAlex...", file=sys.stderr)
            references = self.reference_provider.get_references(search_input.doi)

        references = deduplicate_citations(references)
        references = enrich_incomplete_citations(references)
        references = CitationNormalizer.normalize_counts(references)

        result = self.result_builder.build_backward(search_input, paper, references)
        self._save(result, search_input.doi)
        return result

    def _save(self, result, doi):
        print("[SALVANDO NO CACHE]", result.get("resolved_doi"), file=sys.stderr)
        save_to_cache(doi=doi, title=result.get("title"), data=result)

        with open("output.json", "w", encoding="utf-8") as output_file:
            json.dump(result, output_file, ensure_ascii=False, indent=2)


def run_cli(mode):
    sys.stdout.reconfigure(encoding="utf-8")

    try:
        search_input = SearchInput.from_argv(sys.argv)
        pipeline = SnowballingPipeline()
        result = pipeline.run_forward(search_input) if mode == "forward" else pipeline.run_backward(search_input)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"error": "Erro inesperado ao processar o artigo."}, ensure_ascii=False))
        sys.exit(1)
