"""Describe the information currently stored in the Top-down AI knowledge sources.

The overview separates explicit extracted facts from imported wiki pages. A page
being present in SQLite does not mean every statement on that page has been
understood or verified as a fact by the AI.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_BASE_PATH = PROJECT_ROOT / "knowledge_base.json"


def is_knowledge_overview_question(question: str) -> bool:
    """Recognise natural-language requests to inspect the AI's knowledge."""
    if not question or not question.strip():
        return False

    normalised = " ".join(question.casefold().strip().rstrip("?!.").split())
    phrases = (
        "what do you know",
        "tell me what you know",
        "show me what you know",
        "what information do you have",
        "show your knowledge",
        "describe your knowledge",
        "knowledge overview",
        "list everything you know",
        "tell me everything you know",
    )
    return normalised in phrases or normalised.startswith(
        ("what do you know about ", "tell me everything you know about ")
    )


def load_explicit_facts(path: Path = KNOWLEDGE_BASE_PATH) -> list[dict[str, Any]]:
    """Load explicit subject-relationship-object facts, if the file exists."""
    if not path.is_file():
        return []

    with path.open("r", encoding="utf-8") as knowledge_file:
        data = json.load(knowledge_file)

    if not isinstance(data, list):
        raise ValueError("The knowledge base must contain a JSON list.")

    return [
        fact for fact in data
        if isinstance(fact, dict)
        and {"subject", "relationship", "object"}.issubset(fact)
    ]


def get_database_overview() -> dict[str, Any]:
    """Return imported-page and source-dump statistics from the SQLite database."""
    from src.database.database import get_connection

    connection = get_connection()
    try:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if "pages" not in tables:
            return {"available": False, "page_count": 0, "namespaces": [], "dumps": []}

        page_count = connection.execute(
            "SELECT COUNT(*) FROM pages"
        ).fetchone()[0]
        namespaces = [
            dict(row)
            for row in connection.execute(
                """
                SELECT namespace_name, COUNT(*) AS page_count
                FROM pages
                GROUP BY namespace_name
                ORDER BY page_count DESC, namespace_name
                """
            )
        ]

        dumps = []
        if "source_dumps" in tables:
            dumps = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT source_name, dump_date, import_status, completed_at
                    FROM source_dumps
                    ORDER BY dump_id
                    """
                )
            ]

        return {
            "available": True,
            "page_count": page_count,
            "namespaces": namespaces,
            "dumps": dumps,
        }
    finally:
        connection.close()


def build_knowledge_overview(
    facts_path: Path = KNOWLEDGE_BASE_PATH,
) -> dict[str, Any]:
    """Collect a truthful inventory of explicit facts and imported source pages."""
    facts = load_explicit_facts(facts_path)
    try:
        database = get_database_overview()
    except (ImportError, ModuleNotFoundError, OSError):
        database = {
            "available": False,
            "page_count": 0,
            "namespaces": [],
            "dumps": [],
        }

    return {
        "explicit_fact_count": len(facts),
        "facts": facts,
        "database": database,
        "knowledge_base_path": str(facts_path),
    }


def format_knowledge_overview(overview: dict[str, Any]) -> str:
    """Format the inventory as a readable answer."""
    lines = [
        "Here is what I currently have stored.",
        "",
        "EXPLICIT KNOWLEDGE",
        f"I have {overview['explicit_fact_count']} structured fact(s).",
    ]

    if overview["facts"]:
        for number, fact in enumerate(overview["facts"], start=1):
            lines.append(
                f"{number}. {fact['subject']} — {fact['relationship']} — "
                f"{fact['object']}"
            )
    else:
        lines.append("No structured facts are currently stored.")

    database = overview["database"]
    lines.extend(["", "IMPORTED SOURCE MATERIAL"])
    if not database["available"]:
        lines.append("The SQLite page database is not available or has not been created.")
    else:
        lines.append(f"I have {database['page_count']:,} imported wiki page(s).")
        if database["namespaces"]:
            lines.append("Pages by namespace:")
            for item in database["namespaces"]:
                lines.append(f"- {item['namespace_name']}: {item['page_count']:,}")
        if database["dumps"]:
            lines.append("Source imports:")
            for dump in database["dumps"]:
                status = dump.get("import_status") or "status not recorded"
                date = dump.get("dump_date") or "date not recorded"
                lines.append(f"- {dump['source_name']} ({date}; {status})")

    lines.extend([
        "",
        "IMPORTANT",
        "Imported wiki pages are source material, not automatically understood "
        "or verified facts. My explicit structured knowledge is listed above. "
        "I can retrieve and inspect individual imported pages when asked.",
    ])
    return "\n".join(lines)


def answer_knowledge_overview(question: str) -> str | None:
    """Return the overview for a recognised question, otherwise None."""
    if not is_knowledge_overview_question(question):
        return None
    return format_knowledge_overview(build_knowledge_overview())


if __name__ == "__main__":
    print(format_knowledge_overview(build_knowledge_overview()))
