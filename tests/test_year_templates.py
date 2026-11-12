from collections import Counter
import re
import mwparserfromhell

from src.ingestion.xml_reader import inter_page_data

DUMP_PATH = "/home/fax/Downloads/uespwiki-2026-11-01-current.xml.bz2"
YEAR_PATTERN = re.compile(r"\{\{\s*Year\s*(?:\||\}\})")


def main():
    year_values = Counter()
    pages_with_year = 0
    total_year_templates = 0

    for page in inter_page_data(DUMP_PATH):
        page_text = page["text"]

        if YEAR_PATTERN.search(page_text) is None:
            continue

        wikicode = mwparserfromhell.parse(page_text)

        templates = [
            template
            for template in wikicode.filter_templates()
            if str(template.name).strip() == "Year"
        ]

        if not templates:
            continue

        pages_with_year += 1

        for template in templates:
            total_year_templates += 1

            if template.has(1):
                value = str(template.get(1).value).strip()
                year_values[value] += 1

    print("\nYear template analysis complete")
    print(f"Pages containing Year: {pages_with_year:,}")
    print(f"Total Year templates: {total_year_templates:,}")
    print(f"Unique Year values: {len(year_values):,}")

    print("\nMost common values:")

    for value, count in year_values.most_common(30):
        print(f"{value}: {count:,}")


if __name__ == "__main__":
    main()
