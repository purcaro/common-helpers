#!/usr/bin/env python3
"""Tests for Make_ssh_public_private_key.py (run: python3 -m unittest)."""

import importlib.util
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

SCRIPT = Path(__file__).resolve().parent / "Make_ssh_public_private_key.py"
_spec = importlib.util.spec_from_file_location("mssh", SCRIPT)
mssh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mssh)


class ResolveTests(unittest.TestCase):
    def test_full_ip_not_doubled(self):
        # Regression: a base that is already a full IP must NOT get the host's
        # trailing number appended (z026 + 10.5.16.26 -> 10.5.16.26, not .26.26).
        self.assertEqual(mssh.resolve_server_ip("z026", "10.5.16.26"), "10.5.16.26")

    def test_subnet_expands_with_host_suffix(self):
        self.assertEqual(mssh.resolve_server_ip("node10", "10.5.19"), "10.5.19.10")

    def test_is_full_ipv4(self):
        self.assertTrue(mssh.is_full_ipv4("10.5.16.26"))
        self.assertFalse(mssh.is_full_ipv4("10.5.16.26.26"))  # the doubled-octet bug
        self.assertFalse(mssh.is_full_ipv4("10.5.16"))


class ConfigBase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.home = Path(self._tmp.name)
        (self.home / ".ssh").mkdir()
        self._old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)
        self.config = self.home / ".ssh" / "config"
        # Isolate from the test machine's real /etc/hosts.
        self._orig_lookup = mssh.lookup_ip_in_etc_hosts
        mssh.lookup_ip_in_etc_hosts = lambda *a, **k: None

    def tearDown(self):
        mssh.lookup_ip_in_etc_hosts = self._orig_lookup
        if self._old_home is not None:
            os.environ["HOME"] = self._old_home
        self._tmp.cleanup()

    def mgr(self, ip="10.5.16.26"):
        return mssh.SSHKeyManager("ubuntu", "z026", ip)


class ConfigUpdateTests(ConfigBase):
    def test_self_heals_doubled_hostname(self):
        self.config.write_text(
            "Host z026\n  HostName 10.5.16.26.26\n  User ubuntu\n  Port 22\n"
        )
        self.assertTrue(self.mgr().update_hostname_in_ssh_config("10.5.16.26"))
        text = self.config.read_text()
        self.assertIn("HostName 10.5.16.26\n", text)
        self.assertNotIn("10.5.16.26.26", text)

    def test_removes_duplicate_blocks(self):
        self.config.write_text(
            "Host z026\n  HostName 10.5.16.26\n  Port 22\n"
            "\nHost other\n  HostName 1.2.3.4\n"
            "\nHost z026\n  HostName 10.5.16.99\n  Port 22\n"
        )
        self.assertTrue(self.mgr().remove_duplicate_host_blocks())
        text = self.config.read_text()
        self.assertEqual(text.count("Host z026"), 1)   # collapsed to one
        self.assertIn("Host other", text)              # unrelated block preserved
        self.assertIn("HostName 10.5.16.26", text)     # first block kept
        self.assertNotIn("10.5.16.99", text)           # later duplicate dropped

    def test_no_false_dedupe_for_single_block(self):
        self.config.write_text("Host z026\n  HostName 10.5.16.26\n")
        self.assertFalse(self.mgr().remove_duplicate_host_blocks())


class RunGuardTests(ConfigBase):
    def test_run_refuses_malformed_ip(self):
        m = self.mgr("10.5.16.26.26")
        pushed = []
        m.copy_key_to_remote = lambda: pushed.append("push")
        m.generate_key = lambda: pushed.append("keygen")
        m.run()
        # A bogus address must never be written to the config nor deployed.
        cfg = self.config.read_text() if self.config.exists() else ""
        self.assertNotIn("Host z026", cfg)
        self.assertEqual(pushed, [])


if __name__ == "__main__":
    unittest.main()
