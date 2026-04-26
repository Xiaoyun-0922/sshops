# Prompt Templates for `$ssh-server-ops`

Copy one of these into a new Codex session and replace the placeholders.

If you launch `codex exec` from PowerShell, wrap the whole prompt in single quotes so `$ssh-server-ops` is passed through literally.

If password-backed bootstrap or transfer may be needed, set `SSH_SERVER_PASSWORD` in the local terminal first. Do not paste passwords into chat.

## 1. Bootstrap a new server

```text
Use $ssh-server-ops to take over a new Linux server from this local machine.

Host alias: <alias>
Host/IP: <host>
Port: <port>
User: <user>
Authentication available now: password only
Password status: available locally in terminal only, not pasted here
Goal: configure SSH access, switch to key-based login, and confirm Codex can operate the server.

After setup, run:
- whoami
- pwd
- ls -1A ~ | sort | head -50

Report the exact verification commands you ran and the observed results.
```

## 2. Operate an already configured server

```text
Use $ssh-server-ops on the saved host <alias>.

Goal: <what you need done on the server>

Before making changes:
- run the toolkit doctor step
- verify non-interactive SSH access
- inspect the current remote state relevant to the task

After each meaningful change, run fresh verification on the server and report the exact command outputs.
```

## 3. Sync files between local and remote

```text
Use $ssh-server-ops to sync files with the server.

Host alias: <alias>
Direction: upload | download | two-way review then decide
Local path: <local-path>
Remote path: <remote-path>
Goal: <why the sync is needed>

Requirements:
- inspect both sides first
- use the safest focused transfer method and report which transport was used
- do not overwrite broadly unless necessary
- verify the target contents after transfer
```

## 4. Run a remote code or deployment task

```text
Use $ssh-server-ops to execute a server-side code or deployment task.

Host alias: <alias>
Remote project path: <remote-project-path>
Task: <run tests | pull code | edit files | restart service | deploy | collect logs>
Constraints: <service name, branch, env, downtime limits, anything risky>

Process requirements:
- inspect the current repo/service state first
- make the smallest change that solves the task
- verify on the server immediately after the change
- report commands, outputs, and any residual risks
```

## 5. Read-only diagnosis

```text
Use $ssh-server-ops for a read-only diagnosis on host <alias>.

Investigate:
- <symptom 1>
- <symptom 2>

Do not change files or restart services.
Run the toolkit doctor step first, collect the key command outputs, identify the likely root cause, and recommend the next safe action.
```
