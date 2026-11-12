from src.ingestion.xml_reader import inter_page_data

DUMP_PATH = "/home/fax/Downloads/uespwiki-2026-11-01-current.xml.bz2"


def main():
    total_pages = 0

    for page in inter_page_data(DUMP_PATH):
        total_pages += 1

    print("\nXML reading benchmark complete")
    print(f"Pages read: {total_pages:,}")


if __name__ == "__main__":
    main()
