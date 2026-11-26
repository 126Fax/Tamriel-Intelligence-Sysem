use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use tamriel_intelligence::{ai_preparation, analysis, database, knowledge};

const FIXTURE: &str = include_str!("../../tests/fixtures/extraction_parity.json");

fn normalized_template_name(value: &str) -> String {
    value
        .replace('_', " ")
        .split_whitespace()
        .map(str::to_lowercase)
        .collect::<Vec<_>>()
        .join(" ")
}

fn normalized_parameter_value(value: &str) -> String {
    value
        .lines()
        .map(|line| {
            line.trim()
                .trim_start_matches(|character| matches!(character, '*' | '#' | ';' | ':'))
                .trim()
        })
        .filter(|line| !line.is_empty())
        .collect::<Vec<_>>()
        .join(" ")
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

fn fixture_string(value: &Value) -> &str {
    value.as_str().expect("fixture value must be a string")
}

fn load_fixture() -> Value {
    let fixture = match std::env::var_os("TIS_EXTRACTION_PARITY_FIXTURE") {
        Some(path) => std::fs::read_to_string(path).expect("read parity fixture override"),
        None => FIXTURE.to_string(),
    };
    serde_json::from_str(&fixture).expect("valid extraction parity fixture")
}

#[test]
fn shared_extraction_fixture_preserves_semantics_and_provenance() {
    let fixture = load_fixture();
    let source_name = fixture_string(&fixture["source_name"]);
    let pages = fixture["pages"]
        .as_array()
        .expect("fixture pages must be an array");

    let temporary = tempfile::tempdir().unwrap();
    let database_path = temporary.path().join("parity.db");
    let connection = database::connect(&database_path).unwrap();
    let dump_id = database::register_dump(&connection, source_name).unwrap();
    database::set_dump_status(&connection, dump_id, "completed").unwrap();

    for page in pages {
        let page_id = page["page_id"].as_i64().unwrap();
        let title = fixture_string(&page["title"]);
        let namespace_id = page["namespace"].as_i64().unwrap();
        let revision_id = page["revision_id"].as_i64().unwrap();
        let text = fixture_string(&page["text"]);
        connection
            .execute(
                "INSERT INTO pages (
                    dump_id,page_id,title,namespace_id,namespace_name,
                    revision_id,text_length,page_text
                 ) VALUES (?1,?2,?3,?4,'',?5,?6,?7)",
                rusqlite::params![
                    dump_id,
                    page_id,
                    title,
                    namespace_id,
                    revision_id,
                    text.len() as i64,
                    text
                ],
            )
            .unwrap();
    }
    drop(connection);

    analysis::analyse_dump(&database_path, dump_id, 2).unwrap();
    ai_preparation::prepare_dump(&database_path, dump_id, 2, false).unwrap();

    let connection = database::connect(&database_path).unwrap();
    for page in pages {
        let expected = &page["expected"];
        let page_id = page["page_id"].as_i64().unwrap();
        let title = fixture_string(&page["title"]);

        let (template_count, link_count, heading_count, tag_count): (i64, i64, i64, i64) =
            connection
                .query_row(
                    "SELECT template_count,wikilink_count,heading_count,tag_count
                 FROM page_analysis WHERE dump_id=?1 AND page_id=?2",
                    rusqlite::params![dump_id, page_id],
                    |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
                )
                .unwrap();

        let templates_json: String = connection
            .query_row(
                "SELECT templates_json FROM ai_pages
                 WHERE dump_id=?1 AND page_id=?2",
                rusqlite::params![dump_id, page_id],
                |row| row.get(0),
            )
            .unwrap();
        let templates: Value = serde_json::from_str(&templates_json).unwrap();
        let mut actual_template_counts = BTreeMap::new();
        for template in templates.as_array().unwrap() {
            *actual_template_counts
                .entry(normalized_template_name(fixture_string(&template["name"])))
                .or_insert(0usize) += 1;
        }
        let expected_template_counts: BTreeMap<String, usize> = expected["template_counts"]
            .as_object()
            .unwrap()
            .iter()
            .map(|(name, count)| (name.clone(), count.as_u64().unwrap() as usize))
            .collect();
        assert_eq!(
            actual_template_counts, expected_template_counts,
            "template inventory for {title}"
        );
        assert_eq!(
            template_count as usize,
            templates.as_array().unwrap().len(),
            "template count for {title}"
        );

        let mut parameter_statement = connection
            .prepare(
                "SELECT template_name,parameter_name,is_named,parameter_value,
                        evidence_text,extraction_method,source_page_id,source_title
                 FROM page_template_parameters
                 WHERE dump_id=?1 AND source_page_id=?2",
            )
            .unwrap();
        let parameter_rows = parameter_statement
            .query_map(rusqlite::params![dump_id, page_id], |row| {
                Ok((
                    normalized_template_name(&row.get::<_, String>(0)?),
                    row.get::<_, String>(1)?,
                    row.get::<_, i64>(2)? != 0,
                    row.get::<_, String>(3)?,
                    row.get::<_, String>(4)?,
                    row.get::<_, String>(5)?,
                    row.get::<_, i64>(6)?,
                    row.get::<_, String>(7)?,
                ))
            })
            .unwrap()
            .collect::<rusqlite::Result<Vec<_>>>()
            .unwrap();
        let actual_parameters: BTreeSet<_> = parameter_rows
            .iter()
            .map(|row| {
                (
                    row.0.clone(),
                    row.1.clone(),
                    row.2,
                    normalized_parameter_value(&row.3),
                )
            })
            .collect();
        let expected_parameters: BTreeSet<_> = expected["template_parameters"]
            .as_array()
            .unwrap()
            .iter()
            .map(|parameter| {
                (
                    fixture_string(&parameter["template"]).to_string(),
                    fixture_string(&parameter["name"]).to_string(),
                    parameter["named"].as_bool().unwrap(),
                    normalized_parameter_value(fixture_string(&parameter["value"])),
                )
            })
            .collect();
        assert_eq!(
            expected_parameters, actual_parameters,
            "template parameters for {title}"
        );
        for row in &parameter_rows {
            assert_eq!(row.5, "template_parameter_rust_v1");
            assert_eq!(row.6, page_id);
            assert_eq!(row.7, title);
            assert!(row.4.contains("{{"));
        }

        let mut link_statement = connection
            .prepare(
                "SELECT destination,display_text FROM page_links
                 WHERE dump_id=?1 AND source_page_id=?2",
            )
            .unwrap();
        let actual_link_rows: Vec<_> = link_statement
            .query_map(rusqlite::params![dump_id, page_id], |row| {
                Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
            })
            .unwrap()
            .collect::<rusqlite::Result<_>>()
            .unwrap();
        let actual_link_counts: BTreeMap<_, usize> =
            actual_link_rows
                .iter()
                .fold(BTreeMap::new(), |mut counts, link| {
                    *counts.entry(link.clone()).or_insert(0) += 1;
                    counts
                });
        let expected_link_counts: BTreeMap<_, usize> = expected["links"]
            .as_array()
            .unwrap()
            .iter()
            .fold(BTreeMap::new(), |mut counts, link| {
                let pair = (
                    fixture_string(&link["destination"]).to_string(),
                    fixture_string(&link["display_text"]).to_string(),
                );
                *counts.entry(pair).or_insert(0) += 1;
                counts
            });
        assert_eq!(
            expected_link_counts, actual_link_counts,
            "links for {title}"
        );
        assert_eq!(link_count as usize, actual_link_rows.len());

        let (readable_text, headings_json, categories_json, external_links_json): (
            String,
            String,
            String,
            String,
        ) = connection
            .query_row(
                "SELECT readable_text,headings_json,categories_json,external_links_json
                 FROM ai_pages WHERE dump_id=?1 AND page_id=?2",
                rusqlite::params![dump_id, page_id],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
            )
            .unwrap();
        for value in expected["text_contains"].as_array().unwrap() {
            assert!(
                readable_text.contains(fixture_string(value)),
                "missing readable text in {title}: {value}"
            );
        }
        let headings: Value = serde_json::from_str(&headings_json).unwrap();
        let actual_headings: Vec<_> = headings
            .as_array()
            .unwrap()
            .iter()
            .map(|heading| fixture_string(&heading["text"]).to_string())
            .collect();
        let expected_headings: Vec<_> = expected["headings"]
            .as_array()
            .unwrap()
            .iter()
            .map(|heading| fixture_string(heading).to_string())
            .collect();
        assert_eq!(actual_headings, expected_headings, "headings for {title}");
        assert_eq!(
            heading_count as usize,
            expected_headings.len(),
            "heading count for {title}"
        );
        assert!(
            tag_count >= expected["reference_count"].as_i64().unwrap() * 2,
            "reference tags for {title}"
        );

        let categories: Value = serde_json::from_str(&categories_json).unwrap();
        let actual_categories: BTreeSet<_> = categories
            .as_array()
            .unwrap()
            .iter()
            .map(|category| fixture_string(category).to_string())
            .collect();
        let expected_categories: BTreeSet<_> = expected["categories"]
            .as_array()
            .unwrap()
            .iter()
            .map(|category| fixture_string(category).to_string())
            .collect();
        assert_eq!(expected_categories, actual_categories);

        let external_links: Value = serde_json::from_str(&external_links_json).unwrap();
        let actual_external_urls: BTreeSet<_> = external_links
            .as_array()
            .unwrap()
            .iter()
            .map(|link| fixture_string(&link["url"]).to_string())
            .collect();
        let expected_external_urls: BTreeSet<_> = expected["external_urls"]
            .as_array()
            .unwrap()
            .iter()
            .map(|url| fixture_string(url).to_string())
            .collect();
        assert_eq!(expected_external_urls, actual_external_urls);

        let mut fact_statement = connection
            .prepare(
                "SELECT subject,relationship,object,evidence_text,extraction_method,
                        source_page_id,source_title
                 FROM candidate_facts
                 WHERE dump_id=?1 AND source_page_id=?2",
            )
            .unwrap();
        let fact_rows = fact_statement
            .query_map(rusqlite::params![dump_id, page_id], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, String>(3)?,
                    row.get::<_, String>(4)?,
                    row.get::<_, i64>(5)?,
                    row.get::<_, String>(6)?,
                ))
            })
            .unwrap()
            .collect::<rusqlite::Result<Vec<_>>>()
            .unwrap();
        let actual_facts: BTreeSet<_> = fact_rows
            .iter()
            .map(|fact| {
                (
                    fact.0.clone(),
                    fact.1.clone(),
                    fact.2.clone(),
                    fact.3.clone(),
                    fact.4.clone(),
                )
            })
            .collect();
        let expected_facts: BTreeSet<_> = expected["facts"]
            .as_array()
            .unwrap()
            .iter()
            .map(|fact| {
                (
                    fixture_string(&fact["subject"]).to_string(),
                    fixture_string(&fact["relationship"]).to_string(),
                    fixture_string(&fact["object"]).to_string(),
                    fixture_string(&fact["evidence"]).to_string(),
                    fixture_string(&fact["extraction_method"]).to_string(),
                )
            })
            .collect();
        assert_eq!(expected_facts, actual_facts, "facts for {title}");
        for fact in &fact_rows {
            assert_eq!(fact.5, page_id);
            assert_eq!(fact.6, title);
            assert!(!fact.3.is_empty());
        }

        let mut candidate_statement = connection
            .prepare(
                "SELECT entity_type,value,evidence_text,extraction_method,
                        source_type,source_id,source_page_id,source_title
                 FROM entity_candidates
                 WHERE dump_id=?1 AND source_page_id=?2",
            )
            .unwrap();
        let candidate_rows = candidate_statement
            .query_map(rusqlite::params![dump_id, page_id], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, String>(3)?,
                    row.get::<_, String>(4)?,
                    row.get::<_, String>(5)?,
                    row.get::<_, i64>(6)?,
                    row.get::<_, String>(7)?,
                ))
            })
            .unwrap()
            .collect::<rusqlite::Result<Vec<_>>>()
            .unwrap();
        let actual_candidates: BTreeSet<_> = candidate_rows
            .iter()
            .map(|candidate| (candidate.0.clone(), candidate.1.clone()))
            .collect();
        let expected_candidates: BTreeSet<_> = expected["typed_candidates"]
            .as_array()
            .unwrap()
            .iter()
            .map(|candidate| {
                (
                    fixture_string(&candidate["entity_type"]).to_string(),
                    fixture_string(&candidate["value"]).to_string(),
                )
            })
            .collect();
        assert_eq!(
            expected_candidates, actual_candidates,
            "typed candidates for {title}"
        );
        for candidate in &candidate_rows {
            assert_eq!(candidate.4, "uesp");
            assert_eq!(candidate.5, source_name);
            assert_eq!(candidate.6, page_id);
            assert_eq!(candidate.7, title);
            assert!(candidate.2.contains("{{"));
            assert!(!candidate.3.is_empty());
        }
    }

    let export_path = temporary.path().join("rust-knowledge.json");
    let exported_count =
        knowledge::export_knowledge_base(&database_path, dump_id, &export_path).unwrap();
    let exported: Value = serde_json::from_slice(&std::fs::read(export_path).unwrap()).unwrap();
    let required_fields: BTreeSet<_> = [
        "subject",
        "relationship",
        "object",
        "source_page",
        "source_page_id",
        "evidence",
        "extraction_method",
        "confidence",
    ]
    .into_iter()
    .collect();
    let mut actual_export = BTreeMap::new();
    for fact in exported.as_array().unwrap() {
        let fields: BTreeSet<_> = fact
            .as_object()
            .unwrap()
            .keys()
            .map(String::as_str)
            .collect();
        assert_eq!(fields, required_fields);
        assert!((0.0..=1.0).contains(&fact["confidence"].as_f64().unwrap()));
        actual_export.insert(
            (
                fixture_string(&fact["subject"]).to_string(),
                fixture_string(&fact["relationship"]).to_string(),
                fixture_string(&fact["object"]).to_string(),
                fixture_string(&fact["source_page"]).to_string(),
                fact["source_page_id"].as_i64().unwrap(),
                fixture_string(&fact["evidence"]).to_string(),
                fixture_string(&fact["extraction_method"]).to_string(),
            ),
            fact["confidence"].as_f64().unwrap(),
        );
    }
    let expected_export: BTreeMap<_, _> = pages
        .iter()
        .flat_map(|page| {
            page["expected"]["facts"]
                .as_array()
                .unwrap()
                .iter()
                .map(move |fact| {
                    (
                        (
                            fixture_string(&fact["subject"]).to_string(),
                            fixture_string(&fact["relationship"]).to_string(),
                            fixture_string(&fact["object"]).to_string(),
                            fixture_string(&page["title"]).to_string(),
                            page["page_id"].as_i64().unwrap(),
                            fixture_string(&fact["evidence"]).to_string(),
                            fixture_string(&fact["extraction_method"]).to_string(),
                        ),
                        fact["confidence"].as_f64().unwrap(),
                    )
                })
        })
        .collect();
    assert_eq!(exported_count, expected_export.len());
    assert_eq!(
        actual_export.keys().collect::<BTreeSet<_>>(),
        expected_export.keys().collect::<BTreeSet<_>>()
    );
    for (fact, expected_confidence) in expected_export {
        let actual_confidence = actual_export[&fact];
        assert!((actual_confidence - expected_confidence).abs() < 1e-12);
    }
}
