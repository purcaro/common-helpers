#!/usr/bin/env python3
"""Tests for cleanup_zfs_snapshots.py"""

import subprocess
import sys
import unittest
from io import StringIO
from unittest.mock import MagicMock, call, patch

from cleanup_zfs_snapshots import ZfsSnapshotCleaner


class TestFormatBytes(unittest.TestCase):
    def setUp(self):
        self.cleaner = ZfsSnapshotCleaner(pool_name="tank", threshold_gib=50)

    def test_zero(self):
        self.assertEqual(self.cleaner._format_bytes(0), "0B")

    def test_none(self):
        self.assertEqual(self.cleaner._format_bytes(None), "N/A")

    def test_bytes(self):
        self.assertEqual(self.cleaner._format_bytes(512), "512.00B")

    def test_kilobytes(self):
        self.assertEqual(self.cleaner._format_bytes(1024), "1.00KB")

    def test_megabytes(self):
        self.assertEqual(self.cleaner._format_bytes(1024 ** 2), "1.00MB")

    def test_gigabytes(self):
        self.assertEqual(self.cleaner._format_bytes(1024 ** 3), "1.00GB")

    def test_terabytes(self):
        self.assertEqual(self.cleaner._format_bytes(1024 ** 4), "1.00TB")

    def test_fractional(self):
        self.assertEqual(self.cleaner._format_bytes(int(1.5 * 1024 ** 3)), "1.50GB")


class TestRunCommand(unittest.TestCase):
    def setUp(self):
        self.cleaner = ZfsSnapshotCleaner(pool_name="tank", threshold_gib=50)

    @patch("cleanup_zfs_snapshots.subprocess.run")
    def test_list_command_success(self, mock_run):
        mock_run.return_value = MagicMock(stdout="output", returncode=0)
        result = self.cleaner._run_command(["zfs", "list"])
        self.assertEqual(result, "output")
        mock_run.assert_called_once_with(
            ["zfs", "list"], check=True, capture_output=True, text=True, shell=False
        )

    @patch("cleanup_zfs_snapshots.subprocess.run")
    def test_shell_string_command(self, mock_run):
        mock_run.return_value = MagicMock(stdout="piped", returncode=0)
        result = self.cleaner._run_command("echo foo | cat")
        self.assertEqual(result, "piped")
        mock_run.assert_called_once_with(
            "echo foo | cat", check=True, capture_output=True, text=True, shell=True
        )

    @patch("cleanup_zfs_snapshots.subprocess.run", side_effect=FileNotFoundError)
    def test_file_not_found_exits(self, _mock_run):
        with self.assertRaises(SystemExit):
            self.cleaner._run_command(["zfs", "list"])

    @patch("cleanup_zfs_snapshots.subprocess.run",
           side_effect=subprocess.CalledProcessError(1, "zfs", stderr="bad"))
    def test_called_process_error_exits(self, _mock_run):
        with self.assertRaises(SystemExit):
            self.cleaner._run_command(["zfs", "list"])


class TestCheckPoolHealth(unittest.TestCase):
    def setUp(self):
        self.cleaner = ZfsSnapshotCleaner(pool_name="tank", threshold_gib=50)

    @patch.object(ZfsSnapshotCleaner, "_run_command")
    def test_online_pool_passes(self, mock_run):
        mock_run.return_value = "  state: ONLINE\n  scan: scrub repaired\n"
        self.cleaner._check_pool_health()  # should not raise

    @patch.object(ZfsSnapshotCleaner, "_run_command")
    def test_degraded_pool_exits(self, mock_run):
        mock_run.return_value = "  state: DEGRADED\n"
        with self.assertRaises(SystemExit):
            self.cleaner._check_pool_health()

    @patch.object(ZfsSnapshotCleaner, "_run_command")
    def test_missing_state_exits(self, mock_run):
        mock_run.return_value = "no state line here\n"
        with self.assertRaises(SystemExit):
            self.cleaner._check_pool_health()


class TestGetSnapshotUsage(unittest.TestCase):
    def setUp(self):
        self.cleaner = ZfsSnapshotCleaner(pool_name="tank", threshold_gib=50)

    @patch.object(ZfsSnapshotCleaner, "_run_command")
    def test_filters_below_threshold(self, mock_run):
        # 60 GiB is above threshold; 10 GiB is below
        gib = 1024 ** 3
        mock_run.return_value = (
            f"tank/big\t{60 * gib}\n"
            f"tank/small\t{10 * gib}\n"
        )
        result = self.cleaner._get_snapshot_usage()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], 'tank/big')

    @patch.object(ZfsSnapshotCleaner, "_run_command")
    def test_sorted_largest_first(self, mock_run):
        gib = 1024 ** 3
        mock_run.return_value = (
            f"tank/a\t{60 * gib}\n"
            f"tank/b\t{200 * gib}\n"
            f"tank/c\t{80 * gib}\n"
        )
        result = self.cleaner._get_snapshot_usage()
        self.assertEqual([ds['name'] for ds in result], ['tank/b', 'tank/c', 'tank/a'])

    @patch.object(ZfsSnapshotCleaner, "_run_command")
    def test_empty_output(self, mock_run):
        mock_run.return_value = ""
        result = self.cleaner._get_snapshot_usage()
        self.assertEqual(result, [])

    @patch.object(ZfsSnapshotCleaner, "_run_command")
    def test_malformed_lines_skipped(self, mock_run):
        gib = 1024 ** 3
        mock_run.return_value = (
            f"tank/good\t{60 * gib}\n"
            "this-is-garbage\n"
            "\n"
        )
        result = self.cleaner._get_snapshot_usage()
        self.assertEqual(len(result), 1)


