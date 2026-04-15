---
name: ssh-server-ops
description: Use when Codex needs to bootstrap, diagnose, or operate SSH access from a Windows machine to Linux, jump hosts, managed gateways, or Slurm/HPC login nodes using the bundled Windows-first toolkit.
---

# SSH Server Ops

This skill is the agent wrapper for the bundled Windows-first SSH toolkit in `scripts/`. The toolkit is the product surface; the skill tells Codex when to use it, in what order, and where the safety boundaries are.

Prefer the toolkit entrypoint:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 <subcommand> ...
```

Current subcommands:

- `doctor`: read-only SSH diagnosis and environment inspection
- `configure`: create or repair a host block in `~/.ssh/config`
- `bootstrap-key`: install a public key over one password-backed session, then verify non-interactive SSH
- `transfer`: password-backed Paramiko upload/download fallback
- `run`: standardize remote command execution through `ssh`

## When to Use

Use this skill when:

- a Windows machine needs to reach a Linux, POSIX, gateway, or HPC target over SSH
- SSH partially works and Codex needs to determine which layer is broken
- Codex needs to repair `~/.ssh/config`, key auth, or Windows-side SSH assumptions
- file transfer is failing and Codex needs a fallback path
- the task lives on a login node or behind a bastion or managed gateway

Do not use this skill for Windows remoting, RDP, or cases where the user explicitly wants to avoid SSH automation.

## Security Rules

- Never ask the user to paste passwords, tokens, private keys, or MFA codes into chat.
- If password bootstrap is required, the password must stay in the local terminal session only, usually in a short-lived environment variable such as `SSH_SERVER_PASSWORD`.
- Never store passwords in `~/.ssh/config`, `SKILL.md`, prompt templates, or repo files.
- Treat destructive remote actions the same way you treat destructive local actions: explicit user intent first.
- `doctor` is the preferred first step because it is read-only.

## Workflow

### 1. Gather facts

Collect:

- alias, host or IP, port, username
- whether the target is a normal Linux host, jump host, managed gateway, or HPC login node
- whether key auth, interactive password auth, or both are available today
- whether the task is diagnose, configure, bootstrap, transfer, run, sync, or HPC job control

### 2. Run read-only diagnosis first

Prefer `doctor` before changing anything:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 doctor -Alias <alias>
```

If the alias is not configured yet:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 doctor `
  -HostName <host> `
  -Port <port> `
  -User <user>
```

Read the structured output, especially:

- `local_tools`
- `network`
- `auth`
- `transfer`
- `remote_shell`
- `likely_root_cause`
- `recommended_next_step`

Use the diagnosis to decide the next safe action instead of guessing.

### 3. Configure the host entry only when needed

If the host is not yet saved or the alias is wrong, write a focused `~/.ssh/config` block:

```powershell
$keyPath = Join-Path $HOME ".ssh\id_ed25519_<alias>"
powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 configure `
  -Alias <alias> `
  -HostName <host> `
  -Port <port> `
  -User <user> `
  -IdentityFile $keyPath `
  -PreferredAuthentications publickey
```

This step is low risk, but it still changes local SSH state. Report what changed.

### 4. Bootstrap key auth only when password auth exists locally

If non-interactive SSH is still broken but the user has a valid password locally, bootstrap once:

```powershell
$env:SSH_SERVER_PASSWORD = "<set-locally-in-terminal>"
powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 bootstrap-key `
  -HostName <host> `
  -Port <port> `
  -User <user> `
  -PublicKey <path-to-public-key> `
  -PrivateKey <path-to-private-key>
Remove-Item Env:SSH_SERVER_PASSWORD
```

Do not ask the user to put the password in chat. If the password is not already available in the local terminal, tell the user what variable to set and wait.

### 5. Use the toolkit for execution and transfer

Remote command execution:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 run `
  -Alias <alias> `
  -Command "git status --short" `
  -RemoteDir ~/repo `
  -Bash `
  -BatchMode
```

Password-backed file transfer fallback:

```powershell
$env:SSH_SERVER_PASSWORD = "<set-locally-in-terminal>"
powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 transfer `
  -HostName <host> `
  -Port <port> `
  -User <user> `
  -Direction download `
  -RemotePath <remote-path> `
  -LocalPath <local-path>
Remove-Item Env:SSH_SERVER_PASSWORD
```

Prefer direct OpenSSH operations when they are already healthy. Use Paramiko fallback when diagnosis shows OpenSSH auth or `scp` is the weak link.

### 6. Treat HPC as a first-class workflow

On HPC or Slurm-backed systems:

- distinguish login nodes from compute nodes
- inspect scheduler state before launching work
- use `squeue`, `sinfo`, `sbatch`, `srun`, and log collection deliberately
- avoid treating a compute node shell like a durable host unless the scheduler says it is

See `references/hpc-slurm-playbook.md`.

## Risk Levels

- `doctor`: read-only
- `configure`, `bootstrap-key`: low-risk local or account configuration changes
- `run`, `transfer`: medium risk, because they can affect remote state depending on the command or target path
- delete, reset, overwrite, restart, package install, or service-impacting actions: high risk and require explicit user approval

## Output Expectations

Report:

- the target and how it was addressed, alias or direct
- the diagnosis result, including `likely_root_cause` and `recommended_next_step`
- which toolkit subcommands were used
- any local or remote state changes
- exact verification commands and observed results
- residual risks, especially on shared or HPC systems

## References

- `README.md`: public project framing and direct toolkit usage
- `SECURITY.md`: secrets handling and publishing checklist
- `references/windows-linux-ssh-playbook.md`: common run, sync, and diagnose patterns
- `references/hpc-slurm-playbook.md`: login-node and Slurm workflows
- `references/prompt-templates.md`: safe prompt templates that avoid putting secrets in chat
