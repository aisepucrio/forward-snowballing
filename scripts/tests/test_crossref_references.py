import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import services.search as search
import services.snowballing_pipeline as pipeline
from services.search import (
    crossref_reference_to_record,
    fetch_crossref_references,
    is_crossref_reference_fragment,
    merge_records_across_sources,
)
from services.snowballing_pipeline import SearchInput, SnowballingPipeline


class CrossrefFragmentTests(unittest.TestCase):
    def test_author_list_only_is_fragment(self):
        ref = {"key": "b10", "unstructured": "Ashouri, A.H., Killian, W., Silvano, C.,"}
        self.assertTrue(is_crossref_reference_fragment(ref))

    def test_unstructured_with_year_is_kept(self):
        ref = {"unstructured": "Alipourfard, O., 2017. Cherrypick: Adaptively unearthing..."}
        self.assertFalse(is_crossref_reference_fragment(ref))

    def test_lettered_year_and_missing_year_are_kept(self):
        # Versão anterior descartava os dois: "1988a" não casava com \bANO\b.
        self.assertFalse(is_crossref_reference_fragment(
            {"unstructured": "Lynch, D. V., and Steponkus, P. L. (1988b).Cryobiology (in press)."}
        ))
        self.assertFalse(is_crossref_reference_fragment(
            {"unstructured": "J. Franch Gutiérrez, Bridging the gap among academics, pp. 267–273."}
        ))

    def test_structured_entries_are_kept(self):
        self.assertFalse(is_crossref_reference_fragment({"DOI": "10.1/a"}))
        self.assertFalse(is_crossref_reference_fragment({"series-title": "Software Creativity 2.0"}))


class CrossrefRecordTests(unittest.TestCase):
    def test_article_in_proceedings(self):
        record = crossref_reference_to_record({
            "article-title": "Systematic mapping studies in software engineering",
            "series-title": "EASE 2008",
            "author": "Petersen",
            "year": "2008",
        })
        self.assertEqual(record["title"], "Systematic mapping studies in software engineering")
        self.assertEqual(record["venue"], "EASE 2008")
        self.assertEqual(record["authors"], [{"name": "Petersen"}])
        self.assertEqual(record["doi"], "-")

    def test_book_without_article_title(self):
        record = crossref_reference_to_record({"series-title": "Software Creativity 2.0", "year": "2006"})
        self.assertEqual(record["title"], "Software Creativity 2.0")
        self.assertEqual(record["venue"], "-")

    def test_book_chapter_does_not_take_the_book_title(self):
        record = crossref_reference_to_record({
            "volume-title": "Membranes, Metabolism and Dry Organisms",
            "first-page": "188",
            "year": "1986",
            "unstructured": "Crowe, J. H. (1986a). InMembranes, Metabolism and Dry Organisms, Chap. 11",
        })
        self.assertEqual(record["title"], "-")
        self.assertEqual(record["venue"], "Membranes, Metabolism and Dry Organisms")

    def test_unstructured_only_keeps_text_out_of_title(self):
        record = crossref_reference_to_record({"unstructured": "Franks, F. (1985). Biophysics..."})
        self.assertEqual(record["title"], "-")
        self.assertEqual(record["unstructured"], "Franks, F. (1985). Biophysics...")

    def test_fetch_drops_fragments_and_handles_failure(self):
        payload = {"message": {"reference": [
            {"DOI": "10.1/A", "article-title": "A"},
            {"unstructured": "Kolesnikov, S., Siegmund, N.,"},
        ]}}
        with mock.patch.object(search, "safe_get", return_value=payload):
            records = fetch_crossref_references("10.1/seed")
        self.assertEqual([r["doi"] for r in records], ["10.1/a"])
        with mock.patch.object(search, "safe_get", return_value=None):
            self.assertEqual(fetch_crossref_references("10.1/seed"), [])


