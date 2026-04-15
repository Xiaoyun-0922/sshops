# Windows to Linux SSH Playbook

Use these patterns after `doctor` has given you a clear next step. Prefer the toolkit wrapper when possible:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 <subcommand> ...
```

If `doctor` reports healthy non-interactive SSH, use `run` or direct `ssh` depending on what is clearer for the task.

## Remote execution

Basic command:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 run `
  -Alias <alias> `
  -Command "whoami && pwd" `
  -Bash `
  -BatchMode
```

Run in a repo or working directory:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 run `
  -Alias <alias> `
  -RemoteDir ~/repo `
  -Command "git status --short" `
  -Bash `
  -BatchMode

powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 run `
  -Alias <alias> `
  -RemoteDir ~/repo `
  -Command "python run_job.py" `
  -Bash `
  -BatchMode

powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 run `
  -Alias <alias> `
  -RemoteDir ~/repo `
  -Command "pytest tests/test_api.py -q" `
  -Bash `
  -BatchMode
```

Service, process, and system checks:

```powershell
ssh <alias> "bash -lc 'systemctl status myservice --no-pager'"
ssh <alias> "bash -lc 'journalctl -u myservice -n 200 --no-pager'"
ssh <alias> "bash -lc 'ps -ef | grep myservice | grep -v grep'"
ssh <alias> "bash -lc 'ss -ltnp'"
ssh <alias> "bash -lc 'df -h && free -h'"
```

## File transfer

If direct OpenSSH transfer is already known-good, `scp` is fine. If not, prefer diagnosis first and then fall back to the toolkit-backed transfer path.

Password-backed fallback upload or download:

```powershell
$env:SSH_SERVER_PASSWORD = "<set-locally-in-terminal>"
powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 transfer `
  -HostName <host> `
  -Port <port> `
  -User <user> `
  -Direction upload `
  -RemotePath <remote-path> `
  -LocalPath <local-path>
Remove-Item Env:SSH_SERVER_PASSWORD
```

Direct `scp` examples when OpenSSH auth is already healthy:

```powershell
scp .\local-file.txt <alias>:~/remote-file.txt
scp <alias>:~/remote-file.txt .\local-file.txt
scp -r .\local-dir <alias>:~/remote-dir
scp -r <alias>:~/remote-dir .\local-dir
```

## Directory sync without rsync

For simple cases, prefer `scp -r`.

For larger trees where tar is available on both sides:

```powershell
tar -cf - -C .\local-dir . | ssh <alias> "mkdir -p ~/remote-dir && tar -xf - -C ~/remote-dir"
ssh <alias> "tar -cf - -C ~/remote-dir ." | tar -xf - -C .\local-dir
```

Verify the target after sync:

```powershell
ssh <alias> "bash -lc 'cd ~/remote-dir && find . -maxdepth 2 | sort | head -200'"
```

## Typical remote edit workflow

1. Inspect before changing:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sshops.ps1 run `
  -Alias <alias> `
  -RemoteDir ~/repo `
  -Command "git status --short && git rev-parse --abbrev-ref HEAD" `
  -Bash `
  -BatchMode
```

2. Transfer only the files you changed or copy a focused patch/worktree.

3. Run the narrowest verification command on the server immediately after the change.

4. Pull back the exact logs or outputs needed for analysis.

## Troubleshooting

OpenSSH rejects `~/.ssh/config` on Windows:

- Re-run `scripts/configure_ssh_host.ps1` to rewrite the host block and repair ACLs.

`Permission denied (publickey,password)` after bootstrap:

- Confirm the remote `~/.ssh/authorized_keys` contains the expected public key.
- Confirm remote permissions are `700` on `~/.ssh` and `600` on `authorized_keys`.
- Re-run `scripts/sshops.ps1 doctor` to see whether key auth is still failing.

Need first-time password bootstrap:

- Use a temporary environment variable only.
- Example: set `$env:SSH_SERVER_PASSWORD` locally in the terminal, run `scripts/sshops.ps1 bootstrap-key`, then `Remove-Item Env:SSH_SERVER_PASSWORD`.

Do not store the password in `~/.ssh/config` or in the skill files.
