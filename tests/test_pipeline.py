"""Integration tests using a small synthetic MediaWiki XML dump.

The fixture is intentionally tiny so the ingestion and analysis pipeline can
be tested without downloading the full UESP export.
"""

import bz2
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import mwparserfromhell

from src.analysis.dataset_scanner import scan_dataset
from src.analysis.page_structure import analyse_page_structure
from src.database import database
from src.ingestion.namespaces import read_namespaces
from src.ingestion.xml_reader import extract_page_data, inter_page_data, read_pages


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_wiki_dump.xml.fixture"


class SyntheticDumpPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Compress the committed XML fixture because the real dump readers
        # consume bzip2-compressed MediaWiki exports.
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.dump_path = Path(cls.temp_dir.name) / "sample_wiki_dump.xml.bz2"

        with FIXTURE_PATH.open("rb") as source_file:
            with bz2.open(cls.dump_path, "wb") as dump_file:
                dump_file.write(source_file.read())

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_xml_reader_extracts_latest_revision(self):
        pages = list(inter_page_data(self.dump_path))
        self.assertEqual(len(pages), 12)

        revision_page = next(
            page for page in pages if page["title"] == "Revision history example"
        )
        self.assertEqual(revision_page["revision_id"], "1013")
        self.assertIn("latest revision", revision_page["text"])
        self.assertNotIn("old revision", revision_page["text"])

    def test_namespace_reader_and_dataset_scanner(self):
        namespaces = read_namespaces(self.dump_path)
        self.assertEqual(namespaces[0], "")
        self.assertEqual(namespaces[6], "File")
        self.assertEqual(namespaces[14], "Category")

        results = scan_dataset(self.dump_path)
        self.assertEqual(results["total_pages"], 12)
        self.assertEqual(results["namespace_counts"][""], 6)
        self.assertEqual(results["namespace_counts"]["Category"], 1)
        self.assertEqual(results["namespace_counts"]["Unknown"], 1)

    def test_page_structure_analysis(self):
        results = analyse_page_structure(self.dump_path)
        self.assertEqual(results["total_pages"], 12)
        self.assertEqual(results["empty_pages"], 1)
        self.assertEqual(results["shortest_page"], 0)
        self.assertGreater(results["longest_page"], results["shortest_page"])
        self.assertIsNotNone(results["shortest_page_data"])
        self.assertIsNotNone(results["longest_page_data"])

    def test_year_template_examples(self):
        year_values = []
        pages_with_year = 0

        for page in inter_page_data(self.dump_path):
            wikicode = mwparserfromhell.parse(page["text"])
            templates = [
                template
                for template in wikicode.filter_templates()
                if str(template.name).strip() == "Year"
            ]

            if templates:
                pages_with_year += 1
                year_values.extend(
                    str(template.get(1).value).strip()
                    for template in templates
                    if template.has(1)
                )

        self.assertEqual(pages_with_year, 4)
        self.assertEqual(year_values.count("4E 201"), 2)
        self.assertIn("2E 582", year_values)
        self.assertIn("2E 583", year_values)
        self.assertIn("1E 420", year_values)

    def test_database_batch_import_and_duplicate_handling(self):
        database_path = Path(self.temp_dir.name) / "test_database.db"

        # Redirect database connections to a temporary database so tests
        # never alter the project's real development database.
        with patch.object(database, "DATABASE_PATH", database_path):
            database.initialise_database()
            database.migrate_database()

            dump_id = database.register_source_dump(
                self.dump_path.name,
                "2026-11-13",
            )
            namespace_map = read_namespaces(self.dump_path)

            first_insert_count = database.insert_pages_batch(
                dump_id,
                inter_page_data(self.dump_path),
                namespace_map,
                batch_size=3,
            )
            second_insert_count = database.insert_pages_batch(
                dump_id,
                inter_page_data(self.dump_path),
                namespace_map,
                batch_size=3,
            )

            self.assertEqual(first_insert_count, 12)
            self.assertEqual(second_insert_count, 0)

            connection = database.get_connection()
            try:
                page_count = connection.execute(
                    "SELECT COUNT(*) FROM pages WHERE dump_id = ?",
                    (dump_id,),
                ).fetchone()[0]
                self.assertEqual(page_count, 12)

                database.update_import_status(dump_id, "completed")
                status = connection.execute(
                    "SELECT import_status FROM source_dumps WHERE dump_id = ?",
                    (dump_id,),
                ).fetchone()[0]
                self.assertEqual(status, "completed")
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
