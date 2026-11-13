
import json

from config.paths import PROCESSED_DIR, XML_DUMP_PATH
from src.analysis.dataset_scanner import scan_dataset


def main():
    if XML_DUMP_PATH is None:
        raise RuntimeError(
            "XML dump path is not configured. "
            "Set XML_DUMP_PATH in config/local.py."
        )

    if not XML_DUMP_PATH.exists():
        raise FileNotFoundError(f"XML dump not found: {XML_DUMP_PATH}")

    results = scan_dataset(XML_DUMP_PATH)

    report = {
        "total_pages": results["total_pages"],
        "namespace_counts": dict(results["namespace_counts"]),
    }

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    report_path = PROCESSED_DIR / "namespace_scan.json"

    with report_path.open("w", encoding="utf-8") as report_file:
        json.dump(report, report_file, indent=4)

    print("\nDataset scan complete")
    print(f"Total pages scanned: {results['total_pages']:,}")

    print("\nPages per namespace:")

    for namespace, count in sorted(results["namespace_counts"].items()):
        print(f"{namespace}: {count:,}")


if __name__ == "__main__":
    main()
