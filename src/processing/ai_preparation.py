"""Prepare imported MediaWiki pages into a consistent, AI-readable format.

The original pages table is read-only from this module's perspective. Prepared
representations are stored in the additional ai_pages table.
"""

import hashlib
import json
import re

import mwparserfromhell

from src.database import database


PROCESSOR_VERSION = "1.0"


def _clean_whitespace(text):
    """Tidy parser output without merging separate paragraphs."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _plain_text(value):
    """Convert a MediaWiki fragment into readable text."""
    return _clean_whitespace(value.strip_code())


def _extract_headings(wikicode):
    headings = []

    for heading in wikicode.filter_headings():
        headings.append(
            {
                "level": int(heading.level),
                "text": _plain_text(heading.title),
            }
        )

    return headings


def _extract_templates(wikicode):
    templates = []

    for template in wikicode.filter_templates():
        parameters = []

        for parameter in template.params:
            parameters.append(
                {
                    "name": str(parameter.name).strip(),
                    "value": _plain_text(parameter.value),
                    "raw_value": str(parameter.value).strip(),
                    "explicit_name": bool(parameter.showkey),
                }
            )

        templates.append(
            {
                "name": _clean_whitespace(str(template.name)),
                "parameters": parameters,
            }
        )

    return templates


def _extract_links(wikicode):
    links = []
    categories = []

    for link in wikicode.filter_wikilinks():
        destination = str(link.title).strip()
        display_text = (
            _plain_text(link.text) if link.text is not None else destination
        )

        link_record = {
            "destination": destination,
            "display_text": display_text,
        }
        links.append(link_record)

        if destination.casefold().startswith("category:"):
            categories.append(destination.split(":", 1)[1].strip())

    return links, categories


def _extract_external_links(wikicode):
    external_links = []

    for link in wikicode.filter_external_links():
        external_links.append(
            {
                "url": str(link.url).strip(),
                "display_text": (
                    _plain_text(link.title) if link.title is not None else ""
                ),
            }
        )

    return external_links


def prepare_page(page):
    """Convert one stored source page into a structured AI-readable record.

    The returned record keeps provenance and both readable and structured
    representations. It never changes the supplied source page.
    """
    source_text = page["page_text"] or ""
    wikicode = mwparserfromhell.parse(source_text)

    readable_text = _plain_text(wikicode)
    headings = _extract_headings(wikicode)
    templates = _extract_templates(wikicode)
    links, categories = _extract_links(wikicode)
    external_links = _extract_external_links(wikicode)

    return {
        "dump_id": page["dump_id"],
        "page_id": page["page_id"],
        "title": page["title"],
        "namespace_id": page["namespace_id"],
        "namespace_name": page["namespace_name"],
        "revision_id": page["revision_id"],
        "readable_text": readable_text,
        "headings": headings,
        "templates": templates,
        "links": links,
        "categories": categories,
        "external_links": external_links,
        "source_text_hash": hashlib.sha256(
            source_text.encode("utf-8")
        ).hexdigest(),
        "processor_version": PROCESSOR_VERSION,
    }


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _save_prepared_pages(connection, prepared_pages):
    connection.executemany(
        """
        INSERT INTO ai_pages (
            dump_id,
            page_id,
            title,
            namespace_id,
            namespace_name,
            revision_id,
            readable_text,
            headings_json,
            templates_json,
            links_json,
            categories_json,
            external_links_json,
            source_text_hash,
            processor_version,
            prepared_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(dump_id, page_id) DO UPDATE SET
            title = excluded.title,
            namespace_id = excluded.namespace_id,
            namespace_name = excluded.namespace_name,
            revision_id = excluded.revision_id,
            readable_text = excluded.readable_text,
            headings_json = excluded.headings_json,
            templates_json = excluded.templates_json,
            links_json = excluded.links_json,
            categories_json = excluded.categories_json,
            external_links_json = excluded.external_links_json,
            source_text_hash = excluded.source_text_hash,
            processor_version = excluded.processor_version,
            prepared_at = CURRENT_TIMESTAMP
        """,
        [
            (
                page["dump_id"],
                page["page_id"],
                page["title"],
                page["namespace_id"],
                page["namespace_name"],
                page["revision_id"],
                page["readable_text"],
                _json(page["headings"]),
                _json(page["templates"]),
                _json(page["links"]),
                _json(page["categories"]),
                _json(page["external_links"]),
                page["source_text_hash"],
                page["processor_version"],
            )
            for page in prepared_pages
        ],
    )


def prepare_dump(dump_id, batch_size=250, force=False):
    """Prepare all pages for one imported dump, using bounded memory.

    Already-prepared pages are skipped unless force=True. Work is committed in
    batches, so a later failure does not discard earlier completed batches.
    """
    if batch_size < 1:
        raise ValueError("Batch size must be at least 1.")

    connection = database.get_connection()
    processed_count = 0
    last_page_id = -1

    try:
        dump = connection.execute(
            """
            SELECT dump_id, import_status
            FROM source_dumps
            WHERE dump_id = ?
            """,
            (dump_id,),
        ).fetchone()

        if dump is None:
            raise ValueError(f"Dump ID {dump_id} does not exist.")

        if dump["import_status"] != "completed":
            raise ValueError(
                f"Dump ID {dump_id} is not completed "
                f"(status: {dump['import_status']})."
            )

        while True:
            if force:
                rows = connection.execute(
                    """
                    SELECT p.*
                    FROM pages AS p
                    WHERE p.dump_id = ? AND p.page_id > ?
                    ORDER BY p.page_id
                    LIMIT ?
                    """,
                    (dump_id, last_page_id, batch_size),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT p.*
                    FROM pages AS p
                    LEFT JOIN ai_pages AS a
                        ON a.dump_id = p.dump_id
                        AND a.page_id = p.page_id
                    WHERE p.dump_id = ?
                        AND p.page_id > ?
                        AND (
                            a.page_id IS NULL
                            OR a.processor_version != ?
                        )
                    ORDER BY p.page_id
                    LIMIT ?
                    """,
                    (dump_id, last_page_id, PROCESSOR_VERSION, batch_size),
                ).fetchall()

            if not rows:
                break

            prepared_pages = [prepare_page(row) for row in rows]
            _save_prepared_pages(connection, prepared_pages)
            connection.commit()

            processed_count += len(prepared_pages)
            last_page_id = rows[-1]["page_id"]

        return processed_count

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def _decode_prepared_row(row):
    """Return a prepared SQLite row with JSON fields decoded into Python data."""
    result = dict(row)

    json_columns = {
        "headings_json": "headings",
        "templates_json": "templates",
        "links_json": "links",
        "categories_json": "categories",
        "external_links_json": "external_links",
    }

    for column, field in json_columns.items():
        result[field] = json.loads(result.pop(column))

    return result


