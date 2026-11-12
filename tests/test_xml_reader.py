from collections import Counter

from src.ingestion.xml_reader import NAMESPACE, read_pages

DUMP_PATH = "/home/fax/Downloads/uespwiki-2026-11-01-current.xml.bz2"

namespace_counts = Counter()

for page in read_pages(DUMP_PATH):
    namespace = page.findtext(f"{NAMESPACE}ns")
    namespace_counts[namespace] += 1

print("\nPages per namespace:")

for namespace, count in sorted(namespace_counts.items()):
    print(f"Namespace {namespace}: {count:,} pages")

print(f"\nTotal pages: {sum(namespace_counts.values()):,}")
