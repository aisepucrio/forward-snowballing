import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services import multi_seed
from services.multi_seed import MultiSeedSnowballing, parse_seeds
from services.search import ArticleNotFoundError


def paper(doi, title, citations=(), references=(), partial=False):
    return {
        "resolved_doi": doi,
        "title": title,
        "authors": [{"name": "Author"}],
        "year": 2020,
        "partial_result": partial,
        "citations": [dict(c) for c in citations],
        "references": [dict(r) for r in references],
    }


class FakePipeline:
    """Responde por DOI ou título; um valor Exception é levantado."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def run_forward(self, search_input):
        key = search_input.doi or search_input.title
        self.calls.append(key)
        response = self.responses[key]
        if isinstance(response, Exception):
            raise response
        return response


class ParseSeedsTests(unittest.TestCase):
    def test_accepts_mixed_doi_and_title(self):
        seeds = parse_seeds([
            {"type": "doi", "value": " https://doi.org/10.1000/ABC "},
            {"type": "title", "value": "  A Title "},
        ])
        self.assertEqual(seeds[0]["input_type"], "doi")
        self.assertEqual(seeds[0]["input_value"], "10.1000/abc")
        self.assertEqual(seeds[1], {"index": 1, "input_type": "title", "input_value": "A Title"})

    def test_accepts_doi_link_variants(self):
        # A interface aceita qualquer link doi.org; normalize_doi sozinho
        # deixaria "https://dx.10.1000/abc" e a busca inteira cairia.
        for raw in ("https://dx.doi.org/10.1000/ABC", "http://doi.org/10.1000/abc", "doi:10.1000/abc"):
            with self.subTest(raw=raw):
                seeds = parse_seeds([{"type": "doi", "value": raw}])
                self.assertEqual(seeds[0]["input_value"], "10.1000/abc")

    def test_rejects_invalid_input(self):
        invalid = [
            None,
            [],
            [{"type": "doi", "value": "not a doi"}],
            [{"type": "isbn", "value": "123"}],
            [{"type": "title", "value": "   "}],
            ["10.1000/abc"],
        ]
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_seeds(raw)

    def test_respects_max_seeds(self):
        with mock.patch.dict(os.environ, {"SNOWMAP_MAX_SEEDS": "2"}):
            seeds = [{"type": "title", "value": f"Paper {i}"} for i in range(3)]
            with self.assertRaises(ValueError):
                parse_seeds(seeds)
            self.assertEqual(len(parse_seeds(seeds[:2])), 2)


class MultiSeedRunTests(unittest.TestCase):
    def run_multi(self, responses, raw_seeds):
        pipeline = FakePipeline(responses)
        with mock.patch.object(multi_seed, "_progress"):
            result = MultiSeedSnowballing(pipeline=pipeline).run(raw_seeds)
        return result, pipeline

    def test_union_dedups_across_seeds_and_tracks_origin(self):
        shared = {"title": "Shared", "doi": "10.1000/shared"}
        responses = {
            "10.1000/a": paper("10.1000/a", "Seed A", citations=[shared, {"title": "Only A", "doi": "10.1000/only-a"}],
                            references=[{"title": "Ref A", "doi": "10.1000/ref-a"}]),
            "10.1000/b": paper("10.1000/b", "Seed B", citations=[dict(shared, abstract="filled by B"),
                                                          {"title": "Only B no doi"}]),
        }
        result, _ = self.run_multi(responses, [
            {"type": "doi", "value": "10.1000/a"},
            {"type": "doi", "value": "10.1000/b"},
        ])

        self.assertEqual(result["citations_retrieved"], 3)
        self.assertEqual(result["references_retrieved"], 1)
        by_key = {c["study_key"]: c for c in result["citations"]}
        self.assertEqual(by_key["doi:10.1000/shared"]["found_via_seeds"], [0, 1])
        self.assertEqual(by_key["doi:10.1000/shared"]["abstract"], "filled by B")
        self.assertEqual(by_key["title:only b no doi"]["found_via_seeds"], [1])

        seed_a, seed_b = result["seeds"]
        self.assertEqual(seed_a["citation_keys"], ["doi:10.1000/shared", "doi:10.1000/only-a"])
        self.assertEqual(seed_b["citation_keys"], ["doi:10.1000/shared", "title:only b no doi"])
        self.assertEqual(seed_b["reference_keys"], [])
        self.assertEqual((seed_a["citations_retrieved"], seed_a["references_retrieved"]), (2, 1))

    def test_failed_seed_does_not_abort_the_others(self):
        responses = {
            "10.1000/a": paper("10.1000/a", "Seed A", citations=[{"title": "C", "doi": "10.1000/c"}]),
            "10.1000/missing": ArticleNotFoundError("Artigo não encontrado"),
            "Broken title": RuntimeError("boom"),
        }
        with mock.patch("traceback.print_exc"):
            result, pipeline = self.run_multi(responses, [
                {"type": "doi", "value": "10.1000/missing"},
                {"type": "title", "value": "Broken title"},
                {"type": "doi", "value": "10.1000/a"},
            ])

        self.assertEqual(len(pipeline.calls), 3)
        statuses = [s["status"] for s in result["seeds"]]
        self.assertEqual(statuses, ["not_found", "error", "ok"])
        self.assertEqual(result["seeds_failed"], 2)
        self.assertEqual(result["seeds_succeeded"], 1)
        self.assertTrue(result["partial_result"])
        self.assertEqual(result["citations_retrieved"], 1)

    def test_all_seeds_failing_raises(self):
        responses = {"10.1000/x": ArticleNotFoundError("x"), "10.1000/y": ArticleNotFoundError("y")}
        with self.assertRaises(ValueError):
            self.run_multi(responses, [
                {"type": "doi", "value": "10.1000/x"},
                {"type": "doi", "value": "10.1000/y"},
            ])

    def test_duplicate_seeds_before_and_after_resolution(self):
        responses = {
            "10.1000/a": paper("10.1000/a", "Seed A", citations=[{"title": "C", "doi": "10.1000/c"}]),
            "seed a": paper("10.1000/a", "Seed A"),
        }
        result, pipeline = self.run_multi(responses, [
            {"type": "doi", "value": "10.1000/a"},
            {"type": "doi", "value": "https://doi.org/10.1000/A"},
            {"type": "title", "value": "seed a"},
        ])

        # A repetição literal nem chega a buscar; o título só se revela igual
        # depois de resolvido.
        self.assertEqual(pipeline.calls, ["10.1000/a", "seed a"])
        statuses = [(s["status"], s["duplicate_of"]) for s in result["seeds"]]
        self.assertEqual(statuses, [("ok", None), ("duplicate", 0), ("duplicate", 0)])
        self.assertEqual(result["seeds_failed"], 0)

    def test_seed_found_in_another_seed_list_is_removed(self):
        responses = {
            "10.1000/a": paper("10.1000/a", "Seed A", references=[{"title": "Seed B", "doi": "10.1000/b"},
                                                             {"title": "R", "doi": "10.1000/r"}]),
            "10.1000/b": paper("10.1000/b", "Seed B", citations=[{"title": "Seed A", "doi": "10.1000/a"}]),
        }
        result, _ = self.run_multi(responses, [
            {"type": "doi", "value": "10.1000/a"},
            {"type": "doi", "value": "10.1000/b"},
        ])

        self.assertEqual([r["doi"] for r in result["references"]], ["10.1000/r"])
        self.assertEqual(result["citations"], [])
        self.assertEqual(result["seed_hits_removed"], 2)

    def test_seed_with_partial_sources_is_just_ok(self):
        responses = {"10.1000/a": paper("10.1000/a", "Seed A", partial=True)}
        result, _ = self.run_multi(responses, [{"type": "doi", "value": "10.1000/a"}])
        self.assertEqual(result["seeds"][0]["status"], "ok")
        self.assertEqual(result["seeds_failed"], 0)
        self.assertFalse(result["partial_result"])


class PersistenceFlagsTests(unittest.TestCase):
    def test_cache_and_database_are_off_by_default(self):
        from services import settings
        env = {k: v for k, v in os.environ.items()
               if k not in ("SNOWMAP_ENABLE_CACHE", "SNOWMAP_ENABLE_DB", "SNOWMAP_DISABLE_CACHE")}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertFalse(settings.cache_enabled())
            self.assertFalse(settings.database_enabled())
        with mock.patch.dict(os.environ, {**env, "SNOWMAP_ENABLE_CACHE": "1", "SNOWMAP_ENABLE_DB": "true"}, clear=True):
            self.assertTrue(settings.cache_enabled())
            self.assertTrue(settings.database_enabled())
        with mock.patch.dict(os.environ, {**env, "SNOWMAP_ENABLE_CACHE": "1", "SNOWMAP_DISABLE_CACHE": "1"}, clear=True):
            self.assertFalse(settings.cache_enabled())

    def test_pipeline_skips_cache_and_database_when_disabled(self):
        from services import snowballing_pipeline as pipeline
        result = {"title": "T", "citations": [], "references": []}
        with mock.patch.object(pipeline, "cache_enabled", return_value=False), \
             mock.patch.object(pipeline, "database_enabled", return_value=False), \
             mock.patch.object(pipeline, "save_to_cache") as save_cache, \
             mock.patch.object(pipeline, "_load_database_layer") as load_db:
            pipeline.SnowballingPipeline(write_debug_output=False)._save(result, "10.1000/a")

        save_cache.assert_not_called()
        load_db.assert_not_called()
        self.assertIsNone(result["search_id"])
        self.assertEqual(result["paper_id_map"], {})


class SearchCombinedNotFoundTests(unittest.TestCase):
    def test_raises_instead_of_exiting(self):
        from services import search
        with mock.patch.object(search, "fallback_via_requests", return_value=None), \
             mock.patch.object(search, "fallback_openalex_by_doi", return_value=None), \
             mock.patch.object(search, "fallback_crossref", return_value=None), \
             mock.patch.object(search, "cache_enabled", return_value=False):
            with self.assertRaises(ArticleNotFoundError):
                search.search_combined(doi="10.1000/none")


if __name__ == "__main__":
    unittest.main()
