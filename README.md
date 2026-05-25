# common-helpers

Personal scripts, shell shortcuts, and small utilities.

## Setup

Create a local virtual environment and install Python dependencies (`colorama` for `commit.py`):

```bash
python3 setup.py
source .venv/bin/activate   # optional; commit.py auto-uses .venv when present
```

Add shell shortcuts to `~/.bashrc`:

```bash
source /home/mjp/common-helpers/bash-shortcuts.sh
```

## Contents

| Item | Description |
|------|-------------|
| [`commit.py`](commit.py) | Interactive git helper: status, stage all, commit, push. Alias **`gg`** in `bash-shortcuts.sh`. See [`commit.md`](commit.md). |
| [`Make_ssh_public_private_key.py`](Make_ssh_public_private_key.py) | Generate Ed25519 keys, update `~/.ssh/config`, deploy keys to remote hosts (single, batch, or Slurm). See [`Make_ssh_public_private_key.md`](Make_ssh_public_private_key.md). |
| [`count_files.sh`](count_files.sh) | Count files (alias **`c`** in `bash-shortcuts.sh`). |
| [`clean_cache.sh`](clean_cache.sh) | Clear Chrome, Chromium, Firefox, and pip cache files. |
| [`bash-shortcuts.sh`](bash-shortcuts.sh) | Aliases, `PATH`, prompt, and editor settings for daily use. |
| [`setup.py`](setup.py) | Bootstraps `.venv/` and installs required packages. |
| [`utils/`](utils/) | Shared Python helpers (`git.py`, `get_yes_no.py`). See [`utils/README.md`](utils/README.md). |
| [`ssh_2fa/`](ssh_2fa/) | Ansible playbook for SSH 2FA with Google Authenticator and internal-network bypass. See [`ssh_2fa/README.md`](ssh_2fa/README.md). |
| [`rmdir_depth.sh`](rmdir_depth.sh) | Remove empty directories under the current path (`find … -empty -exec rmdir`). |

## Documentation

Each major script has a matching `.md` file with version, features, and usage examples.
