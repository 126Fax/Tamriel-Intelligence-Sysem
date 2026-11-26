"""Run the Knowledge Cleaner against a candidate knowledge-base JSON file.

From the repository root:
    python -m cleaner.run_cleaner
    python -m cleaner.run_cleaner --input knowledge_base.json --output data/cleaner/review.json
"""
import argparse

from cleaner.knowledge_cleaner import DEFAULT_INPUT, DEFAULT_OUTPUT, clean_file


def main():
    parser = argparse.ArgumentParser(
        description="Review bottom-up candidate facts without modifying the source file."
    )
    parser.add_argument("--input", default=str(DEFAULT_INPUT),
                        help="Candidate JSON file (default: knowledge_base.json).")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT),
                        help="Review report destination.")
    args = parser.parse_args()

    report = clean_file(args.input, args.output)
    summary = report["summary"]
    print("\n===== KNOWLEDGE CLEANER REPORT =====")
    print(f"Candidates reviewed: {summary['total']:,}")
    print(f"Approved:            {summary['approved']:,}")
    print(f"Rejected:            {summary['rejected']:,}")
    print(f"Needs review:        {summary['needs_review']:,}")
    print(f"\nDetailed report: {args.output}")
    print("\nThis prototype does not alter the input file or claim that approved facts")
    print("are universally true; approval means the evidence passed these basic checks.")


if __name__ == "__main__":
    main()
