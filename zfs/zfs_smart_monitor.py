#!/usr/bin/env python3
"""
ZFS Pool and SMART Monitor Script
Object-oriented version with classes for better maintainability
Designed to run as an hourly cron job on Ubuntu 22.04
"""

import os
import subprocess
import datetime
import glob
import sys
import json
from pathlib import Path
from typing import List, Tuple, Optional


class CommandRunner:
    """Handles running shell commands safely"""
    
    @staticmethod
    def run(cmd: str, timeout: int = 60) -> Tuple[str, str, int]:
        """Run a shell command and return output, handling errors gracefully"""
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=timeout
            )
            return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            return "", "Command timed out", 1
        except Exception as e:
            return "", f"Error running command: {str(e)}", 1


class DriveDetector:
    """Detects available drives for SMART monitoring"""
    
    def __init__(self):
        self.command_runner = CommandRunner()
    
    def get_all_drives(self) -> List[str]:
        """Get list of all available drives for smartctl using lsblk JSON output"""
        drives = self._get_drives_from_lsblk()
        
        if not drives:
            print("lsblk method failed or found no drives, falling back to glob method", 
                  file=sys.stderr)
            drives = self._get_drives_from_glob()
        
        return sorted(drives)
    
    def _get_drives_from_lsblk(self) -> List[str]:
        """Get drives using lsblk JSON output"""
        drives = []
        
        stdout, stderr, returncode = self.command_runner.run("lsblk --json")
        
        if returncode != 0 or not stdout:
            return drives
        
        try:
            lsblk_data = json.loads(stdout)
            
            for device in lsblk_data.get("blockdevices", []):
                device_name = device.get("name", "")
                device_type = device.get("type", "")
                
                if self._is_valid_drive(device_name, device_type):
                    drives.append(f"/dev/{device_name}")
                    
        except json.JSONDecodeError as e:
            print(f"Error parsing lsblk JSON output: {e}", file=sys.stderr)
        except Exception as e:
            print(f"Error processing lsblk data: {e}", file=sys.stderr)
        
        return drives
    
    def _get_drives_from_glob(self) -> List[str]:
        """Fallback method using glob patterns"""
        drives = []
        
        # Check various drive patterns
        patterns = [
            '/dev/sd[a-z]',      # SATA drives
            '/dev/nvme[0-9]n[0-9]',  # NVMe drives
            '/dev/hd[a-z]'       # IDE drives (older systems)
        ]
        
        for pattern in patterns:
            drives.extend(glob.glob(pattern))
        
        return drives
    
    @staticmethod
    def _is_valid_drive(device_name: str, device_type: str) -> bool:
        """Check if device is a valid storage drive we want to monitor"""
        return (device_type == "disk" and 
                device_name.startswith(('sd', 'nvme', 'hd')) and 
                not device_name.startswith('sr'))  # exclude CD-ROM drives


class ZPoolMonitor:
    """Handles ZFS pool status monitoring"""
    
    def __init__(self):
        self.command_runner = CommandRunner()
    
    def collect_status(self) -> str:
        """Collect zpool status output"""
        print("Collecting zpool status...")
        stdout, stderr, returncode = self.command_runner.run("zpool status")
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        output = f"# ZPool Status collected at {timestamp}\n"
        output += f"# Return code: {returncode}\n\n"
        
        if stdout:
            output += stdout
        if stderr:
            output += f"\n# STDERR:\n{stderr}"
        
        return output


