#!/usr/bin/env python3
"""Shared, read-only-source helpers for SQLite storage experiments."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any


def backup_database(source_path: Path, destination_path: Path) -> None:
    """Create a consistent SQLite backup without writing to the source DB."""
    source_uri = f"file:{source_path.resolve().as_posix()}?mode=ro"
    source = sqlite3.connect(source_uri, uri=True)
    destination = sqlite3.connect(destination_path)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def pragma_value(connection: sqlite3.Connection, pragma: str) -> Any:
    return connection.execute(f"PRAGMA {pragma}").fetchone()[0]


def prepare_database(path: Path) -> dict[str, Any]:
    """Checkpoint, compact and analyse an independent experiment copy."""
    connection = sqlite3.connect(path)
    details: dict[str, Any] = {"journal_mode_before": pragma_value(connection, "journal_mode")}
    try:
        if str(details["journal_mode_before"]).lower() == "wal":
            details["wal_checkpoint"] = list(
                connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            )
        started = time.perf_counter()
        connection.execute("VACUUM")
        details["vacuum_seconds"] = time.perf_counter() - started
        started = time.perf_counter()
        connection.execute("ANALYZE")
        details["analyze_seconds"] = time.perf_counter() - started
        connection.commit()
    finally:
        connection.close()
    return details



def capture_source_metadata(path: Path) -> dict[str, Any]:
    """Record original source configuration and sidecar sizes without writes."""
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        page_size = int(pragma_value(connection, "page_size"))
        page_count = int(pragma_value(connection, "page_count"))
        freelist_count = int(pragma_value(connection, "freelist_count"))
        wal_path, shm_path = Path(str(path) + "-wal"), Path(str(path) + "-shm")
        return {
            "sqlite_version": connection.execute("SELECT sqlite_version()").fetchone()[0],
            "journal_mode": pragma_value(connection, "journal_mode"),
            "synchronous": pragma_value(connection, "synchronous"),
            "page_size": page_size,
            "page_count": page_count,
            "freelist_count": freelist_count,
            "allocated_page_bytes_excluding_freelist": (page_count - freelist_count) * page_size,
            "physical_main_database_bytes": path.stat().st_size,
            "wal_bytes": wal_path.stat().st_size if wal_path.exists() else 0,
            "shm_bytes": shm_path.stat().st_size if shm_path.exists() else 0,
        }
    finally:
        connection.close()


def _dbstat(connection: sqlite3.Connection) -> dict[str, Any]:
    try:
        rows = connection.execute(
            """SELECT name, SUM(pgsize), SUM(payload), SUM(unused), COUNT(*)
               FROM dbstat GROUP BY name ORDER BY name"""
        ).fetchall()
        objects = {
            row[0]: {
                "allocated_bytes": row[1],
                "payload_bytes": row[2],
                "unused_bytes": row[3],
                "pages": row[4],
            }
            for row in rows
        }
        return {"available": True, "objects": objects,
                "total_allocated_bytes": sum(x["allocated_bytes"] for x in objects.values()),
                "total_payload_bytes": sum(x["payload_bytes"] for x in objects.values()),
                "total_unused_bytes": sum(x["unused_bytes"] for x in objects.values())}
    except sqlite3.Error as error:
        return {"available": False, "error": str(error), "objects": {}}


def capture_metrics(path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        page_size = int(pragma_value(connection, "page_size"))
        page_count = int(pragma_value(connection, "page_count"))
        frellist_count = int(pragma_value(connection, "freelist_count"))
        integrity_rows = [row[0] for row in connection.execute("PRAGMA integrity_check")]
        fk_errors = [list(row) for row in connection.execute("PRAGMA foreign_key_check")]
        tables = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )]
        row_counts = {}
        for table in tables:
            escaped = table.replace('"', '""')
            row_counts[table] = connection.execute(f'SELECT COUNT(*) FROM "{escaped}"').fetchone()[0]
        dbstat = _dbstat(connection)
        main_bytes = path.stat().st_size
        wal_path = Path(str(path) + "-wal")
        shm_path = Path(str(path) + "-shm")
        return {
            "database": str(path),
            "sqlite_version": connection.execute("SELECT sqlite_version()").fetchone()[0],
            "journal_mode": pragma_value(connection, "journal_mode"),
            "synchronous": pragma_value(connection, "synchronous"),
            "page_size": page_size,
            "page_count": page_count,
            "frelist_count": freelist_count,
            "allocated_page_bytes_excluding_freelist": (page_count - freelist_count) * page_size,
            "physical_main_database_bytes": main_bytes,
            "wal_bytes": wal_path.stat().st_size if wal_path.exists() else 0,
            "shm_bytes": shm_path.stat().st_size if shm_path.exists() else 0,
            "integrity_check": integrity_rows,
            "foreign_key_errors": fk_errors,
            "row_counts": row_counts,
            "dbstat": dbstat,
            "logical_payload_bytes": dbstat.get("total_payload_bytes"),
            "dbstat_unused_bytes": dbstat.get("total_unused_bytes"),
        }
    finally:
        connection.close()


def canonical_hash(rows: list[dict[str, Any]]) -> tuple[str, int]:
    """Hash canonical records after sorting; never depend on SQLite row order."""
    encoded = [json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":")) for row in rows]
    encoded.sort()
    digest = hashlib.sha256()
    for item in encoded:
        digest.update(item.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest(), len(encoded)
