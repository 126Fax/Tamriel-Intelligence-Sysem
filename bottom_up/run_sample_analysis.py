"""Analyse the committed UESP sample database without touching the main database.

Run from the repository root:
    python -m bottom_up.run_sample_analysis

The runner reports page structure and extracts outgoing wiki links. A link is
recorded as a source-to-destination reference; it is not treated as proof of a
semantic relationship between the two pages.
"""

from pathlib import Path
from unittest.mock import patch

from src.analysis.content_structure import analyse_content_structure
from src.database import database


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DATABASE_PATH = (
    PROJECT_ROOT / "data" / "database" / "tamriel_sample.db"
)


def load_sample_pages():
    """Return page titles and text from the isolated sample database."""
    if not SAMPLE_DATABASE_PATH.is_file():
        raise FileNotFoundError(
            "Sample database not found. Run "
            "'python -m bottom_up.run_sample_import' first."
        )

    # Redirect only this database-module operation to the sample database.
    with patch.object(database, "DATABASE_PATH", SAMPLE_DATABASE_PATH):
        connection = database.get_connection()

        try:
            return connection.execute(
                """
                SELECT title, page_text
                FROM pages
                ORDER BY title
                """
            ).fetchall()
        finally:
            connection.close()


def analyse_sample_pages(pages):
    """Analyse wiki markup and retain each page's structural findings."""
    results = []

    for page in pages:
        page_text = page["page_text"]
        analysis = analyse_content_structure(page_text)

        results.append(
            {
                "title": page["title"],
                "text_length": len(page_text),
                "analysis": analysis,
            }
        )

    return results


def extract_link_records(results):
    """Convert each page's parsed wikilinks into source/destination records."""
    link_records = []

    for result in results:
        for link in result["analysis"]["link_details"]:
            destination = link["destination"]
            prefix, separator, page_title = destination.partition(":")

            link_records.append(
                {
                    "source_page": result["title"],
                    "destination": destination,
                    "destination_prefix": prefix if separator else None,
                    "destination_title": page_title if separator else destination,
                    "display_text": link["display_text"],
                }
            )

    return link_records


def print_analysis_report(results, link_records):
    """Print page-level structure statistics and extracted wiki links."""
    print("===== UESP SAMPLE ANALYSIS =====")
    print(f"Pages analysed: {len(results)}")
    print(f"Wiki links discovered: {len(link_records)}")

    print("\n===== PAGE STRUCTURE =====")

    for result in results:
        analysis = result["analysis"]

        print(f"\n{result['title']}")
        print(f"  Text length: {result['text_length']}")
        print(f"  Templates: {analysis['template_count']}")
        print(f"  Wikilinks: {analysis['wikilink_count']}")
        print(f"  External links: {analysis['external_link_count']}")
        print(f"  Headings: {analysis['heading_count']}")
        print(f"  Tags: {analysis['tag_count']}")

        if analysis["template_names"]:
            print(f"  Template names: {analysis['template_names']}")

    print("\n===== EXTRACTED LINK RECORDS =====")

    for link in link_records:
        print(
            f"{link['source_page']} -> {link['destination']} "
            f"(display: {link['display_text']})"
        )


def main():
    """Load, analyse and report on the isolated UESP sample."""
    pages = load_sample_pages()
    results = analyse_sample_pages(pages)
    link_records = extract_link_records(results)
    print_analysis_report(results, link_records)


if __name__ == "__main__":
    main()
