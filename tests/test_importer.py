"""Correctness and repeatability tests for full-dump ingestion."""

import bz2
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.database import database
from src.ingestion.importer import import_dump
from config import paths


FIXTURE = Path(__file__).parent / "fixtures" / "sample_wiki_dump.xml.fixture"


class FullDumpImporterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.dump_path = root / "tiny_uesp.xml.bz2"
        self.database_path = root / "test.db"

        with FIXTURE.open("rb") as source:
            with bz2.open(self.dump_path, "wb") as target:
                target.write(source.read())

        self.database_patch = patch.object(
            database, "DATABASE_PATH", self.database_path
        )
        self.database_patch.start()
        database.initialise_database()
        database.migrate_database()

    def tearDown(self):
        self.database_patch.stop()
        self.temp_dir.cleanup()

    def test_import_reads_all_fixture_pages(self):
        result = import_dump(self.dump_path, batch_size=3)

        self.assertEqual(result["pages_inserted"], 12)
        self.assertEqual(result["pages_in_database"], 12)
        self.assertGreater(result["elapsed_seconds"], 0)

        connection = database.get_connection()
        try:
            status = connection.execute(
                "SELECT import_status FROM source_dumps WHERE dump_id = ?",
                (result["dump_id"],),
            ).fetchone()[0]
            self.assertEqual(status, "completed")
        finally:
            connection.close()

    def test_reimport_does_not_duplicate_pages_or_dump_records(self):
        first = import_dump(self.dump_path, batch_size=4)
        second = import_dump(self.dump_path, batch_size=5)

        self.assertEqual(first["dump_id"], second["dump_id"])
        self.assertEqual(first["pages_inserted"], 12)
        self.assertEqual(second["pages_inserted"], 0)
        self.assertEqual(second["pages_in_database"], 12)

        connection = database.get_connection()
        try:
            dump_count = connection.execute(
                "SELECT COUNT(*) FROM source_dumps"
            ).fetchone()[0]
            self.assertEqual(dump_count, 1)
        finally:
            connection.close()

    def test_invalid_batch_size_is_rejected(self):
        with self.assertRaises(ValueError):
            import_dump(self.dump_path, batch_size=0)

    def test_raw_folder_is_used_when_no_local_override_exists(self):
        raw_dir = Path(self.temp_dir.name) / "raw"
        raw_dir.mkdir()
        raw_dump = raw_dir / "uesp.xml.bz2"
        raw_dump.write_bytes(b"placeholder")

        with (
            patch.object(paths, "XML_DUMP_PATH", None),
            patch.object(paths, "RAW_DATA_DIR", raw_dir),
        ):
            self.assertEqual(paths.get_xml_dump_path(), raw_dump)

    def test_missing_local_override_falls_back_to_raw_folder(self):
        raw_dir = Path(self.temp_dir.name) / "raw"
        raw_dir.mkdir()
        raw_dump = raw_dir / "uesp.xml.bz2"
        raw_dump.write_bytes(b"placeholder")

        with (
            patch.object(paths, "XML_DUMP_PATH", "/home/fax/Downloads/missing.xml.bz2"),
            patch.object(paths, "RAW_DATA_DIR", raw_dir),
        ):
            self.assertEqual(paths.get_xml_dump_path(), raw_dump)

    def test_multiple_raw_dumps_require_an_explicit_choice(self):
        raw_dir = Path(self.temp_dir.name) / "raw"
        raw_dir.mkdir()
        (raw_dir / "one.xml.bz2").touch()
        (raw_dir / "two.xml.bz2").touch()

        with (
            patch.object(paths, "XML_DUMP_PATH", None),
            patch.object(paths, "RAW_DATA_DIR", raw_dir),
        ):
            with self.assertRaises(RuntimeError):
                paths.get_xml_dump_path()


if __name__ == "__main__":
    unittest.main()
