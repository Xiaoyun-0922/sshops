import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "sshops.py"


def load_module():
    spec = importlib.util.spec_from_file_location("sshops_cli", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ConfigBlockTests(unittest.TestCase):
    def setUp(self):
        self.sshops = load_module()

    def test_upsert_host_block_replaces_exact_alias_only(self):
        existing = (
            "Host alpha\n"
            "  HostName old.example\n"
            "\n"
            "Host alpha-extra\n"
            "  HostName keep.example\n"
        )

        updated = self.sshops.upsert_host_block(
            existing,
            alias="alpha",
            hostname="new.example",
            port=2222,
            user="alice",
            identity_file="~/.ssh/id_alpha",
            preferred_authentications="publickey",
        )

        self.assertIn("Host alpha\n  HostName new.example\n  Port 2222\n  User alice", updated)
        self.assertIn("Host alpha-extra\n  HostName keep.example", updated)
        self.assertNotIn("old.example", updated)
        self.assertTrue(updated.endswith("\n"))

    def test_build_ssh_args_supports_direct_target_options(self):
        args = self.sshops.build_ssh_args(
            alias=None,
            hostname="login.example.edu",
            port=2200,
            user="alice",
            command="whoami",
            remote_dir="~/project",
            bash=True,
            batch_mode=True,
            connect_timeout=9,
            config_file="/tmp/ssh_config",
            identity_file="~/.ssh/id_ed25519",
            identities_only=True,
        )

        self.assertEqual(args[:2], ["-o", "ConnectTimeout=9"])
        self.assertIn("-p", args)
        self.assertIn("2200", args)
        self.assertIn("alice@login.example.edu", args)
        self.assertIn("BatchMode=yes", args)
        self.assertIn("IdentitiesOnly=yes", args)
        self.assertTrue(args[-1].startswith("bash -lc "))
        self.assertIn("cd", args[-1])


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.sshops = load_module()

    def test_doctor_reports_missing_ssh_without_network_probe(self):
        result = self.sshops.build_doctor_report(
            alias=None,
            hostname="example.invalid",
            port=22,
            user="alice",
            conda_env="sshops",
            skip_auth_test=True,
            command_resolver=lambda name: None,
            tcp_probe=lambda host, port, timeout: (_ for _ in ()).throw(
                AssertionError("tcp probe should not run without ssh")
            ),
            command_runner=lambda args, timeout: self.fail("command runner should not run"),
            conda_probe=lambda name: self.sshops.CondaInfo(requested_name=name, effective_name=name),
        )

        self.assertEqual(result["likely_root_cause"], "openssh_missing")
        self.assertFalse(result["local_tools"]["ssh"]["available"])
        self.assertIsNone(result["network"]["tcp_reachable"])

    def test_doctor_json_is_serializable(self):
        result = self.sshops.build_doctor_report(
            alias="server",
            hostname=None,
            port=22,
            user=None,
            conda_env="sshops",
            skip_auth_test=True,
            command_resolver=lambda name: f"/usr/bin/{name}" if name != "conda" else None,
            tcp_probe=lambda host, port, timeout: True,
            command_runner=lambda args, timeout: self.sshops.CommandResult(0, "hostname server\nuser alice\nport 22\n", ""),
            conda_probe=lambda name: self.sshops.CondaInfo(requested_name=name, effective_name=name),
        )

        encoded = json.dumps(result)
        self.assertIn("auth_not_tested", encoded)
        self.assertEqual(result["resolved"]["host"], "server")


if __name__ == "__main__":
    unittest.main()
