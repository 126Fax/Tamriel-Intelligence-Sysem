from collections import Counter

from config.paths import get_xml_dump_path
from src.ingestion.xml_reader import NAMESPACE, read_pages


def main():
    xml_dump_path = get_xml_dump_path()
    namespace_counts = Counter()

    for page in read_pages(xml_dump_path):
        namespace = page.findtext(f"{NAMESPACE}ns")
        namespace_counts[namespace] += 1

    print("\nPages per namespace:")

    for namespace, count in sorted(namespace_counts.items()):
        print(f"Namespace {namespace}: {count:,} pages")

    print(f"\nTotal pages: {sum(namespace_counts.values()):,}")


if __name__ == "__main__":
    main()
