import json

from src.analysis.dataset_scanner import scan_dataset

DUMP_PATH = "/home/fax/Downloads/uespwiki-2026-11-01-current.xml.bz2"
REPORT_PATH = "data/processed/namespace_scan.json"


def main():
    results = scan_dataset(DUMP_PATH)

    report = {
        "total_pages": results["total_pages"],
        "namespace_counts": dict(results["namespace_counts"]),
    }

    with open(REPORT_PATH, "w", encoding="utf-8") as report_file:
        json.dump(report, report_file, indent=4)

    print("\nDataset scan complete")
    print(f"Total pages scanned: {results['total_pages']:,}")

    print("\nPages per namespace:")

    for namespace, count in sorted(results["namespace_counts"].items()):
        print(f"{namespace}: {count:,}")


if __name__ == "__main__":
    main()
