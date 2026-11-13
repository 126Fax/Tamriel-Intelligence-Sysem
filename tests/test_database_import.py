from time import perf_counter

from config.paths import get_xml_dump_path
from src.database.database import (
    get_connection,
    insert_pages_batch,
    register_source_dump,
    update_import_status,
)
from src.ingestion.namespaces import read_namespaces
from src.ingestion.xml_reader import inter_page_data


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


def get_or_register_dump(dump_name):
    connection = get_connection()

    try:
        result = connection.execute(
            """
            SELECT dump_id
            FROM source_dumps
            WHERE source_name = ?
            """,
            (dump_name,),
        ).fetchone()

        if result is not None:
            return result["dump_id"]

    finally:
        connection.close()

    return register_source_dump(dump_name, DUMP_DATE)


def main():
    dump_path = get_xml_dump_path()
    dump_name = dump_path.name
    dump_id = get_or_register_dump(dump_name)

    print(f"Source dump ID: {dump_id}")
    print("Reading namespace information...")

    namespace_map = read_namespaces(dump_path)

    try:
        update_import_status(dump_id, "importing")

        print("Starting page import...")

        start_time = perf_counter()

        inserted_count = insert_pages_batch(
            dump_id,
            inter_page_data(dump_path),
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
