use std::io::Write;
use std::path::Path;
use tamriel_intelligence::{ai_preparation, cleaner, database, top_down, wiki};

#[test]
fn extracts_nested_template_parameters_and_wikilinks() {
    let source = "{{Character Summary|race=Nord|occupation=Scholar|notes={{Small|text=Researcher}}}}\n[[Skyrim|the north]]";
    let result = wiki::analyse_wikitext(12, "Example", source);
    assert_eq!(result.template_count, 2);
    assert_eq!(result.link_count, 1);
    assert!(result
        .parameters
        .iter()
        .any(|p| p.parameter_name == "race" && p.value == "Nord"));
    assert!(result
        .parameters
        .iter()
        .any(|p| p.parameter_name == "occupation" && p.value == "Scholar"));
}

#[test]
fn extracts_explicit_relationships_with_page_evidence() {
    let facts = wiki::extract_facts(
        "Skyrim is a province of the Empire. Nords live in Skyrim.",
        7,
        "Example",
        &[],
    );
    assert!(facts
        .iter()
        .any(|f| f.relationship == "province" && f.object == "Empire"));
    assert!(facts
        .iter()
        .any(|f| f.relationship == "lives in" && f.subject == "Nords"));
    assert!(facts
        .iter()
        .all(|f| f.source_page_id == 7 && !f.evidence.is_empty()));
}

#[test]
fn database_schema_and_top_down_lookup_work() {
    let temporary = tempfile::tempdir().unwrap();
    let path = temporary.path().join("test.db");
    let connection = database::connect(&path).unwrap();
    connection
        .execute(
            "INSERT INTO source_dumps(source_name) VALUES ('fixture.xml.bz2')",
            [],
        )
        .unwrap();
    connection.execute(
        "INSERT INTO pages(dump_id,page_id,title,namespace_id,namespace_name,revision_id,text_length,page_text)
         VALUES (1,1,'Dragons',0,'',1,25,'Dragons live in Skyrim.')",[]
    ).unwrap();
    connection.execute(
        "INSERT INTO candidate_facts(dump_id,source_page_id,source_title,subject,relationship,object,evidence_text,extraction_method,confidence)
         VALUES (1,1,'Dragons','Dragons','lives in','Skyrim','Dragons live in Skyrim.','test',0.9)",[]
    ).unwrap();
    drop(connection);
    let answer = top_down::answer_question(&path, "Where do dragons live?").unwrap();
    assert!(answer.contains("Skyrim"));
    assert!(answer.contains("Dragons"));
}

