import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import services.search as search
from services.search import (
    collapse_duplicates_by_key,
    extract_opencitations_doi,
    fallback_opencitations_by_doi,
    merge_records_across_sources,
)


class ExtractOpenCitationsDoiTests(unittest.TestCase):
    def test_v1_plain_doi(self):
        self.assertEqual(
            extract_opencitations_doi("10.5753/wei.2017.3556"),
            "10.5753/wei.2017.3556",
        )

    def test_v2_multiple_identifiers(self):
        value = "omid:br/061604163724 doi:10.5753/wei.2017.3556 openalex:W3004"
        self.assertEqual(extract_opencitations_doi(value), "10.5753/wei.2017.3556")

    def test_v2_without_doi_is_discarded(self):
        # Sem DOI não há como casar com as outras fontes nem enriquecer via
        # Crossref; o registro seria só ruído com título "-".
        self.assertIsNone(extract_opencitations_doi("omid:br/0616 openalex:W3004"))

    def test_empty(self):
        self.assertIsNone(extract_opencitations_doi(None))
        self.assertIsNone(extract_opencitations_doi(""))

    def test_v1_doi_with_colons_is_kept(self):
        # DOIs no padrão SICI têm dois-pontos no sufixo. Uma versão anterior
        # deste parser rejeitava qualquer ":" no formato da v1 e os descartava.
        sici = "10.1002/(SICI)1097-4571(199806)49:8<693::AID-ASI4>3.0.CO;2-O"
        self.assertIsNotNone(extract_opencitations_doi(sici))
        self.assertIsNotNone(extract_opencitations_doi(f"omid:br/1 doi:{sici}"))


class FallbackOpenCitationsTests(unittest.TestCase):
    def test_network_failure_returns_empty_list(self):
        with mock.patch.object(search, "safe_get", return_value=None):
            self.assertEqual(fallback_opencitations_by_doi("10.1/x"), [])

    def test_unexpected_payload_returns_empty_list(self):
        with mock.patch.object(search, "safe_get", return_value={"error": "x"}):
            self.assertEqual(fallback_opencitations_by_doi("10.1/x"), [])

    def test_repeated_dois_are_collapsed(self):
        payload = [
            {"cited": "doi:10.1/a"},
            {"cited": "omid:br/1 doi:10.1/a"},
            {"cited": "doi:10.1/b"},
        ]
        with mock.patch.object(search, "safe_get", return_value=payload):
            refs = fallback_opencitations_by_doi("10.1/seed")
        self.assertEqual([r["doi"] for r in refs], ["10.1/a", "10.1/b"])
        self.assertTrue(all(r["source"] == "opencitations" for r in refs))


class OpenCitationsAddedCountTests(unittest.TestCase):
    """
    O aviso do pipeline conta as referências com source == "opencitations"
    no resultado final. Isso só é correto se, quando a mesma referência vem
    também de outra fonte, sobreviver o registro da outra fonte.
    """

    def _final(self, openalex, opencitations):
        return collapse_duplicates_by_key(
            merge_records_across_sources(
                merge_records_across_sources([], openalex),
                opencitations,
            )
        )

    def test_overlap_is_not_counted_as_added(self):
        # Caso real do 10.5753/sbie.2021.216837: as 2 referências da
        # OpenCitations já estavam entre as do OpenAlex.
        openalex = [
            {"doi": "10.5753/wei.2017.3556", "title": "Scratch", "source": "openalex"},
            {"doi": "10.5753/wit.2020.11282", "title": "Robotica", "source": "openalex"},
            {"doi": "10.5753/cbie.wie.2015.62", "title": "Jogos", "source": "openalex"},
        ]
        opencitations = [
            {"doi": "10.5753/wei.2017.3556", "title": "-", "source": "opencitations"},
            {"doi": "10.5753/wit.2020.11282", "title": "-", "source": "opencitations"},
        ]
        final = self._final(openalex, opencitations)
        self.assertEqual(len(final), 3)
        self.assertEqual(sum(r["source"] == "opencitations" for r in final), 0)

    def test_only_new_references_are_counted(self):
        openalex = [{"doi": "10.1/a", "title": "A", "source": "openalex"}]
        opencitations = [
            {"doi": "10.1/a", "title": "-", "source": "opencitations"},
            {"doi": "10.1/new", "title": "-", "source": "opencitations"},
        ]
        final = self._final(openalex, opencitations)
        self.assertEqual(len(final), 2)
        self.assertEqual(sum(r["source"] == "opencitations" for r in final), 1)


class RunForwardOpenCitationsTests(unittest.TestCase):
    """
    Regra de disparo dentro do run_forward: a OpenCitations é consultada
    quando o Semantic Scholar não entregou lista de referências (bloqueio da
    editora ou 429), e não é consultada quando entregou.
    """

    class FakeReferenceProvider:
        def __init__(self, references):
            self.references = references
            self.last_warning = None

        def get_references(self, doi=None, openalex_id=None):
            return [dict(r) for r in self.references]

    def _run(self, semantic_references, opencitations_references):
        import services.snowballing_pipeline as pipeline

        paper = {
            "doi": "10.1/seed",
            "title": "Seed",
            "citations": [],
            "references": semantic_references,
            "api": "openalex",
        }
        provider = self.FakeReferenceProvider([
            {"doi": "10.1/a", "title": "A", "source": "openalex"},
        ])
        opencitations = mock.Mock(return_value=opencitations_references)

        with mock.patch.object(pipeline, "init_db"), \
             mock.patch.object(pipeline, "get_cached", return_value=None), \
             mock.patch.object(pipeline, "search_combined", return_value=paper), \
             mock.patch.object(pipeline, "enrich_incomplete_citations", side_effect=lambda r: r), \
             mock.patch.object(pipeline, "fallback_opencitations_by_doi", opencitations), \
             mock.patch.object(pipeline.SnowballingPipeline, "_save"):
            result = pipeline.SnowballingPipeline(reference_provider=provider).run_forward(
                pipeline.SearchInput(doi="10.1/seed")
            )
        return result, opencitations

    def test_consulted_when_semantic_has_no_references(self):
        result, opencitations = self._run(
            semantic_references=[],
            opencitations_references=[
                {"doi": "10.1/a", "title": "-", "source": "opencitations"},
                {"doi": "10.1/new", "title": "-", "source": "opencitations"},
            ],
        )
        opencitations.assert_called_once_with("10.1/seed")
        self.assertEqual(result["references_retrieved"], 2)
        self.assertIn("acrescentou 1 referência ", result["warning"])

    def test_not_consulted_when_semantic_delivered_references(self):
        result, opencitations = self._run(
            semantic_references=[{"doi": "10.1/s", "title": "S", "source": "semantic"}],
            opencitations_references=[],
        )
        opencitations.assert_not_called()
        self.assertEqual(result["references_retrieved"], 2)

    def test_no_note_when_nothing_is_new(self):
        result, _ = self._run(
            semantic_references=[],
            opencitations_references=[
                {"doi": "10.1/a", "title": "-", "source": "opencitations"},
            ],
        )
        self.assertEqual(result["references_retrieved"], 1)
        self.assertNotIn("OpenCitations", result.get("warning") or "")


if __name__ == "__main__":
    unittest.main()
