import json

from src.analysis.page_structure import analyse_page_structure

DUMP_PATH = "/home/fax/Downloads/uespwiki-2026-11-01-current.xml.bz2"
REPORT_PATH = "data/processed/page_structure.json"


def main():
    results = analyse_page_structure(DUMP_PATH)

    report = {
        "total_pages": results["total_pages"],
        "total_text_length": results["total_text_length"],
        "average_text_length": results["average_text_length"],
        "median_text_length": results["median_text_length"],
        "first_quartile": results["first_quartile"],
        "third_quartile": results["third_quartile"],
        "shortest_page": results["shortest_page"],
        "longest_page": results["longest_page"],
        "empty_pages": results["empty_pages"],
        "shortest_page_data": results["shortest_page_data"],
        "longest_page_data": results["longest_page_data"],
    }

    with open(REPORT_PATH, "w", encoding="utf-8") as report_file:
        json.dump(report, report_file, indent=4)

    print("\nPage structure analysis complete")
    print(f"Total pages analysed: {results['total_pages']:,}")
    print(f"Total text length: {results['total_text_length']:,} characters")
    print(f"Average page length: {results['average_text_length']:,} characters")
    print(f"Median page length: {results['median_text_length']:,} characters")
    print(f"First quartile (25%): {results['first_quartile']:,} characters")
    print(f"Third quartile (75%): {results['third_quartile']:,} characters")
    print(f"Shortest page: {results['shortest_page']:,} characters")
    print(f"Longest page: {results['longest_page']:,} characters")
    print(f"Empty pages: {results['empty_pages']:,}")


if __name__ == "__main__":
    main()