class TestGetUserSelection(unittest.TestCase):
    def setUp(self):
        self.cleaner = ZfsSnapshotCleaner(pool_name="tank", threshold_gib=50)
        gib = 1024 ** 3
        self.datasets = [
            {"name": "tank/ds1", "used_bytes": 100 * gib},
            {"name": "tank/ds2", "used_bytes": 60 * gib},
        ]

    @patch("builtins.input", return_value="a")
    def test_a_returns_all(self, _mock_input):
        result = self.cleaner._get_user_selection(self.datasets)
        self.assertEqual(result, self.datasets)

    @patch("builtins.input", return_value="")
    def test_empty_returns_all(self, _mock_input):
        result = self.cleaner._get_user_selection(self.datasets)
        self.assertEqual(result, self.datasets)

    @patch("builtins.input", return_value="1")
    def test_number_returns_single(self, _mock_input):
        result = self.cleaner._get_user_selection(self.datasets)
        self.assertEqual(result, [self.datasets[0]])

    @patch("builtins.input", return_value="2")
    def test_second_number(self, _mock_input):
        result = self.cleaner._get_user_selection(self.datasets)
        self.assertEqual(result, [self.datasets[1]])

    @patch("builtins.input", return_value="q")
    def test_q_exits(self, _mock_input):
        with self.assertRaises(SystemExit):
            self.cleaner._get_user_selection(self.datasets)

    @patch("builtins.input", side_effect=["99", "bad", "1"])
    def test_invalid_then_valid(self, _mock_input):
        result = self.cleaner._get_user_selection(self.datasets)
        self.assertEqual(result, [self.datasets[0]])


class TestExecuteCleanup(unittest.TestCase):
    def setUp(self):
        self.cleaner = ZfsSnapshotCleaner(pool_name="tank", threshold_gib=50)
        self.dataset = {"name": "tank/ds1", "used_bytes": 100 * 1024 ** 3}

    @patch.object(ZfsSnapshotCleaner, "_run_command")
    def test_no_snapshots_skips_destroy(self, mock_run):
        mock_run.return_value = ""
        self.cleaner._execute_cleanup(self.dataset)
        mock_run.assert_called_once()  # only the list call, no destroy

    @patch.object(ZfsSnapshotCleaner, "_run_command")
    def test_destroys_each_snapshot(self, mock_run):
        mock_run.side_effect = [
            "tank/ds1@snap1\ntank/ds1@snap2\n",  # list call
            "",  # destroy snap1
            "",  # destroy snap2
        ]
        self.cleaner._execute_cleanup(self.dataset)
        self.assertEqual(mock_run.call_count, 3)
        mock_run.assert_any_call(["zfs", "destroy", "tank/ds1@snap1"])
        mock_run.assert_any_call(["zfs", "destroy", "tank/ds1@snap2"])


class TestConfirmAndExecute(unittest.TestCase):
    def setUp(self):
        self.cleaner = ZfsSnapshotCleaner(pool_name="tank", threshold_gib=50)
        self.dataset = {"name": "tank/ds1", "used_bytes": 100 * 1024 ** 3}

    @patch("builtins.input", return_value="yes")
    @patch.object(ZfsSnapshotCleaner, "_execute_cleanup")
    def test_yes_calls_execute(self, mock_execute, _mock_input):
        self.cleaner._confirm_and_execute(self.dataset)
        mock_execute.assert_called_once_with(self.dataset)

    @patch("builtins.input", return_value="no")
    @patch.object(ZfsSnapshotCleaner, "_execute_cleanup")
    def test_no_skips_execute(self, mock_execute, _mock_input):
        self.cleaner._confirm_and_execute(self.dataset)
        mock_execute.assert_not_called()

    @patch("builtins.input", return_value="")
    @patch.object(ZfsSnapshotCleaner, "_execute_cleanup")
    def test_empty_skips_execute(self, mock_execute, _mock_input):
        self.cleaner._confirm_and_execute(self.dataset)
        mock_execute.assert_not_called()


