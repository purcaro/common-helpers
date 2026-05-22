import os
import subprocess
from typing import List


class Git:
    @staticmethod
    def _run(args: List[str], **kwargs) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], **kwargs)

    @staticmethod
    def in_git_folder() -> bool:
        return (
            Git._run(
                ["rev-parse"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            == 0
        )

    @staticmethod
    def cd_git_root() -> None:
        result = Git._run(
            ["rev-parse", "--show-cdup"],
            capture_output=True,
            text=True,
            check=True,
        )
        root_dir = result.stdout.strip()
        if root_dir:
            os.chdir(root_dir)

    @staticmethod
    def no_changes_exist() -> bool:
        result = Git._run(
            ["status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
        return not result.stdout.strip()

    @staticmethod
    def unpushed_commits() -> bool:
        result = Git._run(
            ["rev-list", "--count", "@{upstream}..HEAD"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False
        return int(result.stdout.strip() or "0") > 0

    @staticmethod
    def current_branch() -> str:
        result = Git._run(
            ["rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    @staticmethod
    def push() -> None:
        if Git._run(["push"]).returncode == 0:
            return
        branch = Git.current_branch()
        if Git._run(["push", "-u", "origin", branch]).returncode != 0:
            raise RuntimeError("invalid git push")

    @staticmethod
    def repack() -> None:
        # http://gcc.gnu.org/ml/gcc/2007-12/msg00165.html
        if Git._run(["repack", "-a", "-d", "--depth=250", "--window=250", "-f"]).returncode != 0:
            raise RuntimeError("invalid git repack")
