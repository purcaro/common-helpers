#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ZFS Pool Management Script

A command-line tool to parse 'zpool status', display drive information,
and provide a menu for managing drives within a ZFS pool.

Author: Gemini
Version: 4.6

Disclaimer:
This script performs potentially destructive operations. The author is not
responsible for any data loss. Always have backups. Use at your own risk.
Run this script with root privileges (sudo).

Required tools: zpool, smartctl, lsblk, wipefs, dd.
"""

import sys
import os
import subprocess
import re
import time
from typing import List, Optional, Tuple, Dict
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed


class Colors:
    """ANSI color codes for terminal output."""
    YELLOW = '\033[93m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BLINK_RED = '\033[5;91m'
    RESET = '\033[0m'

class Partition:
    """Represents a ZFS vdev, which can be a whole disk or a partition."""
    def __init__(self, pool_identifier: str, role: str, parent_drive: 'Drive', zfs_manager: 'ZFSManager'):
        self.pool_identifier = pool_identifier
        self.role = role
        self.parent_drive = parent_drive
        self.size_bytes: int = 0
        self.size_hr: str = "0B"
        self.zfs_manager = zfs_manager # To access _run_command and other helpers

    def populate_size(self):
        """Gets the size of this specific partition/device."""
        device_to_check = self.zfs_manager._find_device_path(self.pool_identifier)
        if not device_to_check: return

        success, out, _ = self.zfs_manager._run_command(['lsblk', '-b', '-n', '-o', 'SIZE', device_to_check])
        if success and out:
            size_str = out.splitlines()[0]
            self.size_bytes = int(size_str)
            self.size_hr = self.zfs_manager._human_readable_size(self.size_bytes)
    
    def __str__(self) -> str:
        role_colors = {
            'Data': Colors.YELLOW, 'Spare': Colors.GREEN, 'Log': Colors.BLUE,
            'Cache': Colors.CYAN, 'Available': Colors.RESET
        }
        role_color = role_colors.get(self.role, Colors.RESET)
        highlighted_role = f"{role_color}{self.role}{Colors.RESET}"
        highlighted_size = f"{Colors.YELLOW}{self.size_hr}{Colors.RESET}"

        return (
            f"ZFS Device: {self.pool_identifier} | Role: {highlighted_role} | Size: {highlighted_size}"
        )

    def detach(self):
        """Detaches this partition from the ZFS pool."""
        command = ['zpool', 'detach', self.zfs_manager.pool_name, self.pool_identifier]
        print(f"\n{Colors.GREEN}Proposed command: {' '.join(command)}{Colors.RESET}")
        if self.zfs_manager.dry_run:
            print(f"[DRY RUN] Would execute the command above.")
            return

        if not self.zfs_manager._confirm_action(f"This will remove {self.pool_identifier} from the pool."):
            print("Detach cancelled.")
            return

        success, out, err = self.zfs_manager._run_command(command)
        if success: print(f"{Colors.GREEN}Successfully detached {self.pool_identifier}.{Colors.RESET}\n{out}")
        else: print(f"{Colors.RED}Error detaching drive: {err}{Colors.RESET}")

    def replace(self, new_drive: 'Drive'):
        """Replaces this partition with a new drive."""
        new_drive_path = new_drive.stable_path if new_drive.stable_path != new_drive.path else new_drive.path
        command = ['zpool', 'replace', self.zfs_manager.pool_name, self.pool_identifier, new_drive_path]

        print(f"\n{Colors.GREEN}Proposed command: {' '.join(command)}{Colors.RESET}")
        if self.zfs_manager.dry_run:
            print(f"[DRY RUN] Would execute the command above.")
            return

        prompt = (f"This will start a resilver to replace '{self.pool_identifier}' with "
                  f"'{new_drive_path}'. The old device detaches after completion.")
        if not self.zfs_manager._confirm_action(prompt):
            print("Replace cancelled.")
            return

        success, out, err = self.zfs_manager._run_command(command)
        if success:
            print(f"{Colors.GREEN}Successfully initiated replacement of {self.pool_identifier}.{Colors.RESET}\n{out}")
            print("Monitor 'zpool status' to see the resilvering progress.")
        else: print(f"{Colors.RED}Error replacing drive: {err}{Colors.RESET}")


class Drive:
    """Represents a single physical storage drive."""
    def __init__(self, device_name: str, zfs_manager: 'ZFSManager'):
        self.device_name = device_name
        self.path = f"/dev/{device_name}"
        self.realpath = os.path.realpath(self.path)
        self.stable_path = self.path
        self.make = "Unknown"
        self.model = "Unknown"
        self.serial = "Unknown"
        self.health_status = "Unknown"
        self.temperature = "N/A"
        self.partitions: List[Partition] = []
        self.zfs_manager = zfs_manager
        self.size_bytes: int = 0
        self.size_hr: str = "0B"

    def __str__(self):
        """String representation for an available drive."""
        health_color = Colors.GREEN if ('OK' in self.health_status or 'PASSED' in self.health_status) else Colors.RED
        highlighted_health = f"{health_color}{self.health_status}{Colors.RESET}"
        
        path_display = f"{self.path} | {os.path.basename(self.stable_path)}"
        details = (
            f"[{self.make}] {self.model}, SN: {self.serial}, "
            f"Health: {highlighted_health}, Temp: {self.temperature}"
        )
        return f"Physical Drive: {path_display}\n  └─ {details}"


    def populate_smart_info(self):
        """Gathers SMART info for this physical drive."""
        success, out, _ = self.zfs_manager._run_command(['smartctl', '-a', self.path])
        if not success:
            print(f"{Colors.YELLOW}Warning: Could not get SMART info for {self.path}.{Colors.RESET}")
            return
            
        self.health_status = "Unknown"
        found_health_status = False
        found_temperature = False

        for line in out.splitlines():
            clean_line = line.strip().lower()
            if clean_line.startswith('device model:'): self.model = line.split(':', 1)[1].strip()
            elif clean_line.startswith('product:'): self.model = line.split(':', 1)[1].strip()
            elif clean_line.startswith('serial number:'): self.serial = line.split(':', 1)[1].strip()
            elif clean_line.startswith('vendor:'): self.make = line.split(':', 1)[1].strip()
            elif clean_line.startswith('smart health status:'):
                self.health_status = line.split(':', 1)[1].strip()
                found_health_status = True
            elif 'overall-health self-assessment test result' in clean_line and not found_health_status:
                self.health_status = line.split(':', 1)[1].strip()
            elif clean_line.startswith('current drive temperature:') and not found_temperature:
                self.temperature = line.split(':', 1)[1].strip()
                found_temperature = True
            elif clean_line.startswith('temperature:') and not found_temperature:
                try:
                    parts = line.split(':', 1)[1].strip().split()
                    if len(parts) > 0 and parts[0].isdigit():
                        self.temperature = f"{parts[0]} C"
                        found_temperature = True
                except (ValueError, IndexError):
                    pass
            elif 'temperature_celsius' in clean_line and not found_temperature:
                try:
                    parts = line.strip().split()
                    if len(parts) >= 10:
                        temp_val = parts[9]
                        if temp_val.isdigit():
                            self.temperature = f"{temp_val} C"
                except (ValueError, IndexError):
                    pass # Ignore if parsing fails
        
        if self.make == "Unknown" and self.model != "Unknown": self.make = self.model.split()[0]
        
        try:
            if os.path.isdir('/dev/disk/by-id'):
                for link_name in os.listdir('/dev/disk/by-id'):
                    if link_name.startswith('wwn-'):
                        link_path = os.path.join('/dev/disk/by-id', link_name)
                        if os.path.realpath(link_path) == self.realpath:
                            self.stable_path = link_path
                            break
        except Exception as e:
            print(f"{Colors.YELLOW}Warning: Could not scan /dev/disk/by-id for {self.path}: {e}{Colors.RESET}")
            
    def populate_size(self):
        """Gets the size of this physical drive."""
        success, out, _ = self.zfs_manager._run_command(['lsblk', '-b', '-d', '-n', '-o', 'SIZE', self.path])
        if success and out:
            self.size_bytes = int(out.splitlines()[0])
            self.size_hr = self.zfs_manager._human_readable_size(self.size_bytes)
            
    def populate_details_for_available(self):
        """Gathers SMART info and size for a drive not in a pool."""
        self.populate_smart_info()
        self.populate_size()

    def detach(self):
        """Convenience method to detach if the drive has only one ZFS partition."""
        if len(self.partitions) == 1:
            print(f"Drive {self.path} has one ZFS device. Detaching {self.partitions[0].pool_identifier}...")
            self.partitions[0].detach()
        else:
            print(f"{Colors.YELLOW}This action is only available for drives with a single ZFS device.{Colors.RESET}")
            time.sleep(2)

    def replace(self):
        """Convenience method to replace if the drive has only one ZFS partition."""
        if len(self.partitions) == 1:
            print(f"Drive {self.path} has one ZFS device. Starting replacement for {self.partitions[0].pool_identifier}...")
            self.zfs_manager._replace_menu(self.partitions[0])
        else:
            print(f"{Colors.YELLOW}This action is only available for drives with a single ZFS device.{Colors.RESET}")
            time.sleep(2)

    def wipe(self) -> bool:
        """Wipes filesystem signatures from this physical drive."""
        command = ['wipefs', '-a', self.path]
        if self.zfs_manager.dry_run:
            print(f"[DRY RUN] Would execute: {' '.join(command)}")
            return True # Pretend success for dry run

        if not self.zfs_manager._confirm_action(f"This will run 'wipefs -a' on physical drive {self.path}. This is DESTRUCTIVE."):
            print("Wipe cancelled.")
            return False

        success, out, err = self.zfs_manager._run_command(command)
        if success:
            print(f"{Colors.GREEN}Successfully wiped {self.path}.{Colors.RESET}\n{out}")
            return True
        else:
            print(f"{Colors.RED}Error wiping drive: {err}{Colors.RESET}")
            return False

    def blink(self):
        """Uses dd to cause drive activity on this physical drive."""
        command = ['dd', f'if={self.path}', 'of=/dev/null', 'bs=4M']
        if self.zfs_manager.dry_run:
            print(f"[DRY RUN] Would execute: {' '.join(command)}")
            print("[DRY RUN] This would normally run until you press Enter.")
            return

        print(f"\n{Colors.GREEN}Starting high I/O on {self.path} to blink activity light.{Colors.RESET}")
        print("--- PRESS ENTER TO STOP ---")
        try:
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            input()
        finally:
            process.terminate(); process.wait()
            print(f"Stopped I/O on {self.path}.")


class ZFSManager:
    """Orchestrator for ZFS pool management."""
    def __init__(self, pool_name: str, dry_run: bool = False, debug: bool = False):
        self.pool_name = pool_name
        self.dry_run = dry_run
        self.debug = debug
        self.pool_drives: Dict[str, Drive] = {} # Key: physical device name (e.g., 'sda')
        self.available_drives: List[Drive] = []
        self._check_privileges()
        self._check_dependencies()
        if self.dry_run:
            print(f"\n{'*'*60}\n{' ' * 20}DRY RUN MODE ENABLED\n{' ' * 5}No destructive or state-changing commands will be executed.\n{'*'*60}\n")

    def _check_privileges(self):
        if os.geteuid() != 0:
            print(f"{Colors.RED}Error: This script requires root privileges. Please run with sudo.{Colors.RESET}")
            sys.exit(1)

    def _check_dependencies(self):
        dependencies = ['zpool', 'smartctl', 'lsblk', 'wipefs', 'dd']
        for cmd in dependencies:
            if subprocess.run(['which', cmd], capture_output=True).returncode != 0:
                print(f"{Colors.RED}Error: Required command '{cmd}' not found.{Colors.RESET}")
                sys.exit(1)

    def _run_command(self, command: list) -> Tuple[bool, str, str]:
        if self.debug: print(f"{Colors.CYAN}DEBUG CMD: {' '.join(command)}{Colors.RESET}")
        try:
            process = subprocess.run(command, capture_output=True, text=True, check=False)
            success = process.returncode == 0
            if self.debug:
                if process.stdout: print(f"{Colors.CYAN}DEBUG STDOUT: {process.stdout.strip()}{Colors.RESET}")
                if process.stderr: print(f"{Colors.CYAN}DEBUG STDERR: {process.stderr.strip()}{Colors.RESET}")
            return success, process.stdout.strip(), process.stderr.strip()
        except Exception as e: return False, "", f"An error occurred: {e}"

    def _human_readable_size(self, size_bytes: int) -> str:
        if size_bytes == 0: return "0B"
        power, n, labels = 1024, 0, {0: '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
        while size_bytes > power and n < len(labels):
            size_bytes /= power; n += 1
        return f"{size_bytes:.2f} {labels[n]}B"

    def _find_device_path(self, identifier: str) -> Optional[str]:
        potential_paths = [ identifier, f"/dev/{identifier}", f"/dev/disk/by-id/{identifier}", f"/dev/disk/by-partuuid/{identifier}", f"/dev/disk/by-uuid/{identifier}" ]
        for path in potential_paths:
            if os.path.exists(path): return os.path.realpath(path)
        return None

    def parse_zpool_status(self) -> bool:
        print(f"\n{Colors.GREEN}Parsing status for ZFS pool '{self.pool_name}'...{Colors.RESET}")
        success, out, err = self._run_command(['zpool', 'status', self.pool_name])
        if not success:
            print(f"{Colors.RED}Error getting pool status: {err}{Colors.RESET}"); return False

        self.pool_drives = {}
        in_config, current_role = False, "Data"
        device_regex = re.compile(r'^\s+([\w\-.:]+)\s+(ONLINE|DEGRADED|FAULTED|AVAIL)')

        for line in out.splitlines():
            stripped = line.strip()
            if stripped == 'config:': in_config = True; continue
            if not in_config: continue

            if stripped == 'logs': current_role = 'Log'; continue
            elif stripped == 'cache': current_role = 'Cache'; continue
            elif stripped == 'spares': current_role = 'Spare'; continue
            elif stripped.startswith(('raidz', 'mirror', self.pool_name)): current_role = 'Data'

            match = device_regex.match(line)
            if match:
                zfs_id = match.group(1).strip()
                resolved = self._find_device_path(zfs_id)
                if not resolved: continue
                
                basename = os.path.basename(resolved)
                phys_dev_name = None

                # Optimization: if the path is obviously a whole disk, don't check for parent
                if re.match(r'^(sd|hd)[a-z]+$|^nvme\d+n\d+$', basename):
                    phys_dev_name = basename
                else:
                    # It could be a partition, so we check for a parent device (PKNAME)
                    success, pkname, _ = self._run_command(['lsblk', '-n', '-o', 'PKNAME', resolved])
                    if success and pkname:
                        phys_dev_name = pkname.strip()
                    else:
                        # Fallback for other whole disk types (e.g., vd, xvd) or if PKNAME fails
                        success, base_device_name, _ = self._run_command(['lsblk', '-d', '-n', '-o', 'NAME', resolved])
                        if success and base_device_name:
                            phys_dev_name = base_device_name.strip()

                if not phys_dev_name:
                    print(f"{Colors.YELLOW}Warning: Could not get physical device for {resolved}. Skipping.{Colors.RESET}")
                    continue

                if phys_dev_name not in self.pool_drives:
                    self.pool_drives[phys_dev_name] = Drive(phys_dev_name, self)
                
                partition = Partition(zfs_id, current_role, self.pool_drives[phys_dev_name], self)
                self.pool_drives[phys_dev_name].partitions.append(partition)
        
        with ThreadPoolExecutor(max_workers=16) as executor:
            drive_futures = [executor.submit(drive.populate_smart_info) for drive in self.pool_drives.values()]
            part_futures = [executor.submit(part.populate_size) for drive in self.pool_drives.values() for part in drive.partitions]
            for future in as_completed(drive_futures + part_futures): future.result()

        print(f"Found {len(self.pool_drives)} physical drives with roles in the pool.")
        return True

    def discover_available_drives(self):
        print(f"\n{Colors.GREEN}Discovering other drives in the system...{Colors.RESET}")
        success, out, err = self._run_command(['lsblk', '-d', '-n', '-o', 'NAME,TYPE'])
        if not success:
            print(f"{Colors.RED}Error discovering drives: {err}{Colors.RESET}"); return
            
        drives_to_populate = []
        for line in out.splitlines():
            try:
                name, disk_type = line.strip().split()
                if disk_type == 'disk' and name not in self.pool_drives:
                    drives_to_populate.append(Drive(name, self))
            except (ValueError, FileNotFoundError): continue
        
        with ThreadPoolExecutor(max_workers=16) as executor:
            futures = [executor.submit(drive.populate_details_for_available) for drive in drives_to_populate]
            for future in as_completed(futures):
                future.result()

        # Determine the minimum size required for a spare
        min_size_in_pool = 0
        data_drives_sizes = [p.size_bytes for d in self.pool_drives.values() for p in d.partitions if p.role == "Data"]
        if data_drives_sizes:
            min_size_in_pool = min(data_drives_sizes)

        # Filter the discovered drives
        if min_size_in_pool > 0:
            self.available_drives = [d for d in drives_to_populate if d.size_bytes >= min_size_in_pool]
        else:
            self.available_drives = drives_to_populate
            if self.pool_drives: # Pool exists but has no data drives
                 print(f"{Colors.YELLOW}Warning: Could not determine minimum data drive size to filter spares.{Colors.RESET}")
        
        print(f"Found {len(self.available_drives)} available drives suitable for use as spares.")

    def _get_user_choice(self, max_value: int) -> Optional[int]:
        while True:
            try:
                choice = input(f"{Colors.BLUE}> {Colors.RESET}").strip().lower()
                if choice in ['q', 'quit']: return None
                return int(choice) if 1 <= int(choice) <= max_value else print("Invalid choice.")
            except (ValueError, IndexError): print("Invalid input.")

    def _confirm_action(self, prompt: str) -> bool:
        print(f"\n{Colors.RED}WARNING: {prompt}{Colors.RESET}")
        return input("Type 'YES' to proceed: ").strip() == 'YES'

    def _add_spare(self, drive: Drive):
        prompt = f"This will first DESTROY ALL DATA on {drive.path} with 'wipefs -a', then add it as a spare."
        if not self._confirm_action(prompt):
            print("Add spare cancelled."); return

        if not drive.wipe():
            print(f"{Colors.RED}Aborting add spare due to wipe failure.{Colors.RESET}")
            return
        
        add_command = ['zpool', 'add', self.pool_name, 'spare', drive.stable_path]
        print(f"\n{Colors.GREEN}Proposed command: {' '.join(add_command)}{Colors.RESET}")
        if self.dry_run:
            print("[DRY RUN] Would execute command above."); return
        
        add_success, add_out, add_err = self._run_command(add_command)
        if add_success: print(f"{Colors.GREEN}Successfully added {drive.path} as a spare.{Colors.RESET}\n{add_out}")
        else: print(f"{Colors.RED}Failed to add spare: {add_err}{Colors.RESET}")

    def main_menu(self):
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            if self.dry_run: print(" " * 20 + f"{Colors.YELLOW}DRY RUN MODE ENABLED{Colors.RESET}")
            if not self.parse_zpool_status(): break
            self.discover_available_drives()
            
            print(f"\n{'='*80}\n{Colors.YELLOW}ZFS Pool Manager :: Managing {Colors.BLINK_RED}'{self.pool_name}'{Colors.RESET}{Colors.YELLOW}{'='*80}{Colors.RESET}")

            menu_items: List[Drive] = []
            
            print("\n--- Physical Drives in Pool ---")
            sorted_drives = sorted(self.pool_drives.values(), key=lambda d: d.path)
            for drive in sorted_drives:
                menu_items.append(drive)
                print(f"\n{len(menu_items)}. {drive}")
                for partition in drive.partitions:
                    print(f"      └─ {partition}")

            print("\n--- Available Physical Drives for Spares ---")
            sorted_available = sorted(self.available_drives, key=lambda d: d.path)
            for drive in sorted_available:
                menu_items.append(drive)
                print(f"\n{len(menu_items)}. {str(drive)} | Size: {Colors.YELLOW}{drive.size_hr}{Colors.RESET}")


            print(f"\n{'-'*80}\n{Colors.GREEN}Select a physical drive by number to manage, or 'q' to quit.{Colors.RESET}")
            
            choice = self._get_user_choice(len(menu_items))
            if choice is None: break

            selected_drive = menu_items[choice - 1]
            if selected_drive.partitions: # Is a drive in the pool
                self._physical_drive_menu(selected_drive)
            else: # Is an available drive
                self._add_spare(selected_drive)

            if choice is not None:
                print(f"\n{Colors.GREEN}Refreshing pool status...{Colors.RESET}"); time.sleep(2)

    def _physical_drive_menu(self, drive: Drive):
        while True:
            print(f"\n{'='*60}\nManaging Physical Drive: {drive.path}\n{'='*60}")
            print("Select a ZFS device to manage, or an action for the entire drive:")

            menu_items: list = []
            for partition in drive.partitions:
                menu_items.append(partition)
                print(f" {len(menu_items)}. Manage {partition}")
            
            print("\n--- Actions for Entire Physical Drive ---")
            
            if len(drive.partitions) == 1:
                menu_items.append("replace_drive")
                print(f" {len(menu_items)}. Replace whole drive (shortcut)")
                menu_items.append("detach_drive")
                print(f" {len(menu_items)}. Detach whole drive (shortcut)")

            menu_items.append("wipe_drive"); print(f" {len(menu_items)}. Wipe drive ({drive.path})")
            menu_items.append("blink_drive"); print(f" {len(menu_items)}. Blink drive light ({drive.path})")
            menu_items.append("back"); print(f" {len(menu_items)}. Back to main menu")

            choice = self._get_user_choice(len(menu_items))
            if choice is None: break
            
            selected_item = menu_items[choice - 1]

            if isinstance(selected_item, Partition):
                self._partition_menu(selected_item); break
            elif selected_item == "replace_drive": drive.replace(); break
            elif selected_item == "detach_drive": drive.detach(); break
            elif selected_item == "wipe_drive": drive.wipe()
            elif selected_item == "blink_drive": drive.blink()
            elif selected_item == "back": break


    def _partition_menu(self, partition: Partition):
        while True:
            print(f"\n{'='*60}\nManaging ZFS Device: {partition.pool_identifier} (on {partition.parent_drive.path})\n{'='*60}")
            print("1. Replace ZFS device")
            print("2. Detach ZFS device from pool")
            print("3. Back to previous menu")
            choice = self._get_user_choice(3)
            if choice in [None, 3]: break
            elif choice == 1: self._replace_menu(partition); break
            elif choice == 2: partition.detach(); break

    def _replace_menu(self, partition: Partition):
        print("\n--- Select a replacement drive ---")
        pool_spares = [p for d in self.pool_drives.values() for p in d.partitions if p.role == "Spare"]
        
        menu_items: List[Drive] = []
        if pool_spares:
            print(f"1. Use active spare: {pool_spares[0].pool_identifier} (on {pool_spares[0].parent_drive.path})")
            menu_items.append(pool_spares[0].parent_drive)

        for drive in self.available_drives:
            print(f"{len(menu_items) + 1}. {drive.path} ({drive.model})")
            menu_items.append(drive)

        print(f"{len(menu_items) + 1}. Cancel")
        choice = self._get_user_choice(len(menu_items) + 1)
        
        if choice is None or choice > len(menu_items):
            print("Replacement cancelled."); return
            
        new_drive = menu_items[choice - 1]
        partition.replace(new_drive)

def main():
    parser = argparse.ArgumentParser(description="ZFS Pool Management Script", formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('pool_name', help="The name of the ZFS pool to manage.")
    parser.add_argument('--dryrun', action='store_true', help="Run in dry-run mode.")
    parser.add_argument('--debug', action='store_true', help="Show all subprocess commands and their output.")
    args = parser.parse_args()
    manager = ZFSManager(args.pool_name, args.dryrun, args.debug)
    manager.main_menu()
    print(f"\n{Colors.BLUE}Exiting ZFS Manager.{Colors.RESET}")


if __name__ == "__main__":
    main()

