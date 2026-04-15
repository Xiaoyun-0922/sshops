#!/usr/bin/env python3
"""Upload or download files/directories over SFTP using password auth."""

from __future__ import annotations

import argparse
import json
import os
import posixpath
import stat
import sys
from pathlib import Path

try:
    import paramiko
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit("paramiko is required. Install it in the chosen conda environment before running this script.") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Copy files or directories over SFTP using password auth.")
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password-env", default="SSH_SERVER_PASSWORD")
    parser.add_argument("--direction", choices=("upload", "download"), required=True)
    parser.add_argument("--remote-path", required=True)
    parser.add_argument("--local-path", required=True)
    return parser.parse_args()


def ensure_remote_dir(sftp: "paramiko.SFTPClient", remote_dir: str, created: set[str]) -> None:
    remote_dir = remote_dir.rstrip("/")
    if not remote_dir:
        return
    parents: list[str] = []
    current = remote_dir
    while current and current not in ("/", "."):
        parents.append(current)
        current = posixpath.dirname(current)
        if current == remote_dir:
            break
        remote_dir = current
    for path in reversed(parents):
        try:
            sftp.stat(path)
        except OSError:
            sftp.mkdir(path)
            created.add(path)


def download_path(
    sftp: "paramiko.SFTPClient",
    remote_path: str,
    local_path: Path,
    counters: dict[str, int],
    created: set[str],
) -> None:
    attributes = sftp.stat(remote_path)
    if stat.S_ISDIR(attributes.st_mode):
        local_path.mkdir(parents=True, exist_ok=True)
        created.add(str(local_path))
        for entry in sftp.listdir_attr(remote_path):
            child_remote = posixpath.join(remote_path, entry.filename)
            child_local = local_path / entry.filename
            download_path(sftp, child_remote, child_local, counters, created)
        return
    local_path.parent.mkdir(parents=True, exist_ok=True)
    sftp.get(remote_path, str(local_path))
    counters["files_copied"] += 1


def upload_path(
    sftp: "paramiko.SFTPClient",
    local_path: Path,
    remote_path: str,
    counters: dict[str, int],
    created: set[str],
) -> None:
    if local_path.is_dir():
        ensure_remote_dir(sftp, remote_path, created)
        for child in local_path.iterdir():
            upload_path(sftp, child, posixpath.join(remote_path, child.name), counters, created)
        return
    ensure_remote_dir(sftp, posixpath.dirname(remote_path), created)
    sftp.put(str(local_path), remote_path)
    counters["files_copied"] += 1


def main() -> int:
    args = parse_args()
    password = os.environ.get(args.password_env)
    if not password:
        raise SystemExit(f"Environment variable {args.password_env} is empty or unset.")

    local_path = Path(args.local_path).expanduser()
    created_dirs: set[str] = set()
    counters = {"files_copied": 0}
    failures: list[dict[str, str]] = []

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=args.host,
        port=args.port,
        username=args.user,
        password=password,
        look_for_keys=False,
        allow_agent=False,
        timeout=20,
        auth_timeout=20,
    )
    try:
        sftp = client.open_sftp()
        try:
            if args.direction == "download":
                download_path(sftp, args.remote_path, local_path, counters, created_dirs)
            else:
                if not local_path.exists():
                    raise FileNotFoundError(f"Local path not found: {local_path}")
                upload_path(sftp, local_path, args.remote_path, counters, created_dirs)
        except Exception as exc:  # pragma: no cover - operational smoke validation is primary
            failures.append({"path": args.remote_path if args.direction == "download" else str(local_path), "error": str(exc)})
        finally:
            sftp.close()
    finally:
        client.close()

    result = {
        "direction": args.direction,
        "host": args.host,
        "port": args.port,
        "user": args.user,
        "remote_path": args.remote_path,
        "local_path": str(local_path),
        "files_copied": counters["files_copied"],
        "directories_created": len(created_dirs),
        "failures": failures,
        "failure_count": len(failures),
    }
    print(json.dumps(result, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
