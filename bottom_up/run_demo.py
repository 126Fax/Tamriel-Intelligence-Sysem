"""Run the current bottom-up data demonstration using the committed UESP sample.

Run from the repository root:
    python -m bottom_up.run_demo

This imports five committed UESP pages into an isolated sample database, then
analyses their wiki markup and reports page structures and outgoing link
references. It is a demonstration of the current data-analysis foundations,
not yet an autonomous semantic knowledge-discovery system.
"""

from bottom_up.run_sample_analysis import (
    analyse_sample_pages,
    extract_link_records,
    load_sample_pages,
    print_analysis_report,
)
from bottom_up.run_sample_import import import_sample


def main():
    print("Tamriel Intelligence System — bottom-up sample demonstration")
    print("Step 1/2: Importing the committed five-page UESP sample...")
    import_sample()

    print("\nStep 2/2: Analysing imported pages...")
    pages = load_sample_pages()
    results = analyse_sample_pages(pages)
    links = extract_link_records(results)
    print_analysis_report(results, links)

    print("\nDemonstration complete.")
    print("The links above are source references, not verified semantic facts.")
    print("The full-dump database is not modified by this demonstration.")


if __name__ == "__main__":
    main()
