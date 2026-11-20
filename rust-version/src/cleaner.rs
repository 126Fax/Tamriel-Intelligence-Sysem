use anyhow::Result;
use serde::Serialize;
use std::path::Path;

#[derive(Serialize)]
struct ReviewItem {
    status: String,
    reason: String,
    fact: serde_json::Value,
}

#[derive(Serialize)]
struct ReviewReport {
    summary: Summary,
    decisions: Vec<ReviewItem>,
}

#[derive(Serialize)]
pub struct Summary {
    pub total: usize,
    pub approved: usize,
    pub rejected: usize,
    pub needs_review: usize,
}

pub fn review_file(input: &Path, output: &Path) -> Result<Summary> {
    let facts: Vec<serde_json::Value> = serde_json::from_slice(&std::fs::read(input)?)?;
    let mut decisions = Vec::new();
    let (mut approved,mut rejected,mut needs_review) = (0,0,0);
    for fact in facts {
        let subject = fact.get("subject").and_then(|v| v.as_str()).unwrap_or("");
        let relation = fact.get("relationship").and_then(|v| v.as_str()).unwrap_or("");
        let object = fact.get("object").and_then(|v| v.as_str()).unwrap_or("");
        let evidence = fact.get("evidence").and_then(|v| v.as_str()).unwrap_or("");
        let confidence = fact.get("confidence").and_then(|v| v.as_f64()).unwrap_or(0.0);
        let (status,reason) = if subject.trim().is_empty() || relation.trim().is_empty() || object.trim().is_empty() {
            rejected += 1; ("rejected","Missing subject, relationship or object.")
        } else if evidence.trim().is_empty() {
            needs_review += 1; ("needs_review","No source evidence was supplied.")
        } else if confidence >= 0.90 {
            approved += 1; ("approved","Required fields and evidence are present; confidence meets the prototype threshold.")
        } else {
            needs_review += 1; ("needs_review","Candidate needs human review.")
        };
        decisions.push(ReviewItem { status: status.to_string(), reason: reason.to_string(), fact });
    }
    let summary = Summary { total: decisions.len(), approved, rejected, needs_review };
    let report = ReviewReport {
        summary: Summary { total: summary.total, approved, rejected, needs_review },
        decisions,
    };
    if let Some(parent) = output.parent() { std::fs::create_dir_all(parent)?; }
    std::fs::write(output,serde_json::to_vec_pretty(&report)?)?;
    Ok(summary)
}
