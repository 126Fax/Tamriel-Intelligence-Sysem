#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

step() {
  printf '\n\n========== %s ==========\n' "$1"
}

fail() {
  printf '\nERROR: %s\n' "$1" >&2
  exit 1
}

step "Checking system requirements"

command -v curl >/dev/null 2>&1 || fail "curl is required to install Rust."
command -v python3 >/dev/null 2>&1 || fail "Python 3 is required for the Python reference tests."

if ! command -v rustc >/dev/null 2>&1 || ! command -v cargo >/dev/null 2>&1; then
  step "Rust not found - installing stable Rust with rustup"
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile default --component clippy --component rustfmt
fi

if [[ -f "$HOME/.cargo/env" ]]; then
  # Load Cargo into PATH for this script, including after a fresh installation.
  # shellcheck disable=SC1091
  source "$HOME/.cargo/env"
fi

command -v rustc >/dev/null 2>&1 || fail "rustc is still unavailable after the Rust installation."
command -v cargo >/dev/null 2>&1 || fail "cargo is still unavailable after the Rust installation."

step "Checking Rust toolchain"
rustc --version
cargo --version
rustup component add clippy rustfmt

step "Preparing Python test environment"
if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

step "Testing Rust comparison engine"
cargo test --manifest-path rust-engine/Cargo.toml

step "Testing Rust implementation"
cargo test --manifest-path rust-version/Cargo.toml

step "Building Rust comparison engine (release)"
cargo build --release --manifest-path rust-engine/Cargo.toml

step "Building Rust implementation (release)"
cargo build --release --manifest-path rust-version/Cargo.toml

step "Testing Python reference implementation"
.venv/bin/python -m unittest discover -s tests -p "test_*.py" -v

step "All requested checks passed"
printf 'Rust engine tests: PASS\n'
printf 'Rust implementation tests: PASS\n'
printf 'Rust release builds: PASS\n'
printf 'Python reference tests: PASS\n'
