"""Optional full-dump batch-size benchmark.

Run from the repository root:
    python -m tests.benchmark_import

Each run uses a separate temporary SQLite database and rereads the dump.
This can take a while and needs temporary disk space. It does not change the
main database. Compare the measured rates on the same machine.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

from config.paths import get_xml_dump_path
from src.database import database
from src.ingestion.importer import import_dump


BATCH_SIZES = (250, 1000, 2500)


def main():
    dump_path = get_xml_dump_path()
    print(f"Benchmark source: {dump_path}")
    print("Each batch size gets a fresh temporary database.\n")

    for batch_size in BATCH_SIZES:
        with tempfile.TemporaryDirectory(prefix="tamriel-import-bench-") as folder:
            temporary_database = Path(folder) / "benchmark.db"
            with patch.object(database, "DATABASE_PATH", temporary_database):
                result = import_dump(dump_path, batch_size=batch_size)

        print(
            f"Batch {batch_size:>5,}: "
            f"{result['pages_in_database']:>9,} pages | "
            f"{result['elapsed_seconds']:>8.2f} sec | "
            f"{result['pages_per_second']:>9,.0f} pages/sec"
        )


if __name__ == "__main__":
    main()
