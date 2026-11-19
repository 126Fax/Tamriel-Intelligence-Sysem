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
