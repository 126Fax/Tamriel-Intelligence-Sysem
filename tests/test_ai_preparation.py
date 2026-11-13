import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.database import database
from src.processing.ai_preparation import (
    get_prepared_page,
    iter_prepared_pages,
    prepare_dump,
    prepare_page,
)


class TestPreparePage(unittest.TestCase):
    def setUp(self):
        self.page = {
            "dump_id": 1,
            "page_id": 42,
            "title": "Example",
            "namespace_id": 0,
            "namespace_name": "",
            "revision_id": 99,
            "page_text": (
                "'''Example''' is a place in [[Skyrim|the province of Skyrim]].\n"
                "== History ==\n"
                "It was founded long ago.\n"
                "{{Location\n| name = Example\n| region = Skyrim\n}}\n"
                "[[Category:Cities]]"
            ),
        }

    def test_extracts_readable_text_and_structured_content(self):
        result = prepare_page(self.page)

        self.assertEqual(result["title"], "Example")
        self.assertIn("the province of Skyrim", result["readable_text"])
        self.assertEqual(result["headings"], [{"level": 2, "text": "History"}])
        self.assertEqual(result["templates"][0]["name"], "Location")
        self.assertEqual(
            result["templates"][0]["parameters"][0]["value"],
            "Example",
        )
        self.assertEqual(
            result["links"][0]["destination"],
            "Skyrim",
        )
        self.assertEqual(
            result["links"][0]["display_text"],
            "the province of Skyrim",
        )
        self.assertEqual(result["categories"], ["Cities"])
        self.assertEqual(len(result["source_text_hash"]), 64)

    def test_does_not_modify_original_page(self):
        original_text = self.page["page_text"]

        prepare_page(self.page)

        self.assertEqual(self.page["page_text"], original_text)


class TestPrepareDump(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "test.db"
        self.database_patch = patch.object(
            database,
            "DATABASE_PATH",
            self.database_path,
        )
        self.database_patch.start()

        database.initialise_database()
        database.migrate_database()

        self.dump_id = database.register_source_dump(
            "test-dump.xml.bz2",
            "2026-11-01",
        )
        database.update_import_status(self.dump_id, "completed")

        database.insert_pages_batch(
            self.dump_id,
            [
                {
                    "page_id": 1,
                    "title": "Skyrim",
                    "namespace": 0,
                    "revision_id": 10,
                    "text": "Skyrim is a province of the Empire.",
                },
                {
                    "page_id": 2,
                    "title": "Morrowind",
                    "namespace": 0,
                    "revision_id": 20,
                    "text": "Morrowind is a province of the Empire.",
                },
            ],
            {0: ""},
            batch_size=2,
        )

    def tearDown(self):
        self.database_patch.stop()
        self.temporary_directory.cleanup()

    def test_prepares_pages_and_skips_them_on_second_run(self):
        self.assertEqual(prepare_dump(self.dump_id, batch_size=1), 2)
        self.assertEqual(prepare_dump(self.dump_id, batch_size=1), 0)

        page = get_prepared_page("Skyrim", self.dump_id)

        self.assertEqual(page["readable_text"], "Skyrim is a province of the Empire.")
        self.assertEqual(page["revision_id"], 10)

    def test_force_reprocesses_existing_pages(self):
        prepare_dump(self.dump_id)
        self.assertEqual(prepare_dump(self.dump_id, force=True), 2)

    def test_pages_can_be_read_as_a_stream(self):
        prepare_dump(self.dump_id)

        pages = list(iter_prepared_pages(self.dump_id, batch_size=1))

        self.assertEqual([page["title"] for page in pages], ["Skyrim", "Morrowind"])


if __name__ == "__main__":
    unittest.main()
