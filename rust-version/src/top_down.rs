use anyhow::Result;
use rusqlite::{params, Connection, OptionalExtension};
use std::path::Path;

fn normalise(value: &str) -> String {
    value
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .to_lowercase()
}

fn clean_target(value: &str) -> String {
    value
        .trim()
        .trim_matches(|ch: char| ch.is_ascii_punctuation() || ch.is_whitespace())
        .trim_start_matches("the ")
        .trim()
        .to_string()
}

fn strip_question_end(value: &str) -> &str {
    value.trim_end_matches(|ch: char| matches!(ch, '?' | '!' | '.'))
}

fn target_after_prefix<'a>(question: &'a str, prefixes: &[&str]) -> Option<String> {
    prefixes.iter().find_map(|prefix| {
        question
            .strip_prefix(prefix)
            .map(clean_target)
            .filter(|target| !target.is_empty())
    })
}

fn fact_lines(
    connection: &Connection,
    relationship: Option<&str>,
    term: Option<&str>,
    limit: usize,
) -> Result<Vec<String>> {
    let mut statement = connection.prepare(
        "SELECT subject,relationship,object,source_title,evidence_text
         FROM candidate_facts
         WHERE (?1 IS NULL OR lower(relationship)=lower(?1)
                OR (?1='province' AND lower(relationship)='province of'))
           AND (?2 IS NULL OR subject LIKE ?2 OR object LIKE ?2 OR evidence_text LIKE ?2)
         ORDER BY confidence DESC LIMIT ?3",
    )?;
    let pattern = term.map(|value| format!("%{value}%"));
    let rows = statement.query_map(params![relationship, pattern, limit as i64], |row| {
        Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, String>(2)?,
            row.get::<_, String>(3)?,
            row.get::<_, String>(4)?,
        ))
    })?;
    let mut output = Vec::new();
    for row in rows {
        let (subject, relation, object, source, evidence) = row?;
        output.push(format!(
            "- {subject} — {relation} — {object}.\n  Source: {source}. Evidence: {evidence}"
        ));
    }
    Ok(output)
}

fn typed_observation_lines(
    connection: &Connection,
    term: &str,
    limit: usize,
) -> Result<Vec<String>> {
    let pattern = format!("%{}%", normalise(term));
    let mut statement = connection.prepare(
        "SELECT entity_type,subject,value,source_type,source_id,mod_id,
                source_page_id,evidence
         FROM (
             SELECT entity_type,source_title AS subject,value,source_type,source_id,
                    COALESCE(mod_id,'') AS mod_id,source_page_id,evidence_text AS evidence
             FROM entity_candidates
             UNION ALL
             SELECT entity_type,subject,value,source_type,source_id,
                    COALESCE(mod_id,'') AS mod_id,NULL AS source_page_id,evidence
             FROM external_observations
         )
         WHERE lower(subject) LIKE ?1 OR lower(value) LIKE ?1 OR lower(evidence) LIKE ?1
         ORDER BY source_type,source_id,subject,entity_type,value
         LIMIT ?2",
    )?;
    let rows = statement.query_map(params![pattern, limit as i64], |row| {
        Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, String>(2)?,
            row.get::<_, String>(3)?,
            row.get::<_, String>(4)?,
            row.get::<_, String>(5)?,
            row.get::<_, Option<i64>>(6)?,
            row.get::<_, String>(7)?,
        ))
    })?;
    let mut output = Vec::new();
    for row in rows {
        let (kind, subject, value, source_type, source_id, mod_id, page_id, evidence) = row?;
        let mod_label = if mod_id.is_empty() {
            String::new()
        } else {
            format!(" (mod {mod_id})")
        };
        let page_label = page_id.map(|id| format!(", page {id}")).unwrap_or_default();
        output.push(format!(
            "- [{kind}] {subject}: {value} [source {source_type}:{source_id}{mod_label}{page_label}]. Evidence: {evidence}"
        ));
    }
    Ok(output)
}

