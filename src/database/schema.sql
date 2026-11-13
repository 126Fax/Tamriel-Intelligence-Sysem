

CREATE TABLE IF NOT EXISTS source_dumps (
    dump_id INTEGER PRIMARY KEY,
    source_name TEXT NOT NULL,
    dump_date TEXT,
    import_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (import_status IN ('pending', 'importing', 'completed', 'failed')),
    completed_at TEXT,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);



CREATE TABLE IF NOT EXISTS pages (
    dump_id INTEGER NOT NULL,
    page_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    namespace_id INTEGER NOT NULL,
    namespace_name TEXT NOT NULL,
    revision_id INTEGER,
    text_length INTEGER NOT NULL,
    page_text TEXT NOT NULL DEFAULT '',

    PRIMARY KEY (dump_id, page_id),

    FOREIGN KEY (dump_id)
        REFERENCES source_dumps(dump_id)
);


CREATE INDEX IF NOT EXISTS idx_pages_title
ON pages(title);


CREATE INDEX IF NOT EXISTS idx_pages_namespace
ON pages(namespace_id);


CREATE INDEX IF NOT EXISTS idx_pages_revision
ON pages(revision_id);


-- AI-readable representations are stored separately from the original pages.
-- The source pages table remains the unmodified record of the imported wiki dump.
CREATE TABLE IF NOT EXISTS ai_pages (
    dump_id INTEGER NOT NULL,
    page_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    namespace_id INTEGER NOT NULL,
    namespace_name TEXT NOT NULL,
    revision_id INTEGER,
    readable_text TEXT NOT NULL DEFAULT '',
    headings_json TEXT NOT NULL DEFAULT '[]',
    templates_json TEXT NOT NULL DEFAULT '[]',
    links_json TEXT NOT NULL DEFAULT '[]',
    categories_json TEXT NOT NULL DEFAULT '[]',
    external_links_json TEXT NOT NULL DEFAULT '[]',
    source_text_hash TEXT NOT NULL,
    processor_version TEXT NOT NULL,
    prepared_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (dump_id, page_id),

    FOREIGN KEY (dump_id, page_id)
        REFERENCES pages(dump_id, page_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ai_pages_title
ON ai_pages(title);

CREATE INDEX IF NOT EXISTS idx_ai_pages_namespace
ON ai_pages(namespace_id);

CREATE INDEX IF NOT EXISTS idx_ai_pages_revision
ON ai_pages(revision_id);
