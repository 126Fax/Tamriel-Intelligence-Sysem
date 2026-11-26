use anyhow::Result;
use regex::RegexBuilder;
use serde::Serialize;
use serde_json::Value;
use std::collections::BTreeMap;
use std::path::Path;

const REQUIRED_FIELDS: [&str; 4] = ["subject", "relationship", "object", "evidence"];
const FRAGMENT_STARTS: [&str; 21] = [
    "and", "but", "or", "because", "although", "after", "before", "while", "when", "if", "who",
    "which", "that", "he", "she", "they", "it", "we", "i", "you", "all",
];
const FRAGMENT_MARKERS: [&str; 10] = [
    "is",
    "are",
    "was",
    "were",
    "who",
    "which",
    "that",
    "used to",
    "wishing to",
    "decided to",
];
const PRONOUN_OBJECTS: [&str; 8] = ["it", "they", "them", "he", "she", "him", "her", "this"];

#[derive(Serialize)]
struct ReviewItem {
    status: &'static str,
    reasons: Vec<String>,
    fact: Value,
}

#[derive(Serialize)]
struct ReviewReport {
    cleaner_version: &'static str,
    review_policy: &'static str,
    summary: Summary,
    results: Vec<ReviewItem>,
}

#[derive(Serialize)]
pub struct Summary {
    pub total: usize,
    pub approved: usize,
    pub rejected: usize,
    pub needs_review: usize,
}

fn normalize(value: &str) -> String {
    value
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .to_lowercase()
}

fn field<'a>(fact: &'a Value, name: &str) -> Option<&'a str> {
    fact.get(name).and_then(Value::as_str)
}

fn result(status: &'static str, reason: impl Into<String>, fact: Value) -> ReviewItem {
    ReviewItem {
        status,
        reasons: vec![reason.into()],
        fact,
    }
}

fn evidence_matches(
    subject: &str,
    relationship: &str,
    object: &str,
    evidence: &str,
) -> Result<Option<bool>> {
    let subject = regex::escape(&subject.split_whitespace().collect::<Vec<_>>().join(" "));
    let object = regex::escape(&object.split_whitespace().collect::<Vec<_>>().join(" "));
    let pattern = match relationship {
        "province" => format!(r"\b{subject}\s+is\s+(?:a|an)\s+province\s+of\s+{object}\b"),
        "lives in" => format!(r"\b{subject}\s+lives?\s+in\s+{object}\b"),
        "located in" => format!(r"\b{subject}\s+is\s+located\s+in\s+{object}\b"),
        _ => return Ok(None),
    };
    let regex = RegexBuilder::new(&pattern).case_insensitive(true).build()?;
    Ok(Some(regex.is_match(evidence)))
}

fn review_fact(fact: Value) -> Result<ReviewItem> {
    if !fact.is_object() {
        return Ok(result("rejected", "Record is not a JSON object.", fact));
    }

    let missing = REQUIRED_FIELDS
        .iter()
        .filter(|&&name| field(&fact, name).is_none_or(|value| value.trim().is_empty()))
        .copied()
        .collect::<Vec<_>>();
    if !missing.is_empty() {
        return Ok(result(
            "rejected",
            format!("Missing or empty required fields: {}", missing.join(", ")),
            fact,
        ));
    }

    let subject = field(&fact, "subject")
        .unwrap()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ");
    let subject = subject
        .trim_matches(|ch: char| " .,:;!?".contains(ch))
        .to_string();
    let object = field(&fact, "object")
        .unwrap()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ");
    let object = object
        .trim_matches(|ch: char| " .,:;!?".contains(ch))
        .to_string();
    let relationship = normalize(field(&fact, "relationship").unwrap());
    let subject_words = subject.split_whitespace().collect::<Vec<_>>();

    if normalize(&subject) == normalize(&object) {
        return Ok(result(
            "rejected",
            "Subject and object are identical.",
            fact,
        ));
    }

    let first_word = subject_words.first().copied().unwrap_or("").to_lowercase();
    if FRAGMENT_STARTS.contains(&first_word.as_str()) {
        return Ok(result(
            "rejected",
            format!("Subject begins with '{first_word}', suggesting a sentence fragment."),
            fact,
        ));
    }

    let lowered_subject = format!(" {} ", normalize(&subject));
    if let Some(marker) = FRAGMENT_MARKERS
        .iter()
        .find(|marker| lowered_subject.contains(&format!(" {marker} ")))
    {
        return Ok(result(
            "rejected",
            format!(
                "Subject contains clause marker '{marker}', suggesting it is not an entity name."
            ),
            fact,
        ));
    }

    if subject_words.len() > 7 {
        return Ok(result(
            "rejected",
            "Subject is longer than seven words and is likely a sentence fragment.",
            fact,
        ));
    }

    if PRONOUN_OBJECTS.contains(&normalize(&object).as_str()) || normalize(&object) == "that" {
        return Ok(result(
            "rejected",
            "Object is a pronoun rather than an identifiable place or entity.",
            fact,
        ));
    }

    if !["province", "lives in", "located in"].contains(&relationship.as_str()) {
        return Ok(result(
            "needs_review",
            format!(
                "No evidence-checking rule exists for relationship '{}'.",
                field(&fact, "relationship").unwrap()
            ),
            fact,
        ));
    }

    let mut reasons = Vec::new();
    if subject_words.len() > 5 {
        reasons.push(
            "Subject is unusually long and should be checked as a possible entity name."
                .to_string(),
        );
    }

    match evidence_matches(
        &subject,
        &relationship,
        &object,
        field(&fact, "evidence").unwrap(),
    )? {
        Some(false) => reasons.push(
            "Evidence does not explicitly support the extracted subject–relationship–object triple."
                .to_string(),
        ),
        None => reasons.push("Evidence could not be checked automatically.".to_string()),
        Some(true) => {}
    }

    if reasons.is_empty() {
        Ok(result(
            "approved",
            "Required fields are valid and the evidence explicitly supports the extracted relationship.",
            fact,
        ))
    } else {
        Ok(ReviewItem {
            status: "needs_review",
            reasons,
            fact,
        })
    }
}

pub fn review_file(input: &Path, output: &Path) -> Result<Summary> {
    let input_value: Value = serde_json::from_slice(&std::fs::read(input)?)?;
    let facts = input_value.as_array().cloned().ok_or_else(|| {
        anyhow::anyhow!("Knowledge base must contain a JSON list of candidate facts.")
    })?;

    let mut counts = BTreeMap::from([
        ("approved", 0usize),
        ("rejected", 0usize),
        ("needs_review", 0usize),
    ]);
    let mut results = Vec::with_capacity(facts.len());
    for fact in facts {
        let item = review_fact(fact)?;
        *counts.get_mut(item.status).unwrap() += 1;
        results.push(item);
    }

    let summary = Summary {
        total: results.len(),
        approved: counts["approved"],
        rejected: counts["rejected"],
        needs_review: counts["needs_review"],
    };
    let report = ReviewReport {
        cleaner_version: "0.1.0",
        review_policy: "rule_based_evidence_checks",
        summary: Summary {
            total: summary.total,
            approved: summary.approved,
            rejected: summary.rejected,
            needs_review: summary.needs_review,
        },
        results,
    };

    if let Some(parent) = output.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let temporary = output.with_extension("json.tmp");
    std::fs::write(&temporary, serde_json::to_vec_pretty(&report)?)?;
    std::fs::rename(temporary, output)?;
    Ok(summary)
}
