"""Explainable discovery of shared sentence patterns."""
from __future__ import annotations

import re
from itertools import combinations
from typing import Iterable

VARIABLE = "[VARIABLE]"
_TOKEN_RE = re.compile(r"\w+(?:['’]\w+)*|[^\w\s]", re.UNICODE)


def tokenize(sentence: str) -> list[str]:
    """Tokenise words and punctuation without discarding source spelling."""
    return _TOKEN_RE.findall(sentence)


def _lcs_matches(first: list[str], second: list[str]) -> list[tuple[int, int]]:
    """Return index pairs for a deterministic longest common subsequence."""
    lengths = [[0] * (len(second) + 1) for _ in range(len(first) + 1)]
    for i in range(len(first) - 1, -1, -1):
        for j in range(len(second) - 1, -1, -1):
            if first[i].casefold() == second[j].casefold():
                lengths[i][j] = 1 + lengths[i + 1][j + 1]
            else:
                lengths[i][j] = max(lengths[i + 1][j], lengths[i][j + 1])

    matches = []
    i = j = 0
    while i < len(first) and j < len(second):
        if first[i].casefold() == second[j].casefold():
            matches.append((i, j))
            i += 1
            j += 1
        elif lengths[i + 1][j] >= lengths[i][j + 1]:
            i += 1
        else:
            j += 1
    return matches


def _pair_pattern(first, second):
    matches = _lcs_matches(first, second)
    pattern = []
    first_values = []
    second_values = []
    first_cursor = second_cursor = 0

    for first_index, second_index in matches:
        first_gap = first[first_cursor:first_index]
        second_gap = second[second_cursor:second_index]
        if first_gap or second_gap:
            pattern.append(VARIABLE)
            first_values.append(" ".join(first_gap))
            second_values.append(" ".join(second_gap))
        pattern.append(first[first_index])
        first_cursor = first_index + 1
        second_cursor = second_index + 1

    first_gap = first[first_cursor:]
    second_gap = second[second_cursor:]
    if first_gap or second_gap:
        pattern.append(VARIABLE)
        first_values.append(" ".join(first_gap))
        second_values.append(" ".join(second_gap))

    fixed_count = sum(token != VARIABLE for token in pattern)
    return pattern, tuple(first_values), tuple(second_values), fixed_count


def compare_sentences(sentence1: str, sentence2: str):
    """Compare two sentences; each contiguous unmatched phrase is one value."""
    first = tokenize(sentence1)
    second = tokenize(sentence2)
    pattern, first_values, second_values, _ = _pair_pattern(first, second)
    return list(zip(first_values, second_values)), [
        token for token in pattern if token != VARIABLE
    ], pattern


def _add_unique(items, value):
    if value not in items:
        items.append(value)


def discover_shared_patterns(
    sentences: Iterable[str],
    minimum_support: int = 2,
    minimum_fixed_tokens: int = 2,
) -> dict[str, dict]:
    """Discover recurring patterns, retaining values by variable position."""
    if minimum_support < 2:
        raise ValueError("minimum_support must be at least 2.")
    if minimum_fixed_tokens < 1:
        raise ValueError("minimum_fixed_tokens must be at least 1.")

    source_sentences = list(dict.fromkeys(
        sentence.strip() for sentence in sentences
        if isinstance(sentence, str) and sentence.strip()
    ))
    tokenised = [(sentence, tokenize(sentence)) for sentence in source_sentences]
    discovered = {}

    for (first_sentence, first_tokens), (second_sentence, second_tokens) in combinations(tokenised, 2):
        pattern, first_values, second_values, fixed_count = _pair_pattern(
            first_tokens, second_tokens
        )
        if fixed_count < minimum_fixed_tokens or VARIABLE not in pattern:
            continue

        key = " ".join(pattern)
        details = discovered.setdefault(key, {
            "words": [],
            "values": [],
            "sentences": [],
            "meaning": None,
            "support": 0,
            "variable_count": pattern.count(VARIABLE),
            "fixed_token_count": fixed_count,
            "variable_positions": [
                index for index, token in enumerate(pattern) if token == VARIABLE
            ],
        })

        for sentence, values in (
            (first_sentence, first_values),
            (second_sentence, second_values),
        ):
            _add_unique(details["sentences"], sentence)
            if values:
                _add_unique(details["values"], values)
                for value in values:
                    if value:
                        _add_unique(details["words"], value)

    result = {}
    for pattern, details in discovered.items():
        support = len(details["sentences"])
        if support >= minimum_support:
            details["support"] = support
            result[pattern] = details
    return result


def find_specialisations(shared_patterns: dict[str, dict]) -> list[dict]:
    """Find patterns that fix one or more slots in a more general pattern."""
    specialisations = []
    patterns = list(shared_patterns)

    def is_more_specific(candidate, base):
        newly_fixed = False
        for base_token, candidate_token in zip(base, candidate):
            if base_token == VARIABLE:
                if candidate_token != VARIABLE:
                    newly_fixed = True
            elif base_token.casefold() != candidate_token.casefold():
                return False
        return newly_fixed

    for first, second in combinations(patterns, 2):
        first_tokens, second_tokens = first.split(), second.split()
        if len(first_tokens) != len(second_tokens):
            continue
        if is_more_specific(second_tokens, first_tokens):
            general, specific = first, second
        elif is_more_specific(first_tokens, second_tokens):
            general, specific = second, first
        else:
            continue
        specialisations.append({
            "general_pattern": general,
            "specialised_pattern": specific,
            "specialized_pattern": specific,
            "general": general,
            "specialised": specific,
            "specialized": specific,
            "general_support": shared_patterns[general].get("support", len(shared_patterns[general].get("sentences", []))),
            "specialised_support": shared_patterns[specific].get("support", len(shared_patterns[specific].get("sentences", []))),
        })
    return specialisations
