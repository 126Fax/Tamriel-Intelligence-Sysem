"""Reference list and audit tools for Tamriel's traditional provinces."""
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROVINCES_PATH = PROJECT_ROOT / "data" / "reference" / "provinces.json"


def load_provinces(path=PROVINCES_PATH):
    with Path(path).open("r", encoding="utf-8") as source:
        provinces = json.load(source)
    if not isinstance(provinces, list) or any(
        not isinstance(name, str) or not name.strip() for name in provinces
    ):
        raise ValueError("Province reference file must be a list of non-empty names.")
    return list(dict.fromkeys(name.strip() for name in provinces))


def audit_discovered_provinces(facts):
    """Compare extracted province candidates with the reference list."""
    expected = load_provinces()
    expected_by_key = {name.casefold(): name for name in expected}
    discovered, unexpected = {}, []
    for fact in facts:
        if str(fact.get("relationship", "")).casefold() not in {"province", "province of"}:
            continue
        subject = str(fact.get("subject", "")).strip()
        if subject.casefold() in expected_by_key:
            discovered.setdefault(expected_by_key[subject.casefold()], []).append(fact)
        else:
            unexpected.append(fact)
    return {
        "expected_count": len(expected), "expected": expected,
        "discovered": discovered,
        "missing": [name for name in expected if name not in discovered],
        "unexpected_candidates": unexpected,
        "discovered_count": len(discovered),
    }


def audit_database(dump_id=None):
    """Audit stored province candidates from SQLite against the reference list."""
    from src.database import database

    connection = database.get_connection()
    try:
        tables = {
            row["name"] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "candidate_facts" not in tables:
            return audit_discovered_provinces([])
        query = """
            SELECT subject, relationship, object, source_title, evidence_text,
                   extraction_method, confidence
            FROM candidate_facts
            WHERE lower(relationship) IN ('province', 'province of')
        """
        parameters = ()
        if dump_id is not None:
            query += " AND dump_id = ?"
            parameters = (dump_id,)
        rows = connection.execute(query, parameters).fetchall()
        facts = [
            {
                "subject": row["subject"],
                "relationship": row["relationship"],
                "object": row["object"],
                "source_page": row["source_title"],
                "evidence": row["evidence_text"],
                "extraction_method": row["extraction_method"],
                "confidence": row["confidence"],
            }
            for row in rows
        ]
        return audit_discovered_provinces(facts)
    finally:
        connection.close()


if __name__ == "__main__":
    report = audit_database()
    print(f"Traditional provinces expected: {report['expected_count']}")
    print(f"Distinct provinces with extracted evidence: {report['discovered_count']}")
    print("\nDISCOVERED")
    for name, evidence in report["discovered"].items():
        print(f"- {name}: {len(evidence)} evidence record(s)")
    print("\nMISSING")
    for name in report["missing"]:
        print(f"- {name}")
    print("\nUNEXPECTED CANDIDATES")
    for fact in report["unexpected_candidates"]:
        print(f"- {fact['subject']} -> {fact['object']} ({fact.get('source_page', 'unknown source')})")
