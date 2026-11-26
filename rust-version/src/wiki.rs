use crate::models::CandidateFact;
use regex::{Regex, RegexSet};
use std::sync::LazyLock;

static FACT_PATTERNS: LazyLock<Vec<(&'static str, Regex, f64)>> = LazyLock::new(|| {
    vec![
    ("province", Regex::new(r"(?i)\b(?P<subject>[A-Z][\w' -]{0,70}?)\s+is\s+(?:a|an)\s+province\s+of\s+(?P<object>[A-Z][\w' -]{0,70}?)(?:[.!?;]|$)").unwrap(), 0.95),
    ("lives in", Regex::new(r"(?i)\b(?P<subject>[A-Z][\w' -]{0,70}?)\s+lives?\s+in\s+(?P<object>[A-Z][\w' -]{0,70}?)(?:[.!?;]|$)").unwrap(), 0.90),
    ("located in", Regex::new(r"(?i)\b(?P<subject>[A-Z][\w' -]{0,70}?)\s+is\s+located\s+in\s+(?P<object>[A-Z][\w' -]{0,70}?)(?:[.!?;]|$)").unwrap(), 0.90),
]
});
// These mandatory phrases are ordered to match FACT_PATTERNS; the original regexes still capture facts.
static FACT_PATTERN_PREFILTERS: LazyLock<RegexSet> = LazyLock::new(|| {
    RegexSet::new([
        r"(?i)is\s+(?:a|an)\s+province\s+of",
        r"(?i)lives?\s+in",
        r"(?i)is\s+located\s+in",
    ])
    .unwrap()
});
static EXTERNAL_LINK_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\[https?://[^\s\]]+(?:\s+([^\]]+))?\]").unwrap());
static TAG_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"(?s)<[^>]*>").unwrap());
static WHITESPACE_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\s+").unwrap());
static COMMENT_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"(?s)<!--.*?-->").unwrap());
static FORMATTING_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"'{2,5}").unwrap());
static ARTICLE_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"(?i)^(the|a|an)\s+").unwrap());

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

#[derive(Debug, Clone)]
pub struct WikiTemplate {
    pub name: String,
    pub evidence: String,
}

