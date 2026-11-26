#!/usr/bin/env python3
"""Create a reproducible, compacted SQLite baseline copy and JSON report.

The supplied source database is opened read-only through SQLite's backup API.
Only the new output copy is checkpointed, VACUUMed and ANALYZEd.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlite_experiment_common import backup_database, capture_metrics, capture_source_metadata, prepare_database


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Existing SQLite database")
    parser.add_argument("--output-dir", required=True, type=Path, help="New, non-existing output directory")
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output_dir.resolve()
    if not source.is_file():
        parser.error(f"Source database does not exist: {source}")
    if output.exists():
        parser.error(f"Output directory already exists: {output}")
    output.mkdir(parents=True)
    baseline = output / "baseline.sqlite"
    source_metadata = capture_source_metadata(source)
    backup_database(source, baseline)
    preparation = prepare_database(baseline)
    metrics = capture_metrics(baseline)
    report = {
        "experiment": "sqlite_storage_baseline",
        "source_database": str(source),
        "source_opened_read_only": True,
        "source_modified": False,
        "source_metadata_before_copy": source_metadata,
        "preparation": preparation,
        "metrics": metrics,
    }
    report_path = output / "baseline-report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"SQLite version:       {metrics['sqlite_version']}")
    print(f"Page size:            {metrics['page_size']:,} bytes")
    print(f"Page count:           {metrics['page_count']:,}")
    print(f"Freelist pages:       {metrics['freelist_count']:,}")
    print(f"Allocated page bytes: {metrics['allocated_page_bytes_excluding_freelist']:,}")
    print(f"Physical file:        {metrics['physical_main_database_bytes']:,} bytes")
    print(f"Logical payload:      {metrics['logical_payload_bytes'] if metrics['logical_payload_bytes'] is not None else 'dbstat unavailable'}")
    print(f"Journal mode:         {metrics['journal_mode']}")
    print(f"Integrity:            {'PASS' if metrics['integrity_check'] == ['ok'] else 'FAIL'}")
    print(f"Foreign keys:         {len(metrics['foreign_key_errors'])} errors")
    print(f"Report:               {report_path}")
    return 0 if metrics['integrity_check'] == ['ok'] and not metrics['foreign_key_errors'] else 1


if __name__ == "__main__":
    raise SystemExit(main())
