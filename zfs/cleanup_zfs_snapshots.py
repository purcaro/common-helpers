#!/usr/bin/env python3
"""Identify ZFS datasets with large snapshot usage and destroy those snapshots."""

import argparse
import subprocess
import sys


class ZfsSnapshotCleaner:
    """Find and clean ZFS datasets whose snapshot usage exceeds a threshold."""

    def __init__(self, pool_name: str, threshold_gib: int):
        self.pool_name = pool_name
        self.threshold_gib = threshold_gib
        self.threshold_bytes = threshold_gib * (1024 ** 3)

    @staticmethod
    def _format_bytes(byte_count: int) -> str:
        """Return a human-readable string for a byte count (B, KB, MB, GB, TB)."""
        if byte_count is None:
            return "N/A"
        if byte_count == 0:
            return "0B"
        power = 1024
        labels = {0: '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
        n = 0
        while byte_count >= power and n < len(labels) - 1:
            byte_count /= power
            n += 1
        return f"{byte_count:.2f}{labels[n]}B"

    def _run_command(self, command) -> str:
        """Run a shell command and return its stdout.

        Accepts a list (no shell) or a string (shell=True, required for pipes).
        Exits on failure.
        """
        use_shell = isinstance(command, str)
        try:
            result = subprocess.run(
                command, check=True, capture_output=True, text=True, shell=use_shell
            )
            return result.stdout
        except FileNotFoundError:
            name = command.split()[0] if use_shell else command[0]
            print(f"Error: '{name}' not found. Is it installed and in your PATH?", file=sys.stderr)
            sys.exit(1)
        except subprocess.CalledProcessError as e:
            cmd_str = command if use_shell else ' '.join(command)
            print(f"Error running '{cmd_str}':\n{e.stderr}", file=sys.stderr)
            sys.exit(1)

    def _check_pool_health(self):
        """Exit with an error if the pool is not ONLINE."""
        print(f"🩺 Checking health of ZFS pool '{self.pool_name}'...")
        output = self._run_command(["zpool", "status", self.pool_name])

        pool_state, scan_lines = None, []
        for line in output.strip().splitlines():
            stripped = line.strip()
            if stripped.startswith('state:'):
                pool_state = stripped
            elif stripped.startswith('scan:'):
                scan_lines.append(stripped)

        if pool_state and 'ONLINE' in pool_state:
            print(f"✅ Pool '{self.pool_name}' is ONLINE. Proceeding...")
            return

        print(f"❌ CRITICAL: Pool '{self.pool_name}' is not healthy.", file=sys.stderr)
        if pool_state:
            print(f"  {pool_state}", file=sys.stderr)
        for line in scan_lines:
            print(f"  {line}", file=sys.stderr)
        print("Aborting to prevent potential data loss.", file=sys.stderr)
        sys.exit(1)

    def _get_snapshot_usage(self) -> list:
        """Return datasets whose snapshot usage exceeds the threshold, sorted largest first."""
        print(f"\n🔎 Searching for datasets with snapshot usage > {self.threshold_gib} GiB...")
        output = self._run_command(["zfs", "list", "-H", "-p", "-o", "name,usedsnap"])

        datasets = []
        for line in output.strip().splitlines():
            try:
                name, used_str = line.split()
                used_bytes = int(used_str)
                if used_bytes > self.threshold_bytes:
                    datasets.append({"name": name, "used_bytes": used_bytes})
            except (ValueError, IndexError):
                continue

        datasets.sort(key=lambda x: x["used_bytes"], reverse=True)
        return datasets

    def _get_user_selection(self, datasets: list) -> list:
        """Display a menu of over-threshold datasets and return the user's selection."""
        print(f"\n❗ Datasets with snapshots using more than {self.threshold_gib} GiB:")
        print("-" * 60)
        print(f"  {'#':<3} {'Dataset Name':<40} {'Snapshot Size':<15}")
        print(f"  {'=':<3} {'============':<40} {'=============':<15}")
        for i, ds in enumerate(datasets):
            print(f"  [{i + 1:<1}] {ds['name']:<40} ({self._format_bytes(ds['used_bytes'])})")
        print(f"  {'[a]':<3} {'All of the above':<40}")
        print("-" * 60)

        while True:
            selection = input(f"Enter number [1-{len(datasets)}], 'a' for all, or 'q' to quit [a]: ").strip().lower()

            if not selection or selection == 'a':
                return datasets
            if selection == 'q':
                print("Exiting.")
                sys.exit(0)
            try:
                choice = int(selection)
                if 1 <= choice <= len(datasets):
                    return [datasets[choice - 1]]
                print("Invalid number. Please try again.", file=sys.stderr)
            except ValueError:
                print("Invalid input. Please enter a number, 'a', or 'q'.", file=sys.stderr)

    def _execute_cleanup(self, dataset_info: dict):
        """Destroy all snapshots for a dataset without prompting."""
        name = dataset_info['name']
        print(f"\n🔥 Executing cleanup for '{name}'...")
        snapshots = self._run_command(
            ["zfs", "list", "-H", "-t", "snapshot", "-o", "name", "-S", "creation", "-r", name]
        ).strip()
        if not snapshots:
            print(f"  No snapshots found for '{name}', skipping.")
            return
        for snap in snapshots.splitlines():
            self._run_command(["zfs", "destroy", snap])
        print(f"✅ Cleanup complete for '{name}'.")

    def _confirm_and_execute(self, dataset_info: dict):
        """Show a destruction warning, ask for confirmation, then run cleanup."""
        name = dataset_info['name']
        print("\n" + "=" * 70)
        print("⚠️  WARNING: You are about to DESTROY ALL SNAPSHOTS for the selected dataset.")
        print("⚠️  This action is IRREVERSIBLE.")
        print(f"\nDataset: {name}")
        print("=" * 70)

        confirm = input(f"Proceed with '{name}'? (yes/no) [no]: ").strip().lower()
        if confirm == 'yes':
            self._execute_cleanup(dataset_info)
        else:
            print(f"\n🚫 Cancelled for '{name}'.")

    def _confirm_all(self, datasets: list) -> bool:
        """Ask once for confirmation before destroying snapshots across all selected datasets."""
        names = [ds['name'] for ds in datasets]
        print("\n" + "=" * 70)
        print("⚠️  WARNING: You are about to DESTROY ALL SNAPSHOTS for ALL listed datasets.")
        print("⚠️  This action is IRREVERSIBLE.")
        print(f"\n{len(datasets)} datasets will be cleaned:")
        for name in names:
            print(f"  - {name}")
        print("=" * 70)
        confirm = input("Type 'yes' to confirm cleanup of ALL datasets [no]: ").strip().lower()
        return confirm == 'yes'

    def run(self):
        """Run the full interactive cleanup workflow."""
        self._check_pool_health()
        large_snap_datasets = self._get_snapshot_usage()

        if not large_snap_datasets:
            print(f"\n✅ No datasets exceed the {self.threshold_gib} GiB snapshot threshold.")
            return

        datasets_to_process = self._get_user_selection(large_snap_datasets)

        if len(datasets_to_process) > 1:
            if not self._confirm_all(datasets_to_process):
                print("\n🚫 Operation cancelled.")
                return
            for i, dataset_info in enumerate(datasets_to_process):
                print(f"\n--- Processing {i + 1} of {len(datasets_to_process)} ---")
                self._execute_cleanup(dataset_info)
        else:
            self._confirm_and_execute(datasets_to_process[0])

        print("\nAll operations complete.")


def main():
    parser = argparse.ArgumentParser(
        description="Find ZFS datasets with large snapshot usage and offer to clean them up.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        '--pool',
        default='tank',
        help='ZFS pool to health-check before performing any operations.',
    )
    parser.add_argument(
        '--threshold',
        type=int,
        default=50,
        help='Snapshot size threshold in GiB above which a dataset is flagged.',
    )
    args = parser.parse_args()
    ZfsSnapshotCleaner(pool_name=args.pool, threshold_gib=args.threshold).run()


if __name__ == "__main__":
    main()
