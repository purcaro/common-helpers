# commit.py

**Version:** 1.1.0

Interactive git workflow helper: stage all changes, commit, and push from the repository root with a single-key confirmation prompt.

## Requirements

- Python 3
- `git` on `PATH`
- Run **`python setup.py`** once to create `.venv/` and install **`colorama`**

`commit.py` automatically re-invokes itself with **`.venv/bin/python3`** when that venv exists, so you do not need to activate it first.

## Features

### Repository checks

- Verifies the current directory is inside a git repository (`git rev-parse`); exits with an error if not
- Changes working directory to the **git root** before any operations

### Change detection

- Exits when the working tree is clean, using **`git status --porcelain`** (covers unstaged, staged, and untracked changes)
- If there is nothing to commit but **unpushed commits** exist on the current branch, offers to push them

### Interactive commit flow

When changes exist:

1. Runs **`git status`** (full output for review)
2. Prompts **`commit?`** — single keystroke yes/no (default **yes**); exits if declined
3. Runs **`git add -A`** (stage all changes, including untracked and deletions)
4. Runs **`git commit`** (uses your normal git commit editor/message flow)
5. Runs **`git push`** (unless `--no-push` is set)

Git commands run via **`subprocess`** with clear error messages on failure.

### Push behavior

- Runs **`git push`** after a successful commit
- If push fails (e.g. no upstream yet), retries with **`git push -u origin <branch>`**

### Colored terminal output

Uses **colorama** for status messages:

- Red — not in a git folder, or git command failure
- Green — nothing to commit
- Yellow — commit/push prompts and progress

## Usage

From anywhere inside a git repository:

```bash
./commit.py
./commit.py --no-push    # commit only, skip push
./commit.py --version
```

| Flag | Description |
|------|-------------|
| `--no-push` | Stage and commit, but do not push |
| `--version` | Print version and exit |

## Utilities

This script imports helpers from the [`utils/`](utils/) directory:

| Module | Role in `commit.py` |
|--------|---------------------|
| [`utils/git.py`](utils/git.py) | Repo checks, change detection, unpushed commits, push |
| [`utils/get_yes_no.py`](utils/get_yes_no.py) | `GetYesNoToQuestion.immediate()` for confirmations |

See [`utils/README.md`](utils/README.md) for full API documentation of both modules.

## Version

```bash
./commit.py --version
```
