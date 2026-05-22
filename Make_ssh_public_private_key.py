#!/usr/bin/env python3

import os
import sys
import argparse
import subprocess
import getpass
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional

HOSTS_FILE = Path("/etc/hosts")

def _normalize_ipv4(ip: str) -> str:
    """Canonical dotted IPv4 for comparison (e.g. 010.5.16.20 -> 10.5.16.20)."""
    parts = ip.strip().split(".")
    if len(parts) != 4:
        return ip.strip()
    try:
        return ".".join(str(int(p)) for p in parts)
    except ValueError:
        return ip.strip()

def lookup_ip_in_etc_hosts(hostname: str) -> Optional[str]:
    """Return the IP for hostname from /etc/hosts if present."""
    if not hostname or not HOSTS_FILE.is_file():
        return None
    try:
        hn_lower = hostname.lower()
        with open(HOSTS_FILE, encoding="utf-8", errors="replace") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                parts = []
                for p in line.split():
                    if p.startswith("#"):
                        break
                    parts.append(p)
                if len(parts) < 2:
                    continue
                ip, names = parts[0], parts[1:]
                if any(n.lower() == hn_lower for n in names):
                    return ip
    except OSError:
        return None
    return None

class SSHKeyManager:
    """Manages the creation, configuration, and deployment of SSH keys."""

    def __init__(self, username: str, server_alias: str, server_ip: str, ssh_password: str = None, key_passphrase: str = ""):
        self.username = username
        self.server_alias = server_alias
        self.server_ip = server_ip
        self.ssh_password = ssh_password
        self.key_passphrase = key_passphrase
        
        self.ssh_dir = Path.home() / ".ssh"
        self.config_file = self.ssh_dir / "config"
        self.key_name = f"id_ed25519_{server_alias}"
        self.key_path = self.ssh_dir / self.key_name
        self.pub_key_path = self.ssh_dir / f"{self.key_name}.pub"

    def setup_directories(self):
        """Ensures the local .ssh directory exists with secure permissions."""
        self.ssh_dir.mkdir(parents=True, exist_ok=True)
        self.ssh_dir.chmod(0o700)

    def get_existing_ip_from_config(self):
        """Extracts the HostName (IP) from ~/.ssh/config if the Host entry already exists."""
        if not self.config_file.exists():
            return None
            
        in_target_host = False
        with open(self.config_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line.lower().startswith("host "):
                    hosts = line.split()[1:]
                    if self.server_alias in hosts:
                        in_target_host = True
                    else:
                        in_target_host = False
                elif in_target_host and line.lower().startswith("hostname "):
                    parts = line.split()
                    if len(parts) >= 2:
                        return parts[1]
        return None

    def update_hostname_in_ssh_config(self, new_ip: str) -> bool:
        """If this host's block exists with a different HostName, rewrite it to new_ip."""
        if not self.config_file.exists():
            return False
        existing = self.get_existing_ip_from_config()
        if existing is None or _normalize_ipv4(existing) == _normalize_ipv4(new_ip):
            return False

        lines = self.config_file.read_text().splitlines(keepends=True)
        in_target_host = False
        changed = False
        new_lines = []

        for line in lines:
            stripped = line.strip()
            if stripped.lower().startswith("host "):
                hosts = stripped.split()[1:]
                in_target_host = self.server_alias in hosts
                new_lines.append(line)
            elif in_target_host and stripped.lower().startswith("hostname "):
                indent = line[: len(line) - len(line.lstrip())]
                eol = "\r\n" if line.endswith("\r\n") else "\n"
                new_lines.append(f"{indent}HostName {new_ip}{eol}")
                changed = True
            else:
                new_lines.append(line)

        if changed:
            with open(self.config_file, "w") as f:
                f.writelines(new_lines)
            self.config_file.chmod(0o600)
            print(f"[INFO] Updated ~/.ssh/config: '{self.server_alias}' HostName changed to '{new_ip}'.")
        return changed

    def is_already_configured(self) -> bool:
        host_exists = self.get_existing_ip_from_config() is not None
        keys_exist = self.key_path.exists() and self.pub_key_path.exists()
        return bool(host_exists and keys_exist)

    def generate_key(self):
        if self.key_path.exists():
            return
        print(f"[INFO] Generating new SSH key: {self.key_path}")
        try:
            subprocess.run([
                "ssh-keygen", "-t", "ed25519", "-f", str(self.key_path), "-N", self.key_passphrase
            ], check=True, stdout=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            print("[ERROR] Failed to generate SSH key.", file=sys.stderr)
            sys.exit(1)

    def update_ssh_config(self):
        print(f"[INFO] Adding '{self.server_alias}' to {self.config_file}")
        config_entry = (
            f"\nHost {self.server_alias}\n"
            f"  HostName {self.server_ip}\n"
            f"  User {self.username}\n"
            f"  IdentityFile {self.key_path}\n"
            f"  IdentitiesOnly yes\n"
            f"  Port 22\n"
        )
        with open(self.config_file, 'a') as f:
            f.write(config_entry)
        self.key_path.chmod(0o600)
        self.pub_key_path.chmod(0o644)
        self.config_file.chmod(0o600)

    def copy_key_to_remote(self):
        print(f"[INFO] Pushing public key to {self.username}@{self.server_ip}...")
        remote_cmd = "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys2 && chmod 600 ~/.ssh/authorized_keys2"
        ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", f"{self.username}@{self.server_ip}", remote_cmd]
        env = os.environ.copy()
        if self.ssh_password:
            ssh_cmd = ["sshpass", "-e"] + ssh_cmd
            env["SSHPASS"] = self.ssh_password
        try:
            with open(self.pub_key_path, 'rb') as pub_file:
                subprocess.run(ssh_cmd, stdin=pub_file, env=env, check=True, stderr=subprocess.DEVNULL)
            print(f"[SUCCESS] Public key copied to {self.server_alias}.")
        except Exception as e:
            print(f"[ERROR] Failed to copy key to {self.server_alias}: {e}", file=sys.stderr)

    def run(self):
        self.setup_directories()

        # Resolution Step 1: Check /etc/hosts (Highest Priority Override)
        hosts_ip = lookup_ip_in_etc_hosts(self.server_alias)
        if hosts_ip and _normalize_ipv4(hosts_ip) != _normalize_ipv4(self.server_ip):
            print(f"[INFO] Using IP '{hosts_ip}' from /etc/hosts for '{self.server_alias}'.")
            self.server_ip = hosts_ip

        # Resolution Step 2: Sync with ~/.ssh/config
        existing_config_ip = self.get_existing_ip_from_config()
        if existing_config_ip and _normalize_ipv4(existing_config_ip) != _normalize_ipv4(self.server_ip):
            # If the current resolved IP differs from the config, rewrite the config
            self.update_hostname_in_ssh_config(self.server_ip)
        
        if self.is_already_configured():
            print(f"[INFO] Host '{self.server_alias}' already fully configured locally. Skipping keygen...")
        else:
            self.generate_key()
            if not existing_config_ip:
                self.update_ssh_config()
            
        self.copy_key_to_remote()

def expand_slurm_nodelist(nodelist_str: str) -> list:
    match = re.match(r"^([^\[]+)(?:\[(.*?)\])?$", nodelist_str)
    if not match: return []
    prefix, brackets = match.group(1), match.group(2)
    if not brackets: return [prefix]
    hosts = []
    for part in brackets.split(','):
        if '-' in part:
            start, end = part.split('-')
            for i in range(int(start), int(end) + 1):
                hosts.append(f"{prefix}{str(i).zfill(len(start))}")
        else: hosts.append(f"{prefix}{part}")
    return hosts

def extract_nodes_from_slurm_conf(filepath: str) -> list:
    hosts = []
    try:
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith("NodeName="):
                    node_string = line.split()[0].split('=')[1]
                    hosts.extend(expand_slurm_nodelist(node_string))
        return list(dict.fromkeys(hosts))
    except FileNotFoundError:
        print(f"[ERROR] Slurm configuration file not found: {filepath}")
        sys.exit(1)

def main():
    description = """
SSH Key Manager & Config Sync Tool
----------------------------------
This script deploys SSH keys to remote servers while ensuring your local 
~/.ssh/config remains synchronized. It uses a prioritized resolution chain:
  1. /etc/hosts (Local system override)
  2. ~/.ssh/config (Existing host entry)
  3. Command Line Arguments (Fallback/Initial input)

If a host is found in multiple places with different IPs, the script uses 
the highest priority source and updates your ~/.ssh/config HostName entry 
to match, keeping your connection environment consistent.
"""

    example_text = """
Examples:
  Single Server (Manual IP):
    %(prog)s root z011 10.10.16.11
    # Deploys key to z011 at 10.10.16.11. Creates config entry if missing.

  Single Server (via /etc/hosts):
    # If /etc/hosts has: 192.168.1.50 proxmox-01
    %(prog)s admin proxmox-01 0.0.0.0
    # Automatically resolves proxmox-01 to 192.168.1.50 and deploys.

  Manual Batch Deployment (Base IP + Slurm-style suffix):
    %(prog)s ubuntu "node[10-25,30]" 10.5.19 --batch
    # Deploys to node10 (10.5.19.10) through node30 (10.5.19.30).

  Manual Batch (Strictly via /etc/hosts):
    %(prog)s user "compute[01-10]" --batch
    # Useful when all 10 compute nodes are already in your local /etc/hosts.

  Slurm Cluster Deployment:
    %(prog)s root 10.20.30 --batch --slurm /etc/slurm/slurm.conf
    # Parses all NodeNames from slurm.conf and maps them to the 10.20.30.x subnet.
"""

    parser = argparse.ArgumentParser(
        description=description,
        epilog=example_text,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument("username", help="Remote SSH username")
    parser.add_argument("target", nargs='?', help="Server alias, batch pattern, or Base IP (if using --slurm)")
    parser.add_argument("ip_or_base", nargs='?', help="Full IP, Base IP subnet (e.g. 10.5.1), or omitted if in /etc/hosts")
    
    parser.add_argument("--batch", action="store_true", help="Process multiple hosts using pattern expansion")
    parser.add_argument("--slurm", metavar="FILE", help="Deploy to all nodes defined in a slurm.conf file")

    args = parser.parse_args()

    if not shutil.which("sshpass"):
        print("\n[ERROR] 'sshpass' is required for automated password handling. Please install it.\n")
        sys.exit(1)

    target_hosts = []
    base_ip = None

    # Logic to determine host list and base IP based on flags
    if args.slurm:
        target_hosts = extract_nodes_from_slurm_conf(args.slurm)
        base_ip = args.target if args.batch else None
    elif args.batch:
        if not args.target: parser.error("Target pattern (e.g. node[1-5]) is required for batch mode.")
        target_hosts = expand_slurm_nodelist(args.target)
        base_ip = args.ip_or_base
    else:
        if not args.target: parser.error("Target alias is required.")
        target_hosts = [args.target]
        base_ip = args.ip_or_base

    # Pre-flight check for IP resolution
    if not base_ip:
        missing = [h for h in target_hosts if not lookup_ip_in_etc_hosts(h)]
        if missing:
            print(f"[ERROR] No Base IP provided and some hosts are missing from /etc/hosts: {', '.join(missing)}")
            sys.exit(1)

    ssh_password = getpass.getpass(f"Enter remote SSH password for '{args.username}': ")
    key_passphrase = getpass.getpass("Enter passphrase for new SSH keys (optional): ")

    print(f"\n--- PROCESSING {len(target_hosts)} HOST(S) ---")
    for host in target_hosts:
        server_ip = base_ip
        if base_ip:
            # If we have a base IP, try to append the numeric suffix from the hostname
            match = re.search(r'(\d+)$', host)
            if match:
                server_ip = f"{base_ip}.{int(match.group(1))}"
            # Otherwise, use base_ip as a literal (common for single-server mode)
        else:
            # Fallback to etc hosts resolution
            server_ip = lookup_ip_in_etc_hosts(host) or host

        manager = SSHKeyManager(args.username, host, server_ip, ssh_password, key_passphrase)
        manager.run()

    print("\n[DEPLOYMENT COMPLETE]")

if __name__ == "__main__":
    main()
