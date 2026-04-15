# SSH Server Ops Toolkit

Windows-first SSH bootstrap, diagnostics, transfer fallback, and remote ops toolkit for Linux and HPC workflows.

This project is **tool-first, skill-second**:

- humans can run the toolkit directly from PowerShell
- Codex can use the bundled plugin plus skill
- Claude Code can use the bundled plugin or the standalone skill

The main problem it solves is the messy last mile between a Windows workstation and a real Linux or HPC target:

- `ssh` works but `scp` does not
- interactive login works but `BatchMode` key auth fails
- `~/.ssh/config` or Windows ACLs are wrong
- PowerShell, OpenSSH, Conda, and Python disagree about the environment
- the target is a gateway, bastion, or Slurm login node instead of a simple single host

## What it provides

- `doctor`: read-only diagnosis with structured JSON output
- `configure`: create or repair a host block in `~/.ssh/config`
- `bootstrap-key`: install a public key over one password-backed session, then verify non-interactive access
- `transfer`: Paramiko-backed upload or download fallback when OpenSSH transfer is not usable
- `run`: standardized remote command execution through `ssh`
- `SKILL.md`: bundled agent wrapper for Codex and Claude Code
- `references/hpc-slurm-playbook.md`: first-pass HPC and Slurm guidance

## Requirements

- Windows with PowerShell
- OpenSSH client tools on PATH: `ssh`, `scp`, `sftp`
- `tar`
- optional: Conda plus `paramiko` for `bootstrap-key` and `transfer`

## Quick start

### 1. Clone and validate

```powershell
git clone https://github.com/Xiaoyun-0922/sshops.git
cd sshops

powershell -ExecutionPolicy Bypass -File .\scripts\validate-toolkit.ps1
```

### 2. Optional: prepare the Python environment for password-backed flows

If you only want read-only diagnosis or already have working key auth, you can skip this at first.

If you want `bootstrap-key` or `transfer`, create a Conda environment and install Paramiko:

```powershell
conda create -y -n sshops python=3.11
conda run -n sshops python -m pip install paramiko
```

Then pass `-CondaEnv sshops` to `doctor`, `bootstrap-key`, and `transfer`.

### 3. Run the first diagnosis without saving anything

Use direct mode when you have a host, port, and username but no SSH alias yet:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 doctor `
  -HostName <host-or-ip> `
  -Port <port> `
  -User <user> `
  -CondaEnv sshops
```

Direct mode is the safest first step because it does not change local SSH config.

### 4. Save the host as an SSH alias when you want a reusable entry

Once the target details are known, create or repair a focused host block in `~/.ssh/config`:

```powershell
$keyPath = Join-Path $HOME ".ssh\id_ed25519_myserver"

powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 configure `
  -Alias myserver `
  -HostName <host-or-ip> `
  -Port <port> `
  -User <user> `
  -IdentityFile $keyPath `
  -PreferredAuthentications publickey
```

After this, the saved alias can be used with `-Alias myserver`.

### 5. Re-run diagnosis using the saved alias

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 doctor `
  -Alias myserver `
  -CondaEnv sshops
```

### 6. Run a remote command

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 run `
  -Alias myserver `
  -Command "whoami && pwd" `
  -Bash `
  -BatchMode
```

Run from a remote project directory:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 run `
  -Alias myserver `
  -RemoteDir ~/repo `
  -Command "git status --short" `
  -Bash `
  -BatchMode
```

## How to configure server information

The toolkit supports two styles.

### Style A: direct target

Use this when you do not want to save anything yet.

You provide:

- `-HostName`
- `-Port`
- `-User`

Example:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 doctor `
  -HostName login.example.edu `
  -Port 22 `
  -User alice `
  -CondaEnv sshops
```

This is the best option for first-time diagnosis.

### Style B: saved alias

Use this when you want a reusable host entry in `~/.ssh/config`.

You provide:

- `-Alias`
- `-HostName`
- `-Port`
- `-User`
- optional: `-IdentityFile`
- optional: `-PreferredAuthentications`

Example:

```powershell
$keyPath = Join-Path $HOME ".ssh\id_ed25519_gpu-login"

powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 configure `
  -Alias gpu-login `
  -HostName login.example.edu `
  -Port 22 `
  -User alice `
  -IdentityFile $keyPath `
  -PreferredAuthentications publickey
```

