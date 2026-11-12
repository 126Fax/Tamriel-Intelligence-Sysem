import bz2
from lxml import etree

NAMESPACE = "{http://www.mediawiki.org/xml/export-0.10/}"


def read_pages(file_path):
    with bz2.open(file_path, "rb") as dump_file:
        context = etree.iterparse(
            dump_file,
            events=("end",),
            tag="{http://www.mediawiki.org/xml/export-0.10/}page",
            huge_tree=True,
            resolve_entities=False,
            no_network=True,
        )

        for event, page in context:
            yield page

            page.clear()

            while page.getprevious() is not None:
                del page.getparent()[0]


def extract_page_data(page):
    revisions = page.findall(f"{NAMESPACE}revision")

    if not revisions:
        return None

    latest_revision = revisions[-1]

    revision_text = latest_revision.findtext(f"{NAMESPACE}text")

    if revision_text is None:
        return None

    page_data = {
        "page_id": page.findtext(f"{NAMESPACE}id"),
        "title": page.findtext(f"{NAMESPACE}title"),
        "namespace": page.findtext(f"{NAMESPACE}ns"),
        "revision_id": latest_revision.findtext(f"{NAMESPACE}id"),
        "text": revision_text,
    }

    return page_data


def inter_page_data(file_path):
    for page in read_pages(file_path):
        page_data = extract_page_data(page)

        if page_data is not None:
            yield page_data


def find_page_by_id(file_path, target_page_id):
    for page_data in inter_page_data(file_path):
        if page_data["page_id"] == str(target_page_id):
            return page_data

    return None
