"""Run the first bottom-up page-clustering experiment."""

import argparse
import bz2
import tempfile
from pathlib import Path
from unittest.mock import patch

from src.ai.bottom_up.clustering import discover_page_clusters
from src.database import database
from src.ingestion.namespaces import read_namespaces
from src.ingestion.xml_reader import inter_page_data


def load_sample_pages():
    """Load the committed synthetic fixture into a temporary database."""
    project_root = Path(__file__).resolve().parents[3]
    fixture_path = (
        project_root / "tests" / "fixtures" / "sample_wiki_dump.xml.fixture"
    )

    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary_path = Path(temporary_directory)
        dump_path = temporary_path / "sample_wiki_dump.xml.bz2"
        database_path = temporary_path / "sample_database.db"

        with fixture_path.open("rb") as source_file:
            with bz2.open(dump_path, "wb") as dump_file:
                dump_file.write(source_file.read())

        with patch.object(database, "DATABASE_PATH", database_path):
            database.initialise_database()
            database.migrate_database()

            dump_id = database.register_source_dump(dump_path.name)
            database.insert_pages_batch(
                dump_id,
                inter_page_data(dump_path),
                read_namespaces(dump_path),
            )

            return list(database.get_pages_for_analysis(namespace_id=0))


def main():
    parser = argparse.ArgumentParser(
        description="Discover groups of similar Elder Scrolls wiki pages."
    )
    parser.add_argument(
        "--clusters",
        type=int,
        default=3,
        help="Number of groups for the algorithm to discover (default: 3).",
    )
    parser.add_argument(
        "--sample-data",
        action="store_true",
        help="Run against the small committed fixture without changing the main database.",
    )
    args = parser.parse_args()

    if args.sample_data:
        pages = load_sample_pages()
        print("Using the synthetic test dataset.")
    else:
        pages = database.get_pages_for_analysis(namespace_id=0)

    if not pages:
        print("No main-namespace page text was found in the database.")
        print("Import the synthetic fixture or a UESP XML dump first.")
        return

    results = discover_page_clusters(
        pages,
        number_of_clusters=args.clusters,
    )

    print(f"Algorithm: {results['algorithm']}")
    print(f"Pages analysed: {results['page_count']}")
    print(f"Groups discovered: {results['cluster_count']}")

    for cluster in results["clusters"]:
        print(f"\nCluster {cluster['cluster_id']} ({cluster['page_count']} pages)")
        print("Representative terms:", ", ".join(cluster["representative_terms"]))

        for page in cluster["pages"]:
            print(f"  - {page['title']}")


if __name__ == "__main__":
    main()