def get_prepared_page(title, dump_id=None):
    """Retrieve one prepared page by exact title.

    If dump_id is omitted, the most recently imported matching page is used.
    """
    connection = database.get_connection()

    try:
        if dump_id is None:
            row = connection.execute(
                """
                SELECT *
                FROM ai_pages
                WHERE title = ?
                ORDER BY dump_id DESC
                LIMIT 1
                """,
                (title,),
            ).fetchone()
        else:
            row = connection.execute(
                """
                SELECT *
                FROM ai_pages
                WHERE title = ? AND dump_id = ?
                LIMIT 1
                """,
                (title, dump_id),
            ).fetchone()

        return _decode_prepared_row(row) if row is not None else None

    finally:
        connection.close()


def iter_prepared_pages(dump_id, batch_size=250):
    """Yield prepared pages in batches without loading the full dump into RAM."""
    if batch_size < 1:
        raise ValueError("Batch size must be at least 1.")

    connection = database.get_connection()

    try:
        cursor = connection.execute(
            """
            SELECT *
            FROM ai_pages
            WHERE dump_id = ?
            ORDER BY page_id
            """,
            (dump_id,),
        )

        while True:
            rows = cursor.fetchmany(batch_size)

            if not rows:
                break

            for row in rows:
                yield _decode_prepared_row(row)

    finally:
        connection.close()
