from config.paths import get_xml_dump_path
from src.ingestion.xml_reader import inter_page_data


def main():
    xml_dump_path = get_xml_dump_path()
    total_pages = 0

    for page in inter_page_data(xml_dump_path):
        total_pages += 1

    print("\nXML reading benchmark complete")
    print(f"Pages read: {total_pages:,}")


if __name__ == "__main__":
    main()
