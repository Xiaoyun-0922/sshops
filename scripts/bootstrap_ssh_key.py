#!/usr/bin/env python3
"""Bootstrap SSH key authentication on a Linux host using one password login."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import paramiko
except ModuleNotFoundError as exc:  # pragma: no cover - import guard
    raise SystemExit(
        "paramiko is required. Install it in the chosen conda environment before running this script."
    ) from exc


def run_checked(client: "paramiko.SSHClient", command: str) -> str:
    stdin, stdout, stderr = client.exec_command(command)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if exit_code != 0:
        raise RuntimeError(
            f"Remote command failed with exit code {exit_code}: {command}\nSTDOUT:\n{out}\nSTDERR:\n{err}"
        )
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install a local public key into a remote Linux account using password auth once.",
    )
    parser.add_argument("--host", required=True, help="Remote host or IP")
    parser.add_argument("--port", type=int, default=22, help="Remote SSH port")
    parser.add_argument("--user", required=True, help="Remote SSH username")
    parser.add_argument("--public-key", required=True, help="Path to the local .pub key file")
    parser.add_argument("--private-key", help="Path to the local private key for non-interactive public-key verification")
    parser.add_argument(
        "--password-env",
        default="SSH_SERVER_PASSWORD",
        help="Environment variable holding the remote password",
    )
    parser.add_argument(
        "--verify-command",
        default="whoami && pwd",
        help="Remote command to run after installing the key",
    )
    parser.add_argument(
        "--verify-publickey",
        dest="verify_publickey",
        action="store_true",
        default=True,
        help="Verify the installed key by opening a fresh public-key-only SSH session.",
    )
    parser.add_argument(
        "--no-verify-publickey",
        dest="verify_publickey",
        action="store_false",
        help="Skip the fresh public-key verification step.",
    )
    parser.add_argument(
        "--allow-publickey-verify-failure",
        action="store_true",
        help="Return success even if the fresh public-key verification step fails.",
    )
    return parser.parse_args()


def verify_publickey_login(
    *,
    host: str,
    port: int,
    user: str,
    private_key: Path,
    verify_command: str,
) -> tuple[bool, str]:
    ssh_executable = shutil.which("ssh")
    if not ssh_executable:
        raise RuntimeError("OpenSSH client 'ssh' is not available on PATH for public-key verification.")
    completed = subprocess.run(
        [
            ssh_executable,
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-i",
            str(private_key),
            "-p",
            str(port),
            "-l",
            user,
            host,
            verify_command,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )
    output = (completed.stdout + completed.stderr).strip()
    return completed.returncode == 0, output


def main() -> int:
    args = parse_args()

    password = os.environ.get(args.password_env)
    if not password:
        raise SystemExit(
            f"Environment variable {args.password_env} is empty or unset. "
            "Set it in the current shell before running the bootstrap."
        )

    public_key_path = Path(args.public_key).expanduser()
    if not public_key_path.exists():
        raise SystemExit(f"Public key file not found: {public_key_path}")
    private_key_path = Path(args.private_key).expanduser() if args.private_key else None
    if args.verify_publickey and private_key_path is None:
        raise SystemExit("--private-key is required unless --no-verify-publickey is used.")
    if args.verify_publickey and private_key_path is not None and not private_key_path.exists():
        raise SystemExit(f"Private key file not found: {private_key_path}")

    public_key = public_key_path.read_text(encoding="utf-8").strip()
    if not public_key.startswith("ssh-"):
        raise SystemExit("Public key file does not look like an OpenSSH public key.")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=args.host,
        port=args.port,
        username=args.user,
        password=password,
        look_for_keys=False,
        allow_agent=False,
        timeout=15,
        auth_timeout=15,
    )

    try:
        home_dir = run_checked(client, "printf '%s\\n' \"$HOME\"").strip()
        if not home_dir:
            raise RuntimeError("Unable to determine remote home directory.")

        run_checked(client, "umask 077 && mkdir -p ~/.ssh && touch ~/.ssh/authorized_keys")

        ssh_dir = f"{home_dir}/.ssh"
        auth_keys = f"{ssh_dir}/authorized_keys"

        sftp = client.open_sftp()
        try:
            try:
                existing_bytes = b""
                with sftp.open(auth_keys, "rb") as handle:
                    existing_bytes = handle.read()
            except OSError:
                existing_bytes = b""

            existing_text = existing_bytes.decode("utf-8", errors="replace")
            existing_lines = [line.strip() for line in existing_text.splitlines() if line.strip()]
            added = public_key not in existing_lines

            if added:
                updated_text = existing_text
                if updated_text and not updated_text.endswith("\n"):
                    updated_text += "\n"
                updated_text += public_key + "\n"
                with sftp.open(auth_keys, "wb") as handle:
                    handle.write(updated_text.encode("utf-8"))

            sftp.chmod(ssh_dir, 0o700)
            sftp.chmod(auth_keys, 0o600)
        finally:
            sftp.close()

        verify_output = run_checked(client, args.verify_command).strip()
        result = {
            "host": args.host,
            "port": args.port,
            "user": args.user,
            "home_dir": home_dir,
            "public_key_path": str(public_key_path),
            "private_key_path": str(private_key_path) if private_key_path else None,
            "key_added": added,
            "verify_command": args.verify_command,
            "verify_output": verify_output,
        }
        publickey_verify_attempted = False
        publickey_verify_success = None
        publickey_verify_output = None
        if args.verify_publickey:
            publickey_verify_attempted = True
            assert private_key_path is not None
            publickey_verify_success, publickey_verify_output = verify_publickey_login(
                host=args.host,
                port=args.port,
                user=args.user,
                private_key=private_key_path,
                verify_command=args.verify_command,
            )
        result["publickey_verify_attempted"] = publickey_verify_attempted
        result["publickey_verify_success"] = publickey_verify_success
        result["publickey_verify_output"] = publickey_verify_output
        print(json.dumps(result, indent=2))
        if publickey_verify_attempted and not publickey_verify_success and not args.allow_publickey_verify_failure:
            return 2
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
