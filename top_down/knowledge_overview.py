"""Summarise the Top-Down AI's current stored knowledge."""
from src.database import database


def build_knowledge_overview(facts):
    lines = [
        "Here is what I currently have stored.",
        f"Structured candidate facts: {len(facts)}.",
    ]
    if facts:
        for index, fact in enumerate(facts, start=1):
            lines.append(
                f"{index}. {fact['subject']} — {fact['relationship']} — {fact['object']}"
            )
    else:
        lines.append("No structured facts are currently stored.")

    connection = database.get_connection()
    try:
        tables = {
            row["name"] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "pages" in tables:
            page_count = connection.execute(
                "SELECT COUNT(*) FROM pages"
            ).fetchone()[0]
            lines.append(f"Imported wiki pages: {page_count:,}.")
        else:
            lines.append("Imported wiki page database is not available yet.")
    finally:
        connection.close()

    lines.append(
        "Imported pages and extracted candidate facts are evidence sources, "
        "not automatically verified lore. Ask about a subject to inspect its sources."
    )
    return "\\n".join(lines)
