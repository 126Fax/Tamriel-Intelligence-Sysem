//! Read-only comparison of the legacy and configurable Bottom-Up relationship extractors.
//!
//! The source SQLite database is opened read-only. The command analyses the same
//! stored pages with both extractors and writes a separate JSON audit report.

use crate::config::project_root;
use crate::models::CandidateFact;
use crate::wiki::{analyse_wikitext, FactExtractor};
use anyhow::{Context, Result};
use regex::Regex;
use rusqlite::{Connection, OpenFlags};
use serde::Serialize;
use std::collections::{BTreeMap, HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::time::Instant;

static LEGACY_PATTERNS: &[(&str, &str, f64)] = &[
    ("province", r"(?i)\b(?P<subject>[A-Z][\w' -]{0,70}?)\s+is\s+(?:a|an)\s+province\s+of\s+(?P<object>[A-Z][\w' -]{0,70}?)(?:[.!?;]|$)", 0.95),
    ("lives in", r"(?i)\b(?P<subject>[A-Z][\w' -]{0,70}?)\s+lives?\s+in\s+(?P<object>[A-Z][\w' -]{0,70}?)(?:[.!?;]|$)", 0.90),
    ("located in", r"(?i)\b(?P<subject>[A-Z][\w' -]{0,70}?)\s+is\s+located\s+in\s+(?P<object>[A-Z][\w' -]{0,70}?)(?:[.!?;]|$)", 0.90),
];

#[derive(Debug, Clone, Serialize)]
pub struct FactExample {
    pub source_page_id: i64,
    pub source_page: String,
    pub subject: String,
    pub relationship: String,
    pub object: String,
    pub evidence: String,
}

impl From<&CandidateFact> for FactExample {
    fn from(f: &CandidateFact) -> Self {
        Self {
            source_page_id: f.source_page_id,
            source_page: f.source_page.clone(),
            subject: f.subject.clone(),
            relationship: f.relationship.clone(),
            object: f.object.clone(),
            evidence: f.evidence.clone(),
        }
    }
}

#[derive(Debug, Serialize)]
pub struct RelationshipComparisonReport {
    pub report_version: u32,
    pub dump_id: i64,
    pub database: String,
    pub pages_compared: u64,
    pub legacy_fact_count: usize,
    pub expanded_fact_count: usize,
    pub added_fact_count: usize,
    pub removed_fact_count: usize,
    pub legacy_seconds: f64,
    pub expanded_seconds: f64,
    pub legacy_facts_per_second: f64,
    pub expanded_facts_per_second: f64,
    pub legacy_relationship_counts: BTreeMap<String, usize>,
    pub expanded_relationship_counts: BTreeMap<String, usize>,
    pub repeated_triple_count_legacy: usize,
    pub repeated_triple_count_expanded: usize,
    pub added_examples: Vec<FactExample>,
    pub removed_examples: Vec<FactExample>,
    pub notes: Vec<String>,
}

fn clean_legacy_entity(value: &str) -> String {
    let compact = value.split_whitespace().collect::<Vec<_>>().join(" ");
    let trimmed = compact.trim_matches(|c: char| c.is_whitespace() || ".,:;!?()[]{}'\"".contains(c));
    Regex::new(r"(?i)^(the|a|an)\s+")
        .expect("constant article regex is valid")
        .replace(trimmed, "")
        .trim()
        .to_string()
}

fn split_sentences(text: &str) -> Vec<&str> {
    let mut sentences = Vec::new();
    let mut start = 0usize;
    let chars = text.char_indices().collect::<Vec<_>>();
    for (index, (position, character)) in chars.iter().enumerate() {
        let next_is_space = chars.get(index + 1)
            .map(|(_, next)| next.is_whitespace()).unwrap_or(true);
        if *character == '\n' || (matches!(character, '.' | '!' | '?') && next_is_space) {
            let end = position + character.len_utf8();
            if end > start { sentences.push(&text[start..end]); }
            start = end;
            while start < text.len() {
                let next = text[start..].chars().next().expect("valid character boundary");
                if !next.is_whitespace() { break; }
                start += next.len_utf8();
            }
        }
    }
    if start < text.len() { sentences.push(&text[start..]); }
    sentences
}

struct LegacyFactExtractor {
    patterns: Vec<(String, Regex, f64)>,
    province_patterns: Vec<(String, [Regex; 3])>,
}

impl LegacyFactExtractor {
    fn new(provinces: &[String]) -> Self {
        let patterns = LEGACY_PATTERNS.iter().map(|(relationship, pattern, confidence)| {
            ((*relationship).to_string(), Regex::new(pattern).expect("legacy regex is valid"), *confidence)
        }).collect();
        let province_patterns = provinces.iter().map(|province| {
            let escaped = regex::escape(province);
            let contexts = [
                format!(r"(?i)\b{escaped}\b.{{0,500}}\b(?:one of the |among the )?(?:nine )?provinces? of Tamriel\b"),
                format!(r"(?i)\bprovinces? of Tamriel\b.{{0,500}}\b{escaped}\b"),
                format!(r"(?i)\bTamriel['’]s (?:nine )?provinces?\b.{{0,500}}\b{escaped}\b"),
            ];
            (province.clone(), contexts.map(|p| Regex::new(&p).expect("province regex is valid")))
        }).collect();
        Self { patterns, province_patterns }
    }

    fn extract_facts(&self, text: &str, page_id: i64, title: &str) -> Vec<CandidateFact> {
        let mut facts = Vec::new();
        for raw in split_sentences(text) {
            let sentence = raw.split_whitespace().collect::<Vec<_>>().join(" ");
            if sentence.is_empty() { continue; }
            for (relationship, pattern, confidence) in &self.patterns {
                for captures in pattern.captures_iter(&sentence) {
                    let subject = clean_legacy_entity(captures.name("subject").unwrap().as_str());
                    let object = clean_legacy_entity(captures.name("object").unwrap().as_str());
                    if subject.is_empty() || object.is_empty() || subject.eq_ignore_ascii_case(&object) { continue; }
                    facts.push(CandidateFact {
                        source_page_id: page_id, source_page: title.to_string(),
                        subject, relationship: relationship.clone(), object,
                        evidence: sentence.chars().take(2000).collect(),
                        extraction_method: "explicit_sentence_pattern_v1".to_string(),
                        confidence: *confidence,
                    });
                }
            }
            for (province, contexts) in &self.province_patterns {
                if contexts.iter().any(|pattern| pattern.is_match(&sentence)) {
                    facts.push(CandidateFact {
                        source_page_id: page_id, source_page: title.to_string(),
                        subject: province.clone(), relationship: "province of".to_string(),
                        object: "Tamriel".to_string(),
                        evidence: sentence.chars().take(2000).collect(),
                        extraction_method: "province_reference_context_v1".to_string(),
                        confidence: 0.92,
                    });
                }
            }
        }
        let mut unique = Vec::new();
        for fact in facts {
            if !unique.iter().any(|old: &CandidateFact| {
                old.subject.eq_ignore_ascii_case(&fact.subject)
                    && old.relationship == fact.relationship
                    && old.object.eq_ignore_ascii_case(&fact.object)
                    && old.evidence == fact.evidence
            }) { unique.push(fact); }
        }
        unique
    }
}

fn normalized(value: &str) -> String {
    value.split_whitespace().collect::<Vec<_>>().join(" ").to_lowercase()
}

fn identity(f: &CandidateFact) -> (i64, String, String, String, String) {
    (f.source_page_id, normalized(&f.subject), normalized(&f.relationship),
     normalized(&f.object), normalized(&f.evidence))
}

fn relationship_counts(facts: &[CandidateFact]) -> BTreeMap<String, usize> {
    let mut counts = BTreeMap::new();
    for fact in facts { *counts.entry(fact.relationship.clone()).or_insert(0) += 1; }
    counts
}

fn repeated_triples(facts: &[CandidateFact]) -> usize {
    let mut counts: HashMap<(String, String, String), usize> = HashMap::new();
    for f in facts {
        *counts.entry((normalized(&f.subject), normalized(&f.relationship), normalized(&f.object))).or_insert(0) += 1;
    }
    counts.values().map(|count| count.saturating_sub(1)).sum()
}

/// Compare both extractors on the same first N pages without changing the database.
pub fn compare_database(
    database_path: &Path,
    dump_id: i64,
    limit: usize,
    output_path: Option<&Path>,
) -> Result<RelationshipComparisonReport> {
    if limit == 0 { anyhow::bail!("comparison page limit must be at least 1"); }
    let connection = Connection::open_with_flags(database_path, OpenFlags::SQLITE_OPEN_READ_ONLY)
        .with_context(|| format!("opening source database read-only: {}", database_path.display()))?;
    let exists: bool = connection.query_row(
        "SELECT EXISTS(SELECT 1 FROM source_dumps WHERE dump_id=?)", [dump_id], |row| row.get(0)
    )?;
    if !exists { anyhow::bail!("dump ID {dump_id} does not exist"); }

    let provinces_path = project_root().join("rust-version/data/reference/provinces.json");
    let provinces: Vec<String> = serde_json::from_slice(&std::fs::read(&provinces_path)?)
        .with_context(|| format!("reading {}", provinces_path.display()))?;
    let expanded = FactExtractor::new(&provinces);
    let legacy = LegacyFactExtractor::new(&provinces);
    let mut statement = connection.prepare(
        "SELECT page_id,title,page_text FROM pages WHERE dump_id=? ORDER BY page_id LIMIT ?"
    )?;
    let mut rows = statement.query(rusqlite::params![dump_id, limit as i64])?;
    let mut legacy_facts = Vec::new();
    let mut expanded_facts = Vec::new();
    let mut pages_compared = 0u64;
    let mut legacy_seconds = 0.0f64;
    let mut expanded_seconds = 0.0f64;
    while let Some(row) = rows.next()? {
        let page_id: i64 = row.get(0)?;
        let title: String = row.get(1)?;
        let source_text: String = row.get(2)?;
        let wiki = analyse_wikitext(page_id, &title, &source_text);
        let legacy_started = Instant::now();
        legacy_facts.extend(legacy.extract_facts(&wiki.plain_text, page_id, &title));
        legacy_seconds += legacy_started.elapsed().as_secs_f64();
        let expanded_started = Instant::now();
        expanded_facts.extend(expanded.extract_facts(&wiki.plain_text, page_id, &title));
        expanded_seconds += expanded_started.elapsed().as_secs_f64();
        pages_compared += 1;
    }

    let legacy_set = legacy_facts.iter().map(identity).collect::<HashSet<_>>();
    let expanded_set = expanded_facts.iter().map(identity).collect::<HashSet<_>>();
    let added = expanded_facts.iter().filter(|f| !legacy_set.contains(&identity(f))).collect::<Vec<_>>();
    let removed = legacy_facts.iter().filter(|f| !expanded_set.contains(&identity(f))).collect::<Vec<_>>();
    let rate = |count: usize, seconds: f64| if seconds > 0.0 { count as f64 / seconds } else { 0.0 };
    let report = RelationshipComparisonReport {
        report_version: 1,
        dump_id,
        database: database_path.display().to_string(),
        pages_compared,
        legacy_fact_count: legacy_facts.len(),
        expanded_fact_count: expanded_facts.len(),
        added_fact_count: added.len(),
        removed_fact_count: removed.len(),
        legacy_seconds,
        expanded_seconds,
        legacy_facts_per_second: rate(legacy_facts.len(), legacy_seconds),
        expanded_facts_per_second: rate(expanded_facts.len(), expanded_seconds),
        legacy_relationship_counts: relationship_counts(&legacy_facts),
        expanded_relationship_counts: relationship_counts(&expanded_facts),
        repeated_triple_count_legacy: repeated_triples(&legacy_facts),
        repeated_triple_count_expanded: repeated_triples(&expanded_facts),
        added_examples: added.iter().take(100).map(|f| FactExample::from(*f)).collect(),
        removed_examples: removed.iter().take(100).map(|f| FactExample::from(*f)).collect(),
        notes: vec![
            "The SQLite source database was opened read-only; no source or derived tables were changed.".to_string(),
            "Both extractors received the same normalised plain text from the same stored pages.".to_string(),
            "Added and removed facts are matched by page, subject, relationship, object and evidence.".to_string(),
            "Repeated triple counts identify the same subject/relationship/object appearing across pages; they are not automatically errors.".to_string(),
            "Added examples are candidates for manual false-positive review, not confirmed false positives.".to_string(),
            "Timing figures are extraction-only and exclude shared page parsing; repeat runs for stable comparisons.".to_string(),
        ],
    };
    if let Some(path) = output_path {
        if let Some(parent) = path.parent().filter(|p| !p.as_os_str().is_empty()) { std::fs::create_dir_all(parent)?; }
        let json = serde_json::to_string_pretty(&report)?;
        std::fs::write(path, json).with_context(|| format!("writing {}", path.display()))?;
    }
    Ok(report)
}

pub fn default_report_path() -> PathBuf {
    project_root().join("rust-version/data/reports/relationship_comparison.json")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn expanded_extractor_is_compared_against_legacy_on_identical_text() {
        let provinces = vec!["Skyrim".to_string()];
        let text = concat!(
            "The Nords live in Skyrim. ",
            "Skyrim is one of the nine provinces of Tamriel. ",
            "Jagar Tharn was born in the Imperial City. ",
            "Ancano is a member of the Thalmor."
        );
        let legacy = LegacyFactExtractor::new(&provinces).extract_facts(text, 7, "Comparison fixture");
        let expanded = FactExtractor::new(&provinces).extract_facts(text, 7, "Comparison fixture");
        let legacy_ids = legacy.iter().map(identity).collect::<HashSet<_>>();
        let expanded_ids = expanded.iter().map(identity).collect::<HashSet<_>>();
        let added = expanded_ids.difference(&legacy_ids).count();
        let removed = legacy_ids.difference(&expanded_ids).count();

        assert!(legacy.len() >= 2, "legacy baseline should find the known geography facts");
        assert!(added >= 2, "expanded rules should add born-in and member-of facts; got {expanded:#?}");
        assert_eq!(removed, 0, "expanded rules should preserve the legacy fixture facts");
    }
    #[test]
    fn database_comparison_reads_the_same_pages_and_leaves_source_database_unchanged() {
        let directory = tempfile::tempdir().expect("temporary directory");
        let database_path = directory.path().join("comparison.db");
        let report_path = directory.path().join("report.json");
        {
            let connection = crate::database::connect(&database_path).expect("create schema");
            connection.execute(
                "INSERT INTO source_dumps(dump_id,source_name,import_status) VALUES(1,'comparison-fixture','completed')",
                [],
            ).expect("insert dump");
            connection.execute(
                "INSERT INTO pages(dump_id,page_id,title,namespace_id,namespace_name,revision_id,text_length,page_text)
                 VALUES(1,10,'Relationship fixture',0,'Main',1,160,
                 'The Nords live in Skyrim. Skyrim is one of the nine provinces of Tamriel. Jagar Tharn was born in the Imperial City. Ancano is a member of the Thalmor.')",
                [],
            ).expect("insert fixture page");
        }

        let report = compare_database(&database_path, 1, 50000, Some(&report_path))
            .expect("comparison should complete");
        assert_eq!(report.pages_compared, 1);
        assert!(report.added_fact_count >= 2, "expanded extractor should add new relation types");
        assert_eq!(report.removed_fact_count, 0, "legacy fixture facts should be retained");
        assert!(report_path.is_file(), "JSON comparison report should be written");

        let connection = rusqlite::Connection::open_with_flags(
            &database_path, rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY
        ).expect("reopen source database read-only");
        let pages: i64 = connection.query_row("SELECT COUNT(*) FROM pages", [], |row| row.get(0))
            .expect("count source pages");
        let facts: i64 = connection.query_row("SELECT COUNT(*) FROM candidate_facts", [], |row| row.get(0))
            .expect("count derived facts");
        assert_eq!(pages, 1, "comparison must not change source pages");
        assert_eq!(facts, 0, "comparison must not rebuild or write derived facts");
    }

}
