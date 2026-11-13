import json

from config.paths import PROCESSED_DIR, get_xml_dump_path
from src.analysis.dataset_scanner import scan_dataset


def main():
    xml_dump_path = get_xml_dump_path()
    results = scan_dataset(xml_dump_path)

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
