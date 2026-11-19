"""Full UESP dump import workflow.

The source dump remains in data/raw and is streamed from bzip2; it is never
loaded into memory all at once.
"""

from time import perf_counter
from pathlib import Path

from src.database import database
from src.ingestion.namespaces import read_namespaces
from src.ingestion.xml_reader import inter_page_data


def get_or_register_dump(dump_path):
    """Reuse the database record for this dump, or create it once."""
    dump_path = Path(dump_path)
    connection = database.get_connection()
    try:
        row = connection.execute(
            "SELECT dump_id FROM source_dumps WHERE source_name = ?",
            (dump_path.name,),
        ).fetchone()
        if row is not None:
            return row["dump_id"]
    finally:
        connection.close()

    return database.register_source_dump(dump_path.name)


def import_dump(dump_path, batch_size=1000, progress_callback=None):
    """Stream a compressed XML dump into SQLite and return import statistics."""
    dump_path = Path(dump_path)

    if not dump_path.is_file():
        raise FileNotFoundError(f"XML dump not found: {dump_path}")
    if dump_path.suffix != ".bz2":
        raise ValueError("The full-dump importer expects a .bz2 file.")
    if batch_size < 1:
        raise ValueError("Batch size must be at least 1.")

    database.initialise_database()
    database.migrate_database()
    dump_id = get_or_register_dump(dump_path)

    started = perf_counter()
    try:
        database.update_import_status(dump_id, "importing")
        namespace_map = read_namespaces(dump_path)
        inserted_count = database.insert_pages_batch(
            dump_id,
            inter_page_data(dump_path),
            namespace_map,
            batch_size=batch_size,
            progress_callback=progress_callback,
        )
        database.update_import_status(dump_id, "completed")
    except Exception:
        database.update_import_status(dump_id, "failed")
        raise

    elapsed = perf_counter() - started
    connection = database.get_connection()
    try:
        page_count = connection.execute(
            "SELECT COUNT(*) FROM pages WHERE dump_id = ?", (dump_id,)
        ).fetchone()[0]
    finally:
        connection.close()

    return {
        "dump_id": dump_id,
        "pages_inserted": inserted_count,
        "pages_in_database": page_count,
        "elapsed_seconds": elapsed,
        "pages_per_second": page_count / elapsed if elapsed else 0,
    }
