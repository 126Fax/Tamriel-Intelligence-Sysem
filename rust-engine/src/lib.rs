//! Experimental Rust processing primitives.
//!
//! The first comparison targets are deliberately narrow:
//! - streaming MediaWiki XML page extraction from .bz2 dumps;
//! - conservative sentence-pattern fact extraction.
//!
//! Python remains the production orchestrator. This crate is not wired into
//! the production pipeline until parity and benchmark results justify it.

use quick_xml::events::Event;
use quick_xml::Reader;
use regex::Regex;
use serde::{Deserialize, Serialize};
use std::io::BufRead;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct PageRecord {
    pub page_id: String,
    pub title: String,
    pub namespace: String,
    pub revision_id: String,
    pub text: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PageText {
    pub page_id: i64,
    pub title: String,
    pub text: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct WikiStats {
    pub page_id: i64,
    pub template_count: usize,
    pub wikilink_count: usize,
    pub heading_count: usize,
    pub tag_count: usize,
}

/// Lightweight regex candidate for structural counts. Nested templates and
/// complex tag syntax are known limitations; parity must be measured.
pub fn count_wikitext_structures(page: &PageText) -> WikiStats {
    let templates = Regex::new(r"(?s)\{\{.*?\}\}").unwrap();
    let links = Regex::new(r"(?s)\[\[.*?\]\]").unwrap();
    let headings = Regex::new(r"(?m)^={1,6}[^\r\n]*?={1,6}\s*$").unwrap();
    let tags = Regex::new(r"(?i)<[a-z][^>]*>").unwrap();
    let template_matches: Vec<_> = templates.find_iter(&page.text).collect();
    WikiStats {
        page_id: page.page_id,
        template_count: template_matches.len(),
        template_parameter_count: template_matches.iter().map(|item| item.as_str().matches('|').count()).sum(),
        wikilink_count: links.find_iter(&page.text).count(),
        heading_count: headings.find_iter(&page.text).count(),
        tag_count: tags.find_iter(&page.text).count(),
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CandidateFact {
    pub source_page_id: i64,
    pub source_page: String,
    pub subject: String,
    pub relationship: String,
    pub object: String,
    pub evidence: String,
    pub extraction_method: String,
    pub confidence: f64,
}

/// Stream MediaWiki export pages from any buffered XML reader.
/// Only the current page is retained in memory.
pub fn read_pages<R: BufRead>(input: R, limit: Option<usize>) -> Result<Vec<PageRecord>, String> {
    let mut pages = Vec::new();
    for_each_page(input, limit, |page| { pages.push(page); Ok(()) })?;
    Ok(pages)
}

/// Process each page as soon as it is complete, keeping memory bounded by one page.
pub fn for_each_page<R, F>(input: R, limit: Option<usize>, mut callback: F) -> Result<(), String>
where
    R: BufRead,
    F: FnMut(PageRecord) -> Result<(), String>,
{
    let mut reader = Reader::from_reader(input);
    reader.config_mut().trim_text(false);

    let mut buf = Vec::new();
    let mut page_count = 0usize;
    let mut in_page = false;
    let mut in_revision = false;
    let mut page_id = String::new();
    let mut title = String::new();
    let mut namespace = String::new();
    let mut revision_id = String::new();
    let mut revision_text: Option<String> = None;
    let mut leaf: Option<String> = None;
    let mut leaf_text = String::new();
    let mut stack: Vec<String> = Vec::new();

    loop {
        match reader.read_event_into(&mut buf) {
            Ok(Event::Start(event)) => {
                let name = String::from_utf8_lossy(event.local_name().as_ref()).into_owned();
                if name == "page" {
                    in_page = true;
                    page_id.clear();
                    title.clear();
                    namespace.clear();
                    revision_id.clear();
                    revision_text = None;
                } else if in_page && name == "revision" {
                    in_revision = true;
                    revision_id.clear();
                    revision_text = None;
                } else if in_page && matches!(name.as_str(), "title" | "ns" | "id" | "text") {
                    // Match only direct children, as Element.findtext() does in Python.
                    let parent = stack.last().map(String::as_str).unwrap_or("");
                    let is_page_field = parent == "page" && matches!(name.as_str(), "title" | "ns" | "id");
                    let is_revision_field = parent == "revision" && matches!(name.as_str(), "id" | "text");
                    if is_page_field || is_revision_field {
                        leaf = Some(name.clone());
                        leaf_text.clear();
                    }
                }
                stack.push(name);
            }
            Ok(Event::Empty(event)) => {
                let name = event.local_name();
                let parent = stack.last().map(String::as_str).unwrap_or("");
                if in_page && parent == "revision" && name.as_ref() == b"text" {
                    revision_text = Some(String::new());
                }
            }
            Ok(Event::Text(event)) => {
                if leaf.is_some() {
                    let decoded = event.decode().map_err(|e| e.to_string())?;
                    let unescaped = quick_xml::escape::unescape(&decoded)
                        .map_err(|e| e.to_string())?;
                    leaf_text.push_str(&unescaped);
                }
            }
            Ok(Event::CData(event)) => {
                if leaf.is_some() {
                    leaf_text.push_str(&event.decode().map_err(|e| e.to_string())?);
                }
            }
            Ok(Event::End(event)) => {
                let name = event.local_name();
                if let Some(current_leaf) = leaf.as_deref() {
                    if name.as_ref() == current_leaf.as_bytes() {
                        match current_leaf {
                            "title" => title = leaf_text.clone(),
                            "ns" => namespace = leaf_text.clone(),
                            "id" if in_revision => revision_id = leaf_text.clone(),
                            "id" => page_id = leaf_text.clone(),
                            "text" => revision_text = Some(leaf_text.clone()),
                            _ => {}
                        }
                        leaf = None;
                        leaf_text.clear();
                    }
                }

                if name.as_ref() == b"revision" && in_page {
                    in_revision = false;
                } else if name.as_ref() == b"page" && in_page {
                    if let Some(text) = revision_text.take() {
                        callback(PageRecord {
                            page_id: page_id.clone(),
                            title: title.clone(),
                            namespace: namespace.clone(),
                            revision_id: revision_id.clone(),
                            text,
                        })?;
                        page_count += 1;
                        if limit.is_some_and(|maximum| page_count >= maximum) {
                            return Ok(());
                        }
                    }
                    in_page = false;
                    in_revision = false;
                    leaf = None;
                }
                stack.pop();
            }
            Ok(Event::Eof) => break,
            Ok(_) => {}
            Err(error) => return Err(format!("XML parse error: {error}")),
        }
        buf.clear();
    }

    Ok(())
}

fn split_sentences(text: &str) -> Vec<&str> {
    let mut sentences = Vec::new();
    let mut start = 0usize;
    let chars: Vec<(usize, char)> = text.char_indices().collect();
    for (index, (byte_pos, ch)) in chars.iter().enumerate() {
        let next_is_space = chars.get(index + 1).map(|(_, next)| next.is_whitespace()).unwrap_or(true);
        if *ch == '\\n' || (matches!(ch, '.' | '!' | '?') && next_is_space) {
            let end = if *ch == '\\n' { *byte_pos } else { byte_pos + ch.len_utf8() };
            if end > start { sentences.push(&text[start..end]); }
            start = byte_pos + ch.len_utf8();
            while start < text.len() {
                let next = text[start..].chars().next().unwrap();
                if !next.is_whitespace() { break; }
                start += next.len_utf8();
            }
        }
    }
    if start < text.len() { sentences.push(&text[start..]); }
    sentences
}

fn clean_entity(value: &str) -> String {
    let wiki_link = Regex::new(r"\[\[([^]|]+)(?:\|([^]]+))?\]\]").unwrap();
    let whitespace = Regex::new(r"\s+").unwrap();
    let article = Regex::new(r"(?i)^(the|a|an)\s+").unwrap();
    let value = wiki_link.replace_all(value, |captures: &regex::Captures| {
        captures.get(2).or_else(|| captures.get(1)).map(|m| m.as_str()).unwrap_or("").to_string()
    });
    let value = whitespace.replace_all(&value, " ");
    let value = value.trim_matches(|c: char| {
        c.is_whitespace() || ".,:;!?()[]{}'\"".contains(c)
    });
    article.replace(value, "").trim().to_string()
}

/// Extract the same three explicit sentence relationships used by the
/// current Python baseline. Province-catalogue matching remains Python-side.
pub fn extract_candidate_facts(page: &PageText) -> Vec<CandidateFact> {
    let patterns = [
        (
            "province",
            Regex::new(r"(?i)\b(?P<subject>[A-Z][\w' -]{0,70}?)\s+is\s+(?:a|an)\s+province\s+of\s+(?P<object>[A-Z][\w' -]{0,70}?)(?:[.!?;]|$)").unwrap(),
            0.95,
        ),
        (
            "lives in",
            Regex::new(r"(?i)\b(?P<subject>[A-Z][\w' -]{0,70}?)\s+lives?\s+in\s+(?P<object>[A-Z][\w' -]{0,70}?)(?:[.!?;]|$)").unwrap(),
            0.90,
        ),
        (
            "located in",
            Regex::new(r"(?i)\b(?P<subject>[A-Z][\w' -]{0,70}?)\s+is\s+located\s+in\s+(?P<object>[A-Z][\w' -]{0,70}?)(?:[.!?;]|$)").unwrap(),
            0.90,
        ),
    ];

    let mut facts = Vec::new();
    for sentence in split_sentences(&page.text) {
        let evidence = Regex::new(r"\s+").unwrap().replace_all(sentence, " ").trim().to_string();
        if evidence.is_empty() { continue; }
        for (relationship, pattern, confidence) in &patterns {
            for captures in pattern.captures_iter(&evidence) {
                let subject = clean_entity(captures.name("subject").unwrap().as_str());
                let object = clean_entity(captures.name("object").unwrap().as_str());
                if subject.is_empty() || object.is_empty() || subject.eq_ignore_ascii_case(&object) {
                    continue;
                }
                facts.push(CandidateFact {
                    source_page_id: page.page_id,
                    source_page: page.title.clone(),
                    subject,
                    relationship: (*relationship).to_string(),
                    object,
                    evidence: evidence.chars().take(2000).collect(),
                    extraction_method: "explicit_sentence_pattern_v1".to_string(),
                    confidence: *confidence,
                });
            }
        }
    }

    let mut unique = Vec::new();
    for fact in facts {
        if !unique.iter().any(|existing: &CandidateFact| {
            existing.subject.eq_ignore_ascii_case(&fact.subject)
                && existing.relationship == fact.relationship
                && existing.object.eq_ignore_ascii_case(&fact.object)
                && existing.evidence == fact.evidence
        }) {
            unique.push(fact);
        }
    }
    unique
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    const XML: &str = r#"<?xml version="1.0"?>
    <mediawiki xmlns="http://www.mediawiki.org/xml/export-0.10/">
      <page><title>Test &amp; Example</title><ns>0</ns><id>101</id>
        <revision><id>201</id><text>A &amp; B &lt;tag&gt; [[Skyrim|the north]].</text></revision>
        <revision><id>202</id><text>Latest revision text.</text></revision>
      </page>
    </mediawiki>"#;

    #[test]
    fn extracts_latest_revision_and_decodes_entities() {
        let pages = read_pages(Cursor::new(XML.as_bytes()), None).unwrap();
        assert_eq!(pages.len(), 1);
        assert_eq!(pages[0].page_id, "101");
        assert_eq!(pages[0].title, "Test & Example");
        assert_eq!(pages[0].revision_id, "202");
        assert_eq!(pages[0].text, "Latest revision text.");
    }

    #[test]
    fn respects_page_limit() {
        let pages = read_pages(Cursor::new(XML.as_bytes()), Some(1)).unwrap();
        assert_eq!(pages.len(), 1);
    }

    #[test]
    fn extracts_explicit_relationships() {
        let page = PageText {
            page_id: 42,
            title: "Example".to_string(),
            text: "Nords live in Skyrim. Vivec is located in Morrowind.".to_string(),
        };
        let facts = extract_candidate_facts(&page);
        assert_eq!(facts.len(), 2);
        assert!(facts.iter().any(|fact| fact.relationship == "lives in"));
        assert!(facts.iter().any(|fact| fact.relationship == "located in"));
    }
}
