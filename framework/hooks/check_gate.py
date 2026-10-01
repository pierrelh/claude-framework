#!/usr/bin/env python3
"""Stop / SubagentStop hook: don't let an agent finish with failing checks.

Opt-in: `fw config set gates.check_on_stop true`. Checks the main checkout and every story
worktree (`fw worktree`, under <repo>.worktrees/) that has changes or sits on a feature
branch: `fw check` — the project's lint / typecheck / test / build commands from
.fw/config.json → commands — runs in each of them. On failure, exit code 2 sends the failing
output back to the agent, which keeps working; a second stop in a row (`stop_hook_active`) is
always allowed, so the agent can still finish with `STATUS: BLOCKED` instead of looping.

A green result is cached per tree state in .fw/local/check-gate.json, so stopping again
without changes costs nothing. A timeout (`gates.check_timeout`, default 900 s per tree) or a
project without commands never blocks.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".fw" / "local" / "check-gate.json"


def git(cwd, *args):
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    return p.stdout if p.returncode == 0 else b""


def trees():
    """The main checkout first, then the story worktrees."""
    base = ROOT.resolve().parent / f"{ROOT.resolve().name}.worktrees"
    out = [ROOT]
    for line in git(ROOT, "worktree", "list", "--porcelain").decode(errors="replace").splitlines():
        if line.startswith("worktree "):
            path = Path(line[9:])
            if base in path.resolve().parents:
                out.append(path)
    return out


def tree_key(tree):
    """Identifies HEAD + uncommitted changes + untracked files (names and contents)."""
    h = hashlib.sha256(git(tree, "rev-parse", "HEAD") + git(tree, "diff", "HEAD", "--binary"))
    for name in sorted(git(tree, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0")):
        path = tree / name.decode(errors="replace")
        if name and path.is_file():
            h.update(name + path.read_bytes())
    return h.hexdigest()


def needs_check(tree):
    branch = git(tree, "rev-parse", "--abbrev-ref", "HEAD").decode().strip()
    dirty = bool(git(tree, "status", "--porcelain").strip())
    return dirty or branch not in ("main", "master")


def run_check(tree, timeout):
    """None when green or not decidable (timeout, unconfigured), else the failed steps."""
    fw = tree / "framework" / "bin" / "fw.py"
    if not fw.exists():
        fw = ROOT / "framework" / "bin" / "fw.py"
    try:
        p = subprocess.run([sys.executable, str(fw), "check", "--json"], cwd=tree, capture_output=True,
                           text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"[fw check-gate] fw check timed out in {tree} — not blocking; run it yourself before finishing.")
        return None
    if p.returncode == 2:  # not configured
        return None
    try:
        result = json.loads(p.stdout)
    except ValueError:
        return None
    return None if result.get("ok") else [s for s in result.get("steps", []) if s.get("exit")]


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        data = {}
    try:
        cfg = json.loads((ROOT / ".fw" / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    gates = cfg.get("gates") or {}
    if not gates.get("check_on_stop") or data.get("stop_hook_active") or not (cfg.get("commands") or {}):
        return 0
    try:
        cache = json.loads(CACHE.read_text())
        cache = cache if isinstance(cache.get("trees"), dict) else {"trees": {}}
    except (OSError, ValueError):
        cache = {"trees": {}}

    failures = []
    for tree in trees():
        if not needs_check(tree):
            continue
        key = tree_key(tree)
        if cache["trees"].get(str(tree)) == key:
            continue
        failed = run_check(tree, float(gates.get("check_timeout", 900)))
        if failed is None:
            cache["trees"][str(tree)] = key
        else:
            failures.append((tree, failed))
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache))
    if not failures:
        return 0

    lines = ["Quality gate failed — `framework/bin/fw check`:"]
    for tree, failed in failures:
        where = "" if tree == ROOT else f" in {tree}"
        lines.append("- " + ", ".join(f"{s['name']} (exit {s['exit']})" for s in failed) + where)
    lines.append("Fix it before finishing. If it cannot be fixed within this story, stop and report "
                 "`STATUS: BLOCKED` with the failing output (never weaken or skip the tests).")
    for tree, failed in failures:
        for s in failed:
            lines += ["", f"--- {s['name']}: {s['command']} ({tree.name}, last lines)", s.get("output_tail", "")]
    print("\n".join(lines), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
