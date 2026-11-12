

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
