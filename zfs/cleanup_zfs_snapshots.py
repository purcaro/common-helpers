#!/usr/bin/env python3

import argparse
import subprocess
import sys

class ZfsSnapshotCleaner:
    """
    A class to find and clean ZFS datasets with large snapshot usage.
    """
    def __init__(self, pool_name: str, threshold_gib: int):
        """
        Initializes the ZfsSnapshotCleaner.

        Args:
            pool_name: The name of the ZFS pool to health-check.
            threshold_gib: The snapshot size in GiB to trigger a cleanup warning.
        """
        self.pool_name = pool_name
        self.threshold_gib = threshold_gib
        self.threshold_bytes = threshold_gib * (1024**3)

    @staticmethod
    def _format_bytes(byte_count: int) -> str:
        """Converts a byte count into a human-readable string (TiB, GiB, MiB)."""
        if byte_count is None:
            return "N/A"
        power = 1024
        n = 0
        power_labels = {0: 'B', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
        if byte_count == 0:
            return "0B"
        while byte_count >= power and n < len(power_labels) - 1:
            byte_count /= power
            n += 1
        return f"{byte_count:.2f}{power_labels[n]}B"

    def _run_command(self, command) -> str:
        """
        A helper method to run shell commands and handle common errors.

        Args:
            command: The command as a list of strings or a single string (for shell=True).

        Returns:
            The standard output of the command as a string.
            
        Raises:
            SystemExit: If the command fails for any reason.
        """
        try:
            # shell=True is needed for commands with pipes `|`
            use_shell = isinstance(command, str)
            process = subprocess.run(
                command, check=True, capture_output=True, text=True, shell=use_shell
            )
            return process.stdout
        except FileNotFoundError:
            cmd_name = command.split()[0] if isinstance(command, str) else command[0]
            print(f"Error: '{cmd_name}' not found. Is it installed and in your PATH?", file=sys.stderr)
            sys.exit(1)
        except subprocess.CalledProcessError as e:
            cmd_str = command if isinstance(command, str) else ' '.join(command)
            print(f"Error running command '{cmd_str}':\n{e.stderr}", file=sys.stderr)
            sys.exit(1)

    def _check_pool_health(self):
        """Checks the status of the ZFS pool. Exits if not ONLINE."""
        print(f"🩺 Checking health of ZFS pool '{self.pool_name}'...")
        command = ["zpool", "status", self.pool_name]
        output = self._run_command(command)
        
        pool_state, scan_lines = None, []
        for line in output.strip().splitlines():
            if line.strip().startswith('state:'):
                pool_state = line.strip()
            elif line.strip().startswith('scan:'):
                scan_lines.append(line.strip())

        if pool_state and 'ONLINE' in pool_state:
            print(f"✅ Pool '{self.pool_name}' status is ONLINE. Proceeding...")
            return
        
        print(f"❌ CRITICAL: Pool '{self.pool_name}' is not healthy.", file=sys.stderr)
        if pool_state:
            print(f"  {pool_state}", file=sys.stderr)
        for line in scan_lines:
            print(f"  {line}", file=sys.stderr)
        print("Aborting script to prevent potential data loss.", file=sys.stderr)
        sys.exit(1)

    def _get_snapshot_usage(self) -> list:
        """Fetches snapshot space usage for all datasets."""
        print(f"\n🔎 Searching for datasets with snapshot usage > {self.threshold_gib} GiB...")
        command = ["zfs", "list", "-H", "-p", "-o", "name,usedsnap"]
        output = self._run_command(command)
        
        datasets = []
        for line in output.strip().splitlines():
            try:
                name, used_bytes_str = line.split()
                used_bytes = int(used_bytes_str)
                if used_bytes > self.threshold_bytes:
                    datasets.append({"name": name, "used_bytes": used_bytes})
            except (ValueError, IndexError):
                continue
        
        datasets.sort(key=lambda x: x["used_bytes"], reverse=True)
        return datasets
    
    def _get_user_selection(self, datasets: list) -> list:
        """Displays a menu and gets the user's choice of datasets to process."""
        print(f"\n❗ The following datasets have snapshots using more than {self.threshold_gib} GiB:")
        print("-" * 60)
        print(f"  {'#':<3} {'Dataset Name':<40} {'Snapshot Size':<15}")
        print(f"  {'=':<3} {'============':<40} {'=============':<15}")
        for i, ds in enumerate(datasets):
            print(f"  [{i+1:<1}] {ds['name']:<40} ({self._format_bytes(ds['used_bytes'])})")
        print(f"  {'[a]':<3} {'All of the above':<40}")
        print("-" * 60)

        while True:
            prompt = (f"Enter number [1-{len(datasets)}], 'a' for all, or 'q' to quit [a]: ")
            selection = input(prompt).strip().lower()
            
            if not selection or selection == 'a':
                print("Selected 'all'. Each dataset will require separate confirmation.")
                return datasets
            if selection == 'q':
                print("Exiting.")
                sys.exit(0)
            try:
                choice = int(selection)
                if 1 <= choice <= len(datasets):
                    return [datasets[choice - 1]]
                else:
                    print("Invalid number. Please try again.", file=sys.stderr)
            except ValueError:
                print("Invalid input. Please enter a number, 'a', or 'q'.", file=sys.stderr)

    def _confirm_and_execute(self, dataset_info: dict):
        """Asks for user confirmation, then executes the snapshot deletion."""
        selected_dataset = dataset_info['name']
        destroy_command_str = (
            f"zfs list -H -t snapshot -o name -S creation -r {selected_dataset} | xargs -n 1 zfs destroy"
        )

        print("\n" + "="*70)
        print("⚠️  WARNING: You are about to DESTROY ALL SNAPSHOTS in the selected dataset.")
        print("⚠️  This action is IRREVERSIBLE.")
        print(f"\nDataset selected: {selected_dataset}")
        print("The following command will be executed:")
        print(f"\n  {destroy_command_str}\n")
        print("="*70)
        
        confirm = input(f"Are you sure you want to proceed with '{selected_dataset}'? (yes/no) [no]: ")
        if confirm.lower().strip() == 'yes':
            print(f"\n🔥 Executing cleanup for '{selected_dataset}'...")
            self._run_command(destroy_command_str)
            print("\n✅ Command completed successfully.")
        else:
            print(f"\n🚫 Operation for '{selected_dataset}' cancelled by user.")

    def run(self):
        """The main execution method for the cleaner."""
        self._check_pool_health()
        large_snap_datasets = self._get_snapshot_usage()

        if not large_snap_datasets:
            print(f"\n✅ No datasets found with snapshot usage exceeding the {self.threshold_gib} GiB threshold.")
            return

        datasets_to_process = self._get_user_selection(large_snap_datasets)

        for i, dataset_info in enumerate(datasets_to_process):
            if len(datasets_to_process) > 1:
                print(f"\n--- Processing item {i+1} of {len(datasets_to_process)} ---")
            self._confirm_and_execute(dataset_info)

        print("\nAll operations complete.")

def main():
    """Parses command-line arguments and runs the ZfsSnapshotCleaner."""
    parser = argparse.ArgumentParser(
        description="Find ZFS datasets with large snapshot usage and offer to clean them up.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        '--pool',
        default='tank',
        help='The ZFS pool to health-check before performing any operations.'
    )
    parser.add_argument(
        '--threshold',
        type=int,
        default=50,
        help='The snapshot size threshold in GiB to trigger a warning.'
    )
    args = parser.parse_args()
    
    cleaner = ZfsSnapshotCleaner(pool_name=args.pool, threshold_gib=args.threshold)
    cleaner.run()

if __name__ == "__main__":
    main()
