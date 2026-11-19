"""Tests for full-dump analysis and evidence-backed knowledge export."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.database import database
from bottom_up.full_pipeline import (
    analyse_dump, build_knowledge_base, extract_candidate_facts,
)


class FullPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "pipeline.db"
        self.patch = patch.object(database, "DATABASE_PATH", self.db_path)
        self.patch.start()
        database.initialise_database()
        database.migrate_database()
        self.dump_id = database.register_source_dump("fixture.xml.bz2")
        self.pages = [
            {
                "page_id": "1", "title": "Skyrim", "namespace": "0",
                "revision_id": "10",
                "text": "'''Skyrim''' is a province of the [[Empire]]. "
                        "It contains [[Whiterun|Whiterun Hold]].",
            },
            {
                "page_id": "2", "title": "Dragons",
                "namespace": "0", "revision_id": "20",
                "text": "Dragons live in [[Skyrim]].",
            },
            {
                "page_id": "3", "title": "Lore:Bravil", "namespace": "0",
                "revision_id": "30",
                "text": (
                    "{{Lore Place Summary\n"
                    "|continent=Tamriel\n"
                    "|province=Cyrodiil\n"
                    "|region=Nibenay Valley\n"
                    "|settlement=Bravil\n"
                    "}}"
                ),
            },
        ]
        database.insert_pages_batch(
            self.dump_id, self.pages, {0: ""}, batch_size=2
        )

    def tearDown(self):
        self.patch.stop()
        self.temp_dir.cleanup()

    def test_explicit_relationships_keep_source_evidence(self):
        facts = extract_candidate_facts(
            "Skyrim is a province of the Empire.", 1, "Skyrim"
        )
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["relationship"], "province")
        self.assertEqual(facts[0]["object"], "Empire")
        self.assertIn("Skyrim is a province", facts[0]["evidence"])
        self.assertEqual(facts[0]["source_page_id"], 1)

    def test_full_analysis_persists_page_structure_links_and_facts(self):
        result = analyse_dump(self.dump_id, batch_size=1)
        self.assertEqual(result["pages_analysed"], 3)
        self.assertGreaterEqual(result["wiki_links_extracted"], 2)
        self.assertGreaterEqual(result["candidate_facts_extracted"], 2)

        connection = database.get_connection()
        try:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM page_analysis"
            ).fetchone()[0], 3)
            self.assertGreaterEqual(connection.execute(
                "SELECT COUNT(*) FROM page_links"
            ).fetchone()[0], 2)
            self.assertGreaterEqual(connection.execute(
                "SELECT COUNT(*) FROM candidate_facts"
            ).fetchone()[0], 2)
        finally:
            connection.close()

    def test_analysis_rerun_rebuilds_without_duplicate_rows(self):
        analyse_dump(self.dump_id)
        first = analyse_dump(self.dump_id)
        self.assertEqual(first["pages_analysed"], 3)
        connection = database.get_connection()
        try:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM page_analysis"
            ).fetchone()[0], 3)
        finally:
            connection.close()

    def test_knowledge_base_export_contains_provenance_and_is_json(self):
        analyse_dump(self.dump_id)
        output = Path(self.temp_dir.name) / "knowledge_base.json"
        result = build_knowledge_base(self.dump_id, output)
        facts = json.loads(output.read_text(encoding="utf-8"))
        self.assertGreaterEqual(result["knowledge_facts"], 2)
        self.assertTrue(all(
            {"subject", "relationship", "object", "source_page",
             "source_page_id", "evidence", "confidence"} <= fact.keys()
            for fact in facts
        ))

    def test_unknown_dump_and_invalid_batch_size_are_rejected(self):
        with self.assertRaises(ValueError):
            analyse_dump(9999)
        with self.assertRaises(ValueError):
            analyse_dump(self.dump_id, batch_size=0)


if __name__ == "__main__":
    unittest.main()
