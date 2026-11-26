#!/usr/bin/env python3
"""Compare SQLite VACUUM with Zstandard archive compression across all selected levels.

The source database is opened read-only. All SQLite copies and .zst files are
created beneath a new output directory. Zstandard is an archive/backup format
here: a .zst file is not directly queryable by SQLite.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

DEFAULT_LEVELS = (1, 3, 5, 7, 9, 12, 15, 18, 19, 20, 21, 22)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup_database(source_path: Path, destination_path: Path) -> None:
    source = sqlite3.connect(
        f"file:{source_path.resolve().as_posix()}?mode=ro", uri=True
    )
    destination = sqlite3.connect(destination_path)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def inspect_database(path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(
        f"file:{path.resolve().as_posix()}?mode=ro", uri=True
    )
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
        return {
            "file_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "integrity_check": integrity,
            "foreign_key_errors": len(foreign_key_errors),
            "page_size": connection.execute("PRAGMA page_size").fetchone()[0],
            "page_count": connection.execute("PRAGMA page_count").fetchone()[0],
            "freelist_pages": connection.execute("PRAGMA freelist_count").fetchone()[0],
        }
    finally:
        connection.close()


def run_zstd(command: list[str]) -> None:
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(command)}\n{detail}"
        )


def compress_levels(
    zstd: str, input_path: Path, label: str, output_dir: Path,
    levels: tuple[int, ...], temp_dir: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    input_bytes = input_path.stat().st_size
    input_hash = sha256_file(input_path)

    for level in levels:
        archive = output_dir / f"{label}-zstd-{level}.db.zst"
        restored = temp_dir / f"{label}-zstd-{level}-restored.db"

        started = time.perf_counter()
        run_zstd([
            zstd, "-q", "-f", f"-{level}", "--threads=1",
            "--no-progress", str(input_path), "-o", str(archive),
        ])
        compression_seconds = time.perf_counter() - started

        started = time.perf_counter()
        run_zstd([
            zstd, "-q", "-d", "-f", "--no-progress",
            str(archive), "-o", str(restored),
        ])
        decompression_seconds = time.perf_counter() - started

        restored_hash = sha256_file(restored)
        byte_identical = restored_hash == input_hash
        sqlite_check = inspect_database(restored) if byte_identical else None
        archive_bytes = archive.stat().st_size

        results.append({
            "input": label,
            "level": level,
            "input_bytes": input_bytes,
            "compressed_bytes": archive_bytes,
            "bytes_saved": input_bytes - archive_bytes,
            "size_reduction_percent": (
                (input_bytes - archive_bytes) / input_bytes * 100
                if input_bytes else 0.0
            ),
            "compression_ratio": (
                input_bytes / archive_bytes if archive_bytes else None
            ),
            "compression_seconds": compression_seconds,
            "decompression_seconds": decompression_seconds,
            "decompressed_sha256": restored_hash,
            "byte_identical_after_decompression": byte_identical,
            "restored_sqlite_integrity": (
                sqlite_check["integrity_check"] if sqlite_check else None
            ),
            "restored_foreign_key_errors": (
                sqlite_check["foreign_key_errors"] if sqlite_check else None
            ),
            "archive_path": str(archive),
        })
        restored.unlink(missing_ok=True)
        print(
            f"{label:12} level {level:2}: {archive_bytes:>14,} bytes | "
            f"{compression_seconds:8.3f}s compress | "
            f"{decompression_seconds:8.3f}s decompress | "
            f"{'PASS' if byte_identical else 'FAIL'} byte check"
        )

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--levels", default=",".join(map(str, DEFAULT_LEVELS)),
        help="Comma-separated Zstandard levels to test (default: %(default)s)",
    )
    parser.add_argument(
        "--zstd", default="zstd",
        help="Zstandard executable name or path (default: %(default)s)",
    )
    args = parser.parse_args()

    source = args.source.resolve()
    output = args.output_dir.resolve()
    if not source.is_file():
        parser.error(f"Source database does not exist: {source}")
    if output.exists():
        parser.error(f"Output directory already exists; choose a new path: {output}")
    try:
        levels = tuple(dict.fromkeys(int(value.strip()) for value in args.levels.split(",")))
    except ValueError:
        parser.error("--levels must be a comma-separated list of integers")
    if not levels or any(level < 1 or level > 22 for level in levels):
        parser.error("Zstandard levels must be between 1 and 22")
    zstd_path = shutil.which(args.zstd)
    if not zstd_path:
        parser.error(
            "Zstandard CLI was not found. Install the 'zstd' package, then rerun."
        )

    version = subprocess.run(
        [zstd_path, "--version"], text=True, capture_output=True, check=True
    ).stdout.strip()
    output.mkdir(parents=True)
    unchanged = output / "baseline-unchanged.sqlite"
    vacuumed = output / "candidate-vacuum.sqlite"
    report_path = output / "comparison.json"

    print(f"Source (read-only): {source}")
    print("Creating independent SQLite baseline copy...")
    backup_database(source, unchanged)
    print("Creating and VACUUM-compacting a separate copy...")
    shutil.copy2(unchanged, vacuumed)
    started = time.perf_counter()
    connection = sqlite3.connect(vacuumed)
    try:
        connection.execute("VACUUM")
    finally:
        connection.close()
    vacuum_seconds = time.perf_counter() - started

    baseline_info = inspect_database(unchanged)
    vacuum_info = inspect_database(vacuumed)
    if baseline_info["integrity_check"] != "ok" or vacuum_info["integrity_check"] != "ok":
        raise RuntimeError("SQLite integrity check failed before Zstandard testing")
    if baseline_info["foreign_key_errors"] or vacuum_info["foreign_key_errors"]:
        raise RuntimeError("Foreign-key check failed before Zstandard testing")

    print()
    print(f"Zstandard: {version}")
    print(f"Testing levels: {', '.join(map(str, levels))}")
    print("Compressing both the unchanged and VACUUMed database copies...")
    with tempfile.TemporaryDirectory(prefix="zstd-verify-", dir=output) as temporary:
        temp_dir = Path(temporary)
        results = compress_levels(
            zstd_path, unchanged, "unchanged", output, levels, temp_dir
        )
        results.extend(compress_levels(
            zstd_path, vacuumed, "vacuumed", output, levels, temp_dir
        ))

    all_valid = all(
        row["byte_identical_after_decompression"]
        and row["restored_sqlite_integrity"] == "ok"
        and row["restored_foreign_key_errors"] == 0
        for row in results
    )
    best = min(results, key=lambda row: row["compressed_bytes"])
    report = {
        "experiment": "sqlite_vacuum_vs_zstandard",
        "source_database": str(source),
        "source_opened_read_only": True,
        "original_source_modified": False,
        "zstandard_version": version,
        "zstandard_levels_tested": list(levels),
        "zstandard_threads": 1,
        "note": (
            "Zstandard outputs are compressed backup/archive files, not live "
            "SQLite databases. Both unchanged and VACUUMed copies are compressed "
            "to separate the effects of VACUUM and Zstandard."
        ),
        "vacuum_seconds": vacuum_seconds,
        "unchanged": baseline_info,
        "vacuumed": vacuum_info,
        "zstandard_results": results,
        "best_compressed_result": best,
        "all_decompression_and_integrity_checks_pass": all_valid,
        "files": {
            "unchanged_sqlite": str(unchanged),
            "vacuumed_sqlite": str(vacuumed),
            "report": str(report_path),
        },
    }
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print()
    print("VACUUM vs Zstandard comparison")
    print("==============================")
    print(f"Unchanged SQLite:    {baseline_info['file_bytes']:,} bytes")
    print(f"VACUUM SQLite:       {vacuum_info['file_bytes']:,} bytes")
    print(f"VACUUM elapsed:      {vacuum_seconds:.3f}s")
    print(
        f"Smallest archive:    {best['compressed_bytes']:,} bytes "
        f"({best['input']} input, Zstd level {best['level']})"
    )
    print(
        "Decompression checks: "
        f"{'PASS' if all_valid else 'FAIL'}"
    )
    print(f"JSON report:         {report_path}")
    print("Note: .zst archives must be decompressed before SQLite can open them.")

    return 0 if all_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
