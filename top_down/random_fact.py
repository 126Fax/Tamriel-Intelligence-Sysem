"""Select and present a random fact from the Top-down AI knowledge base."""
from __future__ import annotations

import random
from typing import Any

from .knowledge_overview import load_explicit_facts

# Keep a shuffled cycle in memory so facts are not repeated until the current
# collection has been exhausted. This state intentionally resets on restart.
_remaining_facts: list[dict[str, Any]] = []
_last_fact: dict[str, Any] | None = None


def is_random_fact_question(question: str) -> bool:
    """Recognise requests for a random stored fact."""
    if not question or not question.strip():
        return False

    normalised = " ".join(question.casefold().strip().rstrip("?!.").split())
    phrases = {
        "random fact",
        "tell me a random fact",
        "give me a random fact",
        "show me a random fact",
        "random lore fact",
        "tell me a random lore fact",
        "give me a random lore fact",
        "surprise me with a fact",
        "surprise me",
    }
    return normalised in phrases


def choose_random_fact(
    facts: list[dict[str, Any]],
    rng: Any = random,
) -> dict[str, Any] | None:
    """Choose a fact without repeating it until all supplied facts were used."""
    global _remaining_facts, _last_fact

    if not facts:
        _remaining_facts = []
        _last_fact = None
        return None

    # Reset the cycle if the knowledge base changed.
    if not _remaining_facts or any(fact not in facts for fact in _remaining_facts):
        _remaining_facts = list(facts)
        rng.shuffle(_remaining_facts)
        if len(_remaining_facts) > 1 and _remaining_facts[-1] == _last_fact:
            _remaining_facts[0], _remaining_facts[-1] = (
                _remaining_facts[-1],
                _remaining_facts[0],
            )

    selected = _remaining_facts.pop()
    _last_fact = selected
    return selected


def format_random_fact(fact: dict[str, Any]) -> str:
    """Turn a stored subject-relationship-object fact into a readable response."""
    subject = str(fact["subject"]).strip()
    relationship = str(fact["relationship"]).strip()
    object_value = str(fact["object"]).strip()
    answer = f"Random fact: {subject} {relationship} {object_value}."

    # Include provenance only when the extractor actually stored it.
    source = (
        fact.get("source_page")
        or fact.get("source_title")
        or fact.get("page_title")
    )
    if source:
        answer += f"\nSource page: {source}."

    evidence = fact.get("evidence")
    if isinstance(evidence, str) and evidence.strip():
        answer += f"\nEvidence: {evidence.strip()}"

    answer += "\nThis is an extracted candidate fact; check its source evidence before treating it as confirmed lore."
    return answer


def answer_random_fact(question: str) -> str | None:
    """Return one random stored fact for a recognised request."""
    if not is_random_fact_question(question):
        return None

    fact = choose_random_fact(load_explicit_facts())
    if fact is None:
        return (
            "I do not have any structured facts to choose from yet. "
            "I need more facts in knowledge_base.json before I can share one."
        )
    return format_random_fact(fact)
