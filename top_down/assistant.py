"""Public interface for asking the Top-Down AI questions."""
import sqlite3

from top_down.answer_generator import generate_answer
from top_down.database_retriever import count_entities, search_lore
from top_down.knowledge_retriever import load_knowledge_base, retrieve_facts
from top_down.knowledge_overview import build_knowledge_overview
from top_down.random_fact import answer_random_fact
from top_down.question_analyser import analyse_question


def _answer_count(target):
    if not target:
        return "I understood that you want a count, but I could not identify what you want counted."
    result = count_entities(target)
    if result["count"] == 0:
        return (
            f"I cannot give a reliable count of {target} yet. "
            "I could not find matching structured entity records. "
            "A page mentioning something is not enough to prove that it is a separate entity."
        )
    if result["basis"] == "curated_reference_catalog":
        return (
            f"There are {result['count']} {result['label']} in my reference catalogue: "
            f"{', '.join(result['entities'])}. {result['note']}"
        )
    sources = list(dict.fromkeys(
        item.get("source") for item in result.get("evidence", [])
        if item.get("source")
    ))
    source_text = f" Example source pages: {', '.join(sources[:8])}." if sources else ""
    return (
        f"I found {result['count']} distinct {result['label']} record(s) "
        f"in the structured database. {result['note']}{source_text}"
    )


def _answer_lookup(term, facts, analysis):
    if term:
        lowered = term.casefold()
        related = [
            fact for fact in facts
            if lowered in fact["subject"].casefold()
            or lowered in fact["object"].casefold()
        ]
        if related:
            lines = [f"Here is what my structured knowledge base records about {term}:"]
            for fact in related[:15]:
                lines.append(
                    f"- {fact['subject']} — {fact['relationship']} — {fact['object']}."
                )
                source = fact.get("source_page") or fact.get("source_title")
                if source:
                    lines.append(f"  Source page: {source}.")
                evidence = fact.get("evidence")
                if evidence:
                    lines.append(f"  Evidence: {evidence}")
            return "\n".join(lines), related

        try:
            result = search_lore(term)
        except (sqlite3.Error, OSError):
            result = {"pages": [], "facts": []}
        if result["facts"] or result["pages"]:
            lines = [f"I found the following material matching {term}; these are source matches, not automatically verified answers."]
            for fact in result["facts"][:8]:
                lines.append(
                    f"- {fact['subject']} — {fact['relationship']} — {fact['object']}."
                )
                lines.append(f"  Source: {fact['source_title']}. Evidence: {fact['evidence_text']}")
            for page in result["pages"][:8]:
                lines.append(f"- Page: {page['title']} ({page['namespace_name']}).")
                if page.get("snippet"):
                    lines.append(f"  Extract: {page['snippet']}")
            return "\n".join(lines), result["facts"]
    return (
        "I could not identify a specific subject to look up. Try asking about a named person, place, faction or creature.",
        [],
    )


def answer_question(question, knowledge_base_path=None):
    """Analyse, retrieve and answer a question from structured facts and SQLite."""
    analysis = analyse_question(question)

    if analysis["intent"] in {"overview", "random_fact"}:
        facts = (
            load_knowledge_base(knowledge_base_path)
            if knowledge_base_path is not None
            else load_knowledge_base()
        )
        if analysis["intent"] == "overview":
            try:
                answer = build_knowledge_overview(facts)
            except sqlite3.Error:
                answer = "I can list my structured facts, but the imported page database could not be read.\n" + "\n".join(
                    f"- {fact['subject']} — {fact['relationship']} — {fact['object']}"
                    for fact in facts
                )
        else:
            answer = answer_random_fact(facts)
        return {
            "question": question, "answer": answer, "analysis": analysis,
            "facts": facts, "knowledge_base_records": len(facts),
        }

    if analysis["intent"] == "count":
        answer = _answer_count(analysis.get("count_target"))
        return {
            "question": question, "answer": answer, "analysis": analysis,
            "facts": [], "knowledge_base_records": 0,
        }

    facts = (
        load_knowledge_base(knowledge_base_path)
        if knowledge_base_path is not None
        else load_knowledge_base()
    )

    if analysis["intent"] in {"lookup", "search"}:
        answer, matches = _answer_lookup(analysis.get("search_term"), facts, analysis)
    else:
        matches = retrieve_facts(analysis, facts)
        answer = generate_answer(question, analysis, matches)

    return {
        "question": question, "answer": answer, "analysis": analysis,
        "facts": matches, "knowledge_base_records": len(facts),
    }
