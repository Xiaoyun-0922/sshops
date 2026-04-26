#!/usr/bin/env python3
"""Cross-platform repository validation for SSH Server Ops."""

from __future__ import annotations

import json
import py_compile
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "README.md",
    "SECURITY.md",
    "LICENSE",
    "SKILL.md",
    ".codex-plugin/plugin.json",
    ".claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
    "agents/openai.yaml",
    "skills/ssh-server-ops/SKILL.md",
    "skills/ssh-server-ops/agents/openai.yaml",
    "references/prompt-templates.md",
    "references/windows-linux-ssh-playbook.md",
    "references/hpc-slurm-playbook.md",
    "scripts/sshops.ps1",
    "scripts/sshops.py",
    "scripts/remote_run.ps1",
    "scripts/server_preflight.ps1",
    "scripts/configure_ssh_host.ps1",
    "scripts/bootstrap_ssh_key.py",
    "scripts/paramiko_copy_tree.py",
    "tests/test_sshops_cli.py",
]

JSON_FILES = [
    ".codex-plugin/plugin.json",
    ".claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
]


def main() -> int:
    missing = [path for path in REQUIRED_FILES if not (ROOT / path).exists()]
    if missing:
        raise SystemExit("Missing required files: " + ", ".join(missing))

    for relative_path in JSON_FILES:
        with (ROOT / relative_path).open(encoding="utf-8") as handle:
            json.load(handle)

    python_files = sorted((ROOT / "scripts").glob("*.py")) + sorted((ROOT / "tests").glob("test_*.py"))
    for path in python_files:
        py_compile.compile(str(path), doraise=True)

    tests = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-v"],
        cwd=ROOT,
        check=False,
    )
    if tests.returncode != 0:
        return tests.returncode

    result = {
        "root": str(ROOT),
        "required_file_count": len(REQUIRED_FILES),
        "json_files_checked": len(JSON_FILES),
        "python_files_checked": len(python_files),
        "unit_tests": "passed",
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
