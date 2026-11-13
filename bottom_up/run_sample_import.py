"""Import the committed miniature UESP dump into an isolated sample database.

Run explicitly with:
    python -m bottom_up.run_sample_import

This script does not run when the bottom_up package or other project modules
are imported. It uses a separate SQLite file so the main database is untouched.
"""

import base64
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

from src.database import database
from src.ingestion.namespaces import read_namespaces
from src.ingestion.xml_reader import inter_page_data


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DATA_PATH = (
    PROJECT_ROOT / "data" / "samples" / "uesp_sample_5_pages.xml.bz2.base64"
)
SAMPLE_DATABASE_PATH = (
    PROJECT_ROOT / "data" / "database" / "tamriel_sample.db"
)
SOURCE_NAME = "uesp_sample_5_pages.xml.bz2"


def import_sample():
    """Import the five real UESP pages into the isolated sample database."""
    if not SAMPLE_DATA_PATH.is_file():
        raise FileNotFoundError(f"Sample data file not found: {SAMPLE_DATA_PATH}")

    compressed_xml = base64.b64decode(
        SAMPLE_DATA_PATH.read_text(encoding="ascii").strip(),
        validate=True,
    )

    SAMPLE_DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as temporary_directory:
        dump_path = Path(temporary_directory) / SOURCE_NAME
        dump_path.write_bytes(compressed_xml)

        with patch.object(database, "DATABASE_PATH", SAMPLE_DATABASE_PATH):
            database.initialise_database()
            database.migrate_database()

            connection = database.get_connection()
            try:
                existing_dump = connection.execute(
                    "SELECT dump_id FROM source_dumps WHERE source_name = ?",
                    (SOURCE_NAME,),
                ).fetchone()
            finally:
                connection.close()

            if existing_dump is None:
                dump_id = database.register_source_dump(
                    SOURCE_NAME,
                    "2026-11-01",
                )
            else:
                dump_id = existing_dump["dump_id"]

            database.update_import_status(dump_id, "importing")

            try:
                namespace_map = read_namespaces(dump_path)
                inserted_count = database.insert_pages_batch(
                    dump_id,
                    inter_page_data(dump_path),
                    namespace_map,
                    batch_size=5,
                )
                database.update_import_status(dump_id, "completed")
            except Exception:
                database.update_import_status(dump_id, "failed")
                raise

            connection = database.get_connection()
            try:
                total_count = connection.execute(
                    "SELECT COUNT(*) FROM pages WHERE dump_id = ?",
                    (dump_id,),
                ).fetchone()[0]
            finally:
                connection.close()

    print("===== UESP SAMPLE IMPORT =====")
    print(f"New pages inserted: {inserted_count}")
    print(f"Pages in sample database: {total_count}")
    print(f"Database: {SAMPLE_DATABASE_PATH.relative_to(PROJECT_ROOT)}")


def main():
    import_sample()


if __name__ == "__main__":
    main()
