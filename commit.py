#!/usr/bin/env python3

__version__ = "1.1.0"

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_ROOT, "utils"))

from reexec_venv import reexec_in_venv

reexec_in_venv(_ROOT)

import argparse
import subprocess
from typing import List, Optional

import colorama
from colorama import Fore

from get_yes_no import GetYesNoToQuestion
from git import Git


def run_git(*args: str) -> None:
    result = subprocess.run(["git", *args])
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Stage, commit, and push from the git repository root.")
    parser.add_argument("--no-push", action="store_true", help="Commit only; do not push.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    colorama.init(autoreset=True)

    if not Git.in_git_folder():
        print(Fore.RED + "not in git folder")
        return 1

    Git.cd_git_root()

    if Git.no_changes_exist():
        if Git.unpushed_commits():
            print(Fore.YELLOW + "nothing to commit (unpushed commits exist)")
            if GetYesNoToQuestion.immediate(Fore.YELLOW + "push?"):
                print(Fore.YELLOW + "pushing...")
                Git.push()
        else:
            print(Fore.GREEN + "nothing to commit")
        return 0

    run_git("status")

    if not GetYesNoToQuestion.immediate(Fore.YELLOW + "commit?"):
        return 0

    run_git("add", "-A")
    run_git("commit")

    if args.no_push:
        return 0

    print(Fore.YELLOW + "pushing...")
    Git.push()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(Fore.RED + str(exc), file=sys.stderr)
        raise SystemExit(1)
