"""Command-line entry point for importing the full local UESP dump.

Run from the repository root:
    python -m tests.test_database_import
"""

from time import perf_counter

from config.paths import get_xml_dump_path
from src.ingestion.importer import import_dump


BATCH_SIZE = 1000


def main():
    dump_path = get_xml_dump_path()
    print(f"Dump: {dump_path}")
    print(f"Batch size: {BATCH_SIZE:,}")
    print("Starting streaming import...")

    last_reported = 0
    started = perf_counter()

    def report_progress(processed, inserted):
        nonlocal last_reported
        if processed - last_reported >= BATCH_SIZE * 10:
            elapsed = perf_counter() - started
            rate = processed / elapsed if elapsed else 0
            print(
                f"Processed {processed:,} | inserted {inserted:,} | "
                f"{rate:,.0f} pages/sec"
            )
            last_reported = processed

    result = import_dump(
        dump_path,
        batch_size=BATCH_SIZE,
        progress_callback=report_progress,
    )

    print("\nImport completed.")
    print(f"New pages inserted: {result['pages_inserted']:,}")
    print(f"Pages stored for this dump: {result['pages_in_database']:,}")
    print(f"Elapsed: {result['elapsed_seconds'] / 60:.2f} minutes")
    print(f"Average rate: {result['pages_per_second']:,.0f} pages/sec")


if __name__ == "__main__":
    main()
