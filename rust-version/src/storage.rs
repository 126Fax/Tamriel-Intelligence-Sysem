use anyhow::{Context, Result};
use rusqlite::{Connection, OpenFlags};
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone)]
struct StorageFile {
    path: PathBuf,
    bytes: u64,
    category: &'static str,
}

#[derive(Debug)]
struct DatabaseStats {
    page_size: u64,
    page_count: u64,
    free_pages: u64,
    table_rows: Vec<(&'static str, u64)>,
}

fn human_size(bytes: u64) -> String {
    const UNITS: [&str; 5] = ["B", "KiB", "MiB", "GiB", "TiB"];
    let mut value = bytes as f64;
    let mut unit = 0;
    while value >= 1024.0 && unit < UNITS.len() - 1 {
        value /= 1024.0;
        unit += 1;
    }
    if unit == 0 {
        format!("{bytes} B")
    } else {
        format!("{value:.2} {}", UNITS[unit])
    }
}

fn classify(path: &Path, root: &Path) -> &'static str {
    let relative = path.strip_prefix(root).unwrap_or(path);
    let text = relative.to_string_lossy().replace('\\', "/");
    let name = path.file_name().and_then(|value| value.to_str()).unwrap_or("");

    if text.starts_with("data/raw/") || name.ends_with(".xml.bz2") {
        "Original source dump"
    } else if name.ends_with(".db") || name.ends_with(".db-wal") || name.ends_with(".db-shm") {
        "SQLite database and sidecars"
    } else if text.starts_with("rust-version/data/") || name == "knowledge_base.json" {
        "Generated exports and reports"
    } else {
        "Other tracked data"
    }
}

fn collect_files(directory: &Path, root: &Path, files: &mut Vec<StorageFile>) -> Result<()> {
    if !directory.exists() {
        return Ok(());
    }
    for entry in fs::read_dir(directory).with_context(|| format!("reading {}", directory.display()))? {
        let entry = entry?;
        let path = entry.path();
        let file_type = entry.file_type()?;
        if file_type.is_dir() {
            collect_files(&path, root, files)?;
        } else if file_type.is_file() {
            let bytes = entry.metadata()?.len();
            files.push(StorageFile {
                category: classify(&path, root),
                path,
                bytes,
            });
        }
    }
    Ok(())
}

fn add_database_sidecars(path: &Path, root: &Path, files: &mut Vec<StorageFile>) -> Result<()> {
    for candidate in [
        path.to_path_buf(),
        PathBuf::from(format!("{}-wal", path.display())),
        PathBuf::from(format!("{}-shm", path.display())),
    ] {
        if candidate.is_file() && !files.iter().any(|file| file.path == candidate) {
            files.push(StorageFile {
                category: classify(&candidate, root),
                bytes: fs::metadata(&candidate)?.len(),
                path: candidate,
            });
        }
    }
    Ok(())
}

fn database_stats(path: &Path) -> Result<Option<DatabaseStats>> {
    if !path.is_file() {
        return Ok(None);
    }
    let connection = Connection::open_with_flags(path, OpenFlags::SQLITE_OPEN_READ_ONLY)
        .with_context(|| format!("opening database read-only: {}", path.display()))?;
    let page_size: u64 = connection.query_row("PRAGMA page_size", [], |row| row.get(0))?;
    let page_count: u64 = connection.query_row("PRAGMA page_count", [], |row| row.get(0))?;
    let free_pages: u64 = connection.query_row("PRAGMA freelist_count", [], |row| row.get(0))?;

    let tables = [
        "source_dumps",
        "pages",
        "page_analysis",
        "page_template_parameters",
        "page_links",
        "candidate_facts",
        "entity_candidates",
        "external_observations",
        "ai_pages",
    ];
    let mut table_rows = Vec::new();
    for table in tables {
        let exists: bool = connection.query_row(
            "SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type='table' AND name=?1)",
            [table],
            |row| row.get(0),
        )?;
        if exists {
            let sql = format!("SELECT COUNT(*) FROM \"{table}\"");
            let count: u64 = connection.query_row(&sql, [], |row| row.get(0))?;
            table_rows.push((table, count));
        }
    }

    Ok(Some(DatabaseStats {
        page_size,
        page_count,
        free_pages,
        table_rows,
    }))
}

/// Print a read-only inventory of the source dump, SQLite files and generated data.
pub fn print_report(project_root: &Path, database_path: &Path) -> Result<()> {
    let mut files = Vec::new();
    for relative in ["data/raw", "data/database", "rust-version/data"] {
        collect_files(&project_root.join(relative), project_root, &mut files)?;
    }
    let python_export = project_root.join("knowledge_base.json");
    if python_export.is_file() {
        files.push(StorageFile {
            category: classify(&python_export, project_root),
            bytes: fs::metadata(&python_export)?.len(),
            path: python_export,
        });
    }
    add_database_sidecars(database_path, project_root, &mut files)?;
    files.sort_by(|left, right| left.path.cmp(&right.path));

    let mut totals = BTreeMap::<&str, u64>::new();
    for file in &files {
        *totals.entry(file.category).or_default() += file.bytes;
    }
    let total_bytes: u64 = files.iter().map(|file| file.bytes).sum();
    let source_bytes = totals.get("Original source dump").copied().unwrap_or(0);
    let generated_bytes = totals.get("Generated exports and reports").copied().unwrap_or(0);
    let database_bytes = totals.get("SQLite database and sidecars").copied().unwrap_or(0);

    println!("Tamriel Intelligence storage report");
    println!("===================================");
    println!("All sizes use binary units (1 MiB = 1,024 KiB).");
    println!();
    println!("Storage totals:");
    println!("  Original compressed source dump: {}", human_size(source_bytes));
    println!("  SQLite databases and sidecars:   {}", human_size(database_bytes));
    println!("  Generated exports and reports:   {}", human_size(generated_bytes));
    println!("  All inventoried data:             {}", human_size(total_bytes));
    println!();

    println!("Files:");
    if files.is_empty() {
        println!("  No data files found in the scanned locations.");
    } else {
        for file in &files {
            let display_path = file.path.strip_prefix(project_root).unwrap_or(&file.path);
            println!("  {:>12}  {}", human_size(file.bytes), display_path.display());
        }
    }
    println!();

    println!("Rust SQLite database details:");
    println!("  Path: {}", database_path.display());
    match database_stats(database_path)? {
        Some(stats) => {
            let allocated = stats.page_size.saturating_mul(stats.page_count);
            let free = stats.page_size.saturating_mul(stats.free_pages);
            println!("  Allocated SQLite pages: {}", human_size(allocated));
            println!("  Free pages inside database: {} ({})", stats.free_pages, human_size(free));
            println!("  Page size: {} bytes", stats.page_size);
            println!("  Table row counts:");
            for (table, rows) in stats.table_rows {
                println!("    {table}: {rows}");
            }
        }
        None => println!("  Database file not found; import or initialise it first."),
    }
    println!();
    println!("Note: SQLite allocated pages describe the main database file. WAL/SHM sidecars");
    println!("are listed separately and included in the SQLite file total. No files were changed.");
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::human_size;

    #[test]
    fn formats_sizes_in_understandable_units() {
        assert_eq!(human_size(512), "512 B");
        assert_eq!(human_size(1024), "1.00 KiB");
        assert_eq!(human_size(1024 * 1024), "1.00 MiB");
        assert_eq!(human_size(1024_u64 * 1024 * 1024), "1.00 GiB");
    }
}
