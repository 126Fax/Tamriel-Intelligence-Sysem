from collections import Counter

from src.ingestion.xml_reader import inter_page_data
from src.ingestion.namespaces import read_namespaces


def scan_dataset(file_path):
    namespace_count = Counter()
    total_pages = 0
    namespace_map = read_namespaces(file_path)

    for page_data in inter_page_data(file_path):
        namespace_id = int(page_data["namespace"])

        namespace_name = namespace_map.get(namespace_id, "Unknown")
        namespace_counts[namespace_name] += 1

        total_pages += 1

        return {
            "total_pages": total_pages,
            "namespcae_counts": namespcae_counts,
        }
