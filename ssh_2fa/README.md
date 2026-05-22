# SSH 2-Factor Authentication with Internal Network Bypass

This Ansible playbook deploys Two-Factor Authentication via Google Authenticator (`libpam-google-authenticator`) for SSH logins on Ubuntu 22.04/24.04 LTS. Run it locally with `./run.sh`, which executes:

```bash
ansible-playbook -i "localhost," -c local ssh_2fa.yml --ask-become-pass
```

That applies `ssh_2fa.yml` to the current machine with `sudo` (you will be prompted for your password).

## Architecture & Authentication Logic

The playbook configures PAM and OpenSSH as follows:

- **External connections (everything except the internal subnets below):** `AuthenticationMethods keyboard-interactive` — users must authenticate with **password + TOTP**. SSH keys alone are not accepted, and plain password logins without 2FA are blocked.
- **Internal connections (`192.168.1.0/24` and `127.0.0.1`):** A PAM access rule skips the Google Authenticator module for these addresses. The OpenSSH `Match Address` block then allows **SSH key, plain password, or keyboard-interactive** without requiring TOTP (convenient for home/office environments routed through a Ubiquiti UDM Ultra gateway).

Only users listed in the playbook variable `allowed_ssh_users` (default: `mjp`) may SSH in.

## Setup Walkthrough

Complete these steps **in order**.

### 1. Generate your TOTP secret (required before deployment)

The playbook sets `allow_missing_totp: no`, so each allowed user must already have a `~/.google_authenticator` file before you run the playbook.

Run the initialization tool as your normal user account:

```bash
google-authenticator
```

Answer the setup wizard prompts as follows:

- **Time-based tokens?** `y`
- **Scan QR Code:** Pull out your phone and scan the terminal text block.
- **Emergency scratch codes:** Copy and save the 5 backup codes securely!
- **Update configuration file?** `y`
- **Disallow multiple uses of the same token (replay protection)?** `y`
- **Extend log window to 4 minutes?** `n` *(Keeps a tight 1.5-minute drift allowance).*
- **Enable rate-limiting?** `y`

> **💡 Accidental Input Fix:** If you mistakenly answered `y` to the 4-minute window expansion, restore the strict security window by running:
>
> ```bash
> sed -i '/^" WINDOW_SIZE/d' ~/.google_authenticator
> ```

### 2. Deploy the server configuration

From this directory, run:

```bash
./run.sh
```

The playbook will:

- Install `libpam-google-authenticator`
- Add a PAM access file (`/etc/security/access-ssh-totp.conf`) and wire it into `/etc/pam.d/sshd` so internal IPs skip TOTP
- Enable `pam_google_authenticator.so` in PAM
- Set global SSH options: `UsePAM yes`, `KbdInteractiveAuthentication yes`, `AllowUsers`, and `AuthenticationMethods keyboard-interactive`
- Append a `Match Address` block to `/etc/ssh/sshd_config` for the internal bypass subnets
- Restart the `ssh` service if `sshd_config` changed

### Configuration variables

Edit `ssh_2fa.yml` to customize:

| Variable | Default | Purpose |
|----------|---------|---------|
| `pam_internal_subnets` | `192.168.1.0/24 127.0.0.1` | Space-separated subnets for the PAM access bypass file |
| `ssh_internal_subnets` | `192.168.1.0/24,127.0.0.1` | Comma-separated subnets for the OpenSSH `Match Address` block |
| `allowed_ssh_users` | `mjp` | Space-separated list of users allowed to SSH in |
| `allow_missing_totp` | `no` | Set to `yes` only during initial rollout before all users have run `google-authenticator` |

## Troubleshooting & Verification

If your terminal client uses active connection persistence (`ControlMaster`), it will reuse open background sockets and bypass the new 2FA prompts entirely.

To force a completely raw, non-cached handshake for testing, execute:

```bash
ssh -p 9870 -o ControlMaster=no mjp@starr3.mine.nu
```

To drop and terminate lingering background multiplex paths entirely:

```bash
ssh -O exit -p 9870 mjp@starr3.mine.nu
```