fn answer_overview(connection: &Connection) -> Result<String> {
    let count: i64 =
        connection.query_row("SELECT COUNT(*) FROM candidate_facts", [], |row| row.get(0))?;
    let pages: i64 = connection.query_row("SELECT COUNT(*) FROM pages", [], |row| row.get(0))?;
    let links: i64 =
        connection.query_row("SELECT COUNT(*) FROM page_links", [], |row| row.get(0))?;
    let typed_candidates: i64 =
        connection.query_row("SELECT COUNT(*) FROM entity_candidates", [], |row| {
            row.get(0)
        })?;
    let external_observations: i64 =
        connection.query_row("SELECT COUNT(*) FROM external_observations", [], |row| {
            row.get(0)
        })?;
    let mut output = vec![
        "Here is what I currently have stored.".to_string(),
        format!("Structured candidate facts: {count}."),
        format!("Typed candidate observations: {typed_candidates}."),
        format!("Separate user/mod observations: {external_observations}."),
        format!("Imported wiki pages: {pages}; stored wiki links: {links}."),
    ];
    let mut statement = connection.prepare(
        "SELECT subject,relationship,object FROM candidate_facts ORDER BY fact_id LIMIT 5",
    )?;
    let rows = statement.query_map([], |row| {
        Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, String>(2)?,
        ))
    })?;
    for (index, row) in rows.enumerate() {
        let (subject, relationship, object) = row?;
        output.push(format!(
            "{}. {subject} — {relationship} — {object}",
            index + 1
        ));
    }
    if count == 0 {
        output.push("No structured facts are currently stored.".to_string());
    } else if count > 5 {
        output.push(format!("Showing 5 of {count} candidate facts."));
    }
    output.push(
        "Imported pages and extracted candidate facts are evidence sources, not automatically verified lore. Ask about a subject to inspect its sources."
            .to_string(),
    );
    Ok(output.join("\n"))
}

fn answer_random_fact(connection: &Connection) -> Result<String> {
    let fact: Option<(String, String, String, String, String)> = connection
        .query_row(
            "SELECT subject,relationship,object,source_title,evidence_text
             FROM candidate_facts ORDER BY RANDOM() LIMIT 1",
            [],
            |row| {
                Ok((
                    row.get(0)?,
                    row.get(1)?,
                    row.get(2)?,
                    row.get(3)?,
                    row.get(4)?,
                ))
            },
        )
        .optional()?;
    let Some((subject, relationship, object, source, evidence)) = fact else {
        return Ok("I do not have any structured facts to choose from yet.".to_string());
    };
    Ok(format!(
        "Random fact: {subject} {relationship} {object}. Source page: {source}. Evidence: {evidence} This is an extracted candidate fact; check its source evidence before treating it as confirmed lore."
    ))
}

fn singular(value: &str) -> String {
    if let Some(stem) = value.strip_suffix("ies") {
        format!("{stem}y")
    } else if value.ends_with('s') && !value.ends_with("ss") {
        value[..value.len() - 1].to_string()
    } else {
        value.to_string()
    }
}

fn province_list() -> Result<Vec<String>> {
    let path = crate::config::project_root().join("rust-version/data/reference/provinces.json");
    Ok(serde_json::from_slice(&std::fs::read(path)?)?)
}

