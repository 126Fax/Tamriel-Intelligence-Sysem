#!/usr/bin/env python3
"""Shared helpers for reproducible SQLite storage experiments."""
from __future__ import annotations
import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any


def backup_database(source_path: Path, destination_path: Path) -> None:
    """Take a consistent backup while opening the supplied source read-only."""
    uri = f"file:{source_path.resolve().as_posix()}?mode=ro"
    source = sqlite3.connect(uri, uri=True)
    destination = sqlite3.connect(destination_path)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def pragma_value(connection: sqlite3.Connection, name: str) -> Any:
    return connection.execute(f"PRAGMA {name}").fetchone()[0]


def prepare_database(path: Path) -> dict[str, Any]:
    """Checkpoint WAL if present, then VACUUM and ANALYZE an experiment copy."""
    connection = sqlite3.connect(path)
    result = {"journal_mode_before": pragma_value(connection, "journal_mode")}
    try:
        if str(result["journal_mode_before"]).lower() == "wal":
            result["wal_checkpoint"] = list(connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone())
        start = time.perf_counter()
        connection.execute("VACUUM")
        result["vacuum_seconds"] = time.perf_counter() - start
        start = time.perf_counter()
        connection.execute("ANALYZE")
        result["analyze_seconds"] = time.perf_counter() - start
        connection.commit()
    finally:
        connection.close()
    return result


def _sidecar(path: Path, suffix: str) -> int:
    item = Path(str(path) + suffix)
    return item.stat().st_size if item.exists() else 0


def capture_source_metadata(path: Path) -> dict[str, Any]:
    """Read original config and file sizes without modifying the source."""
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        page_size = int(pragma_value(connection, "page_size"))
        page_count = int(pragma_value(connection, "page_count"))
        freelist = int(pragma_value(connection, "freelist_count"))
        return {
            "sqlite_version": connection.execute("SELECT sqlite_version()").fetchone()[0],
            "journal_mode": pragma_value(connection, "journal_mode"),
            "synchronous": pragma_value(connection, "synchronous"),
            "page_size": page_size,
            "page_count": page_count,
            "freelist_count": freelist,
            "allocated_page_bytes_excluding_freelist": (page_count - freelist) * page_size,
            "physical_main_database_bytes": path.stat().st_size,
            "wal_bytes": _sidecar(path, "-wal"),
            "shm_bytes": _sidecar(path, "-shm"),
        }
    finally:
        connection.close()


def _dbstat(connection: sqlite3.Connection) -> dict[str, Any]:
    try:
        rows = connection.execute(
            "SELECT name,SUM(pgsize),SUM(payload),SUM(unused),COUNT(*) FROM dbstat GROUP BY name ORDER BY name"
        ).fetchall()
        objects = {r[0]: {"allocated_bytes": r[1], "payload_bytes": r[2], "unused_bytes": r[3], "pages": r[4]} for r in rows}
        return {"available": True, "objects": objects,
                "total_allocated_bytes": sum(x["allocated_bytes"] for x in objects.values()),
                "total_payload_bytes": sum(x["payload_bytes"] for x in objects.values()),
                "total_unused_bytes": sum(x["unused_bytes"] for x in objects.values())}
    except sqlite3.Error as error:
        return {"available": False, "error": str(error), "objects": {}}


def capture_metrics(path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(path)
    try:
        page_size = int(pragma_value(connection, "page_size"))
        page_count = int(pragma_value(connection, "page_count"))
        freelist = int(pragma_value(connection, "freelist_count"))
        integrity = [r[0] for r in connection.execute("PRAGMA integrity_check")]
        fk_errors = [list(r) for r in connection.execute("PRAGMA foreign_key_check")]
        tables = [r[0] for r in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        counts = {}
        for table in tables:
            escaped = table.replace('"', '""')
            counts[table] = connection.execute(f'SELECT COUNT(*) FROM "{escaped}"').fetchone()[0]
        stats = _dbstat(connection)
        return {
            "database": str(path),
            "sqlite_version": connection.execute("SELECT sqlite_version()").fetchone()[0],
            "journal_mode": pragma_value(connection, "journal_mode"),
            "synchronous": pragma_value(connection, "synchronous"),
            "page_size": page_size,
            "page_count": page_count,
            "freelist_count": freelist,
            "allocated_page_bytes_excluding_freelist": (page_count - freelist) * page_size,
            "physical_main_database_bytes": path.stat().st_size,
            "wal_bytes": _sidecar(path, "-wal"),
            "shm_bytes": _sidecar(path, "-shm"),
            "integrity_check": integrity,
            "foreign_key_errors": fk_errors,
            "row_counts": counts,
            "dbstat": stats,
            "logical_payload_bytes": stats.get("total_payload_bytes"),
            "dbstat_unused_bytes": stats.get("total_unused_bytes"),
        }
    finally:
        connection.close()


def canonical_hash(rows: list[dict[str, Any]]) -> tuple[str, int]:
    """Sort canonical JSON records before hashing; never depend on row order."""
    encoded = sorted(json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":")) for row in rows)
    digest = hashlib.sha256()
    for item in encoded:
        digest.update(item.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest(), len(encoded)
