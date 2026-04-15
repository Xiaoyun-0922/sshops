# Security Notes

## Threat Model

This toolkit operates near credentials, SSH configuration, and remote systems. The main failure modes are:

- secrets pasted into chat or committed to disk
- accidental persistence of passwords in `~/.ssh/config`
- destructive commands executed without explicit intent
- publishing organization-specific examples, aliases, usernames, or hostnames

## Safe Use Rules

- Never paste passwords, tokens, private keys, or MFA codes into chat.
- Keep password-based bootstrap local to the terminal session only.
- Clear short-lived environment variables such as `SSH_SERVER_PASSWORD` immediately after use.
- Do not store passwords in `~/.ssh/config`, repo files, prompt templates, or logs.
- Prefer `doctor` before `configure`, `bootstrap-key`, `transfer`, or `run`.
- Treat delete, reset, overwrite, restart, install, and production-impacting actions as explicit-approval operations.

## Risk Tiers

- `doctor`: read-only
- `configure`, `bootstrap-key`: low-risk account or local-machine mutation
- `run`, `transfer`: medium risk because they can change remote state depending on the command or target path
- destructive or service-impacting actions: high risk

## Publishing Checklist

Before publishing or copying examples to issues, docs, or PRs:

- search for organization-specific aliases, usernames, IPs, domains, and gateway names
- search for local usernames and absolute workstation paths
- search for environment names that only make sense on one machine
- verify that prompt templates never ask users to place secrets into chat
- review README examples and JSON samples for real host data

Recommended local check:

```powershell
rg -n "C:\\Users\\|@example|password:|SSH_SERVER_PASSWORD|NC-|ParaCloud" .
```

Adjust the pattern set for your environment before release.

## Reporting

If you discover a credential leak or a workflow that makes secret handling unsafe, treat it as a security issue first and a documentation issue second. Remove exposed material, rotate secrets if needed, then fix the docs or code path that allowed it.
