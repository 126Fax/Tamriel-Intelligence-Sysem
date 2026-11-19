"""Run an interactive terminal chat with the rule-based lore prototype.

Start with: python -m top_down.chat
"""

from top_down.assistant import answer_question


def main():
    print("Tamriel Intelligence System — top-down prototype")
    print("Ask a question about the facts currently in knowledge_base.json.")
    print("Type 'exit' or 'quit' to stop.\n")

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if question.casefold() in {"exit", "quit"}:
            print("Goodbye.")
            break
        if not question:
            continue

        try:
            result = answer_question(question)
        except (OSError, ValueError) as error:
            print(f"Knowledge-base error: {error}")
            continue

        print(f"Assistant: {result['answer']}")
        if result["facts"]:
            print("Evidence used:")
            for fact in result["facts"]:
                print(
                    f"  - {fact['subject']} --[{fact['relationship']}]--> "
                    f"{fact['object']}"
                )
        print()


if __name__ == "__main__":
    main()