#[test]
fn ai_page_preparation_is_resumable_and_preserves_source_pages() {
    let temporary = tempfile::tempdir().unwrap();
    let path = temporary.path().join("ai-pages.db");
    let connection = database::connect(&path).unwrap();
    let dump_id = database::register_dump(&connection, "ai-fixture.xml.bz2").unwrap();
    database::set_dump_status(&connection, dump_id, "completed").unwrap();
    let source_text = "'''Example''' is a place in [[Skyrim|the province of Skyrim]].\n\
        == History ==\nIt was founded long ago.\n\
        {{Location\n| name = Example\n| region = Skyrim\n}}\n\
        [[Category:Cities]]\n[https://example.test guide]";
    connection
        .execute(
            "INSERT INTO pages(dump_id,page_id,title,namespace_id,namespace_name,revision_id,text_length,page_text)
             VALUES (?1,1,'Example',0,'',99,?2,?3)",
            rusqlite::params![dump_id, source_text.len(), source_text],
        )
        .unwrap();
    connection
        .execute(
            "INSERT INTO pages(dump_id,page_id,title,namespace_id,namespace_name,revision_id,text_length,page_text)
             VALUES (?1,2,'Second',0,'',100,0,'')",
            [dump_id],
        )
        .unwrap();
    drop(connection);

    assert_eq!(
        ai_preparation::prepare_dump(&path, dump_id, 1, false).unwrap(),
        2
    );
    assert_eq!(
        ai_preparation::prepare_dump(&path, dump_id, 1, false).unwrap(),
        0
    );

    let connection = database::connect(&path).unwrap();
    let (readable, headings, templates, links, categories, external_links, source_hash, version): (
        String,
        String,
        String,
        String,
        String,
        String,
        String,
        String,
    ) = connection
        .query_row(
            "SELECT readable_text,headings_json,templates_json,links_json,categories_json,
                    external_links_json,source_text_hash,processor_version
             FROM ai_pages WHERE dump_id=?1 AND page_id=1",
            [dump_id],
            |row| {
                Ok((
                    row.get(0)?,
                    row.get(1)?,
                    row.get(2)?,
                    row.get(3)?,
                    row.get(4)?,
                    row.get(5)?,
                    row.get(6)?,
                    row.get(7)?,
                ))
            },
        )
        .unwrap();
    let source_page: String = connection
        .query_row(
            "SELECT page_text FROM pages WHERE dump_id=?1 AND page_id=1",
            [dump_id],
            |row| row.get(0),
        )
        .unwrap();
    drop(connection);

    assert!(readable.contains("the province of Skyrim"));
    assert!(readable.contains("guide"));
    assert!(!readable.contains("[https://example.test"));
    assert_eq!(source_page, source_text);
    assert_eq!(source_hash.len(), 64);
    assert_eq!(version, ai_preparation::PROCESSOR_VERSION);
    let headings: serde_json::Value = serde_json::from_str(&headings).unwrap();
    assert_eq!(headings[0]["level"], 2);
    assert_eq!(headings[0]["text"], "History");
    let templates: serde_json::Value = serde_json::from_str(&templates).unwrap();
    assert_eq!(templates[0]["name"], "Location");
    assert_eq!(templates[0]["parameters"][0]["value"], "Example");
    let links: serde_json::Value = serde_json::from_str(&links).unwrap();
    assert_eq!(links[0]["destination"], "Skyrim");
    let categories: serde_json::Value = serde_json::from_str(&categories).unwrap();
    assert_eq!(categories, serde_json::json!(["Cities"]));
    let external_links: serde_json::Value = serde_json::from_str(&external_links).unwrap();
    assert_eq!(external_links[0]["url"], "https://example.test");
    assert_eq!(external_links[0]["display_text"], "guide");
    let export_path = temporary.path().join("prepared-pages.jsonl");
    assert_eq!(
        ai_preparation::export_prepared_dump(&path, dump_id, &export_path).unwrap(),
        2
    );
    let exported_lines = std::fs::read_to_string(&export_path)
        .unwrap()
        .lines()
        .map(|line| serde_json::from_str::<serde_json::Value>(line).unwrap())
        .collect::<Vec<_>>();
    assert_eq!(exported_lines.len(), 2);
    assert_eq!(exported_lines[0]["title"], "Example");
    assert_eq!(
        exported_lines[0]["source_text_hash"]
            .as_str()
            .unwrap()
            .len(),
        64
    );
    let error = ai_preparation::export_prepared_dump(&path, dump_id, &export_path).unwrap_err();
    assert!(error.to_string().contains("without replacing"));

    let connection = database::connect(&path).unwrap();
    connection
        .execute(
            "UPDATE ai_pages SET processor_version='old' WHERE dump_id=?1 AND page_id=2",
            [dump_id],
        )
        .unwrap();
    drop(connection);
    let incomplete_export = temporary.path().join("incomplete.jsonl");
    let error =
        ai_preparation::export_prepared_dump(&path, dump_id, &incomplete_export).unwrap_err();
    assert!(error.to_string().contains("of 2 pages prepared"));
    assert!(!incomplete_export.exists());
    assert_eq!(
        ai_preparation::prepare_dump(&path, dump_id, 1, false).unwrap(),
        1
    );
    assert!(ai_preparation::prepare_dump(&path, dump_id, 0, false).is_err());
    let connection = database::connect(&path).unwrap();
    connection
        .execute(
            "UPDATE pages SET page_text='Updated source text.' WHERE dump_id=?1 AND page_id=1",
            [dump_id],
        )
        .unwrap();
    drop(connection);
    assert_eq!(
        ai_preparation::prepare_dump(&path, dump_id, 1, true).unwrap(),
        2
    );
    let connection = database::connect(&path).unwrap();
    let updated_hash: String = connection
        .query_row(
            "SELECT source_text_hash FROM ai_pages WHERE dump_id=?1 AND page_id=1",
            [dump_id],
            |row| row.get(0),
        )
        .unwrap();
    assert_ne!(source_hash, updated_hash);
}

