from time import perf_counter
import re

import mwparserfromhell

from config.paths import get_xml_dump_path
from src.ingestion.xml_reader import inter_page_data


YEAR_PATTERN = re.compile(r"\{\{\s*Year\s*(?:\||\}\})")


def main():
    xml_dump_path = get_xml_dump_path()
    total_pages = 0
    candidate_pages = 0
    pages_with_year = 0
    total_year_templates = 0

    xml_time = 0
    filter_time = 0
    parsing_time = 0

    page_iterator = iter(inter_page_data(xml_dump_path))

    while True:
        start = perf_counter()

        try:
            page = next(page_iterator)
        except StopIteration:
            break

        xml_time += perf_counter() - start
        total_pages += 1

        start = perf_counter()

        page_text = page["text"]
        contains_year = YEAR_PATTERN.search(page_text) is not None
        filter_time += perf_counter() - start

        if not contains_year:
            continue

        candidate_pages += 1

        start = perf_counter()

        wikicode = mwparserfromhell.parse(page_text)

        year_templates = [
            template
            for template in wikicode.filter_templates()
            if str(template.name).strip() == "Year"
        ]

        parsing_time += perf_counter() - start

        if year_templates:
            pages_with_year += 1
            total_year_templates += len(year_templates)

    print("\nYear analysis benchmark complete")
    print(f"Total pages: {total_pages:,}")
    print(f"Candidate pages: {candidate_pages:,}")
    print(f"Pages containing Year templates: {pages_with_year:,}")
    print(f"Total Year templates: {total_year_templates:,}")

    print("\nProcessing times:")
    print(f"XML ingestion: {xml_time:.2f} seconds")
    print(f"Text filtering: {filter_time:.2f} seconds")
    print(f"Wiki parsing: {parsing_time:.2f} seconds")
    print(f"Total measured time: {xml_time + filter_time + parsing_time:.2f} seconds")


if __name__ == "__main__":
    main()