class TestConfirmAll(unittest.TestCase):
    def setUp(self):
        self.cleaner = ZfsSnapshotCleaner(pool_name="tank", threshold_gib=50)
        gib = 1024 ** 3
        self.datasets = [
            {"name": "tank/ds1", "used_bytes": 100 * gib},
            {"name": "tank/ds2", "used_bytes": 60 * gib},
        ]

    @patch("builtins.input", return_value="yes")
    def test_yes_returns_true(self, _mock_input):
        self.assertTrue(self.cleaner._confirm_all(self.datasets))

    @patch("builtins.input", return_value="no")
    def test_no_returns_false(self, _mock_input):
        self.assertFalse(self.cleaner._confirm_all(self.datasets))

    @patch("builtins.input", return_value="")
    def test_empty_returns_false(self, _mock_input):
        self.assertFalse(self.cleaner._confirm_all(self.datasets))


class TestRun(unittest.TestCase):
    def setUp(self):
        self.cleaner = ZfsSnapshotCleaner(pool_name="tank", threshold_gib=50)
        gib = 1024 ** 3
        self.datasets = [
            {"name": "tank/ds1", "used_bytes": 100 * gib},
            {"name": "tank/ds2", "used_bytes": 60 * gib},
        ]

    @patch.object(ZfsSnapshotCleaner, "_check_pool_health")
    @patch.object(ZfsSnapshotCleaner, "_get_snapshot_usage", return_value=[])
    def test_no_datasets_exits_cleanly(self, _mock_usage, _mock_health):
        self.cleaner.run()  # should not raise

    @patch.object(ZfsSnapshotCleaner, "_execute_cleanup")
    @patch.object(ZfsSnapshotCleaner, "_confirm_all", return_value=True)
    @patch.object(ZfsSnapshotCleaner, "_get_user_selection")
    @patch.object(ZfsSnapshotCleaner, "_get_snapshot_usage")
    @patch.object(ZfsSnapshotCleaner, "_check_pool_health")
    def test_all_confirmed_executes_each(self, _health, mock_usage, mock_sel, mock_confirm, mock_exec):
        mock_usage.return_value = self.datasets
        mock_sel.return_value = self.datasets
        self.cleaner.run()
        mock_confirm.assert_called_once_with(self.datasets)
        self.assertEqual(mock_exec.call_count, 2)
        mock_exec.assert_any_call(self.datasets[0])
        mock_exec.assert_any_call(self.datasets[1])

    @patch.object(ZfsSnapshotCleaner, "_execute_cleanup")
    @patch.object(ZfsSnapshotCleaner, "_confirm_all", return_value=True)
    @patch.object(ZfsSnapshotCleaner, "_get_user_selection")
    @patch.object(ZfsSnapshotCleaner, "_get_snapshot_usage")
    @patch.object(ZfsSnapshotCleaner, "_check_pool_health")
    def test_all_executes_deepest_first(self, _health, mock_usage, mock_sel, _confirm, mock_exec):
        gib = 1024 ** 3
        parent = {"name": "tank/projects", "used_bytes": 200 * gib}
        child = {"name": "tank/projects/alphafold", "used_bytes": 100 * gib}
        grandchild = {"name": "tank/projects/alphafold/databases", "used_bytes": 60 * gib}
        mock_usage.return_value = [parent, child, grandchild]
        mock_sel.return_value = [parent, child, grandchild]
        self.cleaner.run()
        calls = [c.args[0]['name'] for c in mock_exec.call_args_list]
        self.assertEqual(calls, [grandchild['name'], child['name'], parent['name']])

    @patch.object(ZfsSnapshotCleaner, "_execute_cleanup")
    @patch.object(ZfsSnapshotCleaner, "_confirm_all", return_value=False)
    @patch.object(ZfsSnapshotCleaner, "_get_user_selection")
    @patch.object(ZfsSnapshotCleaner, "_get_snapshot_usage")
    @patch.object(ZfsSnapshotCleaner, "_check_pool_health")
    def test_all_declined_executes_none(self, _health, mock_usage, mock_sel, mock_confirm, mock_exec):
        mock_usage.return_value = self.datasets
        mock_sel.return_value = self.datasets
        self.cleaner.run()
        mock_confirm.assert_called_once()
        mock_exec.assert_not_called()

    @patch.object(ZfsSnapshotCleaner, "_confirm_and_execute")
    @patch.object(ZfsSnapshotCleaner, "_get_user_selection")
    @patch.object(ZfsSnapshotCleaner, "_get_snapshot_usage")
    @patch.object(ZfsSnapshotCleaner, "_check_pool_health")
    def test_single_dataset_uses_confirm_and_execute(self, _health, mock_usage, mock_sel, mock_cae):
        mock_usage.return_value = self.datasets
        mock_sel.return_value = [self.datasets[0]]
        self.cleaner.run()
        mock_cae.assert_called_once_with(self.datasets[0])


if __name__ == "__main__":
    unittest.main()
