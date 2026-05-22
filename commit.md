# commit.py

**Version:** 1.0.0

Interactive git workflow helper: stage all changes, commit, and push from the repository root with a single-key confirmation prompt.

## Requirements

- Python 3
- `git` on `PATH`
- Python packages: `colorama`, `getch` (used by `utils/get_yes_no.py`)

## Features

### Repository checks

- Verifies the current directory is inside a git repository (`git rev-parse`); exits with an error if not
- Changes working directory to the **git root** before any operations

### Change detection

- Exits successfully with **“nothing to commit”** when:
  - There is no diff in tracked files (`git diff --exit-code`)
  - There are no untracked files (`git status --porcelain`)

### Interactive commit flow

When changes exist:

1. Runs **`git status`** (full output for review)
2. Prompts **`commit?`** — single keystroke yes/no (default **yes**); exits if declined
3. Runs **`git add -A`** (stage all changes, including untracked and deletions)
4. Runs **`git commit`** (uses your normal git commit editor/message flow)
5. Runs **`git push`**

Each git step raises an exception on failure.

### Colored terminal output

Uses **colorama** for status messages:

- Red — not in a git folder
- Green — nothing to commit
- Yellow — commit prompt and “pushing…” message

## Usage

From anywhere inside a git repository:

```bash
./commit.py
```

There are no command-line flags; behavior is fully interactive.

## Utilities

This script imports helpers from the [`utils/`](utils/) directory:

| Module | Role in `commit.py` |
|--------|---------------------|
| [`utils/git.py`](utils/git.py) | `in_git_folder()`, `cd_git_root()`, `no_changes_exist()` |
| [`utils/get_yes_no.py`](utils/get_yes_no.py) | `GetYesNoToQuestion.immediate()` for the commit confirmation |

See [`utils/README.md`](utils/README.md) for full API documentation of both modules.

## Version

```bash
python3 -c "import commit; print(commit.__version__)"
```

Or read `__version__` at the top of `commit.py`.
