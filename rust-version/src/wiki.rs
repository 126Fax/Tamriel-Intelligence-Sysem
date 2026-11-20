use regex::Regex;
use std::sync::LazyLock;
use crate::models::CandidateFact;

static FACT_PATTERNS: LazyLock<Vec<(&'static str, Regex, f64)>> = LazyLock::new(|| vec![
    ("province", Regex::new(r"(?i)\b(?P<subject>[A-Z][\w' -]{0,70}?)\s+is\s+(?:a|an)\s+province\s+of\s+(?P<object>[A-Z][\w' -]{0,70}?)(?:[.!?;]|$)").unwrap(), 0.95),
    ("lives in", Regex::new(r"(?i)\b(?P<subject>[A-Z][\w' -]{0,70}?)\s+lives?\s+in\s+(?P<object>[A-Z][\w' -]{0,70}?)(?:[.!?;]|$)").unwrap(), 0.90),
    ("located in", Regex::new(r"(?i)\b(?P<subject>[A-Z][\w' -]{0,70}?)\s+is\s+located\s+in\s+(?P<object>[A-Z][\w' -]{0,70}?)(?:[.!?;]|$)").unwrap(), 0.90),
]);
static LINK_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\[\[([^]|]+)(?:\|([^]]+))?\]\]").unwrap());
static TAG_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"(?s)<[^>]*>").unwrap());
static TEMPLATE_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"(?s)\{\{.*?\}\}").unwrap());
static WHITESPACE_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\s+").unwrap());

#[derive(Debug, Clone)]
pub struct TemplateParameter {
    pub template_index: usize,
    pub template_name: String,
    pub parameter_index: usize,
    pub parameter_name: String,
    pub is_named: bool,
    pub value: String,
    pub raw_value: String,
    pub evidence: String,
}

#[derive(Debug, Clone)]
pub struct WikiLink {
    pub destination: String,
    pub display_text: String,
}

#[derive(Debug, Clone, Default)]
pub struct WikiAnalysis {
    pub template_count: usize,
    pub parameter_count: usize,
    pub link_count: usize,
    pub heading_count: usize,
    pub tag_count: usize,
    pub parameters: Vec<TemplateParameter>,
    pub links: Vec<WikiLink>,
    pub plain_text: String,
}

// Splits only on top-level separators, keeping nested templates and links together.
fn split_top_level(input: &str, separator: char) -> Vec<&str> {
    let mut parts = Vec::new();
    let mut start = 0usize;
    let mut braces = 0i32;
    let mut links = 0i32;
    let chars: Vec<(usize,char)> = input.char_indices().collect();
    let mut i = 0usize;
    while i < chars.len() {
        let (pos,ch) = chars[i];
        let next = chars.get(i+1).map(|(_,c)| *c);
        if ch == '{' && next == Some('{') { braces += 1; i += 1; }
        else if ch == '}' && next == Some('}') { braces = (braces-1).max(0); i += 1; }
        else if ch == '[' && next == Some('[') { links += 1; i += 1; }
        else if ch == ']' && next == Some(']') { links = (links-1).max(0); i += 1; }
        else if ch == separator && braces == 0 && links == 0 {
            parts.push(&input[start..pos]);
            start = pos + ch.len_utf8();
        }
        i += 1;
    }
    parts.push(&input[start..]);
    parts
}

// Finds outer template blocks while accounting for nested {{...}} pairs.
fn template_blocks(text: &str) -> Vec<&str> {
    let mut blocks: Vec<(usize, &str)> = Vec::new();
    let bytes = text.as_bytes();
    let mut stack: Vec<usize> = Vec::new();
    let mut i = 0usize;
    while i + 1 < bytes.len() {
        if bytes[i] == b'{' && bytes[i+1] == b'{' {
            stack.push(i);
            i += 2;
        } else if bytes[i] == b'}' && bytes[i+1] == b'}' {
            if let Some(start) = stack.pop() {
                blocks.push((start, &text[start..i+2]));
            }
            i += 2;
        } else {
            i += 1;
        }
    }
    blocks.sort_by_key(|(start, _)| *start);
    blocks.into_iter().map(|(_, block)| block).collect()
}

fn remove_templates(text: &str) -> String {
    let bytes = text.as_bytes();
    let mut output = String::new();
    let mut depth = 0usize;
    let mut i = 0usize;
    while i < bytes.len() {
        if i + 1 < bytes.len() && bytes[i] == b'{' && bytes[i+1] == b'{' {
            depth += 1;
            i += 2;
        } else if i + 1 < bytes.len() && bytes[i] == b'}' && bytes[i+1] == b'}' && depth > 0 {
            depth -= 1;
            i += 2;
        } else {
            let character = text[i..].chars().next().unwrap();
            if depth == 0 { output.push(character); }
            i += character.len_utf8();
        }
    }
    output
}

fn strip_markup(text: &str) -> String {
    let without_comments = Regex::new(r"(?s)<!--.*?-->").unwrap().replace_all(text, " ");
    let without_templates = remove_templates(&without_comments);
    let links = LINK_RE.replace_all(&without_templates, |captures: &regex::Captures| {
        captures.get(2).or_else(|| captures.get(1)).map(|m| m.as_str()).unwrap_or("").to_string()
    });
    let tags = TAG_RE.replace_all(&links, " ");
    let formatting = Regex::new(r"'{2,5}").unwrap().replace_all(&tags, "");
    WHITESPACE_RE.replace_all(&formatting, " ").trim().to_string()
}

