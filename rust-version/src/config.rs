use anyhow::{bail, Context, Result};
use std::path::{Path, PathBuf};

pub fn project_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent().expect("rust-version must be inside the repository")
        .to_path_buf()
}

pub fn default_database() -> PathBuf {
    project_root().join("data/database/tamriel_intelligence_rust.db")
}

pub fn default_knowledge_base() -> PathBuf {
    project_root().join("rust-version/data/knowledge_base.json")
}

pub fn find_dump(explicit: Option<PathBuf>) -> Result<PathBuf> {
    if let Some(path) = explicit {
        if path.is_file() { return Ok(path); }
        bail!("The specified XML dump does not exist: {}", path.display());
    }
    let raw = project_root().join("data/raw");
    let mut dumps = std::fs::read_dir(&raw)
        .with_context(|| format!("reading {}", raw.display()))?
        .filter_map(|entry| entry.ok().map(|e| e.path()))
        .filter(|path| path.file_name().and_then(|n| n.to_str())
            .map(|name| name.ends_with(".xml.bz2")).unwrap_or(false))
        .collect::<Vec<_>>();
    dumps.sort();
    match dumps.len() {
        0 => bail!("No .xml.bz2 dump found in {}. Pass --dump PATH.", raw.display()),
        1 => Ok(dumps.remove(0)),
        _ => bail!("Multiple .xml.bz2 dumps found in {}. Pass --dump PATH to choose one.", raw.display()),
    }
}
