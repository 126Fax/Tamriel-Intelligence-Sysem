import bz2
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.database import database
from bottom_up.run_split_dump_import import import_manifest
from tools.split_mediawiki_dump import split_mediawiki_dump


MEDIAWIKI_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.10/" version="0.10" xml:lang="en">
  <siteinfo>
    <sitename>Example Wiki</sitename>
    <namespaces><namespace key="0" /></namespaces>
  </siteinfo>
  <page><title>First</title><ns>0</ns><id>1</id>
    <revision><id>11</id><text>First page</text></revision>
  </page>
  <page><title>Second</title><ns>0</ns><id>2</id>
    <revision><id>22</id><text>Second page</text></revision>
  </page>
</mediawiki>
"""


class TestSplitDumpImport(unittest.TestCase):
    def test_imports_all_parts_as_one_resumable_source_dump(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "uesp-test.xml.bz2"
            output = root / "parts"
            database_path = root / "test.db"
            source.write_bytes(bz2.compress(MEDIAWIKI_XML))

            manifest = split_mediawiki_dump(source, output, max_size_mb=0.0001)
            manifest_path = output / "manifest.json"

            with patch.object(database, "DATABASE_PATH", database_path):
                first_run = import_manifest(manifest_path, batch_size=1)
                second_run = import_manifest(manifest_path, batch_size=1)

                self.assertEqual(first_run["parts"], manifest["part_count"])
                self.assertEqual(first_run["new_pages"], 2)
                self.assertEqual(first_run["total_pages"], 2)
                self.assertEqual(second_run["new_pages"], 0)
                self.assertEqual(second_run["total_pages"], 2)
                self.assertEqual(first_run["dump_id"], second_run["dump_id"])

                connection = database.get_connection()
                try:
                    dump = connection.execute(
                        "SELECT import_status FROM source_dumps WHERE dump_id = ?",
                        (first_run["dump_id"],),
                    ).fetchone()
                    self.assertEqual(dump["import_status"], "completed")
                finally:
                    connection.close()

    def test_rejects_manifest_page_count_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "uesp-test.xml.bz2"
            output = root / "parts"
            source.write_bytes(bz2.compress(MEDIAWIKI_XML))
            split_mediawiki_dump(source, output, max_size_mb=1)

            manifest_path = output / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["total_pages"] = 99
            manifest_path.write_text(
                json.dumps(manifest),
                encoding="utf-8",
            )

            database_path = root / "test.db"
            with patch.object(database, "DATABASE_PATH", database_path):
                with self.assertRaisesRegex(RuntimeError, "does not match"):
                    import_manifest(manifest_path, batch_size=1)


if __name__ == "__main__":
    unittest.main()
