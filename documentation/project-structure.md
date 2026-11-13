# Project Structure

The repository is organised by responsibility. The structure below describes the current folders rather than a proposed future layout.

```text
Tamriel-Intelligence-Sysem/
├── bottom_up/          # Bottom-Up AI prototype and workflow runners
├── top_down/           # Top-Down question analysis prototype
├── src/
│   ├── analysis/       # Page and content analysis
│   ├── database/       # SQLite access and schema
│   ├── ingestion/      # MediaWiki XML and namespace readers
│   └── processing/     # AI-readable data preparation
├── tools/              # Reusable command-line tools
├── tests/
│   └── fixtures/       # Small synthetic XML and evaluation data
├── data/
│   ├── samples/        # Small committed sample input
│   ├── database/       # Local generated databases (ignored by Git)
│   └── processed/      # Local split dumps and manifests (ignored by Git)
├── config/             # Shared paths and ignored local settings
├── docs/               # AI design and development plan
├── documentation/      # Project planning and structure notes
├── README.md
├── requirements.txt
└── .gitignore
```

## Main data flow

1. The XML ingestion code reads MediaWiki exports.
2. The database layer stores the original page text and source metadata.
3. The preparation layer creates a separate AI-readable representation.
4. The Bottom-Up and Top-Down systems can use the stored information for their respective tasks.

## Generated and private data

The original UESP dump, split XML parts, manifests and SQLite databases are local working data. They should remain outside version control. Only small fixtures and sample inputs intended for the repository should be committed.
