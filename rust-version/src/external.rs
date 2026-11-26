use anyhow::Result;
use rusqlite::params;
use serde::Deserialize;
use std::path::Path;

#[derive(Debug,Deserialize)]
struct Observation {
    entity_type: String,
    subject: String,
    value: String,
    source_type: String,
    source_id: String,
    #[serde(default)]
    mod_id: Option<String>,
    #[serde(default)]
    evidence: String,
}

pub fn import_observations(input: &Path, database_path: &Path) -> Result<usize> {
    let observations: Vec<Observation> = serde_json::from_slice(&std::fs::read(input)?)?;
    let mut connection = crate::database::connect(database_path)?;
    let transaction = connection.transaction()?;
    let mut inserted = 0;
    {
        let mut statement = transaction.prepare(
            "INSERT INTO external_observations
             (entity_type,subject,value,source_type,source_id,mod_id,evidence)
             VALUES(?,?,?,?,?,?,?)"
        )?;
        for observation in observations {
            let entity_type = observation.entity_type.to_lowercase();
            if !["race","occupation","book"].contains(&entity_type.as_str()) {
                anyhow::bail!("Unsupported entity_type '{}'; expected race, occupation or book.",observation.entity_type);
            }
            if !["user","mod"].contains(&observation.source_type.as_str()) {
                anyhow::bail!("source_type must be 'user' or 'mod'.");
            }
            if observation.subject.trim().is_empty() || observation.value.trim().is_empty()
                || observation.source_id.trim().is_empty() {
                anyhow::bail!("Each observation needs non-empty subject, value and source_id.");
            }
            if observation.source_type == "mod" && observation.mod_id.as_deref().unwrap_or("").trim().is_empty() {
                anyhow::bail!("Mod observations require mod_id.");
            }
            statement.execute(params![
                entity_type,observation.subject,observation.value,observation.source_type,
                observation.source_id,observation.mod_id,observation.evidence
            ])?;
            inserted += 1;
        }
    }
    transaction.commit()?;
    Ok(inserted)
}
