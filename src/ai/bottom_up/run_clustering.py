"""Run the first bottom-up page-clustering experiment."""

import argparse

from src.ai.bottom_up.clustering import discover_page_clusters
from src.database.database import get_pages_for_analysis


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
    args = parser.parse_args()

    pages = get_pages_for_analysis(namespace_id=0)

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
        print(f"\\nCluster {cluster['cluster_id']} ({cluster['page_count']} pages)")
        print("Representative terms:", ", ".join(cluster["representative_terms"]))

        for page in cluster["pages"]:
            print(f"  - {page['title']}")


if __name__ == "__main__":
    main()
