# VACUUM vs Zstandard compression experiment

This branch is based on `experiment/lossless-storage`. It isolates a comparison between SQLite's `VACUUM` rebuild and Zstandard (Zstd) lossless file compression. It does not change the Rust database schema or production write path.

## What the benchmark does automatically

Run the script once. It performs the complete comparison without requiring manual changes between settings:

1. Opens the supplied SQLite source in read-only mode.
2. Creates an independent SQLite baseline copy.
3. Makes a second copy and runs `VACUUM` on that copy.
4. Tests Zstandard levels 1, 3, 5, 7, 9, 12, 15, 18, 19, 20, 21 and 22 by default.
5. Compresses both the unchanged and VACUUMed copies at every selected level.
6. Measures compressed size, bytes saved, reduction percentage, compression time and decompression time.
7. Decompresses every archive and checks that its SHA-256 is byte-identical to the exact SQLite input.
8. Runs SQLite integrity and foreign-key checks against every restored database.
9. Writes a complete `comparison.json` report and retains the SQLite copies and all compressed archives.

This gives two separate answers:
- How much does VACUUM reduce the live SQLite database?
- How much smaller can an unchanged or VACUUMed database become when stored as a Zstandard archive?

## Requirements

- Python 3.10 or newer.
- SQLite support from Python's standard library.
- The Zstandard command-line program (`zstd`).

On Ubuntu/Debian-based Codespaces, install Zstandard if it is missing:

```bash
sudo apt-get update
sudo apt-get install -y zstd
```

Check it is available:

```bash
zstd --version
```

## Run

From the repository root, use a new output directory for each run:

```bash
python3 scripts/benchmark_vacuum_vs_zstd.py \
  --source data/experiments/lossless-storage/100k-source/tamriel_100k.db \
  --output-dir data/experiments/vacuum-vs-zstd/100k
```

The output directory must not already exist. The source path above is an example for the 100,000-page database; use the path to the sample you want to measure.

To test a different set of levels, pass them all in one run:

```bash
python3 scripts/benchmark_vacuum_vs_zstd.py \
  --source PATH_TO_DATABASE \
  --output-dir PATH_TO_NEW_OUTPUT_DIRECTORY \
  --levels 1,3,5,7,9,12,15,18,19,20,21,22
```

The default already tests those levels, so no manual level-by-level reruns are needed. Levels must be between 1 and 22. Each compression run uses one worker thread so timings are less affected by uncontrolled parallelism.

## Output

The output directory contains:
- `baseline-unchanged.sqlite`: independent SQLite baseline copy.
- `candidate-vacuum.sqlite`: independent copy after VACUUM.
- `unchanged-zstd-LEVEL.db.zst`: archives of the unchanged copy.
- `vacuumed-zstd-LEVEL.db.zst`: archives of the VACUUMed copy.
- `comparison.json`: sizes, timings, checksums, integrity results and settings.

Temporary decompressed verification files are removed automatically.

## Important interpretation

A `.zst` file is a compressed archive, not a live SQLite database. SQLite cannot query it directly; it must be decompressed first. Therefore Zstandard is suitable for backups, archival and transfer, not a direct replacement for the active database format in this experiment.

The script compares Zstandard on both the unchanged and VACUUMed SQLite files. This avoids incorrectly attributing VACUUM's size reduction to Zstandard. It also verifies byte-for-byte restoration, which is stronger than checking only row counts.

Compression timings depend on CPU, disk speed, cache state and the Zstandard build. Treat one run as an initial comparison; repeat runs before drawing conclusions about speed. Do not compare timings from different machines as if they were controlled.

The source database is never modified. All generated files are contained in the new output directory. Do not commit large experiment databases or archives unless explicitly intended.
