#!/usr/bin/env python3
"""PreToolUse guard — the safety net that stays active in fully automatic mode.

Bash: the command line is parsed into simple commands (split on && || ; | & and newlines,
heredoc bodies set aside, sudo/env/bash -c/$(…) unwrapped) and each rule looks at the program
that actually runs, so a commit message or a PR body that merely *mentions* `rm -rf /` is not
blocked. If the line cannot be parsed, a conservative text match is used instead.

Edit / Write / MultiEdit / NotebookEdit: once the project is initialized, framework-owned files
(framework/MANIFEST `owned`) and `.fw/state.json` are read-only — they change through the
upstream template and /fw-update, or through `fw` itself.

Exit code 2 blocks the call and sends the reason back to Claude. Keep the rules unambiguous: it
is a seatbelt, not a policy engine. Every rule has a line in framework/tests/test_guard.py.
"""
import fnmatch
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SEPARATORS = {";", "&", "&&", "|", "||", "|&", "(", ")", "\n", ";;"}
WRAPPERS = {"sudo", "env", "command", "builtin", "exec", "nohup", "time", "nice", "ionice", "stdbuf", "doas"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
DB_CLIENTS = {"mysql", "mariadb", "psql", "sqlite3", "sqlcmd", "mysqlsh", "clickhouse-client", "cockroach"}
DEFAULT_BRANCHES = {"main", "master"}
PROTECTION_API = re.compile(r"(^|/)repos/[^/]+/[^/]+/(rulesets(/|$)|branches/[^/]+/protection)")
REPO_API = re.compile(r"^/?repos/[^/]+/[^/]+/?$")
SQL_RULES = [
    (re.compile(r"\bdrop\s+(database|schema|table)\b", re.I), "dropping a database, schema or table"),
    (re.compile(r"\btruncate\s+(table\s+)?[\w.`\"]", re.I), "truncating a table"),
    (re.compile(r"\bdelete\s+from\s+[\w.`\"]+\s*(;|$|\))", re.I | re.M), "DELETE without a WHERE clause"),
]

# Fallback when the command line cannot be parsed (unbalanced quotes…): plain text match.
RAW_RULES = [
    (r"\brm\s+(-\S+\s+)*-\S*[rR]\S*\s+(-\S+\s+)*(/|~|\$HOME|/\*|\.\.)(\s|/?$)", "recursive delete of /, ~ or .."),
    (r"\bgit\s+push\b[^|;&]*\s(--force|-f|--mirror)(\s|$)", "force push"),
    (r"\bgh\s+repo\s+(delete|archive)\b", "deleting or archiving a repository"),
    (r"\bgh\s+project\s+delete\b", "deleting the GitHub project"),
    (r"\bgit\s+filter-(branch|repo)\b", "rewriting history"),
    (r"\bmkfs(\.\w+)?\b|\bdd\s+[^|;&]*of=/dev/", "writing to a block device"),
    (r"\bdrop\s+(database|schema)\b", "dropping a database"),
]


class Blocked(Exception):
    pass


# --------------------------------------------------------------------------- project state

def config():
    try:
        return json.loads((ROOT / ".fw" / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def protected_patterns():
    """framework-owned paths (MANIFEST) + .fw/state.json, only once the project is initialized."""
    if not config().get("initialized"):
        return []
    pats = [".fw/state.json"]
    try:
        for line in (ROOT / "framework" / "MANIFEST").read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0] == "owned":
                pats.append(parts[1])
    except OSError:
        pats.append("framework/*")
    return pats


def rel_to_root(path):
    root = ROOT.resolve()
    cwd = Path.cwd().resolve()
    wt = root.parent / f"{root.name}.worktrees"
    base = cwd if cwd == root or root in cwd.parents or wt in cwd.parents else root
    p = Path(os.path.expanduser(path))
    p = (p if p.is_absolute() else base / p).resolve()
    try:
        return p.relative_to(root).as_posix()
    except ValueError:
        pass
    worktrees = root.parent / f"{root.name}.worktrees"  # `fw worktree`: <repo>.worktrees/<n>-<slug>/…
    try:
        parts = p.relative_to(worktrees).parts
        return "/".join(parts[1:]) if len(parts) > 1 else None
    except ValueError:
        return None


def check_protected(paths, how):
    pats = protected_patterns()
    if not pats:
        return
    for path in paths:
        rel = rel_to_root(path) if path else None
        if rel and any(fnmatch.fnmatch(rel, p) for p in pats):
            raise Blocked(f"{how} {rel}, which is framework-owned (framework/MANIFEST) or written only by `fw`. "
                          "Change it in the upstream template and run /fw-update; project-specific behaviour "
                          "belongs in CLAUDE.md, .claude/agents/ or docs/")


def git_out(*args):
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, cwd=ROOT, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return subprocess.CompletedProcess(args, 1, "", "")


# --------------------------------------------------------------------------- parsing

HEREDOC = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)([A-Za-z_][\w-]*)\2")


def split_heredocs(cmd):
    """Remove heredoc bodies from the command line; return (command, bodies)."""
    bodies, out, lines, i = [], [], cmd.split("\n"), 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        i += 1
        for m in HEREDOC.finditer(line):
            body = []
            while i < len(lines):
                cur = lines[i]
                i += 1
                if (cur.lstrip("\t") if m.group(1) else cur) == m.group(3):
                    break
                body.append(cur)
            bodies.append("\n".join(body))
    return "\n".join(out), bodies


def substitutions(cmd):
    """Inner commands of $(…) and `…` (not nested), which bash runs even inside double quotes."""
    return re.findall(r"\$\(([^()]*)\)", cmd) + re.findall(r"`([^`]*)`", cmd)


def tokenize(cmd):
    lex = shlex.shlex(cmd, posix=True, punctuation_chars=";&|<>()\n")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    return list(lex)


def simple_commands(tokens):
    """Split tokens into simple commands; drop redirections but report their targets."""
    cmds, cur, writes, i = [], [], [], 0
    while i < len(tokens):
        t = tokens[i]
        if t in SEPARATORS:
            if cur:
                cmds.append(cur)
            cur = []
        elif set(t) <= set("<>&|") and ("<" in t or ">" in t):
            target = tokens[i + 1] if i + 1 < len(tokens) else ""
            if ">" in t and not t.endswith("&") and target:
                writes.append(target)
            if cur and cur[-1].isdigit():
                cur.pop()
            i += 1
        else:
            cur.append(t)
        i += 1
    if cur:
        cmds.append(cur)
    return cmds, writes


def unwrap(argv):
    """Strip VAR=value prefixes and wrappers (sudo, env, nohup…)."""
    while argv:
        if re.match(r"^[A-Za-z_]\w*=", argv[0]):
            argv = argv[1:]
        elif os.path.basename(argv[0]) in WRAPPERS:
            argv = argv[1:]
            while argv and argv[0].startswith("-"):
                argv = argv[2:] if argv[0] in ("-u", "-g", "-n") else argv[1:]
        else:
            break
    return argv


def short_flags(args):
    """Letters of the short option groups (-rf, -fu…) before `--`."""
    letters = set()
    for a in args:
        if a == "--":
            break
        if a.startswith("-") and not a.startswith("--") and len(a) > 1:
            letters |= set(a[1:])
    return letters


def positionals(args):
    out, end = [], False
    for a in args:
        if a == "--" and not end:
            end = True
        elif end or not a.startswith("-"):
            out.append(a)
    return out


# --------------------------------------------------------------------------- rules

DANGEROUS_RM = {"/", "/*", "~", "~/", "~/*", "$HOME", "${HOME}", "$HOME/", "$HOME/*", "..", "../", "../*",
                ".", "./"}


def check_rm(args):
    if "--no-preserve-root" in args:
        raise Blocked("rm --no-preserve-root")
    if not ({"r", "R"} & short_flags(args) or "--recursive" in args):
        return
    for target in positionals(args):
        if target in DANGEROUS_RM or re.fullmatch(r"/[^/]+/?", target):
            raise Blocked(f"recursive delete of {target}")


def git_subcommand(args):
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in ("-C", "-c", "--git-dir", "--work-tree", "--namespace") else 1
    return (args[i], args[i + 1:]) if i < len(args) else (None, [])


def current_branch():
    return git_out("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def tracked_changes():
    return bool(git_out("status", "--porcelain", "--untracked-files=no").stdout.strip())


def remote_default_exists(remote):
    """True when the remote already has main/master, or when we cannot tell (fail closed)."""
    p = git_out("ls-remote", "--exit-code", "--heads", remote, *DEFAULT_BRANCHES)
    return p.returncode != 2  # 2 = reachable, no matching ref


def check_git_push(args):
    if "--mirror" in args:
        raise Blocked("git push --mirror")
    if "--no-verify" in args:
        raise Blocked("git push --no-verify — fix what the hooks report instead of skipping them")
    pos = [a for a in positionals(args)]
    remote, refspecs = (pos[0], pos[1:]) if pos else ("origin", [])
    if "--force" in args or "f" in short_flags(args) or any(r.startswith("+") for r in refspecs):
        raise Blocked("force push — use --force-with-lease, on your own feature branch only")
    dsts = [r.split(":", 1)[-1].replace("refs/heads/", "") for r in refspecs]
    deleting = "--delete" in args or "d" in short_flags(args)
    if any(r.startswith(":") and r[1:].replace("refs/heads/", "") in DEFAULT_BRANCHES for r in refspecs) or \
            (deleting and DEFAULT_BRANCHES & set(dsts)):
        raise Blocked("deleting the default branch on the remote")
    if deleting:
        return
    to_default = bool(DEFAULT_BRANCHES & set(dsts)) or "--all" in args or \
        ((not refspecs or "HEAD" in dsts) and current_branch() in DEFAULT_BRANCHES)
    if to_default and config().get("initialized") and remote_default_exists(remote):
        raise Blocked("direct push to main/master — work on a branch and open a pull request "
                      "(framework/standards/git-workflow.md). Only the very first push of a new repository, "
                      "when the remote has no main yet, may go to main directly")


def check_git(args):
    sub, rest = git_subcommand(args)
    if sub == "push":
        check_git_push(rest)
    elif sub in ("filter-branch", "filter-repo"):
        raise Blocked("rewriting history")
    elif sub in ("commit", "merge") and ("--no-verify" in rest or (sub == "commit" and "n" in short_flags(rest))):
        raise Blocked(f"git {sub} --no-verify — fix what the hooks report instead of skipping them")
    elif sub == "reset" and "--hard" in rest and tracked_changes():
        raise Blocked("git reset --hard with uncommitted changes — commit or stash them first")
    elif sub == "clean" and ("--force" in rest or "f" in short_flags(rest)) and \
            not ("--dry-run" in rest or "n" in short_flags(rest)):
        raise Blocked("git clean -f deletes untracked files — run `git clean -n` and remove what you need by name")
    elif sub == "branch" and ({"d", "D"} & short_flags(rest) or "--delete" in rest) and \
            DEFAULT_BRANCHES & set(positionals(rest)):
        raise Blocked("deleting the default branch")


def check_gh(args):
    pos = positionals(args)
    head = pos[:2]
    if head == ["repo", "delete"] or head == ["repo", "archive"]:
        raise Blocked("deleting or archiving a repository")
    if head == ["repo", "edit"] and any(a.startswith("--visibility") for a in args):
        raise Blocked("changing the repository visibility")
    if head == ["project", "delete"]:
        raise Blocked("deleting the GitHub project")
    if head == ["pr", "merge"] and "--admin" in args:
        raise Blocked("gh pr merge --admin bypasses branch protection — wait for the required checks")
    if pos[:1] == ["api"]:
        method = "GET"
        for i, a in enumerate(args):
            if a in ("-X", "--method") and i + 1 < len(args):
                method = args[i + 1].upper()
            elif a.startswith("--method="):
                method = a.split("=", 1)[1].upper()
            elif a.startswith("-X") and len(a) > 2:
                method = a[2:].upper()
        path = next((p for p in pos[1:] if p.upper() != method), "")
        if method == "DELETE" and REPO_API.search(path):
            raise Blocked("deleting a repository through the API")
        if method != "GET" and PROTECTION_API.search(path):
            raise Blocked("changing branch protection — the user runs `framework/bin/fw protect`")


def check_sql(prog, args, text):
    if prog == "dropdb" or (prog == "mysqladmin" and "drop" in args):
        raise Blocked("dropping a database")
    if prog == "redis-cli" and {"flushall", "flushdb"} & {a.lower() for a in args}:
        raise Blocked("flushing a Redis database")
    if prog in DB_CLIENTS:
        for rx, reason in SQL_RULES:
            if rx.search(text):
                raise Blocked(reason)


def check_command(argv, heredocs):
    argv = unwrap(argv)
    if not argv:
        return
    prog, args = os.path.basename(argv[0]), argv[1:]
    if prog in SHELLS and "-c" in args[:-1]:
        return check_line(args[args.index("-c") + 1])
    if prog == "eval":
        return check_line(" ".join(args))
    if prog == "rm":
        check_rm(args)
        check_protected(positionals(args), "deleting")
    elif prog == "git":
        check_git(args)
    elif prog == "gh":
        check_gh(args)
    elif prog.startswith("mkfs") or (prog == "dd" and any(a.startswith("of=/dev/") for a in args)):
        raise Blocked("writing to a block device")
    elif prog in ("chmod", "chown") and ({"R"} & short_flags(args) or "--recursive" in args) and \
            any(t in DANGEROUS_RM or re.fullmatch(r"/[^/]+/?", t) for t in positionals(args)[1:]):
        raise Blocked(f"recursive {prog} on a system or home directory")
    elif prog == "tee":
        check_protected(positionals(args), "writing to")
    elif prog == "sed" and ("-i" in args or any(a.startswith(("-i", "--in-place")) for a in args)):
        check_protected(positionals(args), "editing")
    elif prog in ("cp", "mv", "install", "ln", "truncate") and positionals(args):
        targets = positionals(args) if prog in ("mv", "truncate") else positionals(args)[-1:]
        check_protected(targets, "writing to")
    check_sql(prog, args, " ".join(args) + "\n" + "\n".join(heredocs))


def check_line(cmd, depth=0):
    if depth > 3:
        return
    line, heredocs = split_heredocs(cmd)
    for inner in substitutions(line):
        check_line(inner, depth + 1)
    try:
        tokens = tokenize(line)
    except ValueError:
        for pattern, reason in RAW_RULES:
            if re.search(pattern, cmd, re.I):
                raise Blocked(reason)
        return
    cmds, writes = simple_commands(tokens)
    check_protected(writes, "redirecting output to")
    for argv in cmds:
        check_command(argv, heredocs)


# --------------------------------------------------------------------------- entry point

def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    tool = data.get("tool_name") or "Bash"
    inp = data.get("tool_input") or {}
    try:
        if tool == "Bash":
            check_line(inp.get("command") or "")
        elif tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
            check_protected([inp.get("file_path") or inp.get("notebook_path") or ""], "modifying")
    except Blocked as e:
        print(f"Blocked by framework guard: {e}. If this is really needed, ask the user to run it themselves.",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
