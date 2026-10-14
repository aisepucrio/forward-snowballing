import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.search import merge_records_across_sources, merge_semantic_with_openalex


class SearchPriorityTests(unittest.TestCase):
    def test_merge_prioritizes_semantic_and_deduplicates_citations(self):
        semantic = {
            "title": "Semantic title",
            "year": 2022,
            "venue": "Semantic venue",
            "abstract": "semantic abstract",
            "doi": "10.1000/semantic",
            "authors": [{"name": "Alice Semantic"}],
            "citationCount": 5,
            "citations": [
                {"title": "Same citation", "doi": "10.1000/same", "citationCount": 2},
                {"title": "Semantic only", "doi": "10.1000/semantic-only", "citationCount": 1},
            ],
            "api": "semantic",
        }

        openalex = {
            "title": "OpenAlex title",
            "year": 2020,
            "venue": "OpenAlex venue",
            "abstract": "openalex abstract",
            "doi": "10.1000/openalex",
            "authors": [{"name": "Bob OpenAlex"}],
            "citationCount": 7,
            "citations": [
                {"title": "Same citation", "doi": "10.1000/same", "citationCount": 2},
                {"title": "OpenAlex only", "doi": "10.1000/openalex-only", "citationCount": 3},
            ],
            "api": "openalex",
        }

        merged = merge_semantic_with_openalex(semantic, openalex)

        self.assertEqual(merged["title"], "Semantic title")
        self.assertEqual(merged["year"], 2022)
        self.assertEqual(merged["venue"], "Semantic venue")
        self.assertEqual(merged["api"], "semantic+openalex")
        self.assertTrue(all(item["source"] == "semantic" for item in merged["citations"][:2]))
        self.assertTrue(merged["citations"][-1]["source"] == "openalex")
        self.assertEqual(len(merged["citations"]), 3)
        self.assertEqual(
            {c["title"] for c in merged["citations"]},
            {"Same citation", "Semantic only", "OpenAlex only"},
        )

    def test_merge_prioritizes_semantic_references_and_deduplicates(self):
        semantic = {
            "title": "Semantic title",
            "doi": "10.1000/semantic",
            "references": [
                {"title": "Reference A", "doi": "10.1000/ref-a", "citationCount": 4},
                {"title": "Reference B", "doi": "10.1000/ref-b", "citationCount": 2},
            ],
            "api": "semantic",
        }

        openalex = {
            "title": "OpenAlex title",
            "doi": "10.1000/openalex",
            "references": [
                {"title": "Reference A", "doi": "10.1000/ref-a", "citationCount": 4},
                {"title": "Reference C", "doi": "10.1000/ref-c", "citationCount": 1},
            ],
            "api": "openalex",
            "openalex_id": "https://openalex.org/W123",
        }

        merged = merge_semantic_with_openalex(semantic, openalex)

        self.assertEqual(len(merged["references"]), 3)
        self.assertEqual(
            {r["title"] for r in merged["references"]},
            {"Reference A", "Reference B", "Reference C"},
        )

    def test_deduplicates_only_across_sources(self):
        merged = merge_records_across_sources(
            [
                {"title": "Same article", "doi": "10.1000/same"},
                {"title": "Semantic only", "doi": "10.1000/semantic-only"},
            ],
            [
                {"title": "Same article", "doi": "10.1000/same"},
                {"title": "Same article", "doi": "10.1000/same"},
                {"title": "OpenAlex only", "doi": "10.1000/openalex-only"},
            ],
        )

        self.assertEqual(
            [record["title"] for record in merged],
            ["Same article", "Semantic only", "OpenAlex only"],
        )


if __name__ == "__main__":
    unittest.main()
