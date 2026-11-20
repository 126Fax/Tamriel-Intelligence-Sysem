"""Probe whether xmlstream can expose the fields needed from MediaWiki pages.

This is intentionally separate from the production importer. It does not
write to the project's SQLite database or alter the XML dump.
"""

from __future__ import annotations

import json
from collections import Counter

from lxml import etree

MEDIAWIKI_NS = "http://www.mediawiki.org/xml/export-0.10/"
SAMPLE_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<mediawiki xmlns="{MEDIAWIKI_NS}">
  <siteinfo>
    <namespaces><namespace key="0" /></namespaces>
  </siteinfo>
  <page>
    <title>Test &amp; Example</title>
    <ns>0</ns>
    <id>101</id>
    <revision>
      <id>202</id>
      <text xml:space="preserve">A line with &amp; and &lt;markup&gt;.
Second line with [[A link]] and {{{{template|value}}}}.</text>
    </revision>
  </page>
</mediawiki>
"""


def main() -> int:
    try:
        from xmlstream import StreamingXMLParser, TagBehavior, TagConfig
    except ImportError:
        print(
            "Candidate package is not installed. Install it with: "
            "python -m pip install -r experiments/xml_parser_comparison/requirements.txt"
        )
        return 2

    callback_records: list[dict[str, str]] = []
    parser_events: list[dict[str, object]] = []

    def on_page_complete(tag_name: str, content: str) -> None:
        callback_records.append(
            {"tag_name": tag_name, "content": content}
        )

    config = TagConfig(
        name="page",
        behavior=TagBehavior.SILENT,
        complete_callback=on_page_complete,
    )
    parser = StreamingXMLParser({"page": config})

    # Small chunks deliberately split tag names, entities and text.
    chunk_size = 37
    for start in range(0, len(SAMPLE_XML), chunk_size):
        chunk = SAMPLE_XML[start : start + chunk_size]
        for event in parser.process_chunk(chunk):
            parser_events.append(
                {
                    "event_type": getattr(event, "event_type", None),
                    "tag_name": getattr(event, "tag_name", None),
                    "content": getattr(event, "content", None),
                }
            )

    event_counts = Counter(
        str(event["event_type"]) for event in parser_events
    )

    # Check whether the callback content is actual nested XML that can be
    # parsed into the required MediaWiki page fields. Do not assume it is.
    reconstructed_fields = None
    reconstruction_error = None
    if callback_records:
        callback_content = callback_records[0]["content"]
        try:
            wrapped = (
                f'<page xmlns="{MEDIAWIKI_NS}">{callback_content}</page>'
            )
            page = etree.fromstring(wrapped.encode("utf-8"))
            ns = {"mw": MEDIAWIKI_NS}
            revision = page.find("mw:revision", ns)
            if revision is None:
                raise ValueError("page callback did not preserve revision markup")
            text_element = revision.find("mw:text", ns)
            reconstructed_fields = {
                "title": page.findtext("mw:title", namespaces=ns),
                "namespace": page.findtext("mw:ns", namespaces=ns),
                "page_id": page.findtext("mw:id", namespaces=ns),
                "revision_id": revision.findtext("mw:id", namespaces=ns),
                "text": text_element.text if text_element is not None else None,
            }
        except Exception as error:  # diagnostic: report incompatibility
            reconstruction_error = f"{type(error).__name__}: {error}"

    baseline_root = etree.fromstring(SAMPLE_XML.encode("utf-8"))
    baseline_page = baseline_root.find(f"{{{MEDIAWIKI_NS}}}page")
    baseline_revision = baseline_page.find(f"{{{MEDIAWIKI_NS}}}revision")
    baseline_text = baseline_revision.find(f"{{{MEDIAWIKI_NS}}}text")
    baseline_fields = {
        "page_id": baseline_page.findtext(f"{{{MEDIAWIKI_NS}}}id"),
        "title": baseline_page.findtext(f"{{{MEDIAWIKI_NS}}}title"),
        "namespace": baseline_page.findtext(f"{{{MEDIAWIKI_NS}}}ns"),
        "revision_id": baseline_revision.findtext(f"{{{MEDIAWIKI_NS}}}id"),
        "text": baseline_text.text if baseline_text is not None else None,
    }
    equivalent = reconstructed_fields == baseline_fields

    print("XML stream parser compatibility probe")
    print(f"Candidate page callbacks: {len(callback_records)}")
    print("Current lxml baseline: " + json.dumps(baseline_fields, ensure_ascii=False))
    print(f"Parser events: {json.dumps(dict(event_counts), sort_keys=True)}")
    print(f"Callback details: {json.dumps(callback_records, ensure_ascii=False)}")
    print(
        "Reconstructed fields: "
        + json.dumps(reconstructed_fields, ensure_ascii=False)
    )
    if reconstruction_error:
        print(f"Reconstruction error: {reconstruction_error}")
    print(f"Matches required page fields: {equivalent}")

    if equivalent:
        print(
            "The small compatibility sample passed. This does not yet prove "
            "full-dump compatibility or performance."
        )
        return 0

    print(
        "The candidate has not demonstrated that it can reproduce the "
        "required MediaWiki page record. Keep lxml as the production parser."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
