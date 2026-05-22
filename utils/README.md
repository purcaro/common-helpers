# utils

Shared Python helpers used by scripts in this repository (notably [`commit.py`](../commit.py)).

## get_yes_no.py

**`GetYesNoToQuestion`** — interactive yes/no prompts with optional single-keystroke input.

### Dependencies

- Standard library only (`termios` / `tty` on Unix, `msvcrt` on Windows)

### API

#### `GetYesNoToQuestion.immediate(question, default="yes")`

Static convenience method. Asks `question` and reads the answer with **one keypress** (no Enter required). Returns `True` for yes, `False` for no.

- **`question`** — prompt string shown to the user
- **`default`** — presumed answer if the user presses Enter with no input; `"yes"`, `"no"`, or `None` (answer required)

Accepted answers: `yes`, `y`, `ye`, `no`, `n` (case-insensitive after lowercasing).

Prompt suffix reflects the default:

| `default` | Prompt |
|-----------|--------|
| `"yes"` | `[Y/n]` |
| `"no"` | `[y/N]` |
| `None` | `[y/n]` |

Invalid input loops with: *Please respond with 'yes' or 'no' (or 'y' or 'n').*

#### `GetYesNoToQuestion.query_yes_no_base(question, default, immediate_input)`

Instance method implementing the prompt logic.

```text
Ask a yes/no question via raw_input() and return their answer.

"question" is a string that is presented to the user.
"default" is the presumed answer if the user just hits <Enter>.
    It must be "yes" (the default), "no" or None (meaning
    an answer is required of the user).

The "answer" return value is one of "yes" or "no".
```

When **`immediate_input`** is `True`, reads a single keypress via `_getch()`; when `False`, uses normal `input()` (Enter to confirm).

### Example

```python
from get_yes_no import GetYesNoToQuestion

if GetYesNoToQuestion.immediate("Proceed?"):
    ...
```

---

## git.py

**`Git`** — static helpers for common git repository checks, push, and maintenance. All git invocations use **`subprocess`** (no shell).

### API

#### `Git.in_git_folder()`

Returns `True` if the current directory is inside a git work tree (`git rev-parse` succeeds), else `False`.

#### `Git.cd_git_root()`

Changes the process working directory to the **repository root** using `git rev-parse --show-cdup`. No-op when already at the root.

#### `Git.no_changes_exist()`

Returns `True` when there is nothing to commit: **`git status --porcelain`** produces no output (unstaged, staged, and untracked changes are all detected).

#### `Git.unpushed_commits()`

Returns `True` when the current branch has commits not yet on its upstream (`git rev-list --count @{upstream}..HEAD` > 0). Returns `False` if there is no upstream or the command fails.

#### `Git.current_branch()`

Returns the abbreviated name of the current branch (`git rev-parse --abbrev-ref HEAD`).

#### `Git.push()`

Runs **`git push`**. On failure (e.g. no upstream configured), retries with **`git push -u origin <branch>`**. Raises `RuntimeError("invalid git push")` if both attempts fail.

#### `Git.repack()`

Runs an aggressive local repack:

```bash
git repack -a -d --depth=250 --window=250 -f
```

Raises `RuntimeError("invalid git repack")` on non-zero exit. Not called by `commit.py`; available for manual or scripted repository maintenance. See [GCC mailing list reference](http://gcc.gnu.org/ml/gcc/2007-12/msg00165.html) in source.

### Example

```python
from git import Git

if Git.in_git_folder():
    Git.cd_git_root()
    if not Git.no_changes_exist():
        ...
    elif Git.unpushed_commits():
        Git.push()
```
