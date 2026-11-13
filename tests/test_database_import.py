from time import perf_counter

from config.paths import XML_DUMP_PATH

from src.database.database import (
    get_connection,
    insert_pages_batch,
    register_source_dump,
    update_import_status,
)
from src.ingestion.namespaces import read_namespaces
from src.ingestion.xml_reader import inter_page_data


DUMP_NAME = XML_DUMP_PATH.name if XML_DUMP_PATH is not None else None
DUMP_DATE = "2026-11-01"
BATCH_SIZE = 1000


def report_progress(processed_count, inserted_count, start_time):
    elapsed_time = perf_counter() - start_time

    processing_rate = processed_count / elapsed_time

    print("\nImport progress:")
    print(f"Pages processed: {processed_count:,}")
    print(f"New pages inserted: {inserted_count:,}")
    print(f"Elapsed time: {elapsed_time / 60:.1f} minutes")
    print(f"Processing rate: {processing_rate:,.0f} pages/second")


def get_or_register_dump():
    connection = get_connection()

    try:
        result = connection.execute(
            """
            SELECT dump_id
            FROM source_dumps
            WHERE source_name = ?
            """,
            (DUMP_NAME,),
        ).fetchone()

        if result is not None:
            return result["dump_id"]

    finally:
        connection.close()

    return register_source_dump(DUMP_NAME, DUMP_DATE)




def main():

    if XML_DUMP_PATH is None:
        raise RuntimeError(
            "XML dump path is not configured. "
            "Set XML_DUMP_PATH in config/local.py."
        )

    if not XML_DUMP_PATH.exists():
        raise FileNotFoundError(f"Dump not found: {XML_DUMP_PATH}")

    dump_id = get_or_register_dump()

    print(f"Source dump ID: {dump_id}")
    print("Reading namespace information...")

    namespace_map = read_namespaces(XML_DUMP_PATH)

    try:
        update_import_status(dump_id, "importing")

        print("Starting page import...")

        start_time = perf_counter()

        inserted_count = insert_pages_batch(
            dump_id,
            inter_page_data(XML_DUMP_PATH),
            namespace_map,
            batch_size=BATCH_SIZE,
            progress_callback=lambda processed, inserted: report_progress(
                processed,
                inserted,
                start_time,
            ),
        )
        update_import_status(dump_id, "completed")

        print("\nImport completed successfully.")
        print(f"New pages inserted: {inserted_count:,}")

    except Exception:
        update_import_status(dump_id, "failed")
        raise


if __name__ == "__main__":
    main()
