#!/usr/bin/env python3
import os
import shutil
import argparse
import re
from datetime import datetime

def organize_files(dry_run=False):
    current_dir = os.getcwd()
    script_name = os.path.basename(__file__)
    
    # Regex to match the pattern: 4 digits, a hyphen, 2 digits, and letters
    # Example matches: 2025-01Jan, 2026-12Dec
    pattern = re.compile(r"^\d{4}-\d{2}[a-zA-Z]+$")
    
    if dry_run:
        print("=== DRY RUN MODE: No items will be moved ===")
    
    for filename in os.listdir(current_dir):
        file_path = os.path.join(current_dir, filename)
        
        # 1. Skip the script itself
        if filename == script_name:
            continue
            
        # 2. Skip folders that already match our destination pattern
        if os.path.isdir(file_path) and pattern.match(filename):
            if dry_run:
                print(f"[Skipped] Existing pattern folder: {filename}/")
            continue
            
        try:
            # Get the last modification time of the item
            stat = os.stat(file_path)
            timestamp = stat.st_mtime
            file_date = datetime.fromtimestamp(timestamp)
            
            # Format: YYYY-mmB (e.g., 2025-01Jan)
            folder_name = file_date.strftime("%Y-%m%b")
            
            # Prevent an item from trying to move into itself 
            if filename == folder_name:
                continue

            if dry_run:
                item_type = "folder" if os.path.isdir(file_path) else "file"
                print(f"[Simulated] Would move {item_type}: {filename} -> {folder_name}/")
            else:
                # Create the target directory if it doesn't exist
                target_dir = os.path.join(current_dir, folder_name)
                if not os.path.exists(target_dir):
                    os.makedirs(target_dir)
                    print(f"Created directory: {folder_name}")
                
                # Move the file or folder
                shutil.move(file_path, os.path.join(target_dir, filename))
                print(f"Moved: {filename} -> {folder_name}/")
            
        except Exception as e:
            print(f"Error processing {filename}: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Organize files and non-pattern folders into YYYY-MMMonth folders.")
    parser.add_argument(
        "--dryrun", 
        action="store_true", 
        help="Show what actions would be taken without actually moving anything."
    )
    args = parser.parse_args()

    organize_files(dry_run=args.dryrun)
    print("Execution finished.")