class FillOnlyMergeTests(unittest.TestCase):
    def test_secondary_fills_but_does_not_add(self):
        primary = [{"doi": "10.1/a", "title": "-", "source": "crossref"}]
        secondary = [
            {"doi": "10.1/a", "title": "Paper A", "abstract": "x", "source": "semantic"},
            {"doi": "10.1/b", "title": "Only in Semantic", "source": "semantic"},
        ]
        merged = merge_records_across_sources(primary, secondary, match_titles=True, keep_unmatched=False)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["title"], "Paper A")
        self.assertEqual(merged[0]["source"], "crossref")

    def test_title_found_inside_citation_text(self):
        primary = [{
            "doi": "-",
            "title": "-",
            "unstructured": "Wolfe, J. (1987). Freezing injury in plant membranes. Aust. J. Plant Physiol. 14",
        }]
        secondary = [{"doi": "10.1/w", "title": "Freezing injury in plant membranes"}]
        merged = merge_records_across_sources(primary, secondary, match_titles=True, keep_unmatched=False)
        self.assertEqual(merged[0]["doi"], "10.1/w")
        self.assertEqual(merged[0]["title"], "Freezing injury in plant membranes")

    def test_book_title_in_several_chapters_is_ambiguous(self):
        book = "Membranes, Metabolism and Dry Organisms"
        primary = [
            {"doi": "-", "title": "-", "unstructured": f"Crowe, J. H. (1986a). In {book} (Leopold, ed.), Chap. 11"},
            {"doi": "-", "title": "-", "unstructured": f"Wolfe, J. (1986b). In {book} (Leopold, ed.), Chap. 17"},
        ]
        merged = merge_records_across_sources(
            primary, [{"doi": "10.1/book", "title": book}], match_titles=True, keep_unmatched=False
        )
        self.assertEqual([r["doi"] for r in merged], ["-", "-"])


class PipelineCrossrefBaseTests(unittest.TestCase):
    def run_pipeline(self, crossref, semantic, openalex):
        provider = mock.Mock(last_warning=None)
        provider.get_references.return_value = openalex
        paper = {"doi": "10.1/seed", "title": "Seed", "references": semantic, "citations": []}
        with mock.patch.object(pipeline, "cache_enabled", return_value=False), \
             mock.patch.object(pipeline, "search_combined", return_value=paper), \
             mock.patch.object(pipeline, "fetch_crossref_references", return_value=crossref), \
             mock.patch.object(pipeline, "fallback_opencitations_by_doi", return_value=[]), \
             mock.patch.object(pipeline, "enrich_incomplete_citations", side_effect=lambda r: r):
            runner = SnowballingPipeline(reference_provider=provider, write_debug_output=False)
            runner._save = lambda result, doi: None
            return runner.run_forward(SearchInput(doi="10.1/seed"))["references"]

    def test_complete_crossref_list_defines_the_set(self):
        crossref = [
            {"doi": "10.1/a", "title": "A paper title long enough", "source": "crossref"},
            {"doi": "-", "title": "-", "unstructured": "Franks, F. (1985). A book.", "source": "crossref"},
        ]
        semantic = [
            {"paperId": "p1", "doi": "10.1/a", "title": "A paper title long enough", "year": 2000},
            {"paperId": "p2", "doi": "10.1/preprint-only", "title": "Only in the preprint", "year": 2019},
        ]
        refs = self.run_pipeline(crossref, semantic, [])
        self.assertEqual(len(refs), 2)
        self.assertEqual(refs[1]["title"], "Franks, F. (1985). A book.")

    def test_incomplete_crossref_list_is_ignored(self):
        crossref = [{"doi": "10.1/a", "title": "A", "source": "crossref"}]
        semantic = [
            {"paperId": f"p{i}", "doi": f"10.1/{i}", "title": f"Semantic reference number {i}", "year": 2000}
            for i in range(10)
        ]
        refs = self.run_pipeline(crossref, semantic, [])
        self.assertEqual(len(refs), 10)


if __name__ == "__main__":
    unittest.main()
