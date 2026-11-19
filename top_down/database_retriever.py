"""Search the imported SQLite corpus for evidence-backed lore information."""
from __future__ import annotations

import re
from src.database import database

OCCUPATION_FIELDS = ("occupation", "profession", "job", "role")
CONTINENT_RELATIONSHIPS = ("continent", "is a continent", "continent of")


def _tables(connection):
    return {row["name"] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}


def _singular(value):
    value = " ".join(value.casefold().split()).strip()
    if value.endswith("ies") and len(value) > 3:
        return value[:-3] + "y"
    if value.endswith("s") and not value.endswith("ss"):
        return value[:-1]
    return value


def count_entities(target):
    """Count distinct entities only when a structured type/occupation field exists."""
    term = _singular(target)
    if term == "province":
        from bottom_up.province_catalog import load_provinces
        provinces = load_provinces()
        return {
            "count": len(provinces), "label": "traditional provinces of Tamriel",
            "entities": provinces, "basis": "curated_reference_catalog",
            "note": "This is the built-in traditional province reference list, not a count independently discovered by the extractor.",
        }

    connection = database.get_connection()
    try:
        tables = _tables(connection)
        names, evidence = set(), []
        if "candidate_facts" in tables:
            if term == "continent":
                rows = connection.execute(
                    """SELECT DISTINCT subject, source_title, evidence_text
                       FROM candidate_facts
                       WHERE lower(relationship) IN (?, ?, ?)
                          OR (lower(relationship) IN ('type','is a')
                              AND lower(object) LIKE '%continent%')
                       ORDER BY subject COLLATE NOCASE""",
                    CONTINENT_RELATIONSHIPS,
                ).fetchall()
            else:
                rows = connection.execute(
                    """SELECT DISTINCT subject, source_title, evidence_text
                       FROM candidate_facts
                       WHERE lower(relationship) IN ('occupation','profession','job','has occupation')
                         AND lower(object) LIKE ?""",
                    (f"%{term}%",),
                ).fetchall()
            for row in rows:
                names.add(row["subject"])
                evidence.append({"entity": row["subject"], "source": row["source_title"],
                                 "evidence": row["evidence_text"]})

        if "page_template_parameters" in tables:
            if term == "continent":
                rows = connection.execute(
                    """SELECT DISTINCT source_title, evidence_text
                       FROM page_template_parameters
                       WHERE lower(parameter_name) IN ('type','category','kind')
                         AND lower(parameter_value) LIKE '%continent%'"""
                ).fetchall()
            else:
                placeholders = ",".join("?" for _ in OCCUPATION_FIELDS)
                rows = connection.execute(
                    f"""SELECT DISTINCT source_title, evidence_text
                        FROM page_template_parameters
                        WHERE lower(parameter_name) IN ({placeholders})
                          AND lower(parameter_value) LIKE ?""",
                    (*OCCUPATION_FIELDS, f"%{term}%"),
                ).fetchall()
            for row in rows:
                names.add(row["source_title"])
                evidence.append({"entity": row["source_title"], "source": row["source_title"],
                                 "evidence": row["evidence_text"]})

        return {
            "count": len(names), "label": term,
            "entities": sorted(names, key=str.casefold),
            "basis": "distinct_database_entities", "evidence": evidence[:20],
            "note": "Count is based on distinct source-page entities with matching structured occupation/type data.",
        }
    finally:
        connection.close()


def search_lore(term, limit=8):
    """Search page titles, page text and extracted facts for a subject or phrase."""
    term = " ".join(str(term).split()).strip()
    if not term:
        return {"pages": [], "facts": []}
    connection = database.get_connection()
    try:
        tables = _tables(connection)
        pages, facts = [], []
        if "pages" in tables:
            pages = [dict(row) for row in connection.execute(
                """SELECT title, namespace_name, page_text
                   FROM pages WHERE title LIKE ? OR page_text LIKE ?
                   ORDER BY CASE WHEN title LIKE ? THEN 0 ELSE 1 END,
                            text_length DESC LIMIT ?""",
                (f"%{term}%", f"%{term}%", f"%{term}%", limit),
            ).fetchall()]
            for page in pages:
                text = re.sub(r"\s+", " ", page.get("page_text") or "")
                match = re.search(re.escape(term), text, re.IGNORECASE)
                page["snippet"] = text[max(0, match.start()-180):match.end()+260].strip() if match else ""
                page.pop("page_text", None)
        if "candidate_facts" in tables:
            facts = [dict(row) for row in connection.execute(
                """SELECT subject, relationship, object, source_title,
                          evidence_text, confidence
                   FROM candidate_facts
                   WHERE subject LIKE ? OR object LIKE ? OR evidence_text LIKE ?
                   ORDER BY confidence DESC LIMIT ?""",
                (f"%{term}%", f"%{term}%", f"%{term}%", limit),
            ).fetchall()]
        return {"pages": pages, "facts": facts}
    finally:
        connection.close()
