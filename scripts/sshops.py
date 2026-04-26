#!/usr/bin/env python3
"""Cross-platform SSH Server Ops command line entrypoint."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import socket
import stat
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable


SCRIPT_ROOT = Path(__file__).resolve().parent


@dataclass
class CommandResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""

    @property
    def combined(self) -> str:
        return (self.stdout + self.stderr).strip()


@dataclass
class CondaInfo:
    requested_name: str
    effective_name: str
    conda_available: bool = False
    fallback_used: bool = False
    env_exists: bool = False
    paramiko_available: bool = False
    paramiko_version: str | None = None


def run_command(args: list[str], timeout: int = 20) -> CommandResult:
    completed = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def tool_info(name: str, command_resolver: Callable[[str], str | None] = shutil.which) -> dict[str, object]:
    source = command_resolver(name)
    return {
        "available": bool(source),
        "source": source,
        "version": None,
    }


def probe_tcp(host: str, port: int, timeout: int = 5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def parse_ssh_config_output(text: str) -> dict[str, str | None]:
    selected = {
        "hostname": None,
        "user": None,
        "port": None,
        "identityfile": None,
        "identitiesonly": None,
        "preferredauthentications": None,
    }
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or " " not in line:
            continue
        key, value = line.split(None, 1)
        lowered = key.lower()
        if lowered in selected:
            selected[lowered] = value.strip()
    return selected


def split_ssh_config(text: str) -> list[tuple[bool, list[str]]]:
    segments: list[tuple[bool, list[str]]] = []
    if not text:
        return segments

    current: list[str] = []
    current_is_host = False
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.strip().lower().startswith("host "):
            if current:
                segments.append((current_is_host, current))
                current = []
            current_is_host = True
        elif not current:
            current_is_host = False
        current.append(line)

    if current:
        segments.append((current_is_host, current))
    return segments


def host_declaration(lines: Iterable[str]) -> str | None:
    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith("host "):
            return stripped[5:].strip()
    return None


def normalize_identity_file(identity_file: str | None) -> str | None:
    if not identity_file:
        return None

    expanded = Path(identity_file).expanduser()
    candidate = expanded.resolve() if expanded.exists() else expanded
    value = str(candidate)
    if os.name == "nt":
        value = value.replace("\\", "/")
    if any(ch.isspace() for ch in value):
        value = f'"{value}"'
    return value


def upsert_host_block(
    text: str,
    *,
    alias: str,
    hostname: str,
    port: int,
    user: str,
    identity_file: str | None = None,
    preferred_authentications: str | None = None,
) -> str:
    managed_block = [
        f"Host {alias}",
        f"  HostName {hostname}",
        f"  Port {port}",
        f"  User {user}",
    ]

    normalized_identity = normalize_identity_file(identity_file)
    if normalized_identity:
        managed_block.append(f"  IdentityFile {normalized_identity}")
        managed_block.append("  IdentitiesOnly yes")
    if preferred_authentications:
        managed_block.append(f"  PreferredAuthentications {preferred_authentications}")

    replacement = "\n".join(managed_block)
    segments = split_ssh_config(text)
    updated: list[str] = []
    matched = False

    for is_host, lines in segments:
        declaration = host_declaration(lines)
        if is_host and declaration == alias:
            updated.append(replacement)
            matched = True
        else:
            segment_text = "\n".join(lines).strip("\n")
            if segment_text:
                updated.append(segment_text)

    if not matched:
        updated.append(replacement)

    return "\n\n".join(segment for segment in updated if segment.strip()) + "\n"


def write_ssh_config(
    *,
    config_path: Path,
    alias: str,
    hostname: str,
    port: int,
    user: str,
    identity_file: str | None,
    preferred_authentications: str | None,
) -> dict[str, object]:
    config_path = config_path.expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    old_text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    new_text = upsert_host_block(
        old_text,
        alias=alias,
        hostname=hostname,
        port=port,
        user=user,
        identity_file=identity_file,
        preferred_authentications=preferred_authentications,
    )
    changed = old_text != new_text
    config_path.write_text(new_text, encoding="utf-8")
    if os.name != "nt":
        config_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    return {
        "alias": alias,
        "hostname": hostname,
        "port": port,
        "user": user,
        "identity_file": normalize_identity_file(identity_file),
        "preferred_authentications": preferred_authentications,
        "config_path": str(config_path.resolve()),
        "changed": changed,
    }


def quote_remote_path(value: str) -> str:
    if value.startswith("~") and not any(ch.isspace() for ch in value):
        return value
    return shlex.quote(value)


def build_ssh_args(
    *,
    alias: str | None,
    hostname: str | None,
    port: int,
    user: str | None,
    command: str,
    remote_dir: str | None,
    bash: bool,
    batch_mode: bool,
    connect_timeout: int,
    config_file: str | None,
    identity_file: str | None,
    identities_only: bool,
) -> list[str]:
    if alias:
        target = alias
    else:
        if not hostname:
            raise ValueError("hostname is required when alias is not provided")
        target = f"{user}@{hostname}" if user else hostname

    remote_command = command
    if remote_dir:
        remote_command = f"cd {quote_remote_path(remote_dir)} && {remote_command}"
    if bash or remote_dir:
        remote_command = f"bash -lc {shlex.quote(remote_command)}"

    args = ["-o", f"ConnectTimeout={connect_timeout}"]
    if batch_mode:
        args += ["-o", "BatchMode=yes"]
    if config_file:
        args += ["-F", config_file]
    if identity_file:
        args += ["-i", identity_file]
    if identities_only:
        args += ["-o", "IdentitiesOnly=yes"]
    if not alias:
        args += ["-p", str(port)]
    args += [target, remote_command]
    return args


def inspect_conda_env(
    environment_name: str,
    command_resolver: Callable[[str], str | None] = shutil.which,
    command_runner: Callable[[list[str], int], CommandResult] = run_command,
) -> CondaInfo:
    info = CondaInfo(requested_name=environment_name, effective_name=environment_name)
    conda = command_resolver("conda")
    if not conda:
        return info

    info.conda_available = True
    env_list = command_runner([conda, "env", "list"], 20)
    if env_list.exit_code == 0:
        for line in env_list.stdout.splitlines():
            parts = line.split()
            if parts and parts[0] == environment_name:
                info.env_exists = True
                break

    if info.env_exists:
        paramiko = command_runner(
            [conda, "run", "-n", info.effective_name, "python", "-c", "import paramiko; print(paramiko.__version__)"],
            20,
        )
        if paramiko.exit_code == 0:
            info.paramiko_available = True
            info.paramiko_version = paramiko.stdout.strip()

    return info


def build_doctor_report(
    *,
    alias: str | None,
    hostname: str | None,
    port: int,
    user: str | None,
    conda_env: str,
    skip_auth_test: bool,
    command_resolver: Callable[[str], str | None] = shutil.which,
    tcp_probe: Callable[[str, int, int], bool] = probe_tcp,
    command_runner: Callable[[list[str], int], CommandResult] = run_command,
    conda_probe: Callable[[str], CondaInfo] | None = None,
) -> dict[str, object]:
    tool_names = ["ssh", "scp", "sftp", "tar", "conda"]
    tools = {name: tool_info(name, command_resolver) for name in tool_names}

    target = alias or (f"{user}@{hostname}" if user and hostname else hostname)
    resolved_host = hostname or alias
    resolved_port = port
    resolved_user = user
    ssh_config = None

    ssh_source = tools["ssh"]["source"]
    if ssh_source and target:
        ssh_g_args = [str(ssh_source), "-G"]
        if not alias:
            ssh_g_args += ["-p", str(port)]
        ssh_g_args.append(target)
        ssh_config_result = command_runner(ssh_g_args, 10)
        if ssh_config_result.exit_code == 0:
            ssh_config = parse_ssh_config_output(ssh_config_result.stdout)
            resolved_host = ssh_config.get("hostname") or resolved_host
            resolved_port = int(ssh_config.get("port") or resolved_port)
            resolved_user = ssh_config.get("user") or resolved_user

    tcp_reachable = None
    if ssh_source and resolved_host and resolved_port:
        tcp_reachable = bool(tcp_probe(str(resolved_host), int(resolved_port), 5))

    auth_tested = not skip_auth_test
    auth_success = None
    auth_exit_code = None
    auth_output = None
    if auth_tested and ssh_source and target:
        auth_args = [str(ssh_source), "-o", "BatchMode=yes", "-o", "ConnectTimeout=8"]
        if not alias:
            auth_args += ["-p", str(resolved_port)]
        auth_args += [target, "whoami"]
        auth_result = command_runner(auth_args, 12)
        auth_exit_code = auth_result.exit_code
        auth_success = auth_result.exit_code == 0
        auth_output = auth_result.combined

    conda_info = conda_probe(conda_env) if conda_probe else inspect_conda_env(conda_env, command_resolver, command_runner)
    conda_dict = asdict(conda_info)

    notes: list[str] = []
    if not tools["ssh"]["available"]:
        notes.append("OpenSSH client is not available locally.")
    if not conda_info.conda_available:
        notes.append("Conda is unavailable; password bootstrap via Conda is not ready.")
    elif not conda_info.env_exists:
        notes.append("The requested Python environment is missing; password bootstrap via Conda is not ready.")
    elif not conda_info.paramiko_available:
        notes.append("The selected Python environment exists but Paramiko is not installed.")
    if auth_tested and auth_success is False:
        notes.append("Key-based non-interactive SSH is not ready yet.")

    alias_unresolved = bool(
        ssh_source
        and alias
        and ((not ssh_config) or (resolved_host == alias and tcp_reachable is False))
    )
    bootstrap_ready = bool(
        tools["ssh"]["available"]
        and conda_info.conda_available
        and conda_info.env_exists
        and conda_info.paramiko_available
        and resolved_host
        and resolved_user
    )

    if not tools["ssh"]["available"]:
        likely_root_cause = "openssh_missing"
        recommended_next_step = "Install or expose the OpenSSH client on PATH, then rerun doctor."
    elif alias_unresolved:
        likely_root_cause = "ssh_alias_unresolved"
        recommended_next_step = "Repair or create the host block with configure, or rerun doctor in direct mode."
    elif tcp_reachable is False:
        likely_root_cause = "tcp_unreachable"
        recommended_next_step = "Verify host, port, VPN, firewall, or gateway routing before trying auth fixes."
    elif auth_tested and auth_success is False:
        likely_root_cause = "non_interactive_publickey_unavailable"
        recommended_next_step = (
            "Either bootstrap public-key access with bootstrap-key or fix the SSH identity selection, then rerun doctor."
            if bootstrap_ready
            else "Prepare Paramiko support or fix the SSH identity selection, then rerun doctor."
        )
    elif auth_tested and auth_success:
        likely_root_cause = "none"
        recommended_next_step = "Proceed with run, direct OpenSSH transfer, or the narrowest server task needed."
    else:
        likely_root_cause = "auth_not_tested"
        recommended_next_step = "Rerun doctor without --skip-auth-test when you are ready to validate non-interactive SSH."

    return {
        "target": target,
        "resolved": {
            "host": resolved_host,
            "port": resolved_port,
            "user": resolved_user,
        },
        "ssh_config": ssh_config,
        "local_tools": tools,
        "network": {
            "target_host": resolved_host,
            "target_port": resolved_port,
            "tcp_reachable": tcp_reachable,
        },
        "auth": {
            "batchmode_publickey_tested": auth_tested,
            "batchmode_publickey_ok": auth_success,
            "batchmode_exit_code": auth_exit_code,
            "batchmode_output": auth_output,
        },
        "transfer": {
            "openssh_scp_available": tools["scp"]["available"],
            "openssh_sftp_available": tools["sftp"]["available"],
            "password_fallback_ready": bootstrap_ready,
            "preferred_order": [
                "openssh-publickey",
                "openssh-password",
                "sftp",
                "paramiko-sftp",
                "tar-over-ssh",
            ],
        },
        "remote_shell": {
            "probe_command": "whoami" if auth_tested else None,
            "non_interactive_probe_ok": auth_success,
        },
        "python_env": conda_dict,
        "likely_root_cause": likely_root_cause,
        "recommended_next_step": recommended_next_step,
        "risk_level": "read-only",
        "tools": tools,
        "tcp": {
            "host": resolved_host,
            "port": resolved_port,
            "reachable": tcp_reachable,
        },
        "bootstrap_ready": bootstrap_ready,
        "notes": notes,
    }


def invoke_python_helper(script_name: str, helper_args: list[str], conda_env: str | None) -> int:
    script_path = SCRIPT_ROOT / script_name
    if conda_env:
        conda = shutil.which("conda")
        if not conda:
            raise SystemExit("conda is not available on PATH; omit --conda-env or install conda.")
        command = [conda, "run", "-n", conda_env, "python", str(script_path), *helper_args]
    else:
        command = [sys.executable, str(script_path), *helper_args]
    completed = subprocess.run(command, check=False)
    return completed.returncode


def add_common_target_arguments(parser: argparse.ArgumentParser) -> None:
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--alias")
    target.add_argument("--host-name")
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--user")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cross-platform SSH Server Ops toolkit")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    doctor = subparsers.add_parser("doctor", help="Run read-only SSH diagnosis")
    add_common_target_arguments(doctor)
    doctor.add_argument("--conda-env", default="sshops")
    doctor.add_argument("--skip-auth-test", action="store_true")

    configure = subparsers.add_parser("configure", help="Create or repair an SSH host block")
    configure.add_argument("--alias", required=True)
    configure.add_argument("--host-name", required=True)
    configure.add_argument("--port", type=int, default=22)
    configure.add_argument("--user", required=True)
    configure.add_argument("--identity-file")
    configure.add_argument("--preferred-authentications")
    configure.add_argument("--config-path", default=str(Path.home() / ".ssh" / "config"))

    bootstrap = subparsers.add_parser("bootstrap-key", help="Install a public key over one password-backed session")
    bootstrap.add_argument("--host-name", required=True)
    bootstrap.add_argument("--port", type=int, default=22)
    bootstrap.add_argument("--user", required=True)
    bootstrap.add_argument("--public-key", required=True)
    bootstrap.add_argument("--private-key")
    bootstrap.add_argument("--password-env", default="SSH_SERVER_PASSWORD")
    bootstrap.add_argument("--verify-command", default="whoami && pwd")
    bootstrap.add_argument("--no-verify-publickey", action="store_true")
    bootstrap.add_argument("--allow-publickey-verify-failure", action="store_true")
    bootstrap.add_argument("--conda-env")

    transfer = subparsers.add_parser("transfer", help="Upload or download through Paramiko SFTP")
    transfer.add_argument("--host-name", required=True)
    transfer.add_argument("--port", type=int, default=22)
    transfer.add_argument("--user", required=True)
    transfer.add_argument("--password-env", default="SSH_SERVER_PASSWORD")
    transfer.add_argument("--direction", choices=("upload", "download"), required=True)
    transfer.add_argument("--remote-path", required=True)
    transfer.add_argument("--local-path", required=True)
    transfer.add_argument("--conda-env")

    run = subparsers.add_parser("run", help="Run a command through OpenSSH")
    add_common_target_arguments(run)
    run.add_argument("--command", required=True)
    run.add_argument("--remote-dir")
    run.add_argument("--bash", action="store_true")
    run.add_argument("--batch-mode", action="store_true")
    run.add_argument("--connect-timeout", type=int, default=15)
    run.add_argument("--config-file")
    run.add_argument("--identity-file")
    run.add_argument("--identities-only", action="store_true")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    if args.subcommand == "doctor":
        if not args.alias and not args.host_name:
            raise SystemExit("doctor requires either --alias or --host-name.")
        report = build_doctor_report(
            alias=args.alias,
            hostname=args.host_name,
            port=args.port,
            user=args.user,
            conda_env=args.conda_env,
            skip_auth_test=args.skip_auth_test,
        )
        print(json.dumps(report, indent=2))
        return 0

    if args.subcommand == "configure":
        result = write_ssh_config(
            config_path=Path(args.config_path),
            alias=args.alias,
            hostname=args.host_name,
            port=args.port,
            user=args.user,
            identity_file=args.identity_file,
            preferred_authentications=args.preferred_authentications,
        )
        print(json.dumps(result, indent=2))
        return 0

    if args.subcommand == "bootstrap-key":
        helper_args = [
            "--host",
            args.host_name,
            "--port",
            str(args.port),
            "--user",
            args.user,
            "--public-key",
            args.public_key,
            "--password-env",
            args.password_env,
            "--verify-command",
            args.verify_command,
        ]
        if args.private_key:
            helper_args += ["--private-key", args.private_key]
        if args.no_verify_publickey:
            helper_args.append("--no-verify-publickey")
        if args.allow_publickey_verify_failure:
            helper_args.append("--allow-publickey-verify-failure")
        return invoke_python_helper("bootstrap_ssh_key.py", helper_args, args.conda_env)

    if args.subcommand == "transfer":
        helper_args = [
            "--host",
            args.host_name,
            "--port",
            str(args.port),
            "--user",
            args.user,
            "--password-env",
            args.password_env,
            "--direction",
            args.direction,
            "--remote-path",
            args.remote_path,
            "--local-path",
            args.local_path,
        ]
        return invoke_python_helper("paramiko_copy_tree.py", helper_args, args.conda_env)

    if args.subcommand == "run":
        ssh = shutil.which("ssh")
        if not ssh:
            raise SystemExit("OpenSSH client 'ssh' is not available on PATH.")
        ssh_args = build_ssh_args(
            alias=args.alias,
            hostname=args.host_name,
            port=args.port,
            user=args.user,
            command=args.command,
            remote_dir=args.remote_dir,
            bash=args.bash,
            batch_mode=args.batch_mode,
            connect_timeout=args.connect_timeout,
            config_file=args.config_file,
            identity_file=args.identity_file,
            identities_only=args.identities_only,
        )
        result = run_command([ssh, *ssh_args], timeout=max(args.connect_timeout + 30, 45))
        print(
            json.dumps(
                {
                    "target": args.alias or (f"{args.user}@{args.host_name}" if args.user else args.host_name),
                    "mode": "alias" if args.alias else "direct",
                    "command": args.command,
                    "remote_dir": args.remote_dir,
                    "bash_wrapped": bool(args.bash or args.remote_dir),
                    "batch_mode": bool(args.batch_mode),
                    "exit_code": result.exit_code,
                    "success": result.exit_code == 0,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "ssh_arguments": ssh_args,
                },
                indent=2,
            )
        )
        return result.exit_code

    raise SystemExit(f"Unsupported subcommand: {args.subcommand}")


if __name__ == "__main__":
    sys.exit(main())
