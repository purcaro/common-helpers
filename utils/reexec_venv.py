import os
import sys


def reexec_in_venv(root: str) -> None:
    """Re-run the current script with the project .venv Python when available."""
    if sys.platform == "win32":
        candidates = [os.path.join(root, ".venv", "Scripts", "python.exe")]
    else:
        candidates = [
            os.path.join(root, ".venv", "bin", "python3"),
            os.path.join(root, ".venv", "bin", "python"),
        ]

    venv_python = next((p for p in candidates if os.path.isfile(p)), None)
    if venv_python is None:
        return

    # Compare paths, not realpath: venv python is often a symlink to system python,
    # but Python only loads the venv site-packages when invoked via the venv path.
    if os.path.normpath(os.path.abspath(sys.executable)) == os.path.normpath(
        os.path.abspath(venv_python)
    ):
        return

    os.execv(venv_python, [venv_python, *sys.argv])