After this, use:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 doctor -Alias gpu-login -CondaEnv sshops
```

## What `doctor` tells you

`doctor` is the preferred first command because it is read-only and returns structured JSON.

Important fields:

- `local_tools`
- `network`
- `auth`
- `transfer`
- `remote_shell`
- `python_env`
- `likely_root_cause`
- `recommended_next_step`

This lets a human or agent tell the difference between:

- local environment problems
- network reachability problems
- SSH key selection problems
- missing Paramiko fallback support

## Password-backed bootstrap

Do not paste passwords into chat or commit them to disk.

Set the password only in the local terminal session:

```powershell
$env:SSH_SERVER_PASSWORD = "<your-password>"
```

Then run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 bootstrap-key `
  -HostName <host-or-ip> `
  -Port <port> `
  -User <user> `
  -PublicKey "$HOME\.ssh\id_ed25519_myserver.pub" `
  -PrivateKey "$HOME\.ssh\id_ed25519_myserver" `
  -CondaEnv sshops
```

Clear the environment variable after use:

```powershell
Remove-Item Env:SSH_SERVER_PASSWORD
```

## Transfer fallback

When diagnosis shows OpenSSH transfer is not the reliable path, use the Paramiko-backed fallback:

```powershell
$env:SSH_SERVER_PASSWORD = "<your-password>"

powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 transfer `
  -HostName <host-or-ip> `
  -Port <port> `
  -User <user> `
  -Direction download `
  -RemotePath /path/on/remote `
  -LocalPath .\local-copy `
  -CondaEnv sshops

Remove-Item Env:SSH_SERVER_PASSWORD
```

## Codex usage

This repo includes a Codex plugin manifest at [`.codex-plugin/plugin.json`](./.codex-plugin/plugin.json).

After installing the plugin, Codex can invoke the bundled skill with prompts like:

```text
Use $ssh-server-ops to diagnose SSH access to my Linux host from this Windows machine.
```

```text
Use $ssh-server-ops to bootstrap key-based SSH access for this server and report the next safe action.
```

The plugin uses the toolkit in `scripts/`, so the PowerShell commands shown above remain the canonical behavior.

## Claude Code usage

This repo includes a Claude plugin manifest at [`.claude-plugin/plugin.json`](./.claude-plugin/plugin.json).

For environments that prefer direct skill installation, the repo root also works as a standalone skill directory because it includes [SKILL.md](./SKILL.md) and the bundled helper scripts.

The practical model is:

- plugin install for Codex or Claude environments that prefer plugins
- direct skill install when Claude Code wants a skill folder
- direct PowerShell usage for humans and shell automation

## Security model

- Do not put passwords, tokens, private keys, or MFA codes into chat.
- Keep password-based bootstrap local to the terminal session only, usually in `SSH_SERVER_PASSWORD`.
- Do not persist passwords in `~/.ssh/config`, repo files, prompt templates, or logs.
- Prefer `doctor` before making changes.
- Treat destructive or production-impacting actions as explicit approvals.

See [SECURITY.md](./SECURITY.md).

## Repository layout

```text
.
|-- .claude-plugin/
|   |-- marketplace.json
|   `-- plugin.json
|-- .codex-plugin/
|   `-- plugin.json
|-- .gitignore
|-- README.md
|-- SECURITY.md
|-- LICENSE
|-- SKILL.md
|-- agents/
|   `-- openai.yaml
|-- references/
|   |-- hpc-slurm-playbook.md
|   |-- prompt-templates.md
|   `-- windows-linux-ssh-playbook.md
`-- scripts/
    |-- bootstrap_ssh_key.py
    |-- configure_ssh_host.ps1
    |-- paramiko_copy_tree.py
    |-- remote_run.ps1
    |-- server_preflight.ps1
    |-- sshops.ps1
    `-- validate-toolkit.ps1
```

## Roadmap

- first-class `scp` and `sftp` probes in `doctor`
- explicit transport fallback reporting
- tar-over-SSH sync helpers
- a standalone packaged `sshops` CLI
- dedicated HPC subcommands instead of playbook-only guidance
