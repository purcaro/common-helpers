# Make_ssh_public_private_key.py

**Version:** 1.1.0

SSH key manager and config sync tool. Generates Ed25519 key pairs, maintains `~/.ssh/config`, and deploys public keys to remote hosts—supporting single servers, batch patterns, and Slurm cluster nodes.

## Requirements

- Python 3
- `ssh-keygen`, `ssh`
- `sshpass` (required for automated password-based deployment)

## Features

### SSH key generation

- Creates **Ed25519** keys per host alias: `~/.ssh/id_ed25519_<alias>` and `.pub`
- Optional **key passphrase** (prompted interactively; empty allowed)
- Skips generation if both private and public key files already exist
- Sets permissions: private key `600`, public key `644`

### Local `~/.ssh/config` management

- Ensures `~/.ssh` exists with mode `700`
- Appends a host block when missing:

  ```
  Host <alias>
    HostName <ip>
    User <username>
    IdentityFile ~/.ssh/id_ed25519_<alias>
    IdentitiesOnly yes
    Port 22
  ```

- **Updates `HostName`** when the resolved IP changes (keeps config in sync with `/etc/hosts` or CLI input)
- Skips adding a new block if the host entry already exists (but may still update IP or deploy keys)
- Config file mode `600`

### IP resolution (priority order)

The tool resolves each host’s address using this chain; higher priority wins and can rewrite `~/.ssh/config`:

1. **`/etc/hosts`** — local override (highest priority)
2. **`~/.ssh/config`** — existing `HostName` for the alias
3. **Command-line arguments** — explicit IP or base subnet

IPv4 addresses are normalized for comparison (e.g. `010.5.16.20` → `10.5.16.20`).

### Public key deployment

- Appends the public key to the remote `~/.ssh/authorized_keys2`
- Creates remote `~/.ssh` with correct permissions via SSH
- Uses **`sshpass`** with a prompted remote SSH password (same password reused for all hosts in a batch)
- `StrictHostKeyChecking=no` for non-interactive first connect

### Single-server mode

Deploy to one host by alias and IP (or rely on `/etc/hosts` when IP is omitted in batch-only scenarios):

```bash
./Make_ssh_public_private_key.py <username> <alias> [<ip>]
```

### Batch mode (`--batch`)

Expand **Slurm-style node lists** and deploy to many hosts:

- Pattern syntax: `prefix[range,range,...]` e.g. `node[10-25,30]` → `node10` … `node25`, `node30`
- **Base IP subnet:** trailing digits of each hostname map to the last octet, e.g. base `10.5.19` + `node10` → `10.5.19.10`
- **Hosts-only batch:** omit base IP when every hostname is listed in `/etc/hosts`

```bash
./Make_ssh_public_private_key.py <username> "<pattern>" [<base_ip>] --batch
```

### Slurm cluster mode (`--slurm`)

Parse **`NodeName=`** entries from a `slurm.conf` file, expand bracket notation, deduplicate, and deploy to all nodes. With `--batch`, the second positional argument is the base IP subnet.

```bash
./Make_ssh_public_private_key.py <username> <base_ip> --batch --slurm /path/to/slurm.conf
```

### Idempotent local setup

If a host already has both keys on disk **and** an entry in `~/.ssh/config`, key generation and config append are skipped; the public key is still pushed to the remote.

### Interactive prompts

- Remote SSH password (for `sshpass`)
- Optional passphrase for newly generated keys

### Help and version

- Run with **no arguments** to print the version and full `--help` text
- **`--version`** prints the version and exits
- **`--help`** / **`-h`** prints usage, description, and examples

## Usage examples

```bash
# Version and help (no arguments)
./Make_ssh_public_private_key.py

# Explicit version
./Make_ssh_public_private_key.py --version

# Single server (explicit IP)
./Make_ssh_public_private_key.py root z011 10.10.16.11

# Single server (IP from /etc/hosts)
./Make_ssh_public_private_key.py admin proxmox-01 0.0.0.0

# Batch: base IP + numeric suffix from hostname
./Make_ssh_public_private_key.py ubuntu "node[10-25,30]" 10.5.19 --batch

# Batch: all hosts resolved via /etc/hosts only
./Make_ssh_public_private_key.py user "compute[01-10]" --batch

# Slurm: all nodes from slurm.conf on a subnet
./Make_ssh_public_private_key.py root 10.20.30 --batch --slurm /etc/slurm/slurm.conf
```

## Version

```bash
./Make_ssh_public_private_key.py              # version + help
./Make_ssh_public_private_key.py --version    # version only
```