#[derive(Debug, Clone, Default)]
pub struct WikiAnalysis {
    pub template_count: usize,
    pub parameter_count: usize,
    pub link_count: usize,
    pub heading_count: usize,
    pub tag_count: usize,
    pub templates: Vec<WikiTemplate>,
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
    let chars: Vec<(usize, char)> = input.char_indices().collect();
    let mut i = 0usize;
    while i < chars.len() {
        let (pos, ch) = chars[i];
        let next = chars.get(i + 1).map(|(_, c)| *c);
        if ch == '{' && next == Some('{') {
            braces += 1;
            i += 1;
        } else if ch == '}' && next == Some('}') {
            braces = (braces - 1).max(0);
            i += 1;
        } else if ch == '[' && next == Some('[') {
            links += 1;
            i += 1;
        } else if ch == ']' && next == Some(']') {
            links = (links - 1).max(0);
            i += 1;
        } else if ch == separator && braces == 0 && links == 0 {
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
        if bytes[i] == b'{' && bytes[i + 1] == b'{' {
            stack.push(i);
            i += 2;
        } else if bytes[i] == b'}' && bytes[i + 1] == b'}' {
            if let Some(start) = stack.pop() {
                blocks.push((start, &text[start..i + 2]));
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
        if depth == 0 && bytes[i..].starts_with(b"{{=}}") {
            output.push('=');
            i += 5;
            continue;
        }
        if depth == 0 && bytes[i..].starts_with(b"{{!}}") {
            output.push('|');
            i += 5;
            continue;
        }
        if i + 1 < bytes.len() && bytes[i] == b'{' && bytes[i + 1] == b'{' {
            if depth == 0 {
                output.push(' ');
            }
            depth += 1;
            i += 2;
        } else if i + 1 < bytes.len() && bytes[i] == b'}' && bytes[i + 1] == b'}' && depth > 0 {
            depth -= 1;
            i += 2;
        } else {
            let character = text[i..].chars().next().unwrap();
            if depth == 0 {
                output.push(character);
            }
            i += character.len_utf8();
        }
    }
    output
}

fn wikilink_ranges(text: &str) -> Vec<(usize, usize)> {
    let bytes = text.as_bytes();
    let mut stack = Vec::new();
    let mut ranges = Vec::new();
    let mut i = 0usize;
    while i + 1 < bytes.len() {
        if bytes[i] == b'[' && bytes[i + 1] == b'[' {
            stack.push(i);
            i += 2;
        } else if bytes[i] == b']' && bytes[i + 1] == b']' {
            if let Some(start) = stack.pop() {
                ranges.push((start, i + 2));
            }
            i += 2;
        } else {
            i += 1;
        }
    }
    ranges.sort_by_key(|(start, _)| *start);
    ranges
}

fn wikilink_parts(inner: &str) -> (String, String) {
    let parts = split_top_level(inner, '|');
    let destination = parts.first().unwrap_or(&"").trim().to_string();
    let display_text = if parts.len() > 1 {
        parts[1..].join("|").trim().to_string()
    } else {
        destination.clone()
    };
    (destination, display_text)
}

fn render_wikilinks(text: &str) -> String {
    let mut output = String::new();
    let mut cursor = 0usize;
    for (start, end) in wikilink_ranges(text) {
        if start < cursor {
            continue;
        }
        output.push_str(&text[cursor..start]);
        let (_, display_text) = wikilink_parts(&text[start + 2..end - 2]);
        output.push_str(&render_wikilinks(&display_text));
        cursor = end;
    }
    output.push_str(&text[cursor..]);
    output
}

fn extract_wikilinks(text: &str) -> Vec<WikiLink> {
    wikilink_ranges(text)
        .into_iter()
        .filter_map(|(start, end)| {
            let (destination, display_text) = wikilink_parts(&text[start + 2..end - 2]);
            (!destination.is_empty()).then_some(WikiLink {
                destination,
                display_text,
            })
        })
        .collect()
}

fn strip_markup(text: &str) -> String {
    let without_comments = COMMENT_RE.replace_all(text, " ");
    let without_templates = remove_templates(&without_comments);
    let links = render_wikilinks(&without_templates);
    let external_links = EXTERNAL_LINK_RE.replace_all(&links, |captures: &regex::Captures| {
        captures
            .get(1)
            .map(|label| label.as_str())
            .unwrap_or("")
            .to_string()
    });
    let tags = TAG_RE.replace_all(&external_links, |captures: &regex::Captures| {
        let tag = captures.get(0).map(|value| value.as_str()).unwrap_or("");
        let lowered_tag = tag.to_ascii_lowercase();
        if lowered_tag.starts_with("<nowiki") || lowered_tag.starts_with("</nowiki") {
            String::new()
        } else {
            " ".to_string()
        }
    });
    let formatting = FORMATTING_RE.replace_all(&tags, "");
    formatting
        .lines()
        .map(|line| WHITESPACE_RE.replace_all(line, " ").trim().to_string())
        .filter(|line| !line.is_empty())
        .collect::<Vec<_>>()
        .join("\n")
}

fn clean_entity(value: &str) -> String {
    let linked = render_wikilinks(value);
    let compact = WHITESPACE_RE.replace_all(&linked, " ");
    let trimmed =
        compact.trim_matches(|c: char| c.is_whitespace() || ".,:;!?()[]{}'\"".contains(c));
    ARTICLE_RE.replace(trimmed, "").trim().to_string()
}

pub fn analyse_wikitext(page_id: i64, title: &str, text: &str) -> WikiAnalysis {
    let blocks = template_blocks(text);
    let mut result = WikiAnalysis::default();
    result.template_count = blocks.len();
    for (template_index, block) in blocks.iter().enumerate() {
        let inner = block.trim_start_matches("{{").trim_end_matches("}}");
        let parts = split_top_level(inner, '|');
        let template_name = parts.first().unwrap_or(&"").trim().replace('_', " ");
        let template_evidence: String = (*block).chars().take(10000).collect();
        result.templates.push(WikiTemplate {
            name: template_name.clone(),
            evidence: template_evidence.clone(),
        });
        let mut positional_index = 0;
        for (parameter_index, raw) in parts.iter().skip(1).enumerate() {
            let pair = split_top_level(raw, '=');
            let (name, value, named) = if pair.len() > 1 {
                (
                    pair[0].trim().to_string(),
                    pair[1..].join("=").trim().to_string(),
                    true,
                )
            } else {
                positional_index += 1;
                (positional_index.to_string(), raw.trim().to_string(), false)
            };
            let cleaned = strip_markup(&value);
            if !cleaned.is_empty() {
                result.parameters.push(TemplateParameter {
                    template_index,
                    template_name: template_name.clone(),
                    parameter_index,
                    parameter_name: name,
                    is_named: named,
                    value: cleaned,
                    raw_value: value,
                    evidence: template_evidence.clone(),
                });
            }
        }
    }
    result.parameter_count = result.parameters.len();

    result.links = extract_wikilinks(text);
    result.link_count = result.links.len();
    result.heading_count = text
        .lines()
        .filter(|line| {
            let trimmed = line.trim();
            let count = trimmed.chars().take_while(|c| *c == '=').count();
            count >= 1 && count <= 6 && trimmed.ends_with(&"=".repeat(count))
        })
        .count();
    result.tag_count = TAG_RE.find_iter(text).count();
    result.plain_text = strip_markup(text);
    let _ = (page_id, title);
    result
}

#[derive(Debug)]
struct ProvincePatterns {
    name: String,
    contexts: [Option<Regex>; 3],
}

#[derive(Debug)]
pub struct FactExtractor {
    provinces: Vec<ProvincePatterns>,
}

impl FactExtractor {
    pub fn new(provinces: &[String]) -> Self {
        let provinces = provinces
            .iter()
            .map(|province| {
                let escaped = regex::escape(province);
                let patterns = [
                    format!(r"(?i)\b{escaped}\b.{{0,500}}\b(?:one of the |among the )?(?:nine )?provinces? of Tamriel\b"),
                    format!(r"(?i)\bprovinces? of Tamriel\b.{{0,500}}\b{escaped}\b"),
                    format!(r"(?i)\bTamriel['’]s (?:nine )?provinces?\b.{{0,500}}\b{escaped}\b"),
                ];
                ProvincePatterns {
                    name: province.clone(),
                    contexts: patterns.map(|pattern| Regex::new(&pattern).ok()),
                }
            })
            .collect();
        Self { provinces }
    }

    pub fn extract_facts(&self, plain_text: &str, page_id: i64, title: &str) -> Vec<CandidateFact> {
        let mut facts = Vec::new();
        let mut sentence_ranges = Vec::new();
        let mut start = 0usize;
        let chars: Vec<(usize, char)> = plain_text.char_indices().collect();
        for (index, (position, character)) in chars.iter().enumerate() {
            let next_is_space = chars
                .get(index + 1)
                .map(|(_, next)| next.is_whitespace())
                .unwrap_or(true);
            if *character == '\n' || (matches!(character, '.' | '!' | '?') && next_is_space) {
                let end = position + character.len_utf8();
                if end > start {
                    sentence_ranges.push(&plain_text[start..end]);
                }
                start = end;
                while start < plain_text.len() {
                    let next = plain_text[start..].chars().next().unwrap();
                    if !next.is_whitespace() {
                        break;
                    }
                    start += next.len_utf8();
                }
            }
        }
        if start < plain_text.len() {
            sentence_ranges.push(&plain_text[start..]);
        }
        for raw_sentence in sentence_ranges {
            let sentence = WHITESPACE_RE
                .replace_all(raw_sentence, " ")
                .trim()
                .to_string();
            if sentence.is_empty() {
                continue;
            }
            let possible_patterns = FACT_PATTERN_PREFILTERS.matches(&sentence);
            for (pattern_index, (relationship, pattern, confidence)) in
                FACT_PATTERNS.iter().enumerate()
            {
                if !possible_patterns.matched(pattern_index) {
                    continue;
                }
                for captures in pattern.captures_iter(&sentence) {
                    let subject = clean_entity(captures.name("subject").unwrap().as_str());
                    let object = clean_entity(captures.name("object").unwrap().as_str());
                    if subject.is_empty()
                        || object.is_empty()
                        || subject.eq_ignore_ascii_case(&object)
                    {
                        continue;
                    }
                    facts.push(CandidateFact {
                        source_page_id: page_id,
                        source_page: title.to_string(),
                        subject,
                        relationship: (*relationship).to_string(),
                        object,
                        evidence: sentence.chars().take(2000).collect(),
                        extraction_method: "explicit_sentence_pattern_v1".to_string(),
                        confidence: *confidence,
                    });
                }
            }
            for province in &self.provinces {
                if province.contexts.iter().any(|pattern| {
                    pattern
                        .as_ref()
                        .map(|regex| regex.is_match(&sentence))
                        .unwrap_or(false)
                }) {
                    facts.push(CandidateFact {
                        source_page_id: page_id,
                        source_page: title.to_string(),
                        subject: province.name.clone(),
                        relationship: "province of".to_string(),
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
            }) {
                unique.push(fact);
            }
        }
        unique
    }
}

pub fn extract_facts(
    plain_text: &str,
    page_id: i64,
    title: &str,
    provinces: &[String],
) -> Vec<CandidateFact> {
    FactExtractor::new(provinces).extract_facts(plain_text, page_id, title)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn removed_templates_do_not_join_adjacent_words() {
        assert_eq!(strip_markup("Skaal{{br}}Village"), "Skaal Village");
    }

    #[test]
    fn escaped_wiki_delimiters_are_preserved() {
        assert_eq!(strip_markup("query{{=}}3{{!}}page"), "query=3|page");
    }

    #[test]
    fn nowiki_inline_content_does_not_gain_surrounding_spaces() {
        assert_eq!(
            strip_markup("ESO<nowiki>:</nowiki> Morrowind"),
            "ESO: Morrowind"
        );
    }

    #[test]
    fn external_links_keep_labels_and_drop_bare_urls() {
        assert_eq!(
            strip_markup(
                "A [https://example.invalid/page source label] B [https://example.invalid/page] C"
            ),
            "A source label B C"
        );
    }

    #[test]
    fn nested_wikilinks_preserve_parent_alias_and_child_link() {
        let analysis = analyse_wikitext(
            1,
            "Nested links",
            "[[File:Example.png|thumb|[[Target|shown]]]]",
        );
        assert_eq!(analysis.links.len(), 2);
        assert_eq!(analysis.links[0].destination, "File:Example.png");
        assert_eq!(analysis.links[0].display_text, "thumb|[[Target|shown]]");
        assert_eq!(analysis.links[1].destination, "Target");
        assert_eq!(analysis.links[1].display_text, "shown");
        assert_eq!(
            strip_markup("[[Outer|before [[Target|shown]] after]]"),
            "before shown after"
        );
    }

    fn legacy_clean_entity(value: &str) -> String {
        let linked = render_wikilinks(value);
        let compact = WHITESPACE_RE.replace_all(&linked, " ");
        let trimmed =
            compact.trim_matches(|c: char| c.is_whitespace() || ".,:;!?()[]{}'\"".contains(c));
        Regex::new(r"(?i)^(the|a|an)\s+")
            .unwrap()
            .replace(trimmed, "")
            .trim()
            .to_string()
    }

    fn legacy_extract_facts(
        plain_text: &str,
        page_id: i64,
        title: &str,
        provinces: &[String],
    ) -> Vec<CandidateFact> {
        let mut facts = Vec::new();
        let mut sentence_ranges = Vec::new();
        let mut start = 0usize;
        let chars: Vec<(usize, char)> = plain_text.char_indices().collect();
        for (index, (position, character)) in chars.iter().enumerate() {
            let next_is_space = chars
                .get(index + 1)
                .map(|(_, next)| next.is_whitespace())
                .unwrap_or(true);
            if *character == '\n' || (matches!(character, '.' | '!' | '?') && next_is_space) {
                let end = position + character.len_utf8();
                if end > start {
                    sentence_ranges.push(&plain_text[start..end]);
                }
                start = end;
                while start < plain_text.len() {
                    let next = plain_text[start..].chars().next().unwrap();
                    if !next.is_whitespace() {
                        break;
                    }
                    start += next.len_utf8();
                }
            }
        }
        if start < plain_text.len() {
            sentence_ranges.push(&plain_text[start..]);
        }
        for raw_sentence in sentence_ranges {
            let sentence = WHITESPACE_RE
                .replace_all(raw_sentence, " ")
                .trim()
                .to_string();
            if sentence.is_empty() {
                continue;
            }
            for (relationship, pattern, confidence) in FACT_PATTERNS.iter() {
                for captures in pattern.captures_iter(&sentence) {
                    let subject = legacy_clean_entity(captures.name("subject").unwrap().as_str());
                    let object = legacy_clean_entity(captures.name("object").unwrap().as_str());
                    if subject.is_empty()
                        || object.is_empty()
                        || subject.eq_ignore_ascii_case(&object)
                    {
                        continue;
                    }
                    facts.push(CandidateFact {
                        source_page_id: page_id,
                        source_page: title.to_string(),
                        subject,
                        relationship: (*relationship).to_string(),
                        object,
                        evidence: sentence.chars().take(2000).collect(),
                        extraction_method: "explicit_sentence_pattern_v1".to_string(),
                        confidence: *confidence,
                    });
                }
            }
            for province in provinces {
                let escaped = regex::escape(province);
                let contexts = [
                    format!(
                        r"(?i)\b{escaped}\b.{{0,500}}\b(?:one of the |among the )?(?:nine )?provinces? of Tamriel\b"
                    ),
                    format!(r"(?i)\bprovinces? of Tamriel\b.{{0,500}}\b{escaped}\b"),
                    format!(r"(?i)\bTamriel['’]s (?:nine )?provinces?\b.{{0,500}}\b{escaped}\b"),
                ];
                if contexts.iter().any(|pattern| {
                    Regex::new(pattern)
                        .map(|r| r.is_match(&sentence))
                        .unwrap_or(false)
                }) {
                    facts.push(CandidateFact {
                        source_page_id: page_id,
                        source_page: title.to_string(),
                        subject: province.clone(),
                        relationship: "province of".to_string(),
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
            }) {
                unique.push(fact);
            }
        }
        unique
    }

    fn assert_same_facts(expected: &[CandidateFact], actual: &[CandidateFact]) {
        assert_eq!(expected.len(), actual.len());
        for (expected, actual) in expected.iter().zip(actual) {
            assert_eq!(expected.source_page_id, actual.source_page_id);
            assert_eq!(expected.source_page, actual.source_page);
            assert_eq!(expected.subject, actual.subject);
            assert_eq!(expected.relationship, actual.relationship);
            assert_eq!(expected.object, actual.object);
            assert_eq!(expected.evidence, actual.evidence);
            assert_eq!(expected.extraction_method, actual.extraction_method);
            assert_eq!(expected.confidence.to_bits(), actual.confidence.to_bits());
        }
    }

    #[test]
    fn prepared_fact_extractor_matches_legacy_facts_in_order() {
        let provinces = vec![
            "Skyrim".to_string(),
            "Morrowind".to_string(),
            "High Rock + Coast (West) Isles".to_string(),
        ];
        let text = concat!(
            "sKyRiM is one of the nine provinces of Tamriel.\n",
            "The provinces of Tamriel include mOrRoWiNd.\n",
            "Tamriel's nine provinces include High Rock + Coast (West) Isles.\n",
            "Tamriel has many provinces with no matching name.\n",
            "The Nords live in Skyrim."
        );
        let expected = legacy_extract_facts(text, 42, "Test page", &provinces);
        let extractor = FactExtractor::new(&provinces);
        let actual = extractor.extract_facts(text, 42, "Test page");

        assert_same_facts(&expected, &actual);
        assert_eq!(actual.len(), 4, "{actual:#?}");
        assert_eq!(actual[0].subject, "Skyrim");
        assert_eq!(actual[1].subject, "Morrowind");
        assert_eq!(actual[2].subject, "High Rock + Coast (West) Isles");
        assert_eq!(actual[3].relationship, "lives in");
    }

    #[test]
    fn relationship_pattern_set_preserves_matches_and_order() {
        let provinces = vec!["Skyrim".to_string(), "Morrowind".to_string()];
        let text = concat!(
            "Skyrim is a province of Tamriel and is located in Morrowind. ",
            "The Nords live in Skyrim. An Orc lives in Morrowind."
        );
        let expected = legacy_extract_facts(text, 73, "Pattern overlap", &provinces);
        let actual = FactExtractor::new(&provinces).extract_facts(text, 73, "Pattern overlap");

        assert_same_facts(&expected, &actual);
        assert_eq!(
            actual
                .iter()
                .map(|fact| fact.relationship.as_str())
                .collect::<Vec<_>>(),
            [
                "province",
                "located in",
                "province of",
                "province of",
                "lives in",
                "lives in"
            ]
        );
    }
}
