# SSH Server Ops Toolkit

[![Validate](https://github.com/Xiaoyun-0922/sshops/actions/workflows/validate.yml/badge.svg)](https://github.com/Xiaoyun-0922/sshops/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)
[![Platforms](https://img.shields.io/badge/local-Windows%20%7C%20macOS%20%7C%20Linux-0F6CBD.svg)](#platform-support)

Cross-platform SSH diagnostics, key bootstrap, transfer fallback, and remote command tooling for Linux, POSIX, gateway, and HPC workflows.

`sshops` is intentionally tool-first and skill-second:

- humans can run the toolkit directly
- Codex can use the bundled plugin and skill
- Claude Code can use the bundled plugin or standalone skill layout

The practical goal is simple: make the last mile of SSH work predictable before an agent changes anything on a remote machine.

## At a glance

| Need | Command | Risk |
| --- | --- | --- |
| Diagnose local SSH, network, auth, and transfer readiness | `doctor` | Read-only |
| Create or repair one `~/.ssh/config` host block | `configure` | Local config change |
| Install a public key using one password-backed session | `bootstrap-key` | Remote account config change |
| Copy files when OpenSSH transfer is unreliable | `transfer` | Local or remote file writes |
| Run a remote command in a consistent JSON-wrapped way | `run` | Depends on command |

## What it solves

Common SSH failures are rarely just "SSH is broken". This toolkit separates the layers:

- local client tools are missing or shadowed on PATH
- the TCP route, VPN, firewall, or gateway is wrong
- interactive login works but `BatchMode` key auth fails
- `ssh` works but `scp` or `sftp` is unreliable
- `~/.ssh/config` points at the wrong host, key, user, or port
- a login node, jump host, bastion, or Slurm cluster needs a different workflow from a simple server

## Platform support

| Local machine | Preferred entrypoint | Notes |
| --- | --- | --- |
| Windows | `powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 ...` | Preserves the original Windows-first workflow and OpenSSH ACL repair. |
| Windows | `python .\scripts\sshops.py ...` | Uses the new cross-platform Python CLI. |
| macOS | `python3 ./scripts/sshops.py ...` | Requires OpenSSH client tools on PATH. |
| Linux | `python3 ./scripts/sshops.py ...` | Requires OpenSSH client tools on PATH. |

Remote targets are expected to be Linux, POSIX, gateway, bastion, or HPC login nodes. This is not a Windows remoting or RDP toolkit.

## Requirements

Required:

- OpenSSH client tools on PATH: `ssh`, `scp`, `sftp`
- Python 3.10 or newer for the cross-platform CLI

Optional:

- PowerShell 5.1+ on Windows, or PowerShell Core for validation
- `tar` for tar-over-SSH sync patterns
- Conda or another Python environment with `paramiko` for `bootstrap-key` and `transfer`

## Install and validate

```bash
git clone https://github.com/Xiaoyun-0922/sshops.git
cd sshops
python scripts/validate-toolkit.py
```

On Windows, the original PowerShell validator is still available:

```powershell
git clone https://github.com/Xiaoyun-0922/sshops.git
cd sshops
powershell -ExecutionPolicy Bypass -File .\scripts\validate-toolkit.ps1
```

## Quick start

### 1. Diagnose without saving SSH config

macOS/Linux:

```bash
python3 ./scripts/sshops.py doctor \
  --host-name login.example.edu \
  --port 22 \
  --user alice
```

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 doctor `
  -HostName login.example.edu `
  -Port 22 `
  -User alice
```

`doctor` returns JSON with fields such as `local_tools`, `network`, `auth`, `transfer`, `python_env`, `likely_root_cause`, and `recommended_next_step`.

### 2. Save a reusable host alias

macOS/Linux:

```bash
python3 ./scripts/sshops.py configure \
  --alias gpu-login \
  --host-name login.example.edu \
  --port 22 \
  --user alice \
  --identity-file ~/.ssh/id_ed25519_gpu \
  --preferred-authentications publickey
```

Windows:

```powershell
$keyPath = Join-Path $HOME ".ssh\id_ed25519_gpu"

powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 configure `
  -Alias gpu-login `
  -HostName login.example.edu `
  -Port 22 `
  -User alice `
  -IdentityFile $keyPath `
  -PreferredAuthentications publickey
```

### 3. Re-run diagnosis by alias

macOS/Linux:

```bash
python3 ./scripts/sshops.py doctor --alias gpu-login
```

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 doctor -Alias gpu-login
```

### 4. Run a remote command

macOS/Linux:

```bash
python3 ./scripts/sshops.py run \
  --alias gpu-login \
  --remote-dir ~/repo \
  --command "git status --short" \
  --bash \
  --batch-mode
```

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 run `
  -Alias gpu-login `
  -RemoteDir ~/repo `
  -Command "git status --short" `
  -Bash `
  -BatchMode
```

## Password-backed flows

Do not paste passwords, tokens, private keys, or MFA codes into chat.

For `bootstrap-key` or `transfer`, keep the password in a short-lived local environment variable.

macOS/Linux:

```bash
export SSH_SERVER_PASSWORD="<set-locally-only>"
python3 -m pip install paramiko
python3 ./scripts/sshops.py bootstrap-key \
  --host-name login.example.edu \
  --port 22 \
  --user alice \
  --public-key ~/.ssh/id_ed25519_gpu.pub \
  --private-key ~/.ssh/id_ed25519_gpu
unset SSH_SERVER_PASSWORD
```

Windows with Conda:

```powershell
conda create -y -n sshops python=3.11
conda run -n sshops python -m pip install paramiko

$env:SSH_SERVER_PASSWORD = "<set-locally-only>"
powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 bootstrap-key `
  -HostName login.example.edu `
  -Port 22 `
  -User alice `
  -PublicKey "$HOME\.ssh\id_ed25519_gpu.pub" `
  -PrivateKey "$HOME\.ssh\id_ed25519_gpu" `
  -CondaEnv sshops
Remove-Item Env:SSH_SERVER_PASSWORD
```

## Transfer fallback

Use direct `scp` or `sftp` when OpenSSH transfer is healthy. Use `transfer` when password-backed Paramiko SFTP is the more reliable fallback.

macOS/Linux:

```bash
export SSH_SERVER_PASSWORD="<set-locally-only>"
python3 ./scripts/sshops.py transfer \
  --host-name login.example.edu \
  --port 22 \
  --user alice \
  --direction download \
  --remote-path /path/on/remote \
  --local-path ./local-copy
unset SSH_SERVER_PASSWORD
```

Windows:

```powershell
$env:SSH_SERVER_PASSWORD = "<set-locally-only>"
powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 transfer `
  -HostName login.example.edu `
  -Port 22 `
  -User alice `
  -Direction download `
  -RemotePath /path/on/remote `
  -LocalPath .\local-copy `
  -CondaEnv sshops
Remove-Item Env:SSH_SERVER_PASSWORD
```

## Agent usage

This repository includes:

- Codex plugin metadata at [`.codex-plugin/plugin.json`](./.codex-plugin/plugin.json)
- Claude plugin metadata at [`.claude-plugin/plugin.json`](./.claude-plugin/plugin.json)
- Standard skill layout at [`skills/ssh-server-ops/`](./skills/ssh-server-ops/)
- A root-level standalone [`SKILL.md`](./SKILL.md)

Install the whole repository or plugin, not only `skills/ssh-server-ops/`. The skill depends on the repo-root `scripts/` and `references/` directories.

Example prompt:

```text
Use $ssh-server-ops to run a read-only diagnosis on my HPC login node and recommend the next safe action.
```

## Security model

- `doctor` is the preferred first step because it is read-only.
- Never store passwords in `~/.ssh/config`, repo files, prompt templates, or logs.
- Keep password bootstrap local to the terminal session through `SSH_SERVER_PASSWORD`.
- Treat delete, reset, overwrite, restart, install, and production-impacting commands as explicit-approval operations.
- On HPC systems, distinguish login nodes, compute nodes, scheduler allocations, and shared storage before making changes.

See [SECURITY.md](./SECURITY.md) for the publishing and secret-handling checklist.

## Repository layout

```text
.
|-- .claude-plugin/
|   |-- marketplace.json
|   `-- plugin.json
|-- .codex-plugin/
|   `-- plugin.json
|-- .github/
|   `-- workflows/
|       `-- validate.yml
|-- agents/
|   `-- openai.yaml
|-- references/
|   |-- hpc-slurm-playbook.md
|   |-- prompt-templates.md
|   `-- windows-linux-ssh-playbook.md
|-- scripts/
|   |-- bootstrap_ssh_key.py
|   |-- configure_ssh_host.ps1
|   |-- paramiko_copy_tree.py
|   |-- remote_run.ps1
|   |-- server_preflight.ps1
|   |-- sshops.py
|   |-- sshops.ps1
|   |-- validate-toolkit.py
|   `-- validate-toolkit.ps1
|-- skills/
|   `-- ssh-server-ops/
|       |-- SKILL.md
|       `-- agents/
|           `-- openai.yaml
|-- tests/
|   `-- test_sshops_cli.py
|-- README.md
|-- SECURITY.md
|-- SKILL.md
`-- LICENSE
```

## Roadmap

- first-class `scp` and `sftp` probes in `doctor`
- explicit transport fallback reporting
- tar-over-SSH sync helpers
- richer `transfer` checksums, retries, and dry-run support
- dedicated HPC subcommands instead of playbook-only guidance
- packaged `sshops` CLI distribution