fn clean_entity(value: &str) -> String {
    let linked = LINK_RE.replace_all(value, |captures: &regex::Captures| {
        captures.get(2).or_else(|| captures.get(1)).map(|m| m.as_str()).unwrap_or("").to_string()
    });
    let compact = WHITESPACE_RE.replace_all(&linked, " ");
    let trimmed = compact.trim_matches(|c: char| c.is_whitespace() || ".,:;!?()[]{}'\"".contains(c));
    Regex::new(r"(?i)^(the|a|an)\s+").unwrap().replace(trimmed, "").trim().to_string()
}

pub fn analyse_wikitext(page_id: i64, title: &str, text: &str) -> WikiAnalysis {
    let blocks = template_blocks(text);
    let mut result = WikiAnalysis::default();
    result.template_count = blocks.len();
    for (template_index, block) in blocks.iter().enumerate() {
        let inner = block.trim_start_matches("{{").trim_end_matches("}}");
        let parts = split_top_level(inner, '|');
        let template_name = parts.first().unwrap_or(&"").trim().replace('_', " ");
        for (parameter_index, raw) in parts.iter().skip(1).enumerate() {
            let pair = split_top_level(raw, '=');
            let (name, value, named) = if pair.len() > 1 {
                (pair[0].trim().to_string(), pair[1..].join("=").trim().to_string(), true)
            } else {
                ((parameter_index + 1).to_string(), raw.trim().to_string(), false)
            };
            let cleaned = strip_markup(&value);
            if !cleaned.is_empty() {
                result.parameters.push(TemplateParameter {
                    template_index, template_name: template_name.clone(),
                    parameter_index, parameter_name: name, is_named: named,
                    value: cleaned, raw_value: value, evidence: (*block).chars().take(10000).collect(),
                });
            }
        }
    }
    result.parameter_count = result.parameters.len();

    for captures in LINK_RE.captures_iter(text) {
        let destination = captures.get(1).map(|m| m.as_str().trim().to_string()).unwrap_or_default();
        let display_text = captures.get(2).map(|m| m.as_str().trim().to_string()).unwrap_or_else(|| destination.clone());
        if !destination.is_empty() {
            result.links.push(WikiLink { destination, display_text });
        }
    }
    result.link_count = result.links.len();
    result.heading_count = text.lines().filter(|line| {
        let trimmed = line.trim();
        let count = trimmed.chars().take_while(|c| *c == '=').count();
        count >= 1 && count <= 6 && trimmed.ends_with(&"=".repeat(count))
    }).count();
    result.tag_count = TAG_RE.find_iter(text).count();
    result.plain_text = strip_markup(text);
    let _ = (page_id, title);
    result
}

pub fn extract_facts(plain_text: &str, page_id: i64, title: &str, provinces: &[String]) -> Vec<CandidateFact> {
    let mut facts = Vec::new();
    let mut sentence_ranges = Vec::new();
    let mut start = 0usize;
    let chars: Vec<(usize, char)> = plain_text.char_indices().collect();
    for (index, (position, character)) in chars.iter().enumerate() {
        let next_is_space = chars.get(index + 1)
            .map(|(_, next)| next.is_whitespace()).unwrap_or(true);
        if *character == '\n' || (matches!(character, '.' | '!' | '?') && next_is_space) {
            let end = position + character.len_utf8();
            if end > start { sentence_ranges.push(&plain_text[start..end]); }
            start = end;
            while start < plain_text.len() {
                let next = plain_text[start..].chars().next().unwrap();
                if !next.is_whitespace() { break; }
                start += next.len_utf8();
            }
        }
    }
    if start < plain_text.len() { sentence_ranges.push(&plain_text[start..]); }
    for raw_sentence in sentence_ranges {
        let sentence = WHITESPACE_RE.replace_all(raw_sentence, " ").trim().to_string();
        if sentence.is_empty() { continue; }
        for (relationship, pattern, confidence) in FACT_PATTERNS.iter() {
            for captures in pattern.captures_iter(&sentence) {
                let subject = clean_entity(captures.name("subject").unwrap().as_str());
                let object = clean_entity(captures.name("object").unwrap().as_str());
                if subject.is_empty() || object.is_empty() || subject.eq_ignore_ascii_case(&object) { continue; }
                facts.push(CandidateFact {
                    source_page_id: page_id, source_page: title.to_string(),
                    subject, relationship: (*relationship).to_string(), object,
                    evidence: sentence.chars().take(2000).collect(),
                    extraction_method: "explicit_sentence_pattern_v1".to_string(),
                    confidence: *confidence,
                });
            }
        }
        for province in provinces {
            let escaped = regex::escape(province);
            let contexts = [
                format!(r"(?i)\b{escaped}\b.{{0,500}}\b(?:one of the |among the )?(?:nine )?provinces? of Tamriel\b"),
                format!(r"(?i)\bprovinces? of Tamriel\b.{{0,500}}\b{escaped}\b"),
                format!(r"(?i)\bTamriel['’]s (?:nine )?provinces?\b.{{0,500}}\b{escaped}\b"),
            ];
            if contexts.iter().any(|pattern| Regex::new(pattern).map(|r| r.is_match(&sentence)).unwrap_or(false)) {
                facts.push(CandidateFact {
                    source_page_id: page_id, source_page: title.to_string(),
                    subject: province.clone(), relationship: "province of".to_string(),
                    object: "Tamriel".to_string(), evidence: sentence.chars().take(2000).collect(),
                    extraction_method: "province_reference_context_v1".to_string(), confidence: 0.92,
                });
            }
        }
    }
    let mut unique = Vec::new();
    for fact in facts {
        if !unique.iter().any(|old: &CandidateFact| old.subject.eq_ignore_ascii_case(&fact.subject)
            && old.relationship == fact.relationship && old.object.eq_ignore_ascii_case(&fact.object)
            && old.evidence == fact.evidence) {
            unique.push(fact);
        }
    }
    unique
}