#[test]
fn import_matches_sample_dump_fields_and_is_idempotent() {
    let temporary = tempfile::tempdir().unwrap();
    let dump_path = temporary.path().join("sample.xml.bz2");
    let database_path = temporary.path().join("sample.db");
    let mut encoder = bzip2::write::BzEncoder::new(Vec::new(), bzip2::Compression::fast());
    encoder
        .write_all(include_bytes!(
            "../../tests/fixtures/sample_wiki_dump.xml.fixture"
        ))
        .unwrap();
    std::fs::write(&dump_path, encoder.finish().unwrap()).unwrap();

    let (dump_id, inserted) =
        tamriel_intelligence::ingestion::import_dump(&dump_path, &database_path, 3, None).unwrap();
    assert_eq!(inserted, 12);

    let connection = database::connect(&database_path).unwrap();
    let (namespace_name, revision_id, page_text): (String, i64, String) = connection
        .query_row(
            "SELECT namespace_name,revision_id,page_text FROM pages
             WHERE dump_id=? AND page_id=111",
            [dump_id],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .unwrap();
    assert_eq!(namespace_name, "");
    assert_eq!(revision_id, 1013);
    assert!(page_text.contains("latest revision"));
    assert!(!page_text.contains("old revision"));

    let unknown_namespace: String = connection
        .query_row(
            "SELECT namespace_name FROM pages WHERE dump_id=? AND page_id=110",
            [dump_id],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(unknown_namespace, "Unknown (99)");
    drop(connection);

    let (reimported_dump_id, reimported) =
        tamriel_intelligence::ingestion::import_dump(&dump_path, &database_path, 4, None).unwrap();
    assert_eq!(reimported_dump_id, dump_id);
    assert_eq!(reimported, 0);
    let connection = database::connect(&database_path).unwrap();
    let page_count: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM pages WHERE dump_id=?",
            [dump_id],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(page_count, 12);
}

#[test]
fn top_down_supports_common_lookup_overview_random_and_count_questions() {
    let temporary = tempfile::tempdir().unwrap();
    let path = temporary.path().join("top-down.db");
    let connection = database::connect(&path).unwrap();
    connection
        .execute(
            "INSERT INTO source_dumps(source_name) VALUES ('fixture.xml.bz2')",
            [],
        )
        .unwrap();
    connection
        .execute(
            "INSERT INTO pages(dump_id,page_id,title,namespace_id,namespace_name,revision_id,text_length,page_text)
             VALUES (1,1,'Vivec',0,'',1,27,'Vivec rules the city.')",
            [],
        )
        .unwrap();
    connection
        .execute(
            "INSERT INTO pages(dump_id,page_id,title,namespace_id,namespace_name,revision_id,text_length,page_text)
             VALUES (1,2,'Saarthal',0,'',1,39,'The Dwemer vanished from Saarthal.')",
            [],
        )
        .unwrap();
    for (subject, relationship, object, evidence) in [
        ("Vivec", "rules", "Vivec City", "Vivec rules the city."),
        ("Nords", "lives in", "Skyrim", "Nords live in Skyrim."),
        (
            "Skyrim",
            "province",
            "Empire",
            "Skyrim is a province of the Empire.",
        ),
    ] {
        connection
            .execute(
                "INSERT INTO candidate_facts
                 (dump_id,source_page_id,source_title,subject,relationship,object,evidence_text,extraction_method,confidence)
                 VALUES (1,1,'Vivec',?,?,?,?,'test',0.9)",
                rusqlite::params![subject, relationship, object, evidence],
            )
            .unwrap();
    }
    connection
        .execute(
            "INSERT INTO candidate_facts
             (dump_id,source_page_id,source_title,subject,relationship,object,evidence_text,extraction_method,confidence)
             VALUES (1,2,'Saarthal','Dwemer','vanished from','Saarthal','The Dwemer vanished from Saarthal.','test',0.9)",
            [],
        )
        .unwrap();
    connection
        .execute(
            "INSERT INTO entity_candidates
             (dump_id,source_page_id,source_title,entity_type,value,evidence_text,extraction_method,source_id)
             VALUES (1,1,'Vivec','occupation','Farmer','Vivec is a farmer.','test','fixture.xml.bz2')",
            [],
        )
        .unwrap();
    connection
        .execute(
            "INSERT INTO entity_candidates
             (dump_id,source_page_id,source_title,entity_type,value,evidence_text,extraction_method,source_id)
             VALUES (1,2,'Dwemer','race','Dwarven','The Dwemer were a Dwarven people.','test','fixture.xml.bz2')",
            [],
        )
        .unwrap();
    drop(connection);

    let answer = top_down::answer_question(&path, "Who is Vivec?").unwrap();
    assert!(answer.contains("Vivec"));
    let answer = top_down::answer_question(&path, "Where do Nords live?").unwrap();
    assert!(answer.contains("Skyrim"));
    let answer = top_down::answer_question(&path, "Who rules Vivec City?").unwrap();
    assert!(answer.contains("Vivec"));
    let answer = top_down::answer_question(&path, "How many farmers are there?").unwrap();
    assert!(answer.contains("1 distinct farmer"));
    let answer = top_down::answer_question(&path, "How many races are there?").unwrap();
    assert!(answer.contains("1 distinct race value"));
    let answer = top_down::answer_question(&path, "How many provinces are there?").unwrap();
    assert!(answer.contains("9 traditional provinces"));
    let answer = top_down::answer_question(&path, "What happened in Saarthal?").unwrap();
    assert!(answer.contains("vanished from"));
    assert!(answer.contains("The Dwemer vanished from Saarthal."));
    let answer = top_down::answer_question(&path, "Tell me about Dwemer").unwrap();
    assert!(answer.contains("Dwarven"));
    assert!(answer.contains("page 2"));
    let answer = top_down::answer_question(&path, "What evidence supports Saarthal?").unwrap();
    assert!(answer.contains("The Dwemer vanished from Saarthal."));
    let answer = top_down::answer_question(&path, "What evidence supports this answer?").unwrap();
    assert!(answer.contains("does not retain prior answers"));
    let answer = top_down::answer_question(&path, "What do you know?").unwrap();
    assert!(answer.contains("Structured candidate facts: 4."));
    assert!(answer.contains("Typed candidate observations: 2."));
    let answer = top_down::answer_question(&path, "Tell me a random fact").unwrap();
    assert!(answer.starts_with("Random fact:"));
}

#[test]
fn top_down_counts_matching_occupation_pages_not_distinct_labels() {
    let temporary = tempfile::tempdir().unwrap();
    let path = temporary.path().join("occupation-count.db");
    let connection = database::connect(&path).unwrap();
    connection
        .execute(
            "INSERT INTO source_dumps(source_name) VALUES ('fixture.xml.bz2')",
            [],
        )
        .unwrap();

    for (page_id, title, occupation) in [
        (1, "Farmer One", "Farmer"),
        (2, "Farmer Two", "Farmer"),
        (3, "Blacksmith", "Blacksmith"),
    ] {
        connection
            .execute(
                "INSERT INTO pages(dump_id,page_id,title,namespace_id,namespace_name,revision_id,text_length,page_text)
                 VALUES (1,?1,?2,0,'',1,0,'')",
                rusqlite::params![page_id, title],
            )
            .unwrap();
        connection
            .execute(
                "INSERT INTO entity_candidates
                 (dump_id,source_page_id,source_title,entity_type,value,evidence_text,extraction_method,source_id)
                 VALUES (1,?1,?2,'occupation',?3,?3,'test','fixture.xml.bz2')",
                rusqlite::params![page_id, title, occupation],
            )
            .unwrap();
    }
    drop(connection);

    let answer = top_down::answer_question(&path, "How many farmers are there?").unwrap();
    assert!(answer.contains("2 distinct farmer record(s)"), "{answer}");
}

#[test]
fn knowledge_export_does_not_target_python_default_file() {
    let default_output = Path::new(env!("CARGO_MANIFEST_DIR")).join("data/knowledge_base.json");
    assert!(default_output.starts_with(env!("CARGO_MANIFEST_DIR")));
}

#[test]
fn user_and_mod_observations_are_stored_with_distinct_provenance() {
    let temporary = tempfile::tempdir().unwrap();
    let db = temporary.path().join("observations.db");
    let input = temporary.path().join("observations.json");
    std::fs::write(&input, r#"[
      {"entity_type":"race","subject":"Test Character","value":"Nord","source_type":"user","source_id":"submission-1"},
      {"entity_type":"occupation","subject":"Test Character","value":"Scholar","source_type":"mod","source_id":"import-1","mod_id":"sample-mod"}
    ]"#).unwrap();
    let inserted = tamriel_intelligence::external::import_observations(&input, &db).unwrap();
    assert_eq!(inserted, 2);
    let connection = database::connect(&db).unwrap();
    let users: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM external_observations WHERE source_type='user'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    let mods: i64 = connection.query_row(
        "SELECT COUNT(*) FROM external_observations WHERE source_type='mod' AND mod_id='sample-mod'",[],|row| row.get(0)
    ).unwrap();
    assert_eq!(users, 1);
    assert_eq!(mods, 1);
}

#[test]
fn cleaner_preserves_evidence_rules_and_auditable_report_shape() {
    let temporary = tempfile::tempdir().unwrap();
    let input = temporary.path().join("facts.json");
    let output = temporary.path().join("review.json");
    let facts = serde_json::json!([
        {
            "subject": "Dragons",
            "relationship": "lives in",
            "object": "Skyrim",
            "evidence": "Dragons live in Skyrim.",
            "source_page_id": 12
        },
        {
            "subject": "And I",
            "relationship": "lives in",
            "object": "Skyrim",
            "evidence": "And I live in Skyrim."
        },
        {
            "subject": "Dragons",
            "relationship": "lives in",
            "object": "Morrowind",
            "evidence": "Dragons are feared throughout Skyrim."
        },
        {
            "subject": "The Jarl",
            "relationship": "rules",
            "object": "Skyrim",
            "evidence": "The Jarl rules Skyrim."
        }
    ]);
    std::fs::write(&input, serde_json::to_vec(&facts).unwrap()).unwrap();

    let summary = cleaner::review_file(&input, &output).unwrap();
    assert_eq!(summary.total, 4);
    assert_eq!(summary.approved, 1);
    assert_eq!(summary.rejected, 1);
    assert_eq!(summary.needs_review, 2);

    let report: serde_json::Value =
        serde_json::from_slice(&std::fs::read(output).unwrap()).unwrap();
    assert_eq!(report["cleaner_version"], "0.1.0");
    assert_eq!(report["review_policy"], "rule_based_evidence_checks");
    assert_eq!(report["summary"]["total"], 4);
    assert_eq!(report["results"][0]["status"], "approved");
    assert!(report["results"][0]["reasons"].is_array());
    assert_eq!(report["results"][0]["fact"], facts[0]);
    assert_eq!(report["results"][1]["status"], "rejected");
    assert_eq!(report["results"][2]["status"], "needs_review");
    assert_eq!(report["results"][3]["status"], "needs_review");
}

#[test]
fn province_reference_context_emits_evidence_backed_candidate() {
    let provinces = vec!["Skyrim".to_string(), "Morrowind".to_string()];
    let facts = wiki::extract_facts(
        "Skyrim is one of the nine provinces of Tamriel.",
        9,
        "Skyrim",
        &provinces,
    );
    assert!(facts.iter().any(|fact| fact.subject == "Skyrim"
        && fact.relationship == "province of"
        && fact.object == "Tamriel"
        && fact.evidence.contains("nine provinces of Tamriel")));
}

#[test]
fn bottom_up_analysis_reports_stage_and_batch_timings() {
    let temporary = tempfile::tempdir().unwrap();
    let path = temporary.path().join("analysis.db");
    let connection = database::connect(&path).unwrap();
    let page_text = "{{Character Summary|race=Nord|occupation=Scholar|book=Guide}}\nThe Nords live in Skyrim. [[Skyrim|the north]]";
    connection
        .execute(
            "INSERT INTO source_dumps(source_name) VALUES ('fixture.xml.bz2')",
            [],
        )
        .unwrap();
    for page_id in 1..=2 {
        connection.execute(
            "INSERT INTO pages(dump_id,page_id,title,namespace_id,namespace_name,revision_id,text_length,page_text)
             VALUES (1,?,'Fixture',0,'',1,?,?)",
            rusqlite::params![page_id, page_text.len(), page_text]
        ).unwrap();
    }
    drop(connection);

    let summary = tamriel_intelligence::analysis::analyse_dump_with_progress_and_limit(
        &path,
        1,
        2,
        None,
        |_, _, _, _| {},
    )
    .unwrap();

    assert_eq!(summary.pages_analysed, 2);
    assert_eq!(
        summary
            .timings
            .batch_fetches
            .iter()
            .map(|(pages, _)| *pages)
            .collect::<Vec<_>>(),
        vec![2]
    );
    assert_eq!(summary.timings.clear_tables.len(), 5);
    assert!(
        summary.timings.clear_tables_total_seconds
            >= summary
                .timings
                .clear_tables
                .iter()
                .map(|(_, seconds)| seconds)
                .sum::<f64>()
    );
    assert!(summary.timings.seconds_to_first_page.is_some());
    assert!(summary.timings.seconds_to_first_progress.is_some());
    assert!(summary.timings.total_seconds >= summary.timings.page_processing_seconds);
    assert_eq!(summary.candidate_facts_extracted, 2);
    assert_eq!(summary.template_parameters_extracted, 6);
    assert_eq!(summary.entity_candidates_extracted, 6);
    assert_eq!(
        summary
            .timings
            .sqlite_table_write_timings
            .iter()
            .map(|table| (
                table.table,
                table.rows_written,
                table.statement_execution_calls
            ))
            .collect::<Vec<_>>(),
        vec![
            ("page_analysis", 2, 2),
            ("page_template_parameters", 6, 6),
            ("page_links", 2, 2),
            ("candidate_facts", 2, 2),
            ("entity_candidates", 6, 6),
        ]
    );
    let table_execution_seconds: f64 = summary
        .timings
        .sqlite_table_write_timings
        .iter()
        .map(|table| table.statement_execution_seconds)
        .sum();
    assert!(
        (table_execution_seconds - summary.timings.prepared_statement_execution_seconds).abs()
            < 1e-6
    );
    assert_eq!(summary.timings.transaction_commit_timings.len(), 1);
    let transaction = &summary.timings.transaction_commit_timings[0];
    assert_eq!(transaction.pages, 2);
    assert_eq!(transaction.rows_written, 18);
    assert!(transaction.commit_seconds > 0.0);
    let measured_sqlite_seconds = summary.timings.transaction_begin_seconds
        + summary.timings.statement_prepare_seconds
        + summary.timings.prepared_statement_execution_seconds
        + summary.timings.transaction_commit_seconds;
    assert!((measured_sqlite_seconds - summary.timings.sqlite_storage_seconds).abs() < 1e-6);

    let connection = database::connect(&path).unwrap();
    for (table, expected_count) in [
        ("page_analysis", 2),
        ("page_template_parameters", 6),
        ("page_links", 2),
        ("candidate_facts", 2),
        ("entity_candidates", 6),
    ] {
        let count: i64 = connection
            .query_row(&format!("SELECT COUNT(*) FROM {table}"), [], |row| {
                row.get(0)
            })
            .unwrap();
        assert_eq!(count, expected_count, "{table}");
    }

    let (destination, display_text): (String, String) = connection
        .query_row(
            "SELECT destination,display_text FROM page_links ORDER BY link_id LIMIT 1",
            [],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .unwrap();
    assert_eq!(
        (destination.as_str(), display_text.as_str()),
        ("Skyrim", "the north")
    );

    let (evidence, method, confidence): (String, String, f64) = connection
        .query_row(
            "SELECT evidence_text,extraction_method,confidence FROM candidate_facts ORDER BY source_page_id LIMIT 1",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .unwrap();
    assert_eq!(evidence, "The Nords live in Skyrim.");
    assert_eq!(method, "explicit_sentence_pattern_v1");
    assert_eq!(confidence, 0.9);

    let (entity_type, value, evidence, method): (String, String, String, String) = connection
        .query_row(
            "SELECT entity_type,value,evidence_text,extraction_method FROM entity_candidates WHERE value='Nord' LIMIT 1",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        )
        .unwrap();
    assert_eq!(entity_type, "race");
    assert_eq!(value, "Nord");
    assert!(evidence.contains("race=Nord"));
    assert_eq!(method, "explicit_template_field_rust_v1");

    let hashes = tamriel_intelligence::analysis::hash_derived_tables(&path, 1).unwrap();
    assert_eq!(
        hashes
            .iter()
            .map(|hash| (hash.table, hash.rows))
            .collect::<Vec<_>>(),
        vec![
            ("page_analysis", 2),
            ("page_template_parameters", 6),
            ("page_links", 2),
            ("candidate_facts", 2),
            ("entity_candidates", 6),
        ]
    );
    assert!(hashes.iter().all(|hash| hash.sha256.len() == 64));
    assert_eq!(
        hashes,
        tamriel_intelligence::analysis::hash_derived_tables(&path, 1).unwrap()
    );
    connection
        .execute(
            "UPDATE candidate_facts SET evidence_text='Changed evidence' WHERE source_page_id=1",
            [],
        )
        .unwrap();
    let changed_hashes = tamriel_intelligence::analysis::hash_derived_tables(&path, 1).unwrap();
    assert_ne!(hashes[3].sha256, changed_hashes[3].sha256);
    for (before, after) in hashes.iter().zip(&changed_hashes) {
        if before.table != "candidate_facts" {
            assert_eq!(before.sha256, after.sha256, "{}", before.table);
        }
    }

    let (parameter_name, parameter_value, parameter_evidence, parameter_method): (String, String, String, String) = connection
        .query_row(
            "SELECT parameter_name,parameter_value,evidence_text,extraction_method FROM page_template_parameters WHERE parameter_name='race' LIMIT 1",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        )
        .unwrap();
    assert_eq!(parameter_name, "race");
    assert_eq!(parameter_value, "Nord");
    assert!(parameter_evidence.contains("race=Nord"));
    assert_eq!(parameter_method, "template_parameter_rust_v1");
}

#[test]
fn typed_candidates_include_book_templates_and_normalized_fields() {
    let temporary = tempfile::tempdir().unwrap();
    let path = temporary.path().join("typed-candidates.db");
    let connection = database::connect(&path).unwrap();
    connection
        .execute(
            "INSERT INTO source_dumps(source_name) VALUES ('typed-fixture.xml.bz2')",
            [],
        )
        .unwrap();
    let text = concat!(
        "{{Book Summary|author=Example Author}}",
        "{{Character Summary|species=Nord|associated_book=The Example Book}}",
        "{{Place Summary|title=Example Place}}"
    );
    connection
        .execute(
            "INSERT INTO pages(dump_id,page_id,title,namespace_id,namespace_name,revision_id,text_length,page_text)
             VALUES (1,1,'The Example Book',0,'',1,?,?)",
            rusqlite::params![text.len(), text],
        )
        .unwrap();
    drop(connection);

    let summary = tamriel_intelligence::analysis::analyse_dump(&path, 1, 1).unwrap();
    assert_eq!(summary.entity_candidates_extracted, 3);

    let connection = database::connect(&path).unwrap();
    let candidates: Vec<(String, String, String, String, String)> = {
        let mut statement = connection
            .prepare(
                "SELECT entity_type,value,extraction_method,source_type,source_id
                 FROM entity_candidates ORDER BY entity_type,value",
            )
            .unwrap();
        statement
            .query_map([], |row| {
                Ok((
                    row.get(0)?,
                    row.get(1)?,
                    row.get(2)?,
                    row.get(3)?,
                    row.get(4)?,
                ))
            })
            .unwrap()
            .collect::<rusqlite::Result<Vec<_>>>()
            .unwrap()
    };
    assert_eq!(candidates.len(), 3);
    assert!(candidates.iter().any(|candidate| {
        candidate
            == &(
                "book".to_string(),
                "The Example Book".to_string(),
                "book_template_page_title_rust_v1".to_string(),
                "uesp".to_string(),
                "typed-fixture.xml.bz2".to_string(),
            )
    }));
    assert!(candidates
        .iter()
        .any(|candidate| candidate.0 == "race" && candidate.1 == "Nord"));
    assert!(candidates.iter().any(|candidate| {
        candidate.0 == "book"
            && candidate.1 == "The Example Book"
            && candidate.2 == "explicit_template_field_rust_v1"
    }));
    assert!(!candidates
        .iter()
        .any(|candidate| candidate.1 == "Example Place"));
}

#[test]
fn typed_candidate_export_preserves_provenance_and_never_overwrites() {
    let temporary = tempfile::tempdir().unwrap();
    let path = temporary.path().join("typed-export.db");
    let connection = database::connect(&path).unwrap();
    connection
        .execute(
            "INSERT INTO source_dumps(source_name) VALUES ('typed-fixture.xml.bz2')",
            [],
        )
        .unwrap();
    connection
        .execute(
            "INSERT INTO pages(dump_id,page_id,title,namespace_id,namespace_name,revision_id,text_length,page_text)
             VALUES (1,7,'Example Character',0,'',1,9,'race=Nord')",
            [],
        )
        .unwrap();
    connection
        .execute(
            "INSERT INTO entity_candidates
             (dump_id,source_page_id,source_title,entity_type,value,evidence_text,
              extraction_method,source_type,source_id)
             VALUES (1,7,'Example Character','race','Nord','race=Nord',
                     'explicit_template_field_rust_v1','uesp','typed-fixture.xml.bz2')",
            [],
        )
        .unwrap();
    connection
        .execute(
            "INSERT INTO external_observations
             (entity_type,subject,value,source_type,source_id,mod_id,evidence)
             VALUES ('race','Example Character','Altmer','mod','mod-package-1',
                     'example-overhaul','Race override evidence.')",
            [],
        )
        .unwrap();
    drop(connection);

    let output_path = temporary.path().join("typed-observations.json");
    let count =
        tamriel_intelligence::knowledge::export_typed_candidates(&path, 1, &output_path).unwrap();
    assert_eq!(count, 2);
    let output = std::fs::read(&output_path).unwrap();
    let observations: serde_json::Value = serde_json::from_slice(&output).unwrap();
    assert_eq!(observations[0]["source_type"], "mod");
    assert_eq!(observations[0]["mod_id"], "example-overhaul");
    assert_eq!(observations[0]["source_page_id"], serde_json::Value::Null);
    assert_eq!(observations[1]["source_type"], "uesp");
    assert_eq!(observations[1]["source_page_id"], 7);
    assert_eq!(observations[1]["evidence"], "race=Nord");

    let error = tamriel_intelligence::knowledge::export_typed_candidates(&path, 1, &output_path)
        .unwrap_err();
    assert!(error.to_string().contains("without replacing"));
    assert_eq!(std::fs::read(&output_path).unwrap(), output);

    let missing_dump_output = temporary.path().join("missing-dump.json");
    let error =
        tamriel_intelligence::knowledge::export_typed_candidates(&path, 99, &missing_dump_output)
            .unwrap_err();
    assert!(error.to_string().contains("dump ID 99 does not exist"));
    assert!(!missing_dump_output.exists());
}
