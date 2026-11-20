use std::path::Path;
use tamriel_intelligence::{database, top_down, wiki};

#[test]
fn extracts_nested_template_parameters_and_wikilinks() {
    let source = "{{Character Summary|race=Nord|occupation=Scholar|notes={{Small|text=Researcher}}}}\n[[Skyrim|the north]]";
    let result = wiki::analyse_wikitext(12,"Example",source);
    assert_eq!(result.template_count,1);
    assert_eq!(result.link_count,1);
    assert!(result.parameters.iter().any(|p| p.parameter_name=="race" && p.value=="Nord"));
    assert!(result.parameters.iter().any(|p| p.parameter_name=="occupation" && p.value=="Scholar"));
}

#[test]
fn extracts_explicit_relationships_with_page_evidence() {
    let facts = wiki::extract_facts(
        "Skyrim is a province of the Empire. Nords live in Skyrim.",
        7,"Example",&[]
    );
    assert!(facts.iter().any(|f| f.relationship=="province" && f.object=="Empire"));
    assert!(facts.iter().any(|f| f.relationship=="lives in" && f.subject=="Nords"));
    assert!(facts.iter().all(|f| f.source_page_id==7 && !f.evidence.is_empty()));
}

#[test]
fn database_schema_and_top_down_lookup_work() {
    let temporary = tempfile::tempdir().unwrap();
    let path = temporary.path().join("test.db");
    let connection = database::connect(&path).unwrap();
    connection.execute("INSERT INTO source_dumps(source_name) VALUES ('fixture.xml.bz2')",[]).unwrap();
    connection.execute(
        "INSERT INTO pages(dump_id,page_id,title,namespace_id,namespace_name,revision_id,text_length,page_text)
         VALUES (1,1,'Dragons',0,'',1,25,'Dragons live in Skyrim.')",[]
    ).unwrap();
    connection.execute(
        "INSERT INTO candidate_facts(dump_id,source_page_id,source_title,subject,relationship,object,evidence_text,extraction_method,confidence)
         VALUES (1,1,'Dragons','Dragons','lives in','Skyrim','Dragons live in Skyrim.','test',0.9)",[]
    ).unwrap();
    drop(connection);
    let answer = top_down::answer_question(&path,"Where do dragons live?").unwrap();
    assert!(answer.contains("Skyrim"));
    assert!(answer.contains("Dragons"));
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
    let inserted = tamriel_intelligence::external::import_observations(&input,&db).unwrap();
    assert_eq!(inserted,2);
    let connection = database::connect(&db).unwrap();
    let users: i64 = connection.query_row(
        "SELECT COUNT(*) FROM external_observations WHERE source_type='user'",[],|row| row.get(0)
    ).unwrap();
    let mods: i64 = connection.query_row(
        "SELECT COUNT(*) FROM external_observations WHERE source_type='mod' AND mod_id='sample-mod'",[],|row| row.get(0)
    ).unwrap();
    assert_eq!(users,1);
    assert_eq!(mods,1);
}
