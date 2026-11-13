"""Import every part in a splitter manifest into one source-dump record.

Run from the repository root:
    python -m bottom_up.run_split_dump_import --manifest data/processed/<dump>/manifest.json

The import can be resumed after interruption. Pages already stored for the
same source dump are ignored by the database's (dump_id, page_id) primary key.
"""

import argparse
import json
from pathlib import Path

from src.database import database
from src.ingestion.namespaces import read_namespaces
from src.ingestion.xml_reader import inter_page_data


def load_manifest(manifest_path):
    """Load a manifest and validate every part path before touching the DB."""
    manifest_path = Path(manifest_path).expanduser().resolve()

    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    parts = manifest.get("parts")

    if not isinstance(parts, list) or not parts:
        raise ValueError("Manifest does not contain any parts.")

    declared_part_count = manifest.get("part_count")
    if declared_part_count is not None and declared_part_count != len(parts):
        raise ValueError(
            f"Manifest declares {declared_part_count} parts but lists {len(parts)}."
        )

    part_paths = []
    manifest_directory = manifest_path.parent.resolve()

    for part in parts:
        filename = part.get("file") if isinstance(part, dict) else None
        if not filename:
            raise ValueError("Manifest contains a part without a file name.")

        part_path = (manifest_directory / filename).resolve()
        if not part_path.is_relative_to(manifest_directory):
            raise ValueError(f"Part path escapes manifest directory: {filename}")
        if not part_path.is_file():
            raise FileNotFoundError(f"Dump part not found: {part_path}")

        part_paths.append(part_path)

    return manifest_path, manifest, part_paths


def get_or_create_dump(source_name, dump_date=None):
    """Reuse the source record when resuming the same original dump."""
    connection = database.get_connection()
    try:
        row = connection.execute(
            """
            SELECT dump_id
            FROM source_dumps
            WHERE source_name = ?
            ORDER BY dump_id DESC
            LIMIT 1
            """,
            (source_name,),
        ).fetchone()
    finally:
        connection.close()

    if row is not None:
        return row["dump_id"]

    return database.register_source_dump(source_name, dump_date)


def count_dump_pages(dump_id):
    connection = database.get_connection()
    try:
        return connection.execute(
            "SELECT COUNT(*) FROM pages WHERE dump_id = ?",
            (dump_id,),
        ).fetchone()[0]
    finally:
        connection.close()


def import_manifest(manifest_path, batch_size=1000, dump_date=None):
    """Import all parts into one dump record and verify the final page count."""
    if batch_size < 1:
        raise ValueError("Batch size must be at least 1.")

    manifest_path, manifest, part_paths = load_manifest(manifest_path)
    source_name = manifest.get("source_file") or manifest_path.name

    database.initialise_database()
    database.migrate_database()
    dump_id = get_or_create_dump(source_name, dump_date)

    database.update_import_status(dump_id, "importing")
    total_inserted = 0

    try:
        for index, part_path in enumerate(part_paths, start=1):
            print(f"[{index}/{len(part_paths)}] Importing {part_path.name} ...")
            namespace_map = read_namespaces(part_path)
            inserted = database.insert_pages_batch(
                dump_id,
                inter_page_data(part_path),
                namespace_map,
                batch_size=batch_size,
            )
            total_inserted += inserted
            print(f"    New pages inserted: {inserted:,}")

        total_pages = count_dump_pages(dump_id)
        expected_pages = manifest.get("total_pages")

        if expected_pages is not None and total_pages != expected_pages:
            raise RuntimeError(
                "Imported page count does not match the splitter manifest: "
                f"expected {expected_pages:,}, found {total_pages:,}."
            )

        database.update_import_status(dump_id, "completed")

    except Exception:
        database.update_import_status(dump_id, "failed")
        raise

    return {
        "dump_id": dump_id,
        "source_name": source_name,
        "parts": len(part_paths),
        "new_pages": total_inserted,
        "total_pages": total_pages,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Import all page-aligned XML parts as one source dump."
    )
    parser.add_argument(
        "--manifest",
        required=True,
        help="Path to the splitter manifest.json.",
    )
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--dump-date", help="Optional source dump date.")
    args = parser.parse_args()

    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1.")

    result = import_manifest(args.manifest, args.batch_size, args.dump_date)

    print("\n===== UESP IMPORT COMPLETE =====")
    print(f"Source dump ID: {result['dump_id']}")
    print(f"Source: {result['source_name']}")
    print(f"Parts imported: {result['parts']:,}")
    print(f"New pages inserted: {result['new_pages']:,}")
    print(f"Total pages in source dump: {result['total_pages']:,}")


if __name__ == "__main__":
    main()
