"""Choose random stored facts without repeating until a cycle is exhausted."""
import random

_remaining = []
_last = None


def answer_random_fact(facts):
    global _remaining, _last
    if not facts:
        return "I do not have any structured facts to choose from yet."
    if not _remaining or any(item not in facts for item in _remaining):
        _remaining = list(facts)
        random.shuffle(_remaining)
        if len(_remaining) > 1 and _remaining[-1] == _last:
            _remaining[0], _remaining[-1] = _remaining[-1], _remaining[0]
    fact = _remaining.pop()
    _last = fact
    answer = (
        f"Random fact: {fact['subject']} {fact['relationship']} {fact['object']}."
    )
    source = fact.get("source_page") or fact.get("source_title")
    if source:
        answer += f" Source page: {source}."
    evidence = fact.get("evidence")
    if evidence:
        answer += f" Evidence: {evidence}"
    answer += " This is an extracted candidate fact; check its source evidence before treating it as confirmed lore."
    return answer
