"""Prepare imported UESP pages for downstream AI components.

Run from the repository root:
    python -m bottom_up.run_data_preparation
    python -m bottom_up.run_data_preparation --dump-id 1
    python -m bottom_up.run_data_preparation --dump-id 1 --force
"""

import argparse

from src.database import database
from src.processing.ai_preparation import prepare_dump


def get_latest_completed_dump_id():
    connection = database.get_connection()

    try:
        row = connection.execute(
            """
            SELECT dump_id
            FROM source_dumps
            WHERE import_status = 'completed'
            ORDER BY dump_id DESC
            LIMIT 1
            """
        ).fetchone()

        return row["dump_id"] if row is not None else None

    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(
        description="Prepare imported wiki pages into AI-readable records."
    )
    parser.add_argument(
        "--dump-id",
        type=int,
        help="Source dump ID to prepare (defaults to the latest completed dump).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=250,
        help="Number of pages to process per database batch (default: 250).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocess pages even if they already have the current format.",
    )
    args = parser.parse_args()

    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1.")

    database.initialise_database()
    database.migrate_database()

    dump_id = args.dump_id or get_latest_completed_dump_id()

    if dump_id is None:
        parser.error(
            "No completed source dump was found. Import the XML dump first."
        )

    print("===== AI DATA PREPARATION =====")
    print(f"Source dump ID: {dump_id}")
    print(f"Batch size: {args.batch_size}")
    print(f"Force reprocessing: {'yes' if args.force else 'no'}")

    processed_count = prepare_dump(
        dump_id,
        batch_size=args.batch_size,
        force=args.force,
    )

    print("\nPreparation completed.")
    print(f"Pages newly prepared or updated: {processed_count:,}")
    print("Prepared records are stored in the ai_pages table.")


if __name__ == "__main__":
    main()
