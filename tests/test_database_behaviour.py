"""Database validation, migration, search and referential-integrity tests."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.database import database


class DatabaseBehaviourTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "test.db"
        self.database_patch = patch.object(database, "DATABASE_PATH", self.database_path)
        self.database_patch.start()
        database.initialise_database()
        database.migrate_database()
        self.dump_id = database.register_source_dump("fixture.xml.bz2")

    def tearDown(self):
        self.database_patch.stop()
        self.temp_dir.cleanup()

    def test_initialisation_and_migration_are_repeatable(self):
        database.initialise_database()
        database.migrate_database()
        connection = database.get_connection()
        try:
            tables = {
                row["name"] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            self.assertTrue({"source_dumps", "pages"} <= tables)
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(pages)")
            }
            self.assertIn("page_text", columns)
        finally:
            connection.close()

    def test_import_status_accepts_valid_values_and_rejects_invalid(self):
        for status in ("pending", "importing", "completed", "failed"):
            database.update_import_status(self.dump_id, status)
        with self.assertRaises(ValueError):
            database.update_import_status(self.dump_id, "unknown")
        with self.assertRaises(ValueError):
            database.update_import_status(99999, "completed")

    def test_search_rejects_blank_terms_and_nonpositive_limits(self):
        with self.assertRaises(ValueError):
            database.search_pages("   ")
        with self.assertRaises(ValueError):
            database.search_pages("Skyrim", limit=0)

    def test_search_and_exact_title_lookup_return_inserted_page(self):
        page = {
            "page_id": "1",
            "title": "Skyrim",
            "namespace": "0",
            "revision_id": "10",
            "text": "Skyrim is a province of the Empire.",
        }
        database.insert_page(self.dump_id, page, "")
        result = database.get_page_by_title("Skyrim")
        self.assertEqual(result["page_text"], page["text"])
        matches = database.search_pages("province")
        self.assertEqual([row["title"] for row in matches], ["Skyrim"])

    def test_page_insert_is_idempotent_for_same_dump_and_page(self):
        page = {
            "page_id": "1",
            "title": "Skyrim",
            "namespace": "0",
            "revision_id": "10",
            "text": "Skyrim.",
        }
        database.insert_page(self.dump_id, page, "")
        database.insert_page(self.dump_id, page, "")
        connection = database.get_connection()
        try:
            count = connection.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
            self.assertEqual(count, 1)
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
