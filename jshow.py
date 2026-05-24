#!/usr/bin/env python3

import importlib.util
import os
import subprocess
import sys

REQUIRED_MODULES = ("pygments", "requests")


def _venv_python(root: str) -> str | None:
    if sys.platform == "win32":
        candidates = [os.path.join(root, ".venv", "Scripts", "python.exe")]
    else:
        candidates = [
            os.path.join(root, ".venv", "bin", "python3"),
            os.path.join(root, ".venv", "bin", "python"),
        ]
    return next((p for p in candidates if os.path.isfile(p)), None)


def _missing_modules() -> list[str]:
    return [m for m in REQUIRED_MODULES if importlib.util.find_spec(m) is None]


def _prepare_environment() -> None:
    """Use .venv and install jshow dependencies when needed."""
    root = os.path.dirname(os.path.abspath(__file__))
    setup_py = os.path.join(root, "setup.py")
    venv_python = _venv_python(root)

    if venv_python is None:
        subprocess.check_call([sys.executable, setup_py, "bootstrap"])
        venv_python = _venv_python(root)
        if venv_python is None:
            sys.exit("error: failed to create .venv; run ./setup.py")

    if os.path.realpath(sys.executable) != os.path.realpath(venv_python):
        os.execv(venv_python, [venv_python, *sys.argv])

    if _missing_modules():
        subprocess.check_call([sys.executable, setup_py, "bootstrap"])
        if _missing_modules():
            missing = ", ".join(_missing_modules())
            sys.exit(f"error: missing packages ({missing}); run ./setup.py")


_prepare_environment()

import glob
import json
import argparse
import errno
import requests
import re
import gzip
from subprocess import Popen, PIPE
from pygments import highlight, lexers, formatters

def colorize(json, force=None):
    # https://stackoverflow.com/questions/25638905/coloring-json-output-in-python
    if force or sys.stdout.isatty():
        colorful_json = highlight(json, lexers.JsonLexer(),
                                  formatters.TerminalFormatter())
        return colorful_json
    return json


def pager(text):
    # be nice
    pager = os.getenv('PAGER')
    if not pager:
        pager = ['less', '-F', '-R', '-X']
    p = Popen(pager, stdin=PIPE)
    try:
        p.stdin.write(text.encode('utf-8'))
    except IOError as e:
        if e.errno == errno.EPIPE or e.errno == errno.EINVAL:
            pass
        else:
            raise
    p.stdin.close()
    p.wait()


class JShow(object):

    def __init__(self, files):
        if isinstance(files, str):
            self._files = [files]
        elif isinstance(files, list):
            self._files = files
        else:
            raise Exception("no valid file provided")

    def show(self, color=None):
        mylist = []
        for fn in self._files:
            if "-" == fn:
                mylist.append(json.load(sys.stdin))
            elif re.match("^[a-zA-Z]+://", fn):
                mylist.append(requests.get(fn).json())
            else:
                if fn.endswith(".gz"):
                    with gzip.open(fn, "rb") as f:
                        mylist.append(json.load(f))
                else:
                    with open(fn, "r") as f:
                        mylist.append(json.load(f))
        if color:
            pager(colorize(json.dumps(mylist, sort_keys=True, indent=4)))
        else:
            pager(json.dumps(mylist, sort_keys=True, indent=4))


if __name__ == "__main__":

    def parse_args():
        parser = argparse.ArgumentParser()
        parser.add_argument('-n', '--nocolor', action="store_true", help='disable color output', default=False)
        parser.add_argument('file', type=str, nargs='*', default="-", help='(list of) file name(s)')
        args = parser.parse_args()
        return args

    # do it
    args = parse_args()
    js = JShow(args.file).show(sys.stdout.isatty() and not args.nocolor)
