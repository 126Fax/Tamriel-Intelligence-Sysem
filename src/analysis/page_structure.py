import statistics
from collections import Counter

from src.ingestion.xml_reader import inter_page_data


def analyse_page_structure(file_path):
    page_lengths = []
    total_pages = 0
    empty_pages = 0
    total_text_length = 0
    text_lengths = Counter()
    shortest_page_data = None
    longest_page_data = None

    for page_data in inter_page_data(file_path):
        text_length = len(page_data["text"])
        if (
            shortest_page_data is None
            or text_length < shortest_page_data["text_length"]
        ):
            shortest_page_data = {
                "page_id": page_data["page_id"],
                "title": page_data["title"],
                "namespace": page_data["namespace"],
                "revision_id": page_data["revision_id"],
                "text_length": text_length,
            }

        if longest_page_data is None or text_length > longest_page_data["text_length"]:
            longest_page_data = {
                "page_id": page_data["page_id"],
                "title": page_data["title"],
                "namespace": page_data["namespace"],
                "revision_id": page_data["revision_id"],
                "text_length": text_length,
            }
        page_lengths.append(text_length)
        if text_length == 0:
            empty_pages += 1
        total_pages += 1
        total_text_length += text_length
        text_lengths[text_length] += 1
    median_text_length = statistics.median(page_lengths)
    page_quartiles = statistics.quantiles(page_lengths, n=4)
    first_quartile = page_quartiles[0]
    third_quartile = page_quartiles[2]
    average_text_length = total_text_length / total_pages
    shortest_page = min(text_lengths)
    longest_page = max(text_lengths)
    return {
        "total_pages": total_pages,
        "total_text_length": total_text_length,
        "average_text_length": round(average_text_length, 2),
        "median_text_length": median_text_length,
        "first_quartile": round(first_quartile, 2),
        "third_quartile": round(third_quartile, 2),
        "text_lengths": dict(text_lengths),
        "shortest_page": shortest_page,
        "longest_page": longest_page,
        "empty_pages": empty_pages,
        "shortest_page_data": shortest_page_data,
        "longest_page_data": longest_page_data,
    }
