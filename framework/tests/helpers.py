"""Shared test helpers: load the framework scripts as modules and build throwaway git repos.

Stdlib only, like the framework itself. Run the suite with:
    python3 -m unittest discover -s framework/tests
"""
import importlib.util
import json
import os
import subprocess
import tempfile
from pathlib import Path

FRAMEWORK = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = FRAMEWORK.parent

GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "fw-tests", "GIT_AUTHOR_EMAIL": "fw-tests@example.com",
           "GIT_COMMITTER_NAME": "fw-tests", "GIT_COMMITTER_EMAIL": "fw-tests@example.com",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def load_module(name, rel_path):
    """Import a framework script (fw.py, guard.py…) as a fresh module, so tests can patch its globals."""
    spec = importlib.util.spec_from_file_location(name, FRAMEWORK / rel_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, env=GIT_ENV, capture_output=True, text=True, check=True).stdout


def git_repo(path, commit=True):
    """Initialise `path` as a git repo on `main`, committing whatever is in it."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    if commit:
        git(path, "add", "-A")
        git(path, "commit", "-q", "--allow-empty", "-m", "init")
    return path


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


class TempDir:
    """`with TempDir() as d:` → a pathlib.Path removed on exit."""

    def __enter__(self):
        self._t = tempfile.TemporaryDirectory(prefix="fw-tests-")
        return Path(self._t.name)

    def __exit__(self, *exc):
        self._t.cleanup()
