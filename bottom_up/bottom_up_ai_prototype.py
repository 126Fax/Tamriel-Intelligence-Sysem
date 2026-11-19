import json
from itertools import combinations

stop_words = {"the", "is", "a", "of", "in", "are", "to"}

def discover_word_patterns(pages):
    word_counts = {}

    for page in pages:
        words = page.lower().split()

        for word in words:
            if word not in stop_words:

                if word not in word_counts:
                    word_counts[word] = 0

                word_counts[word] += 1

    return word_counts

def rank_patterns(word_counts):
    ranked_patterns = sorted(
        word_counts.items(),
        key=lambda item: item[1],
        reverse=True
    )

    return ranked_patterns

def discover_phrases(pages):
    phrase_counts = {}

    for page in pages:
        words = page.lower().split()

        for i in range(len(words) - 1):
            if words[i] in stop_words:
                continue

            phrase = words[i] + " " + words[i + 1]

            if phrase in phrase_counts:
                phrase_counts[phrase] += 1
            else:
                phrase_counts[phrase] = 1

    return phrase_counts

def generate_report(word_patterns, phrase_patterns, sentence_patterns):
    print("\n===== BOTTOM-UP AI REPORT =====")

    print("\nMost common words:")

    for word, count in word_patterns[:5]:
        print(f"{word}: {count}")

    print("\nMost common phrases:")

    for phrase, count in phrase_patterns[:5]:
        print(f"{phrase}: {count}")

    print("\nMost common sentence patterns:")

    for pattern, count in sentence_patterns[:5]:
        print(f"{pattern}: {count}")

relationship_patterns = {
    "province": {
        "words": ["is", "a", "province", "of"],
        "start_position": 1,
        "subject_position": 0,
        "object_position": 6
    },
    "lives in": {
        "words": ["live", "in"],
        "start_position": 1,
        "subject_position": 0,
        "object_position": 3
    }
}


def discover_relationships(pages):
    relationships = []

    for page in pages:
        words = page.split()

        for name, pattern in relationship_patterns.items():
            pattern_words = pattern["words"]
            start = pattern["start_position"]
            end = start + len(pattern_words)

            if words[start:end] == pattern_words:
                relationships.append({
                    "subject": words[pattern["subject_position"]],
                    "relationship": name,
                    "object": words[pattern["object_position"]]
                })

    return relationships

def discover_sentence_patterns(pages):
    pattern_counts = {}

    for page in pages:
        words = page.lower().split()

        for i in range(len(words) - 2):
            pattern = " ".join(words[i:i + 3])

            if pattern in pattern_counts:
                pattern_counts[pattern] += 1
            else:
                pattern_counts[pattern] = 1

    return pattern_counts

# Keep discovery logic separate from the original demonstration.
from bottom_up.pattern_discovery import (
    compare_sentences,
    discover_shared_patterns,
    find_specialisations,
)

def extract_subject(sentence, ending):
    if sentence.endswith(ending):
        subject = sentence.removesuffix(ending)
        return subject

    return None

def extract_all_subjects(sentences, ending):
    subjects = []

    for sentence in sentences:
        subject = extract_subject(sentence, ending)

        if subject is not None:
            subjects.append(subject)

    return subjects

def discover_province_relationships(pages):
    province_ending = " is a province of the Empire"

    subjects = extract_all_subjects(pages, province_ending)

    relationships = []

    for subject in subjects:
        relationships.append({
            "subject": subject,
            "relationship": "province",
            "object": "Empire"
        })

    return relationships

def compare_all_sentences(pages):
    for sentence1, sentence2 in combinations(pages, 2):
            differences, matching_words, pattern = compare_sentences(sentence1, sentence2)

            print("\nComparing:")
            print(sentence1)
            print(sentence2)
            print("Differences:", differences)
            print("Matching words:", matching_words)
            print("Discovered pattern:", " ".join(pattern))


def assign_pattern_meanings(shared_patterns):
    for pattern, details in shared_patterns.items():
        if pattern == "[VARIABLE] is a province of the Empire":
            details["meaning"] = "province"

def build_knowledge_base( relationships, province_relationships):
    knowledge_base = []

    for relationship in province_relationships:
        knowledge_base.append(relationship)

        
    for relationship in relationships:
        if relationship not in knowledge_base:
            knowledge_base.append(relationship)
    return knowledge_base

def save_knowledge_base(knowledge_base):
    with open("knowledge_base.json", "w") as f:
        json.dump(knowledge_base, f, indent=4)

def load_knowledge_base():
    with open("knowledge_base.json", "r") as f:
        knowledge_base = json.load(f)

    return knowledge_base


def main():
    """Run the original hardcoded demonstration when this file is executed."""
    pages = [
        "Skyrim is a province of the Empire",
        "Morrowind is a province of the Empire",
        "Dragons live in Skyrim",
        "The Nords are native to Skyrim",
        "Cyrodiil is a province of the Empire",
        "Hammerfell is a province of the Empire",
        "High Rock is a province of the Empire"
    ]

    for page in pages:
        if "province" in page:
            print(page)

    province_ending = " is a province of the Empire"
    subjects = extract_all_subjects(pages, province_ending)

    print("\n===== EXTRACTED PROVINCES =====")
    for subject in subjects:
        print(subject)

    province_relationships = discover_province_relationships(pages)

    print("\n===== PROVINCE RELATIONSHIPS =====")
    for relationship in province_relationships:
        print(relationship)

    patterns = discover_word_patterns(pages)
    ranked_patterns = rank_patterns(patterns)
    phrases = discover_phrases(pages)
    ranked_phrases = rank_patterns(phrases)
    sentence_patterns = discover_sentence_patterns(pages)
    ranked_sentence_patterns = rank_patterns(sentence_patterns)
    
    generate_report(ranked_patterns, ranked_phrases, ranked_sentence_patterns)
    relationships = discover_relationships(pages)
    shared_patterns = discover_shared_patterns(pages)
    assign_pattern_meanings(shared_patterns)
    knowledge_base = build_knowledge_base( relationships, province_relationships)
    save_knowledge_base(knowledge_base)
    print("\nDiscovered relationships:")
    
    for relationship in relationships:
        print(relationship)
    
    print("\nDiscovered shared patterns:")
    
    for pattern, details in shared_patterns.items():
        print(f"Pattern: {pattern}")
        print(f"Meaning: {details['meaning']}")
        print(f"Sentence count: {len(details['sentences'])}")
        print(f"Sentences: {details['sentences']}")
        print(f"Variable values: {details['words']}")
    
    print("\n===== KNOWLEDGE BASE =====")
    
    for entry in knowledge_base:
        print(entry)
    
    loaded_knowledge = load_knowledge_base()
    
    print("\n===== LOADED KNOWLEDGE BASE =====")
    
    for entry in loaded_knowledge:
        print(entry)
    
    compare_all_sentences(pages)
    save_knowledge_base(knowledge_base)

if __name__ == "__main__":
    main()
