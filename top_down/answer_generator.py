"""Turn retrieved knowledge-base facts into readable answers."""


def generate_answer(question, facts):
    """Create a concise answer, or explain that no matching fact was found."""
    if not facts:
        return (
            "I couldn't find an answer in the current knowledge base. "
            "The information may not have been added yet."
        )

    relationships = {fact["relationship"].casefold() for fact in facts}

    if relationships == {"province"}:
        provinces = sorted({fact["subject"] for fact in facts})
        empire = facts[0]["object"]
        names = ", ".join(provinces)

        if len(provinces) == 1:
            return f"{names} is listed as a province of {empire}."
        return f"The provinces listed as belonging to {empire} are {names}."

    if relationships == {"lives in"}:
        statements = sorted({
            f'{fact["subject"]} live in {fact["object"]}'
            for fact in facts
        })
        return "According to the knowledge base, " + "; ".join(statements) + "."

    statements = sorted({
        f'{fact["subject"]} — {fact["relationship"]} — {fact["object"]}'
        for fact in facts
    })
    return "I found these related facts: " + "; ".join(statements) + "."


if __name__ == "__main__":
    example_facts = [
        {"subject": "Dragons", "relationship": "lives in", "object": "Skyrim"}
    ]
    print(generate_answer("Where do dragons live?", example_facts))
