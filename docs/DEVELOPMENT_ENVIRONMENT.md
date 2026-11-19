# Development environment

## Use one virtual environment

The project uses one local Python virtual environment at the repository root:
`.venv/`. Do not create a separate environment for each component or test
suite. The bottom-up system, top-down system, pipeline and tests all use the
same interpreter and installed dependencies.

Create it once:

```bash
python3 -m venv .venv
```

Activate it in a Codespace/Linux terminal:

```bash
source .venv/bin/activate
```

Install the project dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Check which interpreter is active:

```bash
which python
python --version
echo "$VIRTUAL_ENV"
```

The active interpreter should resolve inside this repository's `.venv`
directory. In VS Code/Codespaces, select that same interpreter for the
workspace rather than creating another environment.

## If duplicate environments already exist

First inspect them and check which one is active:

```bash
echo "Active environment: $VIRTUAL_ENV"
ls -ld .venv .venv-* venv venv-* 2>/dev/null
du -sh .venv .venv-* venv venv-* 2>/dev/null
```

Do not delete the environment shown by `$VIRTUAL_ENV`. Once you have confirmed
that an extra environment is inactive and contains no unique work, it can be
removed explicitly, for example:

```bash
rm -rf venv-1
```

Replace `venv-1` with the exact duplicate directory you inspected. This is a
local cleanup operation; virtual environments are not stored in GitHub.

The repository's `.gitignore` excludes `.venv`, `.venv-*`, `venv` and
`venv-*` so local environments do not become repository files.
