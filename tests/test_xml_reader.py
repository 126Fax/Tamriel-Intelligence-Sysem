from collections import Counter

from config.paths import XML_DUMP_PATH
from src.ingestion.xml_reader import NAMESPACE, read_pages

namespace_counts = Counter()

if XML_DUMP_PATH is None:
    raise RuntimeError(
        "XML dump path is not configured. "
        "Set XML_DUMP_PATH in config/local.py."
    )

if not XML_DUMP_PATH.exists():
    raise FileNotFoundError(f"XML dump not found: {XML_DUMP_PATH}")

for page in read_pages(XML_DUMP_PATH):
    namespace = page.findtext(f"{NAMESPACE}ns")
    namespace_counts[namespace] += 1

print("\nPages per namespace:")

for namespace, count in sorted(namespace_counts.items()):
    print(f"Namespace {namespace}: {count:,} pages")

print(f"\nTotal pages: {sum(namespace_counts.values()):,}")
