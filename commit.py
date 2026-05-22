#!/usr/bin/python3

__version__ = "1.0.0"

import os
import sys

_UTILS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "utils")
sys.path.insert(0, _UTILS_DIR)

import colorama
from colorama import Fore

from get_yes_no import GetYesNoToQuestion
from git import Git

def main():
    colorama.init(autoreset=True)

    if not Git.in_git_folder():
        print(Fore.RED + "not in git folder")
        sys.exit(1)
    Git.cd_git_root()
    if Git.no_changes_exist():
        print(Fore.GREEN + "nothing to commit")
        #if Git.unpushed_commits():
        sys.exit(0)
    if os.system("git status"):
        raise Exception("invalid git status")

    if not GetYesNoToQuestion.immediate(Fore.YELLOW + "commit?"):
        sys.exit(0)

    if os.system("git add -A"):
        raise Exception("invalid git add")

    if os.system("git commit"):
        raise Exception("invalid git commit")
    print(Fore.YELLOW + "pushing...")
    if os.system("git push"):
        raise Exception("invalid git push")

if __name__ == "__main__":
    sys.exit(main())