class SmartMonitor:
    """Handles SMART data collection for drives"""
    
    def __init__(self):
        self.command_runner = CommandRunner()
        self.drive_detector = DriveDetector()
    
    def collect_and_save_data(self, config: 'MonitoringConfig', file_manager: 'FileManager') -> bool:
        """Collect smartctl output for all drives and save to separate files"""
        print("Collecting SMART data...")
        drives = self.drive_detector.get_all_drives()
        
        if not drives:
            # Create a summary file indicating no drives found
            summary_file = os.path.join(config.smartctl_dir, f"no_drives_found_{config.current_time}.txt")
            content = f"# No drives found for SMART monitoring at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            return file_manager.write_output(content, summary_file)
        
        print(f"Found {len(drives)} drives: {', '.join(drives)}")
        
        success = True
        for drive in drives:
            drive_data = self._collect_drive_data(drive)
            drive_file = config.get_smartctl_file(drive)
            
            if not file_manager.write_output(drive_data, drive_file):
                success = False
        
        return success
    
    def _collect_drive_data(self, drive: str) -> str:
        """Collect SMART data for a single drive"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        output = f"# SMART data for {drive}\n"
        output += f"# Collected at {timestamp}\n"
        output += f"{'='*60}\n\n"
        
        # Use the wrapper script for smartctl
        cmd = f"smartctl-wrapper.sh -a {drive}"
        stdout, stderr, returncode = self.command_runner.run(cmd)
        
        output += f"# Command: {cmd}\n"
        output += f"# Return code: {returncode}\n"
        
        # Add helpful message for permission or wrapper issues
        if returncode != 0:
            if "command not found" in stderr.lower() or "smartctl-wrapper.sh" in stderr:
                output += f"# NOTE: smartctl-wrapper.sh not found or not executable\n"
                output += f"# Please ensure /usr/local/bin/smartctl-wrapper.sh exists and is executable\n"
            elif "permission denied" in stderr.lower():
                output += f"# NOTE: Permission denied - check sudo configuration for smartctl\n"
        
        output += f"\n"
        
        if stdout:
            output += stdout
        if stderr:
            output += f"\n# STDERR:\n{stderr}"
        
        return output


class FileManager:
    """Handles file and directory operations"""
    
    @staticmethod
    def ensure_directory(path: str) -> bool:
        """Create directory if it doesn't exist"""
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            print(f"Error creating directory {path}: {e}", file=sys.stderr)
            return False
    
    @staticmethod
    def write_output(content: str, filepath: str) -> bool:
        """Write content to file"""
        try:
            with open(filepath, 'a') as f:
                f.write(content)
            print(f"Data written to {filepath}")
            return True
        except Exception as e:
            print(f"Error writing to {filepath}: {e}", file=sys.stderr)
            return False


class MonitoringConfig:
    """Configuration settings for the monitoring system"""
    
    def __init__(self, zpool_base_dir: str = "/tank/admin/zpool_status",
                 smartctl_base_dir: str = "/tank/admin/smartctl"):
        self.zpool_base_dir = zpool_base_dir
        self.smartctl_base_dir = smartctl_base_dir
        self.current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        self.current_time = datetime.datetime.now().strftime("%H-%M")  # No colons
    
    @property
    def zpool_dir(self) -> str:
        return os.path.join(self.zpool_base_dir, self.current_date)
    
    @property
    def smartctl_dir(self) -> str:
        return os.path.join(self.smartctl_base_dir, self.current_date)
    
    @property
    def zpool_file(self) -> str:
        return os.path.join(self.zpool_dir, f"zpool_status_{self.current_time}.txt")
    
    def get_smartctl_file(self, drive_name: str) -> str:
        """Get smartctl filename for a specific drive"""
        # Extract just the drive name (e.g., 'sda' from '/dev/sda')
        clean_drive_name = drive_name.replace('/dev/', '')
        return os.path.join(self.smartctl_dir, f"smartctl_{clean_drive_name}_{self.current_time}.txt")


class SystemMonitor:
    """Main monitoring system coordinator"""
    
    def __init__(self, config: Optional[MonitoringConfig] = None):
        self.config = config or MonitoringConfig()
        self.file_manager = FileManager()
        self.zpool_monitor = ZPoolMonitor()
        self.smart_monitor = SmartMonitor()
    
    def run(self) -> int:
        """Main monitoring run"""
        print(f"Starting monitoring run at {datetime.datetime.now()}")
        
        # Ensure directories exist
        if not self._setup_directories():
            return 1
        
        # Collect and store zpool status
        if not self._monitor_zpool():
            return 1
        
        # Collect and store smartctl data
        if not self._monitor_smart():
            return 1
        
        print(f"Monitoring run completed successfully at {datetime.datetime.now()}")
        print(f"************************************************************************")
        return 0
    
    def _setup_directories(self) -> bool:
        """Create necessary directories"""
        directories = [self.config.zpool_dir, self.config.smartctl_dir]
        
        for directory in directories:
            if not self.file_manager.ensure_directory(directory):
                print(f"Failed to create directory: {directory}", file=sys.stderr)
                return False
        
        return True
    
    def _monitor_zpool(self) -> bool:
        """Monitor ZFS pool status"""
        try:
            zpool_data = self.zpool_monitor.collect_status()
            return self.file_manager.write_output(zpool_data, self.config.zpool_file)
        except Exception as e:
            print(f"Error collecting zpool status: {e}", file=sys.stderr)
            return False
    
    def _monitor_smart(self) -> bool:
        """Monitor SMART data"""
        try:
            return self.smart_monitor.collect_and_save_data(self.config, self.file_manager)
        except Exception as e:
            print(f"Error collecting SMART data: {e}", file=sys.stderr)
            return False


def main():
    """Main entry point"""
    try:
        config = MonitoringConfig()
        monitor = SystemMonitor(config)
        return monitor.run()
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        print(f"************************************************************************")
        return 1


if __name__ == "__main__":
    sys.exit(main())
