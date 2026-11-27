//! Data-driven discovery of recurring sentence structures.
//!
//! This module does not assign semantic meanings to patterns. It compares
//! evidence sentences already stored in candidate_facts and discovers
//! recurring token sequences with variable spans. The resulting patterns are
//! hypotheses for inspection, not verified lore facts.

use anyhow::Result;
use rusqlite::Connection;
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DiscoveredPattern {
    pub pattern: String,
    pub support: usize,
    pub examples: Vec<String>,
}

fn tokens(sentence: &str) -> Vec<String> {
    sentence
        .split_whitespace()
        .map(|token| {
            token
                .trim_matches(|character: char| character.is_ascii_punctuation())
                .to_lowercase()
        })
        .filter(|token| !token.is_empty())
        .collect()
}

fn lcs_matches(first: &[String], second: &[String]) -> Vec<(usize, usize)> {
    let mut lengths = vec![vec![0usize; second.len() + 1]; first.len() + 1];

    for i in (0..first.len()).rev() {
        for j in (0..second.len()).rev() {
            lengths[i][j] = if first[i] == second[j] {
                1 + lengths[i + 1][j + 1]
            } else {
                lengths[i + 1][j].max(lengths[i][j + 1])
            };
        }
    }

    let (mut i, mut j) = (0, 0);
    let mut matches = Vec::new();
    while i < first.len() && j < second.len() {
        if first[i] == second[j] {
            matches.push((i, j));
            i += 1;
            j += 1;
        } else if lengths[i + 1][j] >= lengths[i][j + 1] {
            i += 1;
        } else {
            j += 1;
        }
    }
    matches
}

fn pair_pattern(first: &[String], second: &[String]) -> (Vec<String>, usize, bool) {
    let matches = lcs_matches(first, second);
    let mut pattern = Vec::new();
    let (mut first_cursor, mut second_cursor) = (0, 0);

    for (first_index, second_index) in matches {
        if first_index > first_cursor || second_index > second_cursor {
            pattern.push("[VARIABLE]".to_string());
        }
        pattern.push(first[first_index].clone());
        first_cursor = first_index + 1;
        second_cursor = second_index + 1;
    }

    if first_cursor < first.len() || second_cursor < second.len() {
        pattern.push("[VARIABLE]".to_string());
    }

    let fixed_tokens = pattern.iter().filter(|token| token.as_str() != "[VARIABLE]").count();
    let has_variable = pattern.iter().any(|token| token == "[VARIABLE]");
    (pattern, fixed_tokens, has_variable)
}

/// Discover shared token patterns from a collection of evidence sentences.
pub fn discover_shared_patterns(
    sentences: &[String],
    minimum_support: usize,
    minimum_fixed_tokens: usize,
) -> Vec<DiscoveredPattern> {
    if minimum_support < 2 || minimum_fixed_tokens == 0 {
        return Vec::new();
    }

    let unique: Vec<String> = sentences
        .iter()
        .map(|sentence| sentence.trim().to_string())
        .filter(|sentence| !sentence.is_empty())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect();
    let tokenised: Vec<Vec<String>> = unique.iter().map(|sentence| tokens(sentence)).collect();
    let mut discovered: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();

    for first_index in 0..tokenised.len() {
        for second_index in (first_index + 1)..tokenised.len() {
            let (pattern, fixed_tokens, has_variable) =
                pair_pattern(&tokenised[first_index], &tokenised[second_index]);
            if fixed_tokens < minimum_fixed_tokens || !has_variable {
                continue;
            }
            discovered
                .entry(pattern.join(" "))
                .or_default()
                .extend([
                    unique[first_index].clone(),
                    unique[second_index].clone(),
                ]);
        }
    }

    discovered
        .into_iter()
        .filter_map(|(pattern, examples)| {
            (examples.len() >= minimum_support).then(|| DiscoveredPattern {
                pattern,
                support: examples.len(),
                examples: examples.into_iter().take(5).collect(),
            })
        })
        .collect()
}

/// Read a bounded sample of stored evidence and discover recurring structures.
pub fn discover_database_patterns(
    database_path: &Path,
    sample_limit: usize,
    minimum_support: usize,
    minimum_fixed_tokens: usize,
) -> Result<Vec<DiscoveredPattern>> {
    let connection = Connection::open(database_path)?;
    let mut statement = connection.prepare(
        "SELECT DISTINCT evidence_text
         FROM candidate_facts
         WHERE evidence_text IS NOT NULL AND trim(evidence_text) <> ''
         ORDER BY evidence_text
         LIMIT ?1",
    )?;
    let rows = statement.query_map([sample_limit as i64], |row| row.get::<_, String>(0))?;
    let mut sentences = Vec::new();
    for row in rows {
        sentences.push(row?);
    }
    Ok(discover_shared_patterns(
        &sentences,
        minimum_support,
        minimum_fixed_tokens,
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn discovers_a_repeated_sentence_structure() {
        let sentences = vec![
            "Skyrim is a province of Tamriel".to_string(),
            "Morrowind is a province of Tamriel".to_string(),
            "Cyrodiil is a province of Tamriel".to_string(),
        ];
        let patterns = discover_shared_patterns(&sentences, 2, 3);
        assert!(patterns.iter().any(|pattern| {
            pattern.pattern == "[VARIABLE] is a province of tamriel"
                && pattern.support == 3
        }));
    }

    #[test]
    fn ignores_patterns_without_enough_support() {
        let sentences = vec![
            "Skyrim is a province of Tamriel".to_string(),
            "Dragons live in Skyrim".to_string(),
        ];
        assert!(discover_shared_patterns(&sentences, 2, 3).is_empty());
    }
}