fn answer_count(connection: &Connection, raw_target: &str) -> Result<String> {
    let target = singular(&normalise(raw_target));
    if target == "province" {
        let provinces = province_list()?;
        return Ok(format!(
            "The reference catalogue contains {} traditional provinces of Tamriel: {}. This is a curated reference count, not proof that the extractor independently discovered all of them.",
            provinces.len(),
            provinces.join(", ")
        ));
    }

    let pattern = format!("%{target}%");
    let entity_type = match target.as_str() {
        "race" | "species" => Some("race"),
        "occupation" | "profession" | "job" => Some("occupation"),
        "book" => Some("book"),
        _ => None,
    };
    let count: i64 = if target == "continent" {
        connection.query_row(
            "SELECT COUNT(DISTINCT entity) FROM (
                SELECT subject AS entity FROM candidate_facts
                 WHERE lower(relationship) IN ('continent','is a continent','continent of')
                    OR (lower(relationship) IN ('type','is a')
                        AND lower(object) LIKE '%continent%')
                UNION
                SELECT source_title AS entity FROM page_template_parameters
                 WHERE parameter_name COLLATE NOCASE IN ('type','category','kind')
                   AND lower(parameter_value) LIKE '%continent%'
            )",
            [],
            |row| row.get(0),
        )?
    } else if let Some(entity_type) = entity_type {
        connection.query_row(
            "SELECT COUNT(DISTINCT value) FROM (
                SELECT value FROM entity_candidates WHERE entity_type=?1
                UNION
                SELECT value FROM external_observations WHERE entity_type=?1
            ) WHERE trim(value) <> ''",
            [entity_type],
            |row| row.get(0),
        )?
    } else {
        connection.query_row(
            "SELECT COUNT(DISTINCT entity) FROM (
                SELECT source_title AS entity FROM entity_candidates WHERE lower(value) LIKE ?1
                UNION
                SELECT subject AS entity FROM external_observations WHERE lower(value) LIKE ?1
                UNION
                SELECT subject AS entity FROM candidate_facts
                 WHERE lower(subject) LIKE ?1 OR lower(object) LIKE ?1
            )",
            [&pattern],
            |row| row.get(0),
        )?
    };
    if count == 0 {
        Ok(format!(
            "I cannot give a reliable count of {raw_target} yet. I could not find matching structured entity records. A page mentioning something is not enough to prove that it is a separate entity."
        ))
    } else {
        let count_label = if entity_type.is_some() {
            format!("distinct {target} value(s)")
        } else {
            format!("distinct {target} record(s)")
        };
        Ok(format!(
            "I found {count} {count_label} in the structured database. This count is based on available structured evidence and may not be complete."
        ))
    }
}

fn readable_snippet(title: &str, text: &str) -> String {
    let readable = crate::wiki::analyse_wikitext(0, title, text).plain_text;
    readable
        .split_whitespace()
        .take(45)
        .collect::<Vec<_>>()
        .join(" ")
}

fn exact_title_matches(connection: &Connection, term: &str) -> Result<Vec<String>> {
    let mut statement = connection.prepare(
        "SELECT title,namespace_name,page_text FROM pages
         WHERE lower(title)=lower(?1) ORDER BY text_length DESC LIMIT 8",
    )?;
    let rows = statement.query_map([term], |row| {
        Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, String>(2)?,
        ))
    })?;
    let mut output = Vec::new();
    for row in rows {
        let (title, namespace, text) = row?;
        let snippet = readable_snippet(&title, &text);
        output.push(format!("- {title} ({namespace}): {snippet}"));
    }
    Ok(output)
}

fn page_search(connection: &Connection, term: &str) -> Result<Vec<String>> {
    let exact = exact_title_matches(connection, term)?;
    if !exact.is_empty() {
        return Ok(exact);
    }

    let mut statement = connection.prepare(
        "SELECT title,namespace_name,page_text FROM pages
         WHERE title LIKE ?1 OR page_text LIKE ?1
         ORDER BY CASE WHEN title LIKE ?1 THEN 0 ELSE 1 END,text_length DESC LIMIT 8",
    )?;
    let pattern = format!("%{term}%");
    let rows = statement.query_map([pattern], |row| {
        Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, String>(2)?,
        ))
    })?;
    let mut output = Vec::new();
    for row in rows {
        let (title, namespace, text) = row?;
        let snippet = readable_snippet(&title, &text);
        output.push(format!("- {title} ({namespace}): {snippet}"));
    }
    Ok(output)
}

