"""Turn retrieved knowledge-base facts into cautious, readable answers."""


def generate_answer(question, analysis, facts):
    """Generate a response using only the facts supplied by the retriever."""
    if not facts:
        return (
            "I don't have enough information in the current knowledge base "
            "to answer that question."
        )

    intent = analysis.get("intent")
    relationship = analysis.get("relationship")

    if intent == "find_subjects":
        subjects = list(dict.fromkeys(fact["subject"] for fact in facts))
        target = analysis.get("object_hint") or "the requested subject"
        if relationship == "province":
            return f"The provinces of {target} recorded in the knowledge base are: {', '.join(subjects)}."
        return f"The matching subjects recorded in the knowledge base are: {', '.join(subjects)}."

    if intent == "find_object":
        answers = list(dict.fromkeys(fact["object"] for fact in facts))
        subject = analysis.get("subject_hint") or facts[0]["subject"]
        if len(answers) == 1:
            return f"{subject} {relationship} {answers[0]}."
        return f"The knowledge base records these answers for {subject}: {', '.join(answers)}."

    return "I found matching facts, but I could not determine how to present them as an answer."