pub fn answer_question(database_path: &Path, question: &str) -> Result<String> {
    let question = normalise(question);
    if question.is_empty() {
        anyhow::bail!("question cannot be empty");
    }
    let plain = strip_question_end(&question);
    let connection = Connection::open(database_path)?;

    if let Some(claim) = target_after_prefix(
        plain,
        &[
            "what evidence supports ",
            "what is the evidence for ",
            "show evidence for ",
        ],
    ) {
        if ["this answer", "the answer", "this", "that"].contains(&claim.as_str()) {
            return Ok(
                "This command-line interface does not retain prior answers, so it cannot resolve 'this answer' to a claim. Ask with a named subject or claim, for example: 'What evidence supports Saarthal?'."
                    .to_string(),
            );
        }
        let facts = fact_lines(&connection, None, Some(&claim), 15)?;
        let observations = typed_observation_lines(&connection, &claim, 15)?;
        if facts.is_empty() && observations.is_empty() {
            return Ok(format!(
                "I could not find structured evidence for '{claim}' in the Rust database."
            ));
        }
        let mut sections = Vec::new();
        if !facts.is_empty() {
            sections.push(format!(
                "Candidate facts matching '{claim}':\n{}",
                facts.join("\n")
            ));
        }
        if !observations.is_empty() {
            sections.push(format!(
                "Typed observations matching '{claim}':\n{}",
                observations.join("\n")
            ));
        }
        return Ok(sections.join("\n"));
    }

    if [
        "what do you know",
        "tell me what you know",
        "show me what you know",
        "tell me everything you know",
        "knowledge overview",
    ]
    .contains(&plain)
    {
        return answer_overview(&connection);
    }
    if [
        "random fact",
        "tell me a random fact",
        "give me a random fact",
        "surprise me with a fact",
        "surprise me",
    ]
    .contains(&plain)
    {
        return answer_random_fact(&connection);
    }

    if let Some(target) = plain.strip_prefix("how many ") {
        let target = [" are there", " exist", " do we know", " are known"]
            .iter()
            .find_map(|ending| target.strip_suffix(ending))
            .unwrap_or(target);
        return answer_count(&connection, target.trim_start_matches("of "));
    }

    let (relationship, term) =
        if let Some(subject) = target_after_prefix(plain, &["where do ", "where does "]) {
            let subject = subject
                .strip_suffix(" live")
                .unwrap_or(&subject)
                .to_string();
            (Some("lives in"), clean_target(&subject))
        } else if let Some(target) = plain.strip_prefix("who rules ") {
            (Some("rules"), clean_target(target))
        } else if let Some((_, target)) = plain
            .strip_prefix("which ")
            .or_else(|| plain.strip_prefix("what "))
            .and_then(|value| {
                value
                    .split_once(" belong to ")
                    .or_else(|| value.split_once(" belongs to "))
            })
        {
            (Some("province"), clean_target(target))
        } else {
            let term = target_after_prefix(
                plain,
                &[
                    "what happened in ",
                    "what happened at ",
                    "what happened to ",
                    "what do you know about ",
                    "what can you tell me about ",
                    "tell me about ",
                    "describe ",
                    "explain ",
                    "who is the ",
                    "who is ",
                    "who was the ",
                    "who was ",
                    "where is the ",
                    "where is ",
                    "when is the ",
                    "when is ",
                    "what is the ",
                    "what is ",
                    "which is the ",
                    "which is ",
                    "who are the ",
                    "what are the ",
                    "what are ",
                ],
            )
            .unwrap_or_else(|| question.clone());
            (None, term)
        };

    let facts = fact_lines(&connection, relationship, Some(&term), 15)?;
    let observations = typed_observation_lines(&connection, &term, 15)?;
    let mut sections = Vec::new();
    if !facts.is_empty() {
        sections.push(format!(
            "Here is what the structured database records:\n{}",
            facts.join("\n")
        ));
    }
    if !observations.is_empty() {
        sections.push(format!(
            "Typed candidate observations:\n{}",
            observations.join("\n")
        ));
    }
    if !sections.is_empty() {
        return Ok(sections.join("\n"));
    }

    let pages = page_search(&connection, &term)?;
    if pages.is_empty() {
        Ok("I could not find matching structured facts or source pages in the Rust database yet. Try a named person, place, faction or creature.".to_string())
    } else {
        Ok(format!(
            "I found source-page matches. These are search results, not automatically verified answers:\n{}",
            pages.join("\n")
        ))
    }
}
