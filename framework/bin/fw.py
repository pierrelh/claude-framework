#!/usr/bin/env python3
"""fw — command-line companion of the framework.

Deterministic plumbing that the skills call instead of improvising: environment
checks, GitHub Project (v2) setup, backlog -> issues, roadmap scheduling,
status moves, agent linting, docs link checks, framework install/update.

Dependencies: Python 3.8+ (stdlib only), git, GitHub CLI (gh).
Run `fw <command> -h` for the options of each command.
"""
import argparse
import datetime as dt
import fnmatch
import hashlib
import heapq
import json
import math
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FW_DIR = ROOT / ".fw"
CONFIG = FW_DIR / "config.json"
STATE = FW_DIR / "state.json"
LOCAL = FW_DIR / "local"

REQUIRED_SCOPES = ("repo", "project", "workflow")
MIN_GH = (2, 40)

PRIORITIES = ["Must", "Should", "Could", "Won't"]
PRIO_RANK = {p: i for i, p in enumerate(PRIORITIES)}
SIZES = [("XS", 1), ("S", 3), ("M", 6), ("L", 12), ("XL", math.inf)]
WORK_TYPES = ["Story", "Task", "Bug"]
DEFAULT_EFFORT = 2.0

F_STATUS, F_TYPE, F_PRIO, F_SIZE = "Status", "Item type", "Priority", "Size"
F_EFFORT, F_REVIEW, F_ACTUAL = "Agent effort (h)", "Human review (h)", "Actual (h)"
F_START, F_TARGET, F_AGENT = "Start date", "Target date", "Agent"
F_WAIT, F_ROUNDS = "Wait (h)", "Review rounds"

PROJECT_FIELDS = [
    (F_TYPE, "SINGLE_SELECT", [("Epic", "PURPLE"), ("Story", "BLUE"), ("Task", "GRAY"), ("Bug", "RED")]),
    (F_PRIO, "SINGLE_SELECT", [("Must", "RED"), ("Should", "ORANGE"), ("Could", "YELLOW"), ("Won't", "GRAY")]),
    (F_SIZE, "SINGLE_SELECT", [("XS", "GREEN"), ("S", "GREEN"), ("M", "YELLOW"), ("L", "ORANGE"), ("XL", "RED")]),
    (F_EFFORT, "NUMBER", None),
    (F_REVIEW, "NUMBER", None),
    (F_ACTUAL, "NUMBER", None),
    (F_START, "DATE", None),
    (F_TARGET, "DATE", None),
    (F_AGENT, "TEXT", None),
    (F_WAIT, "NUMBER", None),
    (F_ROUNDS, "NUMBER", None),
]
STATUS_OPTIONS = [
    ("Backlog", "GRAY", "Waiting on dependencies or refinement"),
    ("Ready", "BLUE", "Ready to be picked up"),
    ("In progress", "YELLOW", "Being implemented"),
    ("In review", "ORANGE", "Pull request open, under review"),
    ("Done", "GREEN", "Merged and verified"),
]
# Canonical status -> accepted option names, most specific first (fallback to GitHub defaults).
STATUS_ALIASES = {
    "backlog": ["backlog", "todo", "to do"],
    "ready": ["ready", "todo", "to do"],
    "in progress": ["in progress", "doing"],
    "in review": ["in review", "review", "in progress"],
    "done": ["done"],
}
LABELS = [
    ("epic", "5319e7", "Groups user stories"),
    ("story", "1d76db", "User story"),
    ("task", "cfd3d7", "Technical task"),
    ("bug", "d73a4a", "Something is broken"),
    ("blocked", "b60205", "Cannot progress"),
    ("needs-human", "fbca04", "Requires a human decision or action"),
    ("hotfix", "e11d21", "Urgent fix: goes before everything else (/fw-work short path)"),
    ("triage", "ededed", "Not qualified yet — /fw-triage"),
    ("needs-info", "d4c5f9", "Waiting for more information from the reporter"),
]
GITIGNORE_LINES = [
    ".claude/settings.local.json",
    ".fw/local/",
    "docs/.obsidian/workspace*.json",
    "docs/.obsidian/cache",
    "site/",
    "__pycache__/",
]
META_FILES = ["README*", "LICENSE*", "CHANGELOG*", ".gitignore", ".gitattributes", ".editorconfig"]
AGENT_SECTIONS = ["Mission", "Scope", "Inputs", "Procedure", "Quality bar", "Output contract", "Escalation"]
ROLE_TOKENS = {"spec": "SPEC:", "implement": "STATUS:", "review": "VERDICT:", "qa": "QA:", "docs": "DOCS:"}

HEADINGS = {
    "en": {
        "as_a": "As a", "i_want": "I want", "so_that": "so that", "context": "Context",
        "ac": "Acceptance criteria", "given": "Given", "when": "When", "then": "Then",
        "measure": "Success measure", "tech": "Technical notes", "oos": "Out of scope",
        "dod": "Definition of Done", "estimate": "Estimate", "effort": "Agent effort",
        "review": "Human review", "size": "Size", "agent": "Assigned agent",
        "deps": "Dependencies", "blocked_by": "Blocked by", "goal": "Goal",
        "description": "Description", "steps": "Steps to reproduce", "expected": "Expected behaviour",
        "actual": "Actual behaviour", "stories": "User stories are attached as sub-issues.",
        "dod_items": [
            "All acceptance criteria are met and verified",
            "Automated tests cover the new behaviour and pass",
            "Code reviewed and approved",
            "Documentation updated (user docs and CLAUDE.md when relevant)",
            "CI is green",
        ],
    },
    "fr": {
        "as_a": "En tant que", "i_want": "je veux", "so_that": "afin de", "context": "Contexte",
        "ac": "Critères d'acceptation", "given": "Étant donné", "when": "Quand", "then": "Alors",
        "measure": "Mesure du succès", "tech": "Notes techniques", "oos": "Hors périmètre",
        "dod": "Definition of Done", "estimate": "Estimation", "effort": "Effort agent",
        "review": "Revue humaine", "size": "Taille", "agent": "Agent assigné",
        "deps": "Dépendances", "blocked_by": "Bloquée par", "goal": "Objectif",
        "description": "Description", "steps": "Étapes de reproduction", "expected": "Comportement attendu",
        "actual": "Comportement constaté", "stories": "Les user stories sont rattachées en sous-issues.",
        "dod_items": [
            "Tous les critères d'acceptation sont remplis et vérifiés",
            "Des tests automatisés couvrent le nouveau comportement et passent",
            "Code relu et approuvé",
            "Documentation mise à jour (doc utilisateur et CLAUDE.md si pertinent)",
            "La CI est verte",
        ],
    },
}
DEPS_RE = re.compile(r"<!--\s*fw:depends-on\s+([#\d,\s]+?)\s*-->")
WAIT_RE = re.compile(r"<!--\s*fw:wait-days\s+(\d+(?:\.\d+)?)\s*-->")
OWNER_RE = re.compile(r"<!--\s*fw:owner\s+(\w+)\s*-->")
ESC_RE = re.compile(r"<!--\s*fw:(escalation|answer|resolved)\s+(\{.*?\})\s*-->", re.S)
ESC_KINDS = ("question", "approval", "blocked")
# Only comments from these authors can open, answer or resolve an escalation: on a public repository
# anyone can comment, and an answer drives an agent. Override with `escalations.trusted_associations`.
TRUSTED_ASSOCIATIONS = ("OWNER", "MEMBER", "COLLABORATOR")
ANSWER_RE = re.compile(r"^/answer(?:\s+(esc-[\w-]+))?(?:\s+([\s\S]*))?$")
# Version of the machine-readable contract (`fw schema`, `--json` outputs). Bump on breaking change.
CONTRACT_VERSION = 1
DEFAULT_STATUS_NAMES = {"todo", "in progress", "done"}


# --------------------------------------------------------------------------- helpers

def die(msg, code=1):
    print(f"fw: {msg}", file=sys.stderr)
    sys.exit(code)


def warn(msg):
    print(f"! {msg}", file=sys.stderr)


def run(cmd, check=True, input=None, cwd=None):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, input=input, cwd=str(cwd or ROOT))
    except FileNotFoundError:
        if check:
            die(f"command not found: {cmd[0]}")
        return subprocess.CompletedProcess(cmd, 127, "", f"{cmd[0]}: not found")
    if check and p.returncode != 0:
        die(f"command failed: {' '.join(cmd)}\n{(p.stderr or p.stdout).strip()}")
    return p


def gh(*args, check=True, input=None):
    return run(["gh", *args], check=check, input=input)


def rest(method, path, body=None, check=True):
    args = ["api", "-X", method, path]
    if body is not None:
        args += ["--input", "-"]
    p = gh(*args, check=False, input=json.dumps(body) if body is not None else None)
    if p.returncode != 0:
        if check:
            die(f"GitHub API {method} {path} failed: {(p.stderr or p.stdout).strip()}")
        return None
    return json.loads(p.stdout) if p.stdout.strip() else {}


def graphql(query, check=True, **variables):
    body = json.dumps({"query": query, "variables": variables})
    p = gh("api", "graphql", "-H", "GraphQL-Features: sub_issues", "--input", "-", check=False, input=body)
    data = None
    try:
        data = json.loads(p.stdout) if p.stdout.strip() else None
    except json.JSONDecodeError:
        pass
    errors = (data or {}).get("errors") if isinstance(data, dict) else None
    if p.returncode != 0 or errors or not data:
        if check:
            msg = "; ".join(e.get("message", "") for e in errors) if errors else (p.stderr or p.stdout).strip()
            die(f"GraphQL error: {msg}")
        return None
    return data["data"]


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def cfg():
    return load_json(CONFIG, {})


def dig(d, dotted, default=None):
    for part in dotted.split("."):
        if not isinstance(d, dict) or part not in d:
            return default
        d = d[part]
    return d


def set_dotted(d, dotted, value):
    parts = dotted.split(".")
    for part in parts[:-1]:
        d = d.setdefault(part, {})
    d[parts[-1]] = value


def gh_ctx():
    g = cfg().get("github") or {}
    if not g.get("project_id"):
        die("GitHub project not configured — run `fw github-setup` (see /fw-init).")
    return g


def today():
    return dt.date.today()


def parse_date(s):
    return dt.datetime.strptime(s, "%Y-%m-%d").date()


def size_for(hours):
    for name, cap in SIZES:
        if hours <= cap:
            return name
    return "XL"


def parse_deps(body):
    m = DEPS_RE.search(body or "")
    return [int(x) for x in re.findall(r"\d+", m.group(1))] if m else []


def parse_wait(body):
    m = WAIT_RE.search(body or "")
    return float(m.group(1)) if m else 0.0


def is_human(item):
    """Human-owned work (backlog `owner: human` → `fw:owner human` marker). The `needs-human` label alone
    is not enough: it also flags agent work paused on a decision, which keeps its agent effort."""
    m = OWNER_RE.search(item.get("body") or "")
    return bool(m and m.group(1) == "human")


def framework_version():
    f = ROOT / "framework" / "VERSION"
    return f.read_text().strip() if f.exists() else "0"


def canon_status(name):
    n = (name or "").strip().lower()
    return {"todo": "ready", "to do": "ready", "doing": "in progress", "review": "in review"}.get(n, n or "backlog")


def manifest(src_root=None):
    owned, scaffold = [], []
    for line in ((src_root or ROOT) / "framework" / "MANIFEST").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        kind, pat = line.split(None, 1)
        (owned if kind == "owned" else scaffold).append(pat)
    return owned, scaffold


def matches(path, patterns):
    return any(fnmatch.fnmatch(path, p) for p in patterns)


def repo_files(root=None):
    root = root or ROOT
    p = run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], check=False, cwd=root)
    if p.returncode == 0:
        return [line for line in p.stdout.splitlines() if line]
    out = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in (".git", "node_modules", "vendor", "__pycache__", "site")]
        out += [os.path.relpath(os.path.join(dp, f), root).replace(os.sep, "/") for f in fns]
    return out


# --------------------------------------------------------------------------- project (v2) access

FIELDS_Q = """query($id:ID!){ node(id:$id){ ... on ProjectV2 { fields(first:50){ nodes{
  ... on ProjectV2FieldCommon { id name dataType }
  ... on ProjectV2SingleSelectField { options { id name } } } } } } }"""

ITEMS_Q = """query($id:ID!,$after:String){ node(id:$id){ ... on ProjectV2 { items(first:100, after:$after){
  pageInfo{ hasNextPage endCursor }
  nodes{ id
    content{ __typename ... on Issue { id number title state body url
      milestone{ number title } parent{ number } labels(first:20){ nodes{ name } } } }
    fieldValues(first:30){ nodes{ __typename
      ... on ProjectV2ItemFieldTextValue { text field{ ... on ProjectV2FieldCommon { name } } }
      ... on ProjectV2ItemFieldNumberValue { number field{ ... on ProjectV2FieldCommon { name } } }
      ... on ProjectV2ItemFieldDateValue { date field{ ... on ProjectV2FieldCommon { name } } }
      ... on ProjectV2ItemFieldSingleSelectValue { name field{ ... on ProjectV2FieldCommon { name } } }
} } } } } } }"""

SET_Q = """mutation($p:ID!,$i:ID!,$f:ID!,$v:ProjectV2FieldValue!){
  updateProjectV2ItemFieldValue(input:{projectId:$p,itemId:$i,fieldId:$f,value:$v}){ projectV2Item{ id } } }"""

ADD_Q = """mutation($p:ID!,$c:ID!){ addProjectV2ItemById(input:{projectId:$p,contentId:$c}){ item{ id } } }"""

LINK_Q = """mutation($p:ID!,$r:ID!){ linkProjectV2ToRepository(input:{projectId:$p,repositoryId:$r}){ repository{ id } } }"""

VIEWS_Q = """query($id:ID!){ node(id:$id){ ... on ProjectV2 { url views(first:20){ nodes{ name layout } } } } }"""


def project_fields(pid):
    out = {}
    for f in graphql(FIELDS_Q, id=pid)["node"]["fields"]["nodes"]:
        if f and f.get("name"):
            out[f["name"]] = {"id": f["id"], "type": f["dataType"],
                              "options": {o["name"]: o["id"] for o in f.get("options") or []}}
    return out


def load_items(ctx):
    items, after = [], None
    while True:
        conn = graphql(ITEMS_Q, id=ctx["project_id"], after=after)["node"]["items"]
        for node in conn["nodes"]:
            c = node.get("content") or {}
            if c.get("__typename") != "Issue":
                continue
            it = {
                "item_id": node["id"], "node_id": c["id"], "number": c["number"], "title": c["title"],
                "state": c["state"], "body": c.get("body") or "", "url": c["url"],
                "milestone": (c.get("milestone") or {}).get("number"),
                "milestone_title": (c.get("milestone") or {}).get("title"),
                "parent": (c.get("parent") or {}).get("number"),
                "labels": [lbl["name"] for lbl in c["labels"]["nodes"]],
            }
            for fv in node["fieldValues"]["nodes"]:
                name = (fv.get("field") or {}).get("name")
                if name:
                    for k in ("text", "number", "date", "name"):
                        if k in fv:
                            it[name] = fv[k]
                            break
            it["deps"] = parse_deps(it["body"])
            it["wait_days"] = parse_wait(it["body"])
            it["status"] = canon_status(it.get(F_STATUS))
            items.append(it)
        if not conn["pageInfo"]["hasNextPage"]:
            return items
        after = conn["pageInfo"]["endCursor"]


def status_option(fields, wanted):
    opts = {k.lower(): v for k, v in fields[F_STATUS]["options"].items()}
    for cand in STATUS_ALIASES.get(wanted.lower(), [wanted.lower()]):
        if cand in opts:
            return opts[cand]
    die(f"status '{wanted}' not found in project (options: {', '.join(fields[F_STATUS]['options'])})")


def set_item_field(ctx, fields, item_id, name, value):
    f = fields.get(name)
    if not f:
        warn(f"project field '{name}' missing — skipped")
        return
    if name == F_STATUS:
        v = {"singleSelectOptionId": status_option(fields, str(value))}
    elif f["type"] == "SINGLE_SELECT":
        opts = {k.lower(): v for k, v in f["options"].items()}
        oid = opts.get(str(value).lower())
        if not oid:
            die(f"'{value}' is not an option of '{name}' ({', '.join(f['options'])})")
        v = {"singleSelectOptionId": oid}
    elif f["type"] == "NUMBER":
        v = {"number": float(value)}
    elif f["type"] == "DATE":
        v = {"date": str(value)}
    else:
        v = {"text": str(value)}
    graphql(SET_Q, p=ctx["project_id"], i=item_id, f=f["id"], v=v)


def ensure_item(ctx, number):
    issue = rest("GET", f"repos/{ctx['repo']}/issues/{number}")
    return graphql(ADD_Q, p=ctx["project_id"], c=issue["node_id"])["addProjectV2ItemById"]["item"]["id"]


def find_item(items, number):
    for it in items:
        if it["number"] == number:
            return it
    return None


# --------------------------------------------------------------------------- doctor

def gh_install_hint():
    if sys.platform == "darwin":
        return "brew install gh"
    if sys.platform.startswith("win"):
        return "winget install --id GitHub.cli"
    return "follow https://github.com/cli/cli/blob/trunk/docs/install_linux.md (distro packages are often outdated)"


def cmd_doctor(a):
    checks = []

    def add(cid, ok, detail, fix=None, required=True):
        checks.append({"id": cid, "ok": ok, "detail": detail, "fix": fix, "required": required})

    add("python", sys.version_info >= (3, 8), sys.version.split()[0], "Install Python 3.8 or newer")
    login = None
    if shutil.which("git"):
        name = run(["git", "config", "user.name"], check=False).stdout.strip()
        email = run(["git", "config", "user.email"], check=False).stdout.strip()
        add("git", True, run(["git", "--version"]).stdout.strip())
        add("git-identity", bool(name and email), f"{name} <{email}>" if name else "not set",
            'git config --global user.name "Your Name" && git config --global user.email "you@example.com"')
    else:
        add("git", False, "not installed", "Install git: https://git-scm.com/downloads")

    if shutil.which("gh"):
        out = run(["gh", "--version"]).stdout
        m = re.search(r"(\d+)\.(\d+)\.(\d+)", out)
        ver = tuple(int(x) for x in m.groups()) if m else (0, 0, 0)
        add("gh", ver[:2] >= MIN_GH, ".".join(map(str, ver)),
            f"Upgrade GitHub CLI to >= {MIN_GH[0]}.{MIN_GH[1]}: {gh_install_hint()}")
        authed = run(["gh", "auth", "status", "-h", "github.com"], check=False).returncode == 0
        add("gh-auth", authed, "authenticated" if authed else "not authenticated",
            "gh auth login -h github.com -s " + ",".join(REQUIRED_SCOPES))
        if authed:
            login = gh("api", "user", "--jq", ".login", check=False).stdout.strip() or None
            headers = gh("api", "-i", "user", check=False).stdout
            m = re.search(r"^x-oauth-scopes:\s*(.*)$", headers, re.I | re.M)
            if m:
                scopes = {s.strip() for s in m.group(1).split(",") if s.strip()}
                missing = [s for s in REQUIRED_SCOPES if s not in scopes]
                add("gh-scopes", not missing, ", ".join(sorted(scopes)) or "none",
                    "gh auth refresh -h github.com -s " + ",".join(missing) if missing else None)
            else:
                add("gh-scopes", None, "fine-grained token or GITHUB_TOKEN: scopes cannot be verified "
                    "(needs Issues, Projects, Contents, Pull requests, Workflows read/write)", None, required=False)
            add("github-api", gh("api", "rate_limit", check=False).returncode == 0, f"logged in as {login}",
                "Check network access to api.github.com")
        for var in ("GH_TOKEN", "GITHUB_TOKEN"):
            if os.environ.get(var):
                add(f"env-{var}", None, f"{var} is set and overrides `gh auth login` credentials", None, required=False)
    else:
        add("gh", False, "not installed", gh_install_hint())

    add("claude", bool(shutil.which("claude")), shutil.which("claude") or "not in PATH",
        "Install Claude Code: https://docs.claude.com/en/docs/claude-code", required=False)

    # Repository state, for the init skill to decide new vs existing project.
    repo = {"initialized": bool(cfg().get("initialized")), "git": False}
    if run(["git", "rev-parse", "--is-inside-work-tree"], check=False).stdout.strip() == "true":
        top = run(["git", "rev-parse", "--show-toplevel"]).stdout.strip()
        repo.update(git=True, toplevel=top, toplevel_is_root=Path(top).resolve() == ROOT,
                    branch=run(["git", "rev-parse", "--abbrev-ref", "HEAD"], check=False).stdout.strip(),
                    commits=int(run(["git", "rev-list", "--count", "HEAD"], check=False).stdout.strip() or 0),
                    remotes={})
        for line in run(["git", "remote", "-v"], check=False).stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                repo["remotes"][parts[0]] = parts[1]
    owned, scaffold = manifest()
    code = [f for f in repo_files() if not matches(f, owned + scaffold + META_FILES + [".fw/*"])]
    repo["project_files"] = len(code)
    repo["project_files_sample"] = code[:15]

    if repo["initialized"]:
        cmds = cfg().get("commands") or {}
        add("commands", bool(cmds.get("test")), ", ".join(k for k in COMMAND_KEYS if cmds.get(k)) or "none configured",
            "framework/bin/fw commands --detect --apply (or fw config set commands.test '\"…\"')", required=False)
    d = drift()
    if d is not None:
        changed = [f for k in ("modified", "added", "deleted") for f in d[k]]
        add("framework-drift", not changed, f"{len(changed)} framework-owned file(s) changed locally: "
            + ", ".join(changed[:5]) if changed else "framework-owned files match the installed version",
            "framework/bin/fw drift — move the change to the template, or restore with /fw-update", required=False)
    gh_repo = dig(cfg(), "github.repo")
    if repo["initialized"] and gh_repo and login:
        readable, ruleset = find_ruleset(gh_repo)
        add("branch-rules", bool(ruleset) if readable else None,
            "default branch protected" if ruleset else ("not protected" if readable else "cannot read rulesets"),
            "framework/bin/fw protect", required=False)

    ok = all(c["ok"] for c in checks if c["required"])
    if a.json:
        print(json.dumps({"ok": ok, "login": login, "checks": checks, "repo": repo}, indent=2))
    else:
        for c in checks:
            mark = "✔" if c["ok"] else ("!" if c["ok"] is None or not c["required"] else "✘")
            print(f"{mark} {c['id']:<14} {c['detail']}")
            if not c["ok"] and c["fix"]:
                print(f"    fix: {c['fix']}")
        print(f"\nrepository: {json.dumps(repo)}")
        print("\nREADY" if ok else "\nNOT READY — fix the ✘ items above, then re-run `fw doctor`.")
    sys.exit(0 if ok else 1)


# --------------------------------------------------------------------------- config / autonomy

def cmd_config(a):
    c = cfg()
    if a.action == "get":
        v = dig(c, a.key) if a.key else c
        print(json.dumps(v, indent=2, ensure_ascii=False) if isinstance(v, (dict, list)) else ("" if v is None else v))
        return
    if a.value is None:
        die("config set needs a value")
    try:
        value = json.loads(a.value)
    except json.JSONDecodeError:
        value = a.value
    set_dotted(c, a.key, value)
    save_json(CONFIG, c)
    print(f"{a.key} = {json.dumps(value, ensure_ascii=False)}")


def cmd_autonomy(a):
    c = cfg()
    c["autonomy"] = a.mode
    save_json(CONFIG, c)
    path = ROOT / ".claude" / "settings.local.json"
    s = load_json(path, {})
    perms = s.setdefault("permissions", {})
    if a.mode == "auto":
        perms["defaultMode"] = "bypassPermissions"
    elif perms.get("defaultMode") == "bypassPermissions":
        del perms["defaultMode"]
    save_json(path, s)
    print(f"autonomy = {a.mode}; {path.relative_to(ROOT)} updated.")
    if a.mode == "auto":
        print("Restart Claude Code for it to take effect (or launch `claude --dangerously-skip-permissions`).")


# --------------------------------------------------------------------------- github setup

def owner_node(login):
    u = rest("GET", f"users/{login}")
    return u["node_id"], ("organization" if u["type"] == "Organization" else "user")


def cmd_github_setup(a):
    if a.restore_status:
        before = load_json(LOCAL / "status-backup.json", None) or die("no .fw/local/status-backup.json")
        restore_statuses(gh_ctx(), before)
        return
    c = cfg()
    g = c.setdefault("github", {})
    login = gh("api", "user", "--jq", ".login").stdout.strip()
    name = a.repo or ROOT.name
    repo = name if "/" in name else f"{a.owner or login}/{name}"
    owner = repo.split("/")[0]

    r = rest("GET", f"repos/{repo}", check=False)
    if r is None:
        if not a.create_repo:
            die(f"repository {repo} not found (pass --create-repo to create it)")
        args = ["repo", "create", repo, f"--{a.visibility}"]
        if a.description:
            args += ["--description", a.description]
        gh(*args)
        r = rest("GET", f"repos/{repo}")
        print(f"✔ repository created: {r['html_url']}")
    else:
        print(f"✔ repository: {r['html_url']}")

    owner_id, owner_type = owner_node(owner)
    title = a.title or r["name"]
    created = False
    if a.project:
        o_type = owner_type
        proj = graphql("query($l:String!,$n:Int!){ %s(login:$l){ projectV2(number:$n){ id number url } } }" % o_type,
                       l=owner, n=int(a.project))[o_type]["projectV2"] or die(f"project {owner}/{a.project} not found")
        pid, number, url = proj["id"], proj["number"], proj["url"]
        print(f"✔ project reused (--project): {url}")
    elif g.get("project_id") and g.get("repo") == repo and not a.new_project:
        pid, number, url = g["project_id"], g["project_number"], g["project_url"]
        print(f"✔ project reused: {url}")
    else:
        tpl = a.template or dig(c, "framework.template_project")
        if tpl:
            t_owner, t_num = tpl.rsplit("/", 1)
            _, t_type = owner_node(t_owner)
            src = graphql("query($l:String!,$n:Int!){ %s(login:$l){ projectV2(number:$n){ id } } }" % t_type,
                          l=t_owner, n=int(t_num))[t_type]["projectV2"]
            proj = graphql("""mutation($p:ID!,$o:ID!,$t:String!){ copyProjectV2(input:{projectId:$p,ownerId:$o,
                title:$t,includeDraftIssues:false}){ projectV2{ id number url } } }""",
                           p=src["id"], o=owner_id, t=title)["copyProjectV2"]["projectV2"]
            print(f"✔ project copied from template {tpl}: {proj['url']}")
        else:
            proj = graphql("""mutation($o:ID!,$t:String!,$r:ID!){ createProjectV2(input:{ownerId:$o,title:$t,
                repositoryId:$r}){ projectV2{ id number url } } }""",
                           o=owner_id, t=title, r=r["node_id"])["createProjectV2"]["projectV2"]
            created = True
            print(f"✔ project created: {proj['url']}")
        pid, number, url = proj["id"], proj["number"], proj["url"]

    # Save right away: a failure in the steps below must not orphan the project (a re-run reuses it).
    g.update(owner=owner, owner_type=owner_type, repo=repo, repo_id=r["node_id"], project_id=pid,
             project_number=number, project_url=url, default_branch=r.get("default_branch") or "main")
    save_json(CONFIG, c)

    graphql(LINK_Q, check=False, p=pid, r=r["node_id"])
    print(f"✔ project linked to {repo}")

    fields = project_fields(pid)
    for fname, dtype, opts in PROJECT_FIELDS:
        if fname in fields:
            continue
        graphql("""mutation($p:ID!,$n:String!,$t:ProjectV2CustomFieldType!,$o:[ProjectV2SingleSelectFieldOptionInput!]){
            createProjectV2Field(input:{projectId:$p,name:$n,dataType:$t,singleSelectOptions:$o}){
            projectV2Field{ ... on ProjectV2FieldCommon { id } } } }""",
                p=pid, n=fname, t=dtype,
                o=[{"name": n, "color": col, "description": ""} for n, col in opts] if opts else None)
        print(f"✔ field created: {fname}")

    current = {n.lower() for n in fields[F_STATUS]["options"]}
    if created or a.fix_status or current == DEFAULT_STATUS_NAMES:
        # Replacing the options drops every item's Status value: remember them and restore after.
        before = [] if created else load_items({"project_id": pid, "repo": repo})
        if before:
            backup = LOCAL / "status-backup.json"
            save_json(backup, before)
            print(f"✔ statuses backed up to {backup.relative_to(ROOT)} "
                  "(if the restore fails: `fw github-setup --restore-status`)")
        wanted = [{"name": n, "color": col, "description": d} for n, col, d in STATUS_OPTIONS]
        ok = graphql("""mutation($f:ID!,$o:[ProjectV2SingleSelectFieldOptionInput!]){
            updateProjectV2Field(input:{fieldId:$f,singleSelectOptions:$o}){
            projectV2Field{ ... on ProjectV2SingleSelectField { id } } } }""",
                     check=False, f=fields[F_STATUS]["id"], o=wanted)
        if ok:
            print("✔ status columns: " + " → ".join(n for n, _, _ in STATUS_OPTIONS))
            restore_statuses({"project_id": pid, "repo": repo}, before)
        else:
            warn("could not customise Status options through the API; defaults (Todo / In Progress / Done) are "
                 "kept and mapped automatically. Optional: add Backlog, Ready and In review in the project settings.")

    for lname, color, desc in LABELS:
        gh("label", "create", lname, "--color", color, "--description", desc, "--force", "-R", repo, check=False)
    print("✔ labels: " + ", ".join(n for n, _, _ in LABELS))

    print(f"✔ saved to {CONFIG.relative_to(ROOT)}\n")
    views_report(pid)


def restore_statuses(ctx, before):
    """Re-apply statuses after the Status options were replaced; Todo splits into Ready/Backlog by dependencies."""
    if not before:
        return
    fields = project_fields(ctx["project_id"])
    closed = {i["number"] for i in before if i["state"] == "CLOSED" or i["status"] == "done"}
    for i in before:
        st = "done" if i["number"] in closed else i["status"]
        if st in ("ready", "backlog") and i.get(F_TYPE) != "Epic":
            st = "ready" if all(d in closed for d in i["deps"]) else "backlog"
        elif st in ("ready", "backlog"):
            st = "backlog"
        set_item_field(ctx, fields, i["item_id"], F_STATUS, st)
    print(f"✔ status restored on {len(before)} item(s)")


def views_report(pid):
    d = graphql(VIEWS_Q, id=pid)["node"]
    layouts = {v["layout"] for v in d["views"]["nodes"]}
    missing = [(lay, label) for lay, label in (("BOARD_LAYOUT", "Board"), ("ROADMAP_LAYOUT", "Roadmap"))
               if lay not in layouts]
    if not missing:
        print("✔ views: Board and Roadmap present")
        return True
    print("! GitHub's API cannot create project views — one-time manual step (≈1 minute):")
    print(f"  open {d['url']}")
    for lay, label in missing:
        if label == "Board":
            print("  • '+ New view' → Board → Column by: Status. Rename it 'Kanban'.")
        else:
            print("  • '+ New view' → Roadmap → Date fields: 'Start date' / 'Target date'; "
                  "Group by: Milestone (or Item type). Rename it 'Roadmap'.")
    print("  then re-run `fw views-check`.")
    return False


RULESET_NAME = "fw: protect the default branch"


def api_try(method, path, body=None):
    """Like rest() but returns (ok, data | error text) instead of dying."""
    args = ["api", "-X", method, path] + (["--input", "-"] if body is not None else [])
    p = gh(*args, check=False, input=json.dumps(body) if body is not None else None)
    if p.returncode != 0:
        return False, (p.stderr or p.stdout).strip()
    return True, json.loads(p.stdout) if p.stdout.strip() else {}


def protection_ruleset(checks, approvals):
    rules = [
        {"type": "deletion"},
        {"type": "non_fast_forward"},
        {"type": "pull_request", "parameters": {
            "required_approving_review_count": approvals, "dismiss_stale_reviews_on_push": False,
            "require_code_owner_review": False, "require_last_push_approval": False,
            "required_review_thread_resolution": False}},
    ]
    if checks:
        rules.append({"type": "required_status_checks", "parameters": {
            "strict_required_status_checks_policy": False,
            "required_status_checks": [{"context": c} for c in checks]}})
    return {"name": RULESET_NAME, "target": "branch", "enforcement": "active", "bypass_actors": [],
            "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}}, "rules": rules}


def find_ruleset(repo):
    ok, data = api_try("GET", f"repos/{repo}/rulesets")
    if not ok:
        return False, data
    return True, next((r for r in data if r.get("name") == RULESET_NAME), None)


def cmd_protect(a):
    c = cfg()
    repo = a.repo or dig(c, "github.repo")
    if not repo:
        die("no repository — pass --repo owner/name or run `fw github-setup` first")
    ok, current = find_ruleset(repo)
    if a.check:
        if not ok:
            print(f"! cannot read the rulesets of {repo}: {current}")
            sys.exit(1)
        print(f"✔ {repo}: default branch protected (ruleset #{current['id']})" if current
              else f"✘ {repo}: default branch not protected — run `framework/bin/fw protect`")
        sys.exit(0 if current else 1)
    prot = (dig(c, "github.protection", {}) or {}) if repo == dig(c, "github.repo") else {}
    checks = prot.get("checks", []) if a.checks is None else [x.strip() for x in a.checks.split(",") if x.strip()]
    approvals = prot.get("approvals", 0) if a.approvals is None else a.approvals
    body = protection_ruleset(checks, approvals)
    if ok and current:
        ok, res = api_try("PUT", f"repos/{repo}/rulesets/{current['id']}", body)
    elif ok:
        ok, res = api_try("POST", f"repos/{repo}/rulesets", body)
    else:
        res = current
    if not ok:
        plan = re.search(r"upgrade|GitHub Pro|not available|HTTP 403", res, re.I)
        print(f"✘ could not protect the default branch of {repo}: {res}")
        if plan:
            print("  Branch rules are not available for private repositories on GitHub Free (and need admin rights).\n"
                  "  The local guard hook still blocks direct pushes to main, but nothing enforces it on GitHub.\n"
                  "  Options: GitHub Pro/Team, a public repository, or accept the risk.")
        sys.exit(4)
    if repo == dig(c, "github.repo"):  # `--repo` on another repository leaves this config alone
        c["github"]["protection"] = {"ruleset_id": res.get("id"), "checks": checks, "approvals": approvals}
        save_json(CONFIG, c)
    print(f"✔ {repo}: default branch protected — pull request required ({approvals} approval(s)), "
          f"no force push, no deletion, no bypass"
          + (f", required checks: {', '.join(checks)}" if checks else ", no required checks yet"))


def cmd_views_check(a):
    sys.exit(0 if views_report(gh_ctx()["project_id"]) else 1)


def cmd_import_issues(a):
    ctx = gh_ctx()
    fields = project_fields(ctx["project_id"])
    known = {it["number"] for it in load_items(ctx)}
    page, added = 1, 0
    while True:
        batch = rest("GET", f"repos/{ctx['repo']}/issues?state=open&per_page=100&page={page}")
        if not batch:
            break
        for issue in batch:
            if "pull_request" in issue or issue["number"] in known:
                continue
            labels = {lbl["name"].lower() for lbl in issue["labels"]}
            itype = "Epic" if "epic" in labels else "Bug" if labels & {"bug", "defect"} else \
                "Story" if "story" in labels else "Task"
            item = graphql(ADD_Q, p=ctx["project_id"], c=issue["node_id"])["addProjectV2ItemById"]["item"]["id"]
            set_item_field(ctx, fields, item, F_TYPE, itype)
            set_item_field(ctx, fields, item, F_STATUS, "backlog")
            added += 1
            print(f"+ #{issue['number']} [{itype}] {issue['title']}")
        page += 1
    print(f"{added} issue(s) imported. Estimate them with /fw-plan before scheduling.")


# --------------------------------------------------------------------------- backlog

def as_list(v):
    return v if isinstance(v, list) else ([v] if v else [])


def ref_number(ref, issues):
    """'#12' -> 12, 'US-3' -> number recorded in state (None if not created yet)."""
    if isinstance(ref, int):
        return ref
    if isinstance(ref, str) and ref.startswith("#") and ref[1:].isdigit():
        return int(ref[1:])
    return (issues.get(ref) or {}).get("number")


def validate_backlog(b, state):
    errors, warns = [], []
    done = state.get("issues", {})
    milestones = {m.get("key") for m in b.get("milestones", [])} | set(state.get("milestones", {}))
    epics = {e.get("key"): e for e in b.get("epics", [])}
    stories = {s.get("key"): s for s in b.get("stories", [])}
    agents = {p.stem for p in (ROOT / ".claude" / "agents").glob("*.md")}

    def key_check(obj, kind, registry):
        k = obj.get("key")
        if not k:
            errors.append(f"{kind} without 'key': {obj.get('title', '?')}")
        elif k in registry and isinstance(registry[k], dict) and registry[k].get("title") != obj.get("title"):
            errors.append(f"{k}: key already used by #{registry[k]['number']} '{registry[k].get('title')}' — pick a new key")
        elif k in registry:
            warns.append(f"{k}: already created on GitHub — will be skipped")
        return k

    for m in b.get("milestones", []):
        key_check(m, "milestone", state.get("milestones", {}))
        if not m.get("title"):
            errors.append(f"milestone {m.get('key')}: missing title")
    for e in b.get("epics", []):
        k = key_check(e, "epic", done)
        for f in ("title", "goal"):
            if not e.get(f):
                errors.append(f"{k}: epic missing '{f}'")
        if e.get("milestone") and e["milestone"] not in milestones:
            errors.append(f"{k}: unknown milestone '{e['milestone']}'")
        if e.get("priority", "Must") not in PRIORITIES:
            errors.append(f"{k}: priority must be one of {PRIORITIES}")

    seen = set()
    for s in b.get("stories", []):
        k = key_check(s, "story", done)
        if k in seen:
            errors.append(f"{k}: duplicate key")
        seen.add(k)
        t = s.get("type", "Story")
        if t not in WORK_TYPES:
            errors.append(f"{k}: type must be one of {WORK_TYPES}")
        title = s.get("title", "")
        if not title:
            errors.append(f"{k}: missing title")
        elif len(title) > 90:
            warns.append(f"{k}: title longer than 90 characters")
        acs = as_list(s.get("acceptance_criteria"))
        if t == "Story":
            for f in ("persona", "want", "benefit", "measure"):
                if not s.get(f):
                    errors.append(f"{k}: story missing '{f}'")
            if len(acs) < 2:
                errors.append(f"{k}: a story needs at least 2 acceptance criteria")
            if not s.get("epic"):
                warns.append(f"{k}: story not attached to an epic")
        else:
            if not s.get("description"):
                errors.append(f"{k}: {t.lower()} missing 'description'")
            if not acs:
                errors.append(f"{k}: needs at least 1 acceptance criterion")
        for ac in acs:
            if isinstance(ac, dict) and not all(ac.get(x) for x in ("given", "when", "then")):
                errors.append(f"{k}: acceptance criterion objects need given/when/then")
        ep = s.get("epic")
        if ep and ep not in epics and ref_number(ep, done) is None:
            errors.append(f"{k}: unknown epic '{ep}'")
        if s.get("milestone") and s["milestone"] not in milestones:
            errors.append(f"{k}: unknown milestone '{s['milestone']}'")
        if s.get("priority", "Should") not in PRIORITIES:
            errors.append(f"{k}: priority must be one of {PRIORITIES}")
        try:
            eff = float(s.get("agent_hours", 0))
            rev = float(s.get("review_hours", 0))
        except (TypeError, ValueError):
            errors.append(f"{k}: agent_hours / review_hours must be numbers")
            eff = rev = 0
        human = s.get("owner") == "human"
        if s.get("owner") not in (None, "agent", "human"):
            errors.append(f"{k}: owner must be 'agent' or 'human'")
        if eff < 0 or (eff == 0 and not human):
            errors.append(f"{k}: agent_hours must be > 0 (or 0 with \"owner\": \"human\")")
        if human and eff + rev <= 0:
            errors.append(f"{k}: a human task needs review_hours > 0 (the user's own time)")
        if human and s.get("agent"):
            warns.append(f"{k}: human task with an agent — the agent is ignored")
        try:
            if float(s.get("wait_days", 0)) < 0:
                errors.append(f"{k}: wait_days must be >= 0")
        except (TypeError, ValueError):
            errors.append(f"{k}: wait_days must be a number")
        if rev < 0:
            errors.append(f"{k}: review_hours must be >= 0")
        expected = size_for(eff + rev)
        if expected == "XL" or s.get("size") == "XL":
            errors.append(f"{k}: XL ({eff + rev:g} h) is too big — split it into smaller stories")
        elif s.get("size") and s["size"] != expected:
            warns.append(f"{k}: size {s['size']} but {eff + rev:g} h suggests {expected}")
        if s.get("agent") and agents and s["agent"] not in agents and not human:
            warns.append(f"{k}: agent '{s['agent']}' has no file in .claude/agents/")
        for d in as_list(s.get("depends_on")):
            if d not in stories and ref_number(d, done) is None:
                errors.append(f"{k}: unknown dependency '{d}'")

    # a dependency on a later milestone delays this one: usually a misplaced item
    ms_rank = {m.get("key"): n for n, m in enumerate(b.get("milestones", []))}

    def ms_of(st):
        return st.get("milestone") or (epics.get(st.get("epic")) or {}).get("milestone")

    for k, st in stories.items():
        mine = ms_rank.get(ms_of(st))
        for d in as_list(st.get("depends_on")):
            theirs = ms_rank.get(ms_of(stories.get(d) or {}))
            if mine is not None and theirs is not None and theirs > mine:
                warns.append(f"{k} ({ms_of(st)}) depends on {d} from a later milestone ({ms_of(stories[d])}) "
                             f"— move {d} earlier or drop the dependency")

    # cycle detection among the stories of this file
    graph = {k: [d for d in as_list(s.get("depends_on")) if d in stories] for k, s in stories.items()}
    color = {}

    def visit(n, path):
        color[n] = 1
        for m in graph.get(n, []):
            if color.get(m) == 1:
                errors.append("dependency cycle: " + " -> ".join(path + [m]))
            elif not color.get(m):
                visit(m, path + [m])
        color[n] = 2

    for n in graph:
        if not color.get(n):
            visit(n, [n])
    return errors, warns


def topo_stories(stories):
    by_key = {s["key"]: s for s in stories}
    order, seen = [], set()

    def visit(k):
        if k in seen or k not in by_key:
            return
        seen.add(k)
        for d in as_list(by_key[k].get("depends_on")):
            visit(d)
        order.append(by_key[k])

    for s in stories:
        visit(s["key"])
    return order


def headings(b):
    lang = b.get("language") or cfg().get("issue_language") or "en"
    h = dict(HEADINGS["en"])
    h.update(HEADINGS.get(lang, {}))
    h.update(b.get("headings") or {})
    return h


def render_ac(ac, h):
    if isinstance(ac, dict):
        return f"- [ ] **{h['given']}** {ac['given']}, **{h['when']}** {ac['when']}, **{h['then']}** {ac['then']}"
    return f"- [ ] {ac}"


def render_story(s, h, dep_numbers):
    t = s.get("type", "Story")
    out = [f"<!-- fw:key {s['key']} -->"]
    if t == "Story":
        out += [f"**{h['as_a']}** {s['persona']}, **{h['i_want']}** {s['want']}, **{h['so_that']}** {s['benefit']}.", ""]
        if s.get("context"):
            out += [f"## {h['context']}", s["context"], ""]
    else:
        out += [f"## {h['description']}", s["description"], ""]
        if t == "Bug":
            for f in ("steps", "expected", "actual"):
                if s.get(f):
                    out += [f"## {h[f]}", s[f] if isinstance(s[f], str) else "\n".join(f"1. {x}" for x in s[f]), ""]
    out += [f"## {h['ac']}"] + [render_ac(ac, h) for ac in as_list(s.get("acceptance_criteria"))] + [""]
    if s.get("measure"):
        out += [f"## {h['measure']}", s["measure"], ""]
    if s.get("technical_notes"):
        out += [f"## {h['tech']}", s["technical_notes"], ""]
    if s.get("out_of_scope"):
        out += [f"## {h['oos']}"] + [f"- {x}" for x in as_list(s["out_of_scope"])] + [""]
    out += [f"## {h['dod']}"] + [f"- [ ] {x}" for x in h["dod_items"] + as_list(s.get("dod_extra"))] + [""]
    eff, rev = float(s["agent_hours"]), float(s.get("review_hours", 0))
    out += [f"## {h['estimate']}", f"| {h['effort']} | {h['review']} | {h['size']} | {h['agent']} |",
            "|---|---|---|---|",
            f"| {eff:g} h | {rev:g} h | {s.get('size') or size_for(eff + rev)} | "
            f"{'human' if s.get('owner') == 'human' else s.get('agent') or '—'} |", ""]
    if s.get("owner") == "human":
        out += ["<!-- fw:owner human -->"]
    if float(s.get("wait_days", 0) or 0) > 0:
        out += [f"<!-- fw:wait-days {float(s['wait_days']):g} -->"]
    if dep_numbers:
        out += [f"## {h['deps']}"] + [f"- {h['blocked_by']} #{n}" for n in dep_numbers] + [""]
        out += [f"<!-- fw:depends-on {','.join(str(n) for n in dep_numbers)} -->"]
    return "\n".join(out).strip() + "\n"


def render_epic(e, h):
    out = [f"<!-- fw:key {e['key']} -->", f"## {h['goal']}", e["goal"], ""]
    if e.get("description"):
        out += [f"## {h['description']}", e["description"], ""]
    if e.get("measure"):
        out += [f"## {h['measure']}", e["measure"], ""]
    if e.get("out_of_scope"):
        out += [f"## {h['oos']}"] + [f"- {x}" for x in as_list(e["out_of_scope"])] + [""]
    out += [f"_{h['stories']}_"]
    return "\n".join(out).strip() + "\n"


def cmd_backlog_validate(a):
    b = load_json(a.file, None) or die(f"cannot read {a.file}")
    errors, warns = validate_backlog(b, load_json(STATE, {}))
    for w in warns:
        print(f"! {w}")
    for e in errors:
        print(f"✘ {e}")
    n = len(b.get("stories", []))
    hours = sum(float(s.get("agent_hours", 0)) + float(s.get("review_hours", 0)) for s in b.get("stories", []))
    print(f"\n{len(b.get('milestones', []))} milestone(s), {len(b.get('epics', []))} epic(s), {n} item(s), "
          f"{hours:g} h estimated — {len(errors)} error(s), {len(warns)} warning(s)")
    sys.exit(1 if errors else 0)


def cmd_backlog_apply(a):
    b = load_json(a.file, None) or die(f"cannot read {a.file}")
    state = load_json(STATE, {})
    errors, _ = validate_backlog(b, state)
    if errors:
        die("backlog has errors — run `fw backlog-validate` first")
    h = headings(b)
    issues = state.setdefault("issues", {})
    ms_state = state.setdefault("milestones", {})
    epics = {e["key"]: e for e in b.get("epics", [])}

    if a.dry_run:
        for e in b.get("epics", []):
            print(f"=== EPIC {e['key']}: {e['title']}\n{render_epic(e, h)}")
        fake = {s["key"]: i + 1000 for i, s in enumerate(b.get("stories", []))}
        for s in topo_stories(b.get("stories", [])):
            deps = [ref_number(d, issues) or fake.get(d) for d in as_list(s.get("depends_on"))]
            print(f"=== {s.get('type', 'Story').upper()} {s['key']}: {s['title']}\n{render_story(s, h, deps)}")
        return

    ctx = gh_ctx()
    repo = ctx["repo"]
    fields = project_fields(ctx["project_id"])
    existing_ms = {m["title"]: m["number"] for m in rest("GET", f"repos/{repo}/milestones?state=all&per_page=100")}

    def save():
        save_json(STATE, state)

    for m in b.get("milestones", []):
        if m["key"] in ms_state:
            continue
        num = existing_ms.get(m["title"]) or rest("POST", f"repos/{repo}/milestones", {
            "title": m["title"], "description": m.get("description", "")})["number"]
        ms_state[m["key"]] = num
        save()
        print(f"✔ milestone {m['key']} → {m['title']} (#{num})")

    def milestone_number(ref):
        if ref is None:
            return None
        if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
            return int(ref)
        return ms_state.get(ref) or existing_ms.get(ref)

    def create(obj, body, labels, itype, milestone, extra_fields, status):
        payload = {"title": obj["title"], "body": body, "labels": labels}
        if milestone:
            payload["milestone"] = milestone
        issue = rest("POST", f"repos/{repo}/issues", payload)
        item = graphql(ADD_Q, p=ctx["project_id"], c=issue["node_id"])["addProjectV2ItemById"]["item"]["id"]
        set_item_field(ctx, fields, item, F_TYPE, itype)
        set_item_field(ctx, fields, item, F_STATUS, status)
        for fname, val in extra_fields.items():
            if val not in (None, ""):
                set_item_field(ctx, fields, item, fname, val)
        issues[obj["key"]] = {"number": issue["number"], "id": issue["id"], "node_id": issue["node_id"],
                              "item_id": item, "type": itype, "title": obj["title"]}
        save()
        print(f"✔ {itype:<5} {obj['key']:<8} #{issue['number']} {obj['title']}")
        return issue

    for e in b.get("epics", []):
        if e["key"] in issues:
            continue
        create(e, render_epic(e, h), ["epic"] + as_list(e.get("labels")), "Epic",
               milestone_number(e.get("milestone")), {F_PRIO: e.get("priority", "Must")}, "backlog")

    dep_api_ok = True
    for s in topo_stories(b.get("stories", [])):
        if s["key"] in issues:
            continue
        t = s.get("type", "Story")
        deps = [ref_number(d, issues) for d in as_list(s.get("depends_on"))]
        deps = [d for d in deps if d]
        epic = epics.get(s.get("epic")) or {}
        ms = milestone_number(s.get("milestone") or epic.get("milestone"))
        eff, rev = float(s["agent_hours"]), float(s.get("review_hours", 0))
        labels = [t.lower()] + as_list(s.get("labels"))
        if s.get("owner") == "human" and "needs-human" not in labels:
            labels.append("needs-human")
        issue = create(s, render_story(s, h, deps), labels, t, ms, {
            F_PRIO: s.get("priority", "Should"), F_SIZE: s.get("size") or size_for(eff + rev),
            F_EFFORT: eff, F_REVIEW: rev, F_AGENT: None if s.get("owner") == "human" else s.get("agent")},
            "backlog" if deps else "ready")
        parent = ref_number(s.get("epic"), issues) if s.get("epic") else None
        if parent:
            if rest("POST", f"repos/{repo}/issues/{parent}/sub_issues", {"sub_issue_id": issue["id"]},
                    check=False) is None:
                warn(f"could not attach #{issue['number']} as sub-issue of #{parent}")
        for d in deps if dep_api_ok else []:
            blocker = rest("GET", f"repos/{repo}/issues/{d}", check=False)
            if not blocker or rest("POST", f"repos/{repo}/issues/{issue['number']}/dependencies/blocked_by",
                                   {"issue_id": blocker["id"]}, check=False) is None:
                dep_api_ok = False
                warn("native issue dependencies unavailable — relying on the fw:depends-on markers")
    print("\nDone. Next: `fw schedule` to compute the roadmap.")


# --------------------------------------------------------------------------- scheduling

def align(d, workdays):
    while d.isoweekday() not in workdays:
        d += dt.timedelta(days=1)
    return d


def add_workdays(base, n, workdays):
    d = align(base, workdays)
    while n > 0:
        d += dt.timedelta(days=1)
        if d.isoweekday() in workdays:
            n -= 1
    return d


def effort(it):
    return agent_effort(it) + float(it.get(F_REVIEW) or 0)


def agent_effort(it):
    e = it.get(F_EFFORT)
    return float(e) if e is not None else DEFAULT_EFFORT


def compute_schedule(items, capacity, start=None):
    hpd = float(capacity.get("hours_per_day", 6))
    pipelined = bool(capacity.get("pipeline"))  # one implementer; review runs while it starts the next item
    lanes = 1 if pipelined else max(1, int(capacity.get("parallel_lanes", 1)))
    workdays = set(capacity.get("workdays", [1, 2, 3, 4, 5]))
    base = align(max(start or today(), today()), workdays)
    work = [i for i in items if i.get(F_TYPE) != "Epic" and i.get(F_PRIO) != "Won't"]
    closed = {i["number"] for i in items if i["state"] == "CLOSED" or i["status"] == "done"}
    pending = {i["number"]: i for i in work if i["number"] not in closed}
    deps = {n: [d for d in i["deps"] if d in pending and d != n] for n, i in pending.items()}
    rdeps = defaultdict(list)
    for n, ds in deps.items():
        for d in ds:
            rdeps[d].append(n)

    by_milestone = capacity.get("order", "milestone") == "milestone"

    def key(n):
        i = pending[n]
        ms = (i.get("milestone") or math.inf) if by_milestone else 0
        return (0 if i["status"] in ("in progress", "in review") else 1, ms, PRIO_RANK.get(i.get(F_PRIO), 1), n)

    indeg = {n: len(ds) for n, ds in deps.items()}
    heap = [(key(n), n) for n, d in indeg.items() if d == 0]
    heapq.heapify(heap)
    order = []
    while heap:
        _, n = heapq.heappop(heap)
        order.append(n)
        for m in rdeps[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                heapq.heappush(heap, (key(m), m))
    cyclic = [n for n in pending if n not in order]
    order += sorted(cyclic, key=key)

    # Agents share `lanes`; the human works on a lane of their own. Waiting time (store review,
    # account approval) is calendar time after the work, on nobody's lane.
    cursor, human_cursor, ends, plan = [0.0] * lanes, 0.0, {}, {}
    for n in order:
        it = pending[n]
        earliest = max([ends.get(d, 0.0) for d in deps[n]] or [0.0])
        if is_human(it):
            s = max(human_cursor, earliest)
            e = human_cursor = s + effort(it)
        else:
            lane = min(range(lanes), key=lambda k: max(cursor[k], earliest))
            s = max(cursor[lane], earliest)
            e = s + effort(it)
            cursor[lane] = s + agent_effort(it) if pipelined else e
        ends[n] = e + float(it.get("wait_days") or 0) * hpd
        e = ends[n]
        plan[n] = (add_workdays(base, int(s // hpd), workdays),
                   add_workdays(base, int(max(e - 1e-6, s) // hpd), workdays))

    # epics span their children (closed children keep their recorded dates)
    for ep in (i for i in items if i.get(F_TYPE) == "Epic"):
        spans = []
        for c in (i for i in items if i.get("parent") == ep["number"]):
            if c["number"] in plan:
                spans.append(plan[c["number"]])
            elif c.get(F_START) and c.get(F_TARGET):
                spans.append((parse_date(c[F_START]), parse_date(c[F_TARGET])))
        if spans:
            plan[ep["number"]] = (min(s for s, _ in spans), max(e for _, e in spans))
    missing = [n for n in pending if pending[n].get(F_EFFORT) is None]
    return plan, cyclic, missing


def must_dates(plan, by_num):
    out = {}
    for n, (_, e) in plan.items():
        i = by_num[n]
        if i.get("milestone") and i.get(F_TYPE) != "Epic" and i.get(F_PRIO) == "Must":
            out[i["milestone"]] = max(out.get(i["milestone"], dt.date.min), e)
    return out


def cmd_schedule(a):
    c = cfg()
    ctx = gh_ctx()
    items = load_items(ctx)
    start = parse_date(a.start) if a.start else (parse_date(c["capacity"]["start_date"])
                                                 if dig(c, "capacity.start_date") else None)
    capacity = dict(c.get("capacity", {}), pipeline=bool(dig(c, "pipeline.enabled")))
    plan, cyclic, missing = compute_schedule(items, capacity, start)
    by_num = {i["number"]: i for i in items}
    if cyclic:
        warn("dependency cycle between: " + ", ".join(f"#{n}" for n in cyclic))
    if missing:
        warn(f"no estimate for {', '.join(f'#{n}' for n in missing)} — assumed {DEFAULT_EFFORT:g} h each")

    rows = sorted(plan.items(), key=lambda kv: (kv[1][0], kv[0]))
    print(f"{'#':>5}  {'type':<5} {'prio':<6} {'h':>5}  {'start':<10}  {'target':<10}  title")
    for n, (s, e) in rows:
        i = by_num[n]
        hrs = "" if i.get(F_TYPE) == "Epic" else f"{effort(i):g}"
        print(f"{n:>5}  {(i.get(F_TYPE) or '?'):<5} {(i.get(F_PRIO) or '-'):<6} {hrs:>5}  {s}  {e}  {i['title'][:60]}")
    ends = [e for _, (_, e) in rows]
    if ends:
        print(f"\nprojected end: {max(ends)}")

    ms_end = defaultdict(lambda: dt.date.min)
    for n, (_, e) in plan.items():
        if by_num[n].get("milestone"):
            ms_end[by_num[n]["milestone"]] = max(ms_end[by_num[n]["milestone"]], e)
    for i in items:
        if i.get("milestone") and i.get(F_TARGET) and i["number"] not in plan:
            ms_end[i["milestone"]] = max(ms_end[i["milestone"]], parse_date(i[F_TARGET]))
    titles = {i["milestone"]: i["milestone_title"] for i in items if i.get("milestone")}
    must_end = must_dates(plan, by_num)
    for m, e in sorted(ms_end.items(), key=lambda kv: kv[1]):
        extra = f" (Musts done by {must_end[m]})" if m in must_end and must_end[m] != e else ""
        print(f"milestone {titles.get(m)}: {e}{extra}")

    if a.apply:
        fields = project_fields(ctx["project_id"])
        changed = 0
        for n, (s, e) in plan.items():
            i = by_num[n]
            for fname, val in ((F_START, s.isoformat()), (F_TARGET, e.isoformat())):
                if i.get(fname) != val:
                    set_item_field(ctx, fields, i["item_id"], fname, val)
                    changed += 1
        for m, e in ms_end.items():
            rest("PATCH", f"repos/{ctx['repo']}/milestones/{m}", {"due_on": f"{e.isoformat()}T23:59:59Z"}, check=False)
        print(f"\n✔ roadmap applied ({changed} date field(s) updated, {len(ms_end)} milestone due date(s))")

    if a.markdown:
        lines = ["# Roadmap", "", f"_Generated by `fw schedule` on {today()} — source of truth: "
                 f"[GitHub project]({ctx['project_url']})._", ""]
        groups = defaultdict(list)
        for n, (s, e) in rows:
            groups[by_num[n].get("milestone_title") or "—"].append((n, s, e))
        for title, entries in sorted(groups.items(), key=lambda kv: min(x[1] for x in kv[1])):
            ms_num = by_num[entries[0][0]].get("milestone")
            lines += [f"## {title}", ""]
            if ms_num in must_end:
                lines += [f"Musts done by **{must_end[ms_num]}** · everything by **{max(x[2] for x in entries)}**", ""]
            lines += ["| # | Type | Priority | Effort (h) | Start | Target | Title |",
                      "|---|---|---|---|---|---|---|"]
            for n, s, e in entries:
                i = by_num[n]
                hrs = "" if i.get(F_TYPE) == "Epic" else f"{effort(i):g}"
                lines.append(f"| #{n} | {i.get(F_TYPE) or ''} | {i.get(F_PRIO) or ''} | {hrs} | {s} | {e} | "
                             f"{i['title'].replace('|', '/')} |")
            lines.append("")
        Path(a.markdown).parent.mkdir(parents=True, exist_ok=True)
        Path(a.markdown).write_text("\n".join(lines), encoding="utf-8")
        print(f"✔ wrote {a.markdown}")


# --------------------------------------------------------------------------- work flow

def ready_items(items):
    closed = {i["number"] for i in items if i["state"] == "CLOSED" or i["status"] == "done"}
    known = {i["number"] for i in items}
    out = []
    for i in items:
        if i["state"] != "OPEN" or i.get(F_TYPE) == "Epic" or i["status"] not in ("backlog", "ready"):
            continue
        if {"needs-human", "blocked"} & set(i["labels"]) or i.get(F_PRIO) == "Won't":
            continue
        if all(d in closed or d not in known for d in i["deps"]):
            out.append(i)
    return sorted(out, key=lambda i: ("hotfix" not in i["labels"], PRIO_RANK.get(i.get(F_PRIO), 1),
                                      i.get(F_START) or "9999", i["number"]))


def cmd_next(a):
    items = ready_items(load_items(gh_ctx()))[: a.limit]
    if a.json:
        print(json.dumps([{k: i.get(k) for k in ("number", "title", "url", F_TYPE, F_PRIO, F_SIZE, F_EFFORT,
                                                 F_AGENT, "milestone_title", "parent")} for i in items],
                         indent=2, ensure_ascii=False))
        return
    if not items:
        print("Nothing ready. (Everything done, in progress, blocked or waiting on dependencies.)")
    for i in items:
        print(f"#{i['number']:<5} {i.get(F_PRIO) or '-':<6} {i.get(F_SIZE) or '-':<3} "
              f"{i.get(F_EFFORT) or '?':>4}h  {i.get(F_AGENT) or '-':<22} {i['title']}")


def get_item(ctx, number):
    items = load_items(ctx)
    it = find_item(items, number)
    if not it:
        ensure_item(ctx, number)
        items = load_items(ctx)
        it = find_item(items, number)
    return items, it


def cmd_set_status(a):
    ctx = gh_ctx()
    _, it = get_item(ctx, a.issue)
    set_item_field(ctx, project_fields(ctx["project_id"]), it["item_id"], F_STATUS, a.status)
    print(f"#{a.issue} → {a.status}")


def cmd_set_field(a):
    ctx = gh_ctx()
    _, it = get_item(ctx, a.issue)
    set_item_field(ctx, project_fields(ctx["project_id"]), it["item_id"], a.field, a.value)
    print(f"#{a.issue} {a.field} = {a.value}")


def timers():
    return load_json(LOCAL / "timers.json", {})


def log_event(issue, event, when=None):
    """Append start / review / pause to the item's local timeline (.fw/local/timers.json)."""
    t = timers()
    cur = t.get(str(issue))
    if cur is None and event != "start":
        return  # not started on this machine: nothing to measure
    events = timeline(cur)
    events.append([event, (when or dt.datetime.now()).isoformat(timespec="seconds")])
    t[str(issue)] = {"events": events}
    save_json(LOCAL / "timers.json", t)


def timeline(entry):
    """Events of a timer entry; the pre-0.7 format was a bare start timestamp."""
    if entry is None:
        return []
    if isinstance(entry, str):
        return [["start", entry]]
    return [list(e) for e in entry.get("events", [])]


def split_time(events, end):
    """(agent hours, waiting hours) from a timeline: agent time runs from each start to the next
    review / pause; waiting time from a review / pause to the next start, or to the end."""
    agent = wait = 0.0
    working = waiting = None
    for event, at in events:
        at = dt.datetime.fromisoformat(at)
        if event == "start":
            if waiting is not None:
                wait += (at - waiting).total_seconds()
                waiting = None
            if working is None:
                working = at
        elif event in ("review", "pause"):
            if working is not None:
                agent += (at - working).total_seconds()
                working = None
            if waiting is None:
                waiting = at
    if working is not None:
        agent += (end - working).total_seconds()
    if waiting is not None:
        wait += (end - waiting).total_seconds()
    return round(agent / 3600, 1), round(wait / 3600, 1)


def cmd_start(a):
    ctx = gh_ctx()
    _, it = get_item(ctx, a.issue)
    if it["state"] != "OPEN":
        die(f"#{a.issue} is closed")
    if it["status"] in ("in progress", "in review") and not a.force:
        die(f"#{a.issue} is already {it['status']} — someone (another machine or a cloud run) may be on it. "
            "Use --force to take it over.", code=3)
    set_item_field(ctx, project_fields(ctx["project_id"]), it["item_id"], F_STATUS, "in progress")
    log_event(a.issue, "start")
    print(f"#{a.issue} → In progress ({it['title']})")


def cmd_review(a):
    ctx = gh_ctx()
    _, it = get_item(ctx, a.issue)
    set_item_field(ctx, project_fields(ctx["project_id"]), it["item_id"], F_STATUS, "in review")
    log_event(a.issue, "review")
    print(f"#{a.issue} → In review")


def cmd_done(a):
    ctx = gh_ctx()
    fields = project_fields(ctx["project_id"])
    items, it = get_item(ctx, a.issue)
    set_item_field(ctx, fields, it["item_id"], F_STATUS, "done")
    if it["state"] == "OPEN":
        rest("PATCH", f"repos/{ctx['repo']}/issues/{a.issue}", {"state": "closed", "state_reason": "completed"})
    it["state"], it["status"] = "CLOSED", "done"
    t = timers()
    events = timeline(t.pop(str(a.issue), None))
    agent_h, wait_h = split_time(events, dt.datetime.now()) if events else (None, None)
    hours = a.actual if a.actual is not None else agent_h
    if hours is not None:
        set_item_field(ctx, fields, it["item_id"], F_ACTUAL, hours)
        print(f"#{a.issue} actual: {hours:g} h of agent work (estimated {agent_effort(it):g} h)")
    if wait_h is not None:
        set_item_field(ctx, fields, it["item_id"], F_WAIT, wait_h)
        print(f"#{a.issue} waited {wait_h:g} h on review / answers")
    if a.rounds is not None:
        set_item_field(ctx, fields, it["item_id"], F_ROUNDS, a.rounds)
    save_json(LOCAL / "timers.json", t)
    print(f"#{a.issue} → Done")

    closed = {i["number"] for i in items if i["state"] == "CLOSED" or i["status"] == "done"}
    for i in items:
        if a.issue in i["deps"] and i["status"] == "backlog" and all(d in closed for d in i["deps"]):
            set_item_field(ctx, fields, i["item_id"], F_STATUS, "ready")
            print(f"  unblocked #{i['number']} → Ready")
    if it.get("parent"):
        siblings = [i for i in items if i.get("parent") == it["parent"]]
        epic = find_item(items, it["parent"])
        if siblings and all(i["number"] in closed for i in siblings) and epic and epic["state"] == "OPEN":
            rest("PATCH", f"repos/{ctx['repo']}/issues/{epic['number']}", {"state": "closed", "state_reason": "completed"})
            set_item_field(ctx, fields, epic["item_id"], F_STATUS, "done")
            print(f"  epic #{epic['number']} complete → closed")
        elif epic and epic["status"] in ("backlog", "ready"):
            set_item_field(ctx, fields, epic["item_id"], F_STATUS, "in progress")


def status_summary(ctx, items):
    work = [i for i in items if i.get(F_TYPE) != "Epic"]
    total = sum(effort(i) for i in work)
    done_n = {i["number"] for i in work if i["state"] == "CLOSED" or i["status"] == "done"}
    done = [i for i in work if i["number"] in done_n]
    done_h = sum(effort(i) for i in done)
    actual = [(agent_effort(i), float(i[F_ACTUAL])) for i in done if i.get(F_ACTUAL) is not None]
    ms = {}
    for i in work:
        if i.get("milestone"):
            m = ms.setdefault(i["milestone"], {"number": i["milestone"], "title": i["milestone_title"],
                                               "done": 0, "total": 0, "hours_done": 0.0, "hours_total": 0.0,
                                               "target": None, "musts_target": None})
            m["total"] += 1
            m["hours_total"] += effort(i)
            if i["number"] in done_n:
                m["done"] += 1
                m["hours_done"] += effort(i)
            elif i.get(F_TARGET):
                m["target"] = max(m["target"] or "", i[F_TARGET])
                if i.get(F_PRIO) == "Must":
                    m["musts_target"] = max(m["musts_target"] or "", i[F_TARGET])

    def brief(i):
        return {"number": i["number"], "title": i["title"], "url": i["url"], "type": i.get(F_TYPE),
                "priority": i.get(F_PRIO), "agent": i.get(F_AGENT), "labels": i["labels"],
                "milestone": i.get("milestone_title")}

    open_targets = [i[F_TARGET] for i in work if i["state"] == "OPEN" and i.get(F_TARGET)]
    return {
        "contract_version": CONTRACT_VERSION, "framework_version": framework_version(),
        "project_url": ctx["project_url"], "repo": ctx["repo"],
        "counts": {k: sum(1 for i in work if ("done" if i["number"] in done_n else i["status"]) == k)
                   for k in ("backlog", "ready", "in progress", "in review", "done")},
        "hours": {"done": done_h, "total": total, "remaining": total - done_h},
        "accuracy": ({"estimated": sum(x for x, _ in actual), "actual": sum(y for _, y in actual),
                      "items": len(actual)} if actual else None),
        "projected_end": max(open_targets) if open_targets else None,
        "milestones": sorted(ms.values(), key=lambda m: m["number"]),
        "in_progress": [brief(i) for i in work if i["status"] == "in progress" and i["number"] not in done_n],
        "in_review": [brief(i) for i in work if i["status"] == "in review" and i["number"] not in done_n],
        "needs_attention": [brief(i) for i in work if i["state"] == "OPEN"
                            and {"needs-human", "blocked"} & set(i["labels"])],
        "ready": [brief(i) for i in ready_items(items)],
    }


def cmd_status(a):
    ctx = gh_ctx()
    items = load_items(ctx)
    if a.json:
        print(json.dumps(status_summary(ctx, items), indent=2, ensure_ascii=False))
        return
    work = [i for i in items if i.get(F_TYPE) != "Epic"]
    by = defaultdict(list)
    for i in work:
        by["done" if i["state"] == "CLOSED" else i["status"]].append(i)
    total = sum(effort(i) for i in work)
    done_h = sum(effort(i) for i in by["done"])
    actual = [(agent_effort(i), float(i[F_ACTUAL])) for i in by["done"] if i.get(F_ACTUAL) is not None]
    print(f"Project: {ctx['project_url']}")
    print("Items:   " + ", ".join(f"{k}: {len(v)}" for k, v in sorted(by.items())))
    print(f"Effort:  {done_h:g} / {total:g} h done ({(100 * done_h / total) if total else 0:.0f}%), "
          f"{total - done_h:g} h remaining")
    if actual:
        est, act = sum(x for x, _ in actual), sum(y for _, y in actual)
        print(f"Accuracy: {act:g} h of agent work vs {est:g} h estimated on {len(actual)} item(s) "
              f"(ratio {act / est:.2f}) — details: fw metrics")
    targets = [i[F_TARGET] for i in work if i["state"] == "OPEN" and i.get(F_TARGET)]
    if targets:
        print(f"Projected end: {max(targets)}")
    ms = defaultdict(lambda: [0, 0])
    for i in work:
        if i.get("milestone_title"):
            ms[i["milestone_title"]][1] += 1
            ms[i["milestone_title"]][0] += i["state"] == "CLOSED"
    for t, (d, n) in ms.items():
        print(f"Milestone {t}: {d}/{n}")
    for label, key in (("In progress", "in progress"), ("In review", "in review")):
        for i in by[key]:
            print(f"{label}: #{i['number']} {i['title']}")
    for i in work:
        if i["state"] == "OPEN" and {"needs-human", "blocked"} & set(i["labels"]):
            print(f"Needs attention: #{i['number']} {i['title']} ({', '.join(i['labels'])})")


def metrics_summary(items, milestone=None):
    """Done items: agent estimate vs actual, waits and review rounds, grouped and with outliers."""
    def in_ms(i):
        return milestone is None or str(milestone) in (str(i.get("milestone")), i.get("milestone_title"))

    rows = []
    for i in items:
        if i.get(F_TYPE) == "Epic" or not (i["state"] == "CLOSED" or i["status"] == "done") or not in_ms(i):
            continue
        est, act = agent_effort(i), i.get(F_ACTUAL)
        rows.append({"number": i["number"], "title": i["title"], "type": i.get(F_TYPE), "size": i.get(F_SIZE),
                     "agent": i.get(F_AGENT), "estimate": est,
                     "actual": float(act) if act is not None else None,
                     "ratio": round(float(act) / est, 2) if act is not None and est > 0 else None,
                     "wait": float(i[F_WAIT]) if i.get(F_WAIT) is not None else None,
                     "rounds": int(i[F_ROUNDS]) if i.get(F_ROUNDS) is not None else None,
                     "escalated": "needs-human" in i["labels"]})
    measured = [r for r in rows if r["ratio"] is not None]

    def group(key):
        out = {}
        for r in measured:
            g = out.setdefault(r[key] or "-", {"items": 0, "estimate": 0.0, "actual": 0.0})
            g["items"] += 1
            g["estimate"] += r["estimate"]
            g["actual"] += r["actual"]
        for g in out.values():
            g["ratio"] = round(g["actual"] / g["estimate"], 2) if g["estimate"] else None
        return dict(sorted(out.items()))

    est, act = sum(r["estimate"] for r in measured), sum(r["actual"] for r in measured)
    rounds = [r["rounds"] for r in rows if r["rounds"] is not None]
    waits = sorted(r["wait"] for r in rows if r["wait"] is not None)
    return {
        "milestone": milestone, "done": len(rows), "measured": len(measured),
        "estimate": est, "actual": act, "ratio": round(act / est, 2) if est else None,
        "by_size": group("size"), "by_type": group("type"), "by_agent": group("agent"),
        "review_rounds": {"average": round(sum(rounds) / len(rounds), 2), "first_time_approved":
                          sum(1 for x in rounds if x <= 1), "items": len(rounds)} if rounds else None,
        "wait": {"total": sum(waits), "median": waits[len(waits) // 2], "max": waits[-1]} if waits else None,
        "outliers": [r for r in rows if (r["ratio"] is not None and not 0.5 <= r["ratio"] <= 2)
                     or (r["rounds"] or 0) >= 3],
        "items": rows,
    }


def cmd_metrics(a):
    m = metrics_summary(load_items(gh_ctx()), a.milestone)
    if a.json:
        print(json.dumps(m, indent=2, ensure_ascii=False))
        return
    scope = f"milestone {a.milestone}" if a.milestone else "all milestones"
    print(f"{m['done']} done item(s) in {scope}, {m['measured']} with measured agent time")
    if m["ratio"] is not None:
        print(f"Agent time: {m['actual']:g} h actual / {m['estimate']:g} h estimated (ratio {m['ratio']:.2f})")
    for title, key in (("size", "by_size"), ("type", "by_type"), ("agent", "by_agent")):
        if m[key]:
            print(f"  by {title}: " + ", ".join(f"{k} {g['ratio']:.2f} ({g['items']})" for k, g in m[key].items()
                                                if g["ratio"] is not None))
    if m["review_rounds"]:
        r = m["review_rounds"]
        print(f"Review rounds: {r['average']:g} on average, {r['first_time_approved']}/{r['items']} approved first time")
    if m["wait"]:
        print(f"Waiting on humans: {m['wait']['total']:g} h in total, median {m['wait']['median']:g} h, "
              f"max {m['wait']['max']:g} h")
    for r in m["outliers"]:
        print(f"Outlier #{r['number']} {r['title']}: {r['actual']} h / {r['estimate']:g} h"
              + (f", {r['rounds']} review rounds" if r["rounds"] else ""))


def schema():
    return {
        "contract_version": CONTRACT_VERSION,
        "framework_version": framework_version(),
        "fields": {"status": F_STATUS, "item_type": F_TYPE, "priority": F_PRIO, "size": F_SIZE,
                   "agent_effort": F_EFFORT, "human_review": F_REVIEW, "actual": F_ACTUAL,
                   "wait": F_WAIT, "review_rounds": F_ROUNDS,
                   "start_date": F_START, "target_date": F_TARGET, "agent": F_AGENT},
        "field_types": {n: t for n, t, _ in PROJECT_FIELDS},
        "field_options": {n: [o for o, _ in opts] for n, _, opts in PROJECT_FIELDS if opts},
        "statuses": [n for n, _, _ in STATUS_OPTIONS],
        "status_aliases": STATUS_ALIASES,
        "priorities": PRIORITIES,
        "work_types": WORK_TYPES,
        "sizes": {n: (None if h == math.inf else h) for n, h in SIZES},
        "labels": [n for n, _, _ in LABELS],
        "markers": {"key": "<!-- fw:key KEY -->", "depends_on": "<!-- fw:depends-on 12,34 -->",
                    "owner": "<!-- fw:owner human -->", "wait_days": "<!-- fw:wait-days N -->"},
        "json_commands": ["doctor --json", "next --json", "status --json", "schema --json", "escalations --json",
                          "escalate", "answer", "resolve"],
        "escalation": {"kinds": list(ESC_KINDS), "states": ["open", "answered", "resolved"],
                       "comment_markers": {"escalation": "<!-- fw:escalation {json} -->",
                                           "answer": "<!-- fw:answer {\"escalation\": id} --> or a comment starting with /answer",
                                           "resolved": "<!-- fw:resolved {\"escalation\": id} -->"},
                       "ask_prefix": "[fw:<kind> <id>]"},
    }


def cmd_schema(a):
    print(json.dumps(schema(), indent=2, ensure_ascii=False))


# --------------------------------------------------------------------------- escalations

def escalation_states(comments, trusted=TRUSTED_ASSOCIATIONS):
    """Fold an issue's comments into escalations: open → answered → resolved (see standards/escalation.md).
    Comments whose `author_association` is not trusted are ignored entirely (anti-forgery)."""
    escs, order = {}, []
    for c in comments:
        if trusted is not None and c.get("author_association") not in trusted:
            continue
        body = c.get("body") or ""
        who = (c.get("user") or {}).get("login")
        found = False
        for kind, raw in ESC_RE.findall(body):
            try:
                data = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(data, dict):
                continue
            found = True
            ref = data.get("id") if kind == "escalation" else data.get("escalation")
            if not isinstance(ref, str):
                continue
            if kind == "escalation":
                if ref in escs:  # an id is never reopened or overwritten
                    continue
                data.update(kind=data.get("kind") if data.get("kind") in ESC_KINDS else "question",
                            question=str(data.get("question") or ""),
                            options=[str(o) for o in data.get("options") or []] if isinstance(data.get("options"), list) else [],
                            state="open", answer=None, answered_by=None, comment_url=c.get("html_url"),
                            created_at=c.get("created_at"), opened_by=who)
                escs[ref] = data
                order.append(ref)
            elif ref in escs and kind == "answer" and escs[ref]["state"] == "open":
                escs[ref].update(state="answered", answer=str(data.get("text") or ""), answered_by=who)
            elif ref in escs and kind == "resolved":
                escs[ref]["state"] = "resolved"
        m = None if found else ANSWER_RE.match(body.strip())
        if m and (m.group(2) or "").strip():  # an empty `/answer` is ignored
            target = m.group(1)
            pending = [i for i in reversed(order) if escs[i]["state"] == "open" and (not target or i == target)]
            if pending:  # `/answer <text>` → latest open escalation; `/answer esc-… <text>` → that one
                escs[pending[0]].update(state="answered", answer=(m.group(2) or "").strip(), answered_by=who)
    return [escs[i] for i in order]


def trusted_associations():
    t = dig(cfg(), "escalations.trusted_associations")
    return tuple(t) if isinstance(t, list) and t else TRUSTED_ASSOCIATIONS


def issue_comments(repo, number):
    out, page = [], 1
    while True:
        batch = rest("GET", f"repos/{repo}/issues/{number}/comments?per_page=100&page={page}") or []
        out += batch
        if len(batch) < 100:
            return out
        page += 1


def visible(text):
    """User text shown in a comment: neutralise HTML comments so it can never carry a marker."""
    return str(text or "").replace("<!--", "&lt;!--").replace("-->", "--&gt;")


def marker(kind, data):
    # Escape <, > and & so user text can never close the HTML comment or fake another marker.
    raw = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return f"<!-- fw:{kind} {raw} -->"


def set_needs_human(repo, number, on):
    if on:
        ok = rest("POST", f"repos/{repo}/issues/{number}/labels", {"labels": ["needs-human"]}, check=False)
    else:
        ok = rest("DELETE", f"repos/{repo}/issues/{number}/labels/needs-human", check=False)
    if ok is None and on:
        warn(f"could not add the needs-human label to #{number} — check the token's issues permission")


def states_for(ctx, issue):
    return escalation_states(issue_comments(ctx["repo"], issue), trusted_associations())


def cmd_escalate(a):
    ctx = gh_ctx()
    options = a.option or []
    if a.recommended is not None and not 0 <= a.recommended < len(options):
        die(f"--recommended must be between 0 and {len(options) - 1}")
    esc = {"v": 1, "id": f"esc-{a.issue}-{dt.datetime.now().strftime('%Y%m%d%H%M%S')}-{os.urandom(2).hex()}",
           "kind": a.kind,
           "issue": a.issue, "question": a.question, "options": options, "recommended": a.recommended,
           "multi": a.multi, "pr": a.pr, "source": a.source}
    lines = [marker("escalation", esc), f"**🙋 Needs you — {a.kind}**" + (f" (PR #{a.pr})" if a.pr else ""), "",
             visible(a.question), ""]
    if a.context:
        lines += [visible(a.context), ""]
    for n, o in enumerate(esc["options"]):
        lines.append(f"{n + 1}. {visible(o)}" + (" *(recommended)*" if a.recommended == n else ""))
    lines += ["", "_Answer with a comment starting with `/answer`, e.g. `/answer "
              + (visible(options[a.recommended or 0]) if options else "yes") + f"` (or `/answer {esc['id']} …`)._"]
    c = rest("POST", f"repos/{ctx['repo']}/issues/{a.issue}/comments", {"body": "\n".join(lines)})
    set_needs_human(ctx["repo"], a.issue, True)
    log_event(a.issue, "pause")
    esc["comment_url"] = c["html_url"]
    print(json.dumps(esc, indent=2, ensure_ascii=False))


def find_escalation(ctx, issue, esc_id, states):
    escs = [e for e in states_for(ctx, issue) if e["state"] in states]
    if esc_id:
        escs = [e for e in escs if e["id"] == esc_id]
    return escs[-1] if escs else die(f"#{issue}: no {'/'.join(states)} escalation" + (f" {esc_id}" if esc_id else ""))


def cmd_answer(a):
    ctx = gh_ctx()
    e = find_escalation(ctx, a.issue, a.id, ("open",))
    rest("POST", f"repos/{ctx['repo']}/issues/{a.issue}/comments",
         {"body": marker("answer", {"v": 1, "escalation": e["id"], "text": a.text}) + f"\n**Answer:** {visible(a.text)}"})
    print(json.dumps({"escalation": e["id"], "issue": a.issue, "state": "answered", "answer": a.text}))


def cmd_resolve(a):
    ctx = gh_ctx()
    e = find_escalation(ctx, a.issue, a.id, ("open", "answered"))
    body = marker("resolved", {"v": 1, "escalation": e["id"]})
    if a.answer:
        body = marker("answer", {"v": 1, "escalation": e["id"], "text": a.answer}) + "\n" + body + \
            f"\n**Answer:** {visible(a.answer)}"
    rest("POST", f"repos/{ctx['repo']}/issues/{a.issue}/comments", {"body": body})
    after = states_for(ctx, a.issue)
    if all(x["state"] == "resolved" for x in after):
        set_needs_human(ctx["repo"], a.issue, False)
    rec = next((x for x in after if x["id"] == e["id"]), e)
    print(json.dumps({"escalation": e["id"], "issue": a.issue, "state": rec["state"], "answer": rec.get("answer")}))


def cmd_escalations(a):
    ctx = gh_ctx()
    if a.issue:
        numbers = [a.issue]
    else:
        numbers, page = [], 1
        while True:
            batch = rest("GET", f"repos/{ctx['repo']}/issues?labels=needs-human&state=open&per_page=100&page={page}") or []
            numbers += [i["number"] for i in batch if "pull_request" not in i]
            if len(batch) < 100:
                break
            page += 1
    states = {"open", "answered"} if not a.all else {"open", "answered", "resolved"}
    out = [e for n in numbers for e in states_for(ctx, n) if e["state"] in states]
    if a.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return
    if not out:
        print("No pending escalation.")
    for e in out:
        print(f"#{e.get('issue', '?'):<5} {e['state']:<9} {e['kind']:<9} {e['question'][:70]}"
              + (f"  → {e['answer'][:40]}" if e.get("answer") else ""))


# --------------------------------------------------------------------------- workflows

def cmd_workflow(a):
    src_dir = ROOT / "framework" / "templates" / "workflows"
    available = sorted(p.stem.replace("fw-", "") for p in src_dir.glob("*.yml"))
    if a.action == "list" or not a.name:
        print("available workflows: " + ", ".join(available))
        return
    src = src_dir / (f"fw-{a.name}.yml" if (src_dir / f"fw-{a.name}.yml").exists() else f"{a.name}.yml")
    if not src.exists():
        die(f"unknown workflow '{a.name}' (available: {', '.join(available)})")
    dst = ROOT / ".github" / "workflows" / src.name
    if dst.exists() and not a.force:
        die(f"{dst.relative_to(ROOT)} exists — use --force to overwrite")
    text = src.read_text(encoding="utf-8")
    for kv in a.env or []:
        key, _, value = kv.partition("=")
        text, n = re.subn(rf'^(\s+{re.escape(key)}:\s*)"[^"\n]*"', lambda m: f'{m.group(1)}"{value}"', text, count=1,
                          flags=re.M)
        if not n:
            die(f"{src.name} has no env variable {key}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text, encoding="utf-8")
    print(f"✔ installed {dst.relative_to(ROOT)}")
    if src.name.startswith("ci-"):
        if not (cfg().get("commands") or {}).get("test"):
            print("  ! .fw/config.json → commands has no `test` — CI fails until it does (`fw commands --detect`)")
        print("  once it has run green on a pull request, require it: framework/bin/fw protect --checks check")
    needed = re.findall(r"secrets\.([A-Z0-9_]+)", src.read_text())
    needed = sorted(set(needed) - {"GITHUB_TOKEN"})
    if needed:
        repo = dig(cfg(), "github.repo")
        have = set()
        if repo:
            r = gh("secret", "list", "-R", repo, "--json", "name", check=False)
            if r.returncode == 0:
                have = {x["name"] for x in json.loads(r.stdout or "[]")}
        for n in needed:
            print(f"  {'✔' if n in have else '✘'} secret {n}" + ("" if n in have else f" — gh secret set {n} -R {repo}"))
    print("  commit it through a pull request (see docs/framework/cloud-runs.md for cloud-run).")


# --------------------------------------------------------------------------- agents & docs quality

def parse_frontmatter(text):
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end < 0:
        return None, text
    fm = {}
    for line in text[3:end].strip().splitlines():
        if ":" in line and not line.startswith((" ", "\t", "-")):
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip().strip("\"'")
    return fm, text[end + 4:]


def cmd_lint_agents(a):
    errors, warns = [], []
    files = sorted((ROOT / ".claude" / "agents").glob("*.md"))
    if not files:
        warns.append("no agents in .claude/agents/ — run /fw-team")
    bodies = {}
    for f in files:
        rel = f.relative_to(ROOT)
        fm, body = parse_frontmatter(f.read_text(encoding="utf-8"))
        bodies[f.stem] = body
        if fm is None:
            errors.append(f"{rel}: missing YAML frontmatter")
            continue
        name = fm.get("name", "")
        if name != f.stem:
            errors.append(f"{rel}: 'name' ({name}) must equal the file name ({f.stem})")
        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", f.stem):
            errors.append(f"{rel}: file name must be kebab-case")
        if len(fm.get("description", "")) < 60:
            errors.append(f"{rel}: 'description' must say what the agent does AND when to use it (>= 60 chars)")
        tools = fm.get("tools")
        if not tools:
            warns.append(f"{rel}: no 'tools' — the agent inherits every tool; restrict it unless intended")
        elif re.search(r"review|qa|audit|owner", f.stem) and re.search(r"\b(Write|Edit)\b", tools):
            warns.append(f"{rel}: review/QA/spec agents should be read-only (drop Write/Edit)")
        heads = [h.strip().lower() for h in re.findall(r"^##\s+(.+)$", body, re.M)]
        for sec in AGENT_SECTIONS:
            if not any(h.startswith(sec.lower()) for h in heads):
                errors.append(f"{rel}: missing section '## {sec}'")
        if len(body) < 800:
            warns.append(f"{rel}: body is short ({len(body)} chars) — is the procedure concrete enough?")
        if re.search(r"\{\{|\bTODO\b|\bTBD\b|lorem", body):
            errors.append(f"{rel}: contains placeholders (TODO / TBD / {{{{ }}}})")
    roles = cfg().get("roles") or {}
    for role, names in roles.items():
        for n in as_list(names):
            if n not in bodies:
                errors.append(f"role '{role}' → agent '{n}' has no file .claude/agents/{n}.md")
            elif role in ROLE_TOKENS and ROLE_TOKENS[role] not in bodies[n]:
                errors.append(f"{n}: role '{role}' requires the output token '{ROLE_TOKENS[role]}' in its Output contract")
    for w in warns:
        print(f"! {w}")
    for e in errors:
        print(f"✘ {e}")
    print(f"{len(files)} agent(s) — {len(errors)} error(s), {len(warns)} warning(s)")
    sys.exit(1 if errors else 0)


def cmd_docs_check(a):
    targets = [p for p in (ROOT / "docs").rglob("*.md") if ".obsidian" not in p.parts]
    targets += [p for p in (ROOT / "CLAUDE.md", ROOT / "README.md") if p.exists()]
    broken, wiki = [], []
    for f in targets:
        text = f.read_text(encoding="utf-8")
        text = re.sub(r"```.*?```", "", text, flags=re.S)
        text = re.sub(r"`[^`\n]*`", "", text)
        for link in re.findall(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)", text):
            if re.match(r"[a-z]+:", link) or link.startswith("#"):
                continue
            target = (f.parent / link.split("#")[0]).resolve()
            if not target.exists():
                broken.append(f"{f.relative_to(ROOT)} → {link}")
        if re.search(r"\[\[[^\]]+\]\]", text):
            wiki.append(str(f.relative_to(ROOT)))
    for w in wiki:
        print(f"! {w}: uses [[wikilinks]] — use relative Markdown links (Obsidian + MkDocs compatible)")
    for b in broken:
        print(f"✘ broken link: {b}")
    print(f"{len(targets)} file(s) checked — {len(broken)} broken link(s)")
    sys.exit(1 if broken else 0)


# --------------------------------------------------------------------------- install / update

INSTALL_EXCLUDE = (".git/", ".fw/local/", ".fw/state.json", ".fw/backlog/", ".fw/framework.lock.json", ".claude/settings.local.json", "site/")


def source_files(src):
    out = []
    for dp, dns, fns in os.walk(src):
        dns[:] = [d for d in dns if d not in (".git", "__pycache__", "node_modules", "site")]
        for f in fns:
            rel = os.path.relpath(os.path.join(dp, f), src).replace(os.sep, "/")
            if not rel.startswith(INSTALL_EXCLUDE):
                out.append(rel)
    return out


def merge_settings(src, dst_path):
    dst = load_json(dst_path, {})
    for event, entries in (src.get("hooks") or {}).items():
        cur = dst.setdefault("hooks", {}).setdefault(event, [])
        known = {(e.get("matcher"), h.get("command")) for e in cur for h in e.get("hooks", [])}
        for e in entries:
            if not any((e.get("matcher"), h.get("command")) in known for h in e.get("hooks", [])):
                cur.append(e)
    for kind in ("allow", "deny"):
        rules = (src.get("permissions") or {}).get(kind) or []
        if rules:
            cur = dst.setdefault("permissions", {}).setdefault(kind, [])
            cur += [r for r in rules if r not in cur]
    save_json(dst_path, dst)


def cmd_install(a):
    dst = Path(a.target).expanduser().resolve()
    if not dst.is_dir():
        die(f"{dst} is not a directory")
    if dst == ROOT:
        die("target is the framework itself")
    owned, scaffold = manifest()
    report = defaultdict(list)
    for rel in source_files(ROOT):
        s, d = ROOT / rel, dst / rel
        if matches(rel, owned):
            kind = "updated" if d.exists() else "added"
        elif matches(rel, scaffold):
            if rel == ".claude/settings.json" and d.exists():
                merge_settings(load_json(s, {}), d)
                report["merged"].append(rel)
                continue
            if rel == "CLAUDE.md" and d.exists():
                text = d.read_text(encoding="utf-8")
                if "@framework/CLAUDE.framework.md" not in text:
                    d.write_text("@framework/CLAUDE.framework.md\n\n" + text, encoding="utf-8")
                    report["merged"].append(rel)
                continue
            if d.exists():
                report["kept"].append(rel)
                continue
            kind = "added"
        else:
            continue
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d)
        report[kind].append(rel)
    # fresh project config, remembering where the framework comes from
    upstream = run(["git", "remote", "get-url", "origin"], check=False).stdout.strip()
    conf = load_json(dst / ".fw" / "config.json", {})
    conf["initialized"] = False
    conf.setdefault("framework", {}).update(upstream=upstream or dig(cfg(), "framework.upstream", ""),
                                             branch="main",
                                             version=(ROOT / "framework" / "VERSION").read_text().strip())
    conf["framework"]["migrated"] = conf["framework"]["version"]
    save_json(dst / ".fw" / "config.json", conf)
    write_lock(dst, conf["framework"]["version"])
    gi = dst / ".gitignore"
    lines = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    extra = [x for x in GITIGNORE_LINES if x not in lines]
    if extra:
        gi.write_text("\n".join(lines + ["", "# framework"] + extra) + "\n", encoding="utf-8")
    os.chmod(dst / "framework" / "bin" / "fw", 0o755)
    for k in ("added", "updated", "merged", "kept"):
        if report[k]:
            print(f"{k:>8}: {len(report[k])} file(s)" + (f" — {', '.join(report[k][:6])}…" if k != "added" else ""))
    print(f"\nFramework installed in {dst}.\nNext: cd {dst} && claude, then run /fw-init "
          "(it detects the existing code and switches to adoption mode).")


def cmd_update(a):
    c = cfg()
    url = a.upstream or dig(c, "framework.upstream")
    if not url:
        die("no upstream — `fw config set framework.upstream <git-url>`")
    branch = a.branch or dig(c, "framework.branch") or "main"
    if a.apply and run(["git", "status", "--porcelain"]).stdout.strip():
        die("working tree not clean — commit or stash first")
    run(["git", "fetch", "--quiet", "--depth", "1", url, branch])
    owned, _ = manifest()
    upstream = [f for f in run(["git", "ls-tree", "-r", "--name-only", "FETCH_HEAD"]).stdout.splitlines()
                if matches(f, owned)]
    removed = sorted(set(f for f in repo_files() if matches(f, owned)) - set(upstream))
    cur = (ROOT / "framework" / "VERSION").read_text().strip()
    new = run(["git", "show", "FETCH_HEAD:framework/VERSION"], check=False).stdout.strip() or "?"
    print(f"framework {cur} → {new} ({url} {branch})")
    notes = changelog_between(run(["git", "show", "FETCH_HEAD:framework/CHANGELOG.md"], check=False).stdout, cur, new)
    if notes:
        print("\n" + notes + "\n")
    print(run(["git", "diff", "--stat", "HEAD", "FETCH_HEAD", "--", *owned], check=False).stdout.strip()
          or "no difference in framework-owned files")
    if removed:
        print("removed upstream: " + ", ".join(removed))
    d = drift()
    if d and any(d.values()):
        print("\n! local changes to framework-owned files — --apply replaces them with the upstream version; "
              "move anything worth keeping to the template first:")
        for kind in ("modified", "added", "deleted"):
            for f in d[kind]:
                print(f"  {kind:<8} {f}")
    if not a.apply:
        print("\n(dry run — re-run with --apply)")
        return
    for i in range(0, len(upstream), 100):
        run(["git", "checkout", "FETCH_HEAD", "--", *upstream[i:i + 100]])
    if removed:
        run(["git", "rm", "-q", "--", *removed])
    up_settings = run(["git", "show", "FETCH_HEAD:.claude/settings.json"], check=False).stdout
    if up_settings.strip():
        merge_settings(json.loads(up_settings), ROOT / ".claude" / "settings.json")
    c.setdefault("framework", {})["version"] = new
    save_json(CONFIG, c)
    write_lock(ROOT, new)
    # migrations live in the new code: run it, not this (old) process
    m = run([sys.executable, str(ROOT / "framework" / "bin" / "fw.py"), "migrate"], check=False)
    print((m.stdout + m.stderr).strip())
    if m.returncode != 0:
        die("migrations failed — fix the error above, then re-run `framework/bin/fw migrate`")
    print("\n✔ framework files updated — review `git diff --staged`, run `fw lint-agents`, then commit.")


# --------------------------------------------------------------------------- project commands / check

CHECK_STEPS = ["lint", "typecheck", "test", "build"]   # what `fw check` runs, in this order, when configured
COMMAND_KEYS = ["install"] + CHECK_STEPS


def cmd_check(a):
    """Run the project's commands (.fw/config.json → commands): the one quality gate for agents, hooks and CI."""
    cmds = cfg().get("commands") or {}
    wanted = a.steps or [k for k in CHECK_STEPS if cmds.get(k)]
    missing = [k for k in wanted if not cmds.get(k)]
    if missing and not a.if_configured:
        die(f"commands.{missing[0]} is not configured — `fw commands --detect`, or "
            f"`fw config set commands.{missing[0]} '\"<command>\"'`", 2)
    steps = [k for k in wanted if cmds.get(k)]
    if not steps:
        if a.if_configured:
            print("nothing to run (no matching command in .fw/config.json → commands)")
            return
        die("no commands configured (.fw/config.json → commands) — run `fw commands --detect`", 2)
    results = []
    for k in steps:
        if not a.json:
            print(f"▶ {k}: {cmds[k]}", flush=True)
        t0 = dt.datetime.now()
        p = subprocess.run(cmds[k], shell=True, cwd=str(ROOT), text=True,
                           capture_output=a.json, stdin=subprocess.DEVNULL)
        r = {"name": k, "command": cmds[k], "exit": p.returncode,
             "seconds": round((dt.datetime.now() - t0).total_seconds(), 1)}
        if a.json:
            r["output_tail"] = "\n".join(((p.stdout or "") + (p.stderr or "")).splitlines()[-60:])
        results.append(r)
        if p.returncode != 0 and a.fail_fast:
            break
    ok = all(r["exit"] == 0 for r in results) and len(results) == len(steps)
    if a.json:
        print(json.dumps({"ok": ok, "steps": results}, indent=2, ensure_ascii=False))
    else:
        print("\n" + "  ".join(f"{'✔' if r['exit'] == 0 else '✘'} {r['name']} ({r['seconds']:g}s)" for r in results))
    sys.exit(0 if ok else 1)


def make_targets(root):
    mk = root / "Makefile"
    if not mk.exists():
        return set()
    return set(re.findall(r"^([A-Za-z][\w-]*):(?!=)", mk.read_text(encoding="utf-8", errors="replace"), re.M))


def detect_commands(root=None):
    """Best-effort commands and CI template from the files in the repository. Returns (commands, ci, sources)."""
    root = root or ROOT
    has = lambda *names: any((root / n).exists() for n in names)  # noqa: E731
    text = lambda n: (root / n).read_text(encoding="utf-8", errors="replace") if (root / n).exists() else ""  # noqa: E731
    cmds, ci, src = {}, "generic", []

    if has("package.json"):
        ci, src = "node", src + ["package.json"]
        scripts = (json.loads(text("package.json") or "{}").get("scripts") or {})
        if has("pnpm-lock.yaml"):
            cmds["install"], runner = "pnpm install --frozen-lockfile", "pnpm"
        elif has("yarn.lock"):
            cmds["install"], runner = "yarn install --immutable", "yarn"
        else:
            cmds["install"], runner = ("npm ci" if has("package-lock.json") else "npm install"), "npm run"
        for key, names in (("lint", ["lint"]), ("typecheck", ["typecheck", "type-check", "tsc", "check-types"]),
                           ("test", ["test"]), ("build", ["build"])):
            name = next((n for n in names if n in scripts), None)
            if name and not (name == "test" and "no test specified" in scripts[name]):
                cmds[key] = f"{runner} {name}"
    elif has("composer.json"):
        ci, src = "php", src + ["composer.json"]
        scripts = (json.loads(text("composer.json") or "{}").get("scripts") or {})
        cmds["install"] = "composer install --no-interaction --prefer-dist --no-progress"
        for key, names in (("lint", ["lint", "cs", "cs-check"]), ("typecheck", ["phpstan", "psalm", "analyse"]),
                           ("test", ["test", "tests"])):
            name = next((n for n in names if n in scripts), None)
            if name:
                cmds[key] = f"composer {name}"
        if "lint" not in cmds and has(".php-cs-fixer.dist.php", ".php-cs-fixer.php"):
            cmds["lint"] = "vendor/bin/php-cs-fixer fix --dry-run --diff"
        elif "lint" not in cmds and has("phpcs.xml", "phpcs.xml.dist"):
            cmds["lint"] = "vendor/bin/phpcs"
        if "typecheck" not in cmds and has("phpstan.neon", "phpstan.neon.dist", "phpstan.dist.neon"):
            cmds["typecheck"] = "vendor/bin/phpstan analyse --no-progress"
        if "test" not in cmds and has("phpunit.xml", "phpunit.xml.dist", "phpunit.dist.xml"):
            cmds["test"] = "vendor/bin/phpunit"
    elif has("pyproject.toml", "requirements.txt", "setup.py"):
        ci, src = "python", src + [n for n in ("pyproject.toml", "requirements.txt", "setup.py") if has(n)]
        deps = text("pyproject.toml") + text("requirements.txt") + text("requirements-dev.txt")
        if has("uv.lock"):
            cmds["install"], run_ = "uv sync", "uv run "
        elif has("poetry.lock"):
            cmds["install"], run_ = "poetry install", "poetry run "
        else:
            cmds["install"] = "pip install -r requirements.txt" if has("requirements.txt") else "pip install -e ."
            run_ = ""
        if "ruff" in deps:
            cmds["lint"] = f"{run_}ruff check ."
        if "mypy" in deps:
            cmds["typecheck"] = f"{run_}mypy ."
        if "pytest" in deps or has("tests", "pytest.ini", "conftest.py"):
            cmds["test"] = f"{run_}pytest"
    elif has("go.mod"):
        ci, src = "go", src + ["go.mod"]
        cmds.update(install="go mod download", lint="go vet ./...", test="go test ./...", build="go build ./...")
    elif has("Cargo.toml"):
        src.append("Cargo.toml")
        cmds.update(install="cargo fetch", lint="cargo clippy -- -D warnings", test="cargo test", build="cargo build")

    targets = make_targets(root)  # an explicit Makefile target is the project's intent: it wins
    for key in COMMAND_KEYS:
        if key in targets:
            cmds[key] = f"make {key}"
    if targets & set(COMMAND_KEYS):
        src.append("Makefile")
    return cmds, ci, src


def cmd_commands(a):
    c = cfg()
    current = c.get("commands") or {}
    if not a.detect:
        print(json.dumps(current, indent=2) if current else "no commands configured — `fw commands --detect`")
        return
    found, ci, src = detect_commands()
    print(f"detected from {', '.join(src) or 'nothing'} — CI template: ci-{ci}")
    for k in COMMAND_KEYS:
        if k in found or k in current:
            mark = "=" if current.get(k) == found.get(k) else ("keep" if k in current else "+")
            print(f"  {mark:<4} {k:<9} {current.get(k) or found[k]}"
                  + (f"   (detected: {found[k]})" if k in current and k in found and current[k] != found[k] else ""))
    if a.apply:
        added = {k: v for k, v in found.items() if k not in current}
        c["commands"] = {**current, **added}
        save_json(CONFIG, c)
        print(f"✔ {len(added)} command(s) added to .fw/config.json → commands (existing ones kept)")
    else:
        print("(dry run — `--apply` adds the missing ones; existing commands are never replaced)")


# --------------------------------------------------------------------------- review pipeline / worktrees

DEFAULT_REVIEW_WIP = 2


def pipeline_state(items, conf, local_timers=()):
    """Can the implementer start a new item? One implementer at a time; at most `review_wip` items
    waiting in review; rework (an item sent back to In progress) always comes first."""
    p = conf.get("pipeline") or {}
    wip = int(p.get("review_wip", DEFAULT_REVIEW_WIP))
    flight = [i for i in items if i["state"] == "OPEN" and i.get(F_TYPE) != "Epic"
              and i["status"] in ("in progress", "in review") and "needs-human" not in i["labels"]]
    brief = lambda i: {"number": i["number"], "title": i["title"], "status": i["status"],  # noqa: E731
                       "mine": str(i["number"]) in local_timers}
    in_review = [brief(i) for i in flight if i["status"] == "in review"]
    in_progress = [brief(i) for i in flight if i["status"] == "in progress"]
    # the limits apply to this machine's pipeline; items started elsewhere are listed, not counted
    busy = [i for i in in_progress if i["mine"]]
    waiting = [i for i in in_review if i["mine"]]
    if not p.get("enabled"):
        can, reason = not busy, ("pipeline disabled: one item at a time" if busy
                                 else "pipeline disabled: free to start")
    elif busy:
        in_progress = busy + [i for i in in_progress if not i["mine"]]
        can, reason = False, (f"the implementer is busy with #{busy[0]['number']} "
                              "(finish it, or its rework, first)")
    elif len(waiting) >= wip:
        can, reason = False, (f"review limit reached ({len(waiting)}/{wip}): wait for a review result "
                              "or a merge — rework comes first")
    else:
        can, reason = True, f"{len(waiting)}/{wip} in review: the implementer may start the next item"
    return {"enabled": bool(p.get("enabled")), "review_wip": wip, "can_start": can, "reason": reason,
            "in_progress": in_progress, "in_review": in_review}


def cmd_pipeline(a):
    c = cfg()
    if a.action in ("on", "off"):
        c.setdefault("pipeline", {})["enabled"] = a.action == "on"
        if a.wip is not None:
            c["pipeline"]["review_wip"] = a.wip
        c["pipeline"].setdefault("review_wip", DEFAULT_REVIEW_WIP)
        save_json(CONFIG, c)
        print(f"✔ review pipeline {a.action} (at most {c['pipeline']['review_wip']} item(s) in review)")
        return
    st = pipeline_state(load_items(gh_ctx()), c, timers())
    if a.json:
        print(json.dumps(st, indent=2, ensure_ascii=False))
        return
    print(("✔ " if st["can_start"] else "· ") + st["reason"])
    for k in ("in_progress", "in_review"):
        for i in st[k]:
            print(f"  {i['status']:<12} #{i['number']} {i['title']}" + ("" if i["mine"] else "  (other machine)"))


def worktrees_base(root=None):
    root = (root or ROOT).resolve()
    return root.parent / f"{root.name}.worktrees"


def slugify(text, limit=40):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower().encode("ascii", "ignore").decode()).strip("-")
    return s[:limit].rstrip("-") or "item"


def branch_for(it):
    prefix = "hotfix" if "hotfix" in it.get("labels", []) else \
        {"Bug": "fix", "Task": "chore"}.get(it.get(F_TYPE), "feat")
    return f"{prefix}/{it['number']}-{slugify(it['title'])}"


def worktree_list(root=None):
    """Story worktrees (under <repo>.worktrees/) with branch, dirty flag and commits ahead."""
    root = root or ROOT
    base = worktrees_base(root)
    out, cur = [], {}
    for line in run(["git", "worktree", "list", "--porcelain"], check=False, cwd=root).stdout.splitlines() + [""]:
        if line.startswith("worktree "):
            cur = {"path": line[9:]}
        elif line.startswith("branch "):
            cur["branch"] = line[7:].replace("refs/heads/", "")
        elif not line and cur.get("path"):
            path = Path(cur["path"])
            if base in path.parents:
                m = re.match(r"(\d+)-", path.name)
                cur.update(number=int(m.group(1)) if m else None,
                           dirty=bool(run(["git", "status", "--porcelain"], check=False, cwd=path).stdout.strip()))
                out.append(cur)
            cur = {}
    return out


def cmd_worktree(a):
    if a.action == "list":
        wts = worktree_list()
        if a.json:
            print(json.dumps(wts, indent=2))
        for w in [] if a.json else wts:
            print(f"#{w['number']:<5} {w.get('branch', '?'):<45} {'dirty ' if w['dirty'] else ''}{w['path']}")
        return
    if a.issue is None:
        die("issue number required")
    existing = next((w for w in worktree_list() if w["number"] == a.issue), None)
    if a.action == "remove":
        if not existing:
            print(f"no worktree for #{a.issue}")
            return
        if existing["dirty"]:
            die(f"{existing['path']} has uncommitted changes — commit them or ask the user before removing it")
        run(["git", "worktree", "remove", existing["path"]])
        run(["git", "worktree", "prune"], check=False)
        print(f"✔ removed {existing['path']} (branch {existing.get('branch')} kept)")
        return
    if existing:  # add is idempotent: resuming an item reuses its worktree
        print(existing["path"])
        return
    ctx = gh_ctx()
    _, it = get_item(ctx, a.issue)
    branch = a.branch or branch_for(it)
    path = worktrees_base() / f"{a.issue}-{slugify(it['title'], 30)}"
    default = dig(cfg(), "github.default_branch") or "main"
    run(["git", "fetch", "--quiet", "origin", default], check=False)
    has_local = run(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"], check=False).returncode == 0
    has_remote = run(["git", "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}"],
                     check=False).returncode == 0
    path.parent.mkdir(parents=True, exist_ok=True)
    if has_local:
        run(["git", "worktree", "add", str(path), branch])
    elif has_remote:
        run(["git", "worktree", "add", "--track", "-b", branch, str(path), f"origin/{branch}"])
    else:
        start = f"origin/{default}" if run(["git", "rev-parse", "--verify", "--quiet", f"origin/{default}"],
                                           check=False).returncode == 0 else default
        run(["git", "worktree", "add", "-b", branch, str(path), start])
    print(path)


def cmd_rework(a):
    ctx = gh_ctx()
    _, it = get_item(ctx, a.issue)
    set_item_field(ctx, project_fields(ctx["project_id"]), it["item_id"], F_STATUS, "in progress")
    log_event(a.issue, "start")
    print(f"#{a.issue} → In progress (rework)")


# --------------------------------------------------------------------------- resume / triage / release

BRANCH_RE = r"^(?:feat|fix|chore|hotfix|docs)/{n}-"


def resume_plan(it, branches, prs, current, dirty, mine, ahead):
    """Where /fw-work should pick an interrupted item up. `branches`: local and remote branch names;
    `prs`: [{number, state, headRefName, url}]; `ahead`: {branch: commits ahead of the default branch}."""
    n = it["number"]
    branch = next((b for b in branches if re.match(BRANCH_RE.format(n=n), b)), None)
    pr = None
    for state in ("OPEN", "MERGED", "CLOSED"):
        pr = pr or next((p for p in prs if p["headRefName"] == branch and p["state"] == state), None)
    out = {"number": n, "title": it["title"], "status": it["status"], "mine": mine, "branch": branch,
           "pr": pr["number"] if pr else None, "pr_state": pr["state"] if pr else None}
    if pr and pr["state"] == "MERGED":
        step, action = 11, f"PR #{pr['number']} is merged: close the loop (`fw done {n}`)"
    elif not mine:
        step, action = None, ("started elsewhere (another machine or a cloud run): leave it — "
                              "`fw start --force` only with the user")
    elif pr and pr["state"] == "OPEN":
        step = 9
        action = f"PR #{pr['number']} is open: " + ("watch CI, then the merge decision" if it["status"] == "in review"
                                                    else f"`fw review {n}`, then CI and the merge decision")
    elif pr:
        step, action = None, f"PR #{pr['number']} was closed without merging: ask the user"
    elif branch and current == branch and dirty:
        step, action = 4, "uncommitted work on the branch: continue implementing, then `fw check`"
    elif branch and ahead.get(branch):
        step, action = 5, (f"{ahead[branch]} commit(s) on {branch}, no PR: check out the branch, "
                           "`fw check`, then review")
    elif branch:
        step, action = 3, f"{branch} exists but has no work yet: check it out and start at the spec check"
    else:
        step, action = 2, "nothing on disk: create the branch and start at the spec check"
    out.update(step=step, action=action)
    return out


def cmd_resume(a):
    ctx = gh_ctx()
    items = [i for i in load_items(ctx) if i["state"] == "OPEN" and i["status"] in ("in progress", "in review")
             and i.get(F_TYPE) != "Epic"]
    mine = set(timers())
    default = (run(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], check=False).stdout.strip()
               or "origin/main")
    local = run(["git", "branch", "--format=%(refname:short)"], check=False).stdout.split()
    remote = [line.split("refs/heads/", 1)[1] for line in
              run(["git", "ls-remote", "--heads", "origin"], check=False).stdout.splitlines() if "refs/heads/" in line]
    p = gh("pr", "list", "--state", "all", "--limit", "200", "--json", "number,state,headRefName,url", check=False)
    prs = json.loads(p.stdout or "[]") if p.returncode == 0 else []
    current = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], check=False).stdout.strip()
    dirty = bool(run(["git", "status", "--porcelain"], check=False).stdout.strip())
    ahead = {}
    for b in set(local):
        c = run(["git", "rev-list", "--count", f"{default}..{b}"], check=False).stdout.strip()
        ahead[b] = int(c) if c.isdigit() else 0
    plans = [resume_plan(i, local + [b for b in remote if b not in local], prs, current, dirty,
                         str(i["number"]) in mine, ahead) for i in items]
    if a.json:
        print(json.dumps(plans, indent=2, ensure_ascii=False))
        return
    if not plans:
        print("nothing to resume — no item in progress or in review")
    for r in plans:
        print(f"#{r['number']:<5} {r['status']:<12} " + (f"step {r['step']:<3}" if r["step"] else "skip    ")
              + f" {r['title']}\n       {r['action']}")


def untriaged(issues, items):
    """Open issues that are not on the board, carry `triage`, or lack a type or an estimate."""
    by_number = {i["number"]: i for i in items}
    out = []
    for issue in issues:
        if "pull_request" in issue or issue.get("state", "open") != "open":
            continue
        labels = [lbl["name"] for lbl in issue.get("labels", [])]
        it = by_number.get(issue["number"])
        reasons = []
        if not it:
            reasons.append("not on the board")
        else:
            if not it.get(F_TYPE):
                reasons.append("no item type")
            elif it.get(F_TYPE) != "Epic" and it.get(F_EFFORT) is None and "needs-human" not in labels:
                reasons.append("no estimate")
        if "triage" in labels:
            reasons.append("labelled triage")
        if reasons:
            out.append({"number": issue["number"], "title": issue["title"], "url": issue.get("html_url"),
                        "author": (issue.get("user") or {}).get("login"),
                        "association": issue.get("author_association"), "labels": labels,
                        "created": issue.get("created_at"), "comments": issue.get("comments", 0),
                        "waiting_info": "needs-info" in labels, "reasons": reasons,
                        "body": (issue.get("body") or "")[:1500]})
    return out


def cmd_untriaged(a):
    ctx = gh_ctx()
    issues, page = [], 1
    while True:
        batch = rest("GET", f"repos/{ctx['repo']}/issues?state=open&per_page=100&page={page}")
        if not batch:
            break
        issues += batch
        page += 1
    out = untriaged(issues, load_items(ctx))
    if a.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return
    if not out:
        print("✔ every open issue is on the board, typed and estimated")
    for i in out:
        print(f"#{i['number']:<5} {i['title']}  [{', '.join(i['reasons'])}]"
              + ("  (waiting for info)" if i["waiting_info"] else ""))


CC_RE = re.compile(r"^(?P<type>[a-zA-Z]+)(?:\((?P<scope>[^)]*)\))?(?P<bang>!)?:\s*(?P<desc>.+)$")
RELEASE_GROUPS = [("Breaking", None), ("Added", "feat"), ("Fixed", "fix"), ("Changed", "perf"),
                  ("Changed", "refactor"), ("Changed", "revert"), ("Security", "security")]
INTERNAL_TYPES = {"docs", "chore", "test", "tests", "ci", "build", "style"}


def parse_commit(subject, body=""):
    m = CC_RE.match(subject.strip())
    pr = re.search(r"\(#(\d+)\)\s*$", subject)
    desc = re.sub(r"\s*\(#\d+\)\s*$", "", m.group("desc") if m else subject.strip())
    return {"type": m.group("type").lower() if m else None, "scope": m.group("scope") if m else None,
            "breaking": bool(m and m.group("bang")) or "BREAKING CHANGE" in (body or ""),
            "description": desc, "pr": int(pr.group(1)) if pr else None}


def next_version(current, commits):
    major, minor, patch = (list(vtuple(current)) + [0, 0, 0])[:3]
    if any(c["breaking"] for c in commits):
        return f"{major + 1}.0.0" if major > 0 else f"0.{minor + 1}.0"
    if any(c["type"] == "feat" for c in commits):
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def release_notes(commits, version, date):
    groups = defaultdict(list)
    for c in commits:
        if c["breaking"]:
            name = "Breaking"
        elif c["type"] in INTERNAL_TYPES:
            continue
        else:
            name = next((g for g, t in RELEASE_GROUPS if t and t == c["type"]), "Other")
        groups[name].append(c)
    lines = [f"## {version} — {date}"]
    for name in ["Breaking", "Added", "Fixed", "Changed", "Security", "Other"]:
        if groups[name]:
            lines += ["", f"### {name}"]
            for c in groups[name]:
                lines.append(f"- {(c['scope'] + ': ') if c['scope'] else ''}{c['description']}"
                             + (f" (#{c['pr']})" if c["pr"] else ""))
    return "\n".join(lines)


def cmd_release_notes(a):
    since = a.since or run(["git", "describe", "--tags", "--abbrev=0", "--match", "v[0-9]*"],
                           check=False).stdout.strip()
    log = run(["git", "log", "--format=%H%x1f%s%x1f%b%x1e", *([f"{since}..HEAD"] if since else [])]).stdout
    commits = []
    for rec in log.split("\x1e"):
        parts = rec.strip("\n").split("\x1f")
        if len(parts) >= 2 and parts[1]:
            commits.append(dict(parse_commit(parts[1], parts[2] if len(parts) > 2 else ""), sha=parts[0][:9]))
    current = a.current or (since.lstrip("v") if re.match(r"^v?\d+\.\d+", since or "") else "0.0.0")
    version = a.version or next_version(current, commits)
    notes = release_notes(commits, version, today().isoformat())
    if a.json:
        print(json.dumps({"since": since or None, "current": current, "version": version, "commits": commits,
                          "notes": notes}, indent=2, ensure_ascii=False))
    else:
        print(notes if commits else f"no commit since {since or 'the beginning'}")


# --------------------------------------------------------------------------- drift / changelog / migrations

def lock_path(root=None):
    return (root or ROOT) / ".fw" / "framework.lock.json"


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def owned_files(root=None):
    root = root or ROOT
    owned, _ = manifest(root)
    return sorted(f for f in repo_files(root) if matches(f, owned) and "__pycache__" not in f
                  and (root / f).is_file())


def write_lock(root, version):
    """Baseline of the framework-owned files as installed/updated, to detect local edits later."""
    save_json(lock_path(root), {"version": version,
                                "files": {f: file_hash(root / f) for f in owned_files(root)}})


def drift(root=None):
    """{'modified', 'added', 'deleted'} framework-owned files since the last install/update, or None."""
    root = root or ROOT
    lock = load_json(lock_path(root), None)
    if lock is None:
        return None
    base, cur = lock.get("files", {}), {f: file_hash(root / f) for f in owned_files(root)}
    return {"modified": sorted(f for f in base if f in cur and cur[f] != base[f]),
            "added": sorted(f for f in cur if f not in base),
            "deleted": sorted(f for f in base if f not in cur)}


def cmd_drift(a):
    d = drift()
    if a.json:
        print(json.dumps(d, indent=2))
    elif d is None:
        print("no baseline (.fw/framework.lock.json) — it is written by `fw install` and `fw update --apply`")
    elif not any(d.values()):
        print("✔ framework-owned files match the installed version")
    else:
        for kind in ("modified", "added", "deleted"):
            for f in d[kind]:
                print(f"{kind:<8} {f}")
        print("\nFramework-owned files are replaced by /fw-update: move these changes to the upstream template, "
              "or put project-specific behaviour in CLAUDE.md, .claude/agents/ or docs/.")
    sys.exit(1 if d and any(d.values()) else 0)


def vtuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:3]) or (0,)


def changelog_between(text, old, new):
    """The CHANGELOG sections with old < version <= new, newest first, as written."""
    out, keep = [], False
    for line in (text or "").splitlines():
        m = re.match(r"^## \[?(\d+(?:\.\d+)*)", line)
        if m:
            keep = vtuple(old) < vtuple(m.group(1)) <= vtuple(new)
        elif line.startswith("## "):
            keep = False
        if keep:
            out.append(line)
    return "\n".join(out).strip()


GUARD_CMD = 'python3 "$CLAUDE_PROJECT_DIR/framework/hooks/guard.py"'


def mig_guard_file_hook(root, apply):
    """Projects updated to 0.4.0 by an older fw (hooks merged by command only) lack the Edit/Write guard."""
    path = root / ".claude" / "settings.json"
    s = load_json(path, {})
    pre = s.get("hooks", {}).get("PreToolUse", [])
    if any("Edit" in (e.get("matcher") or "") and any("framework/hooks/guard.py" in (h.get("command") or "")
                                                      for h in e.get("hooks", [])) for e in pre):
        return False
    if apply:
        s.setdefault("hooks", {}).setdefault("PreToolUse", []).append(
            {"matcher": "Edit|Write|MultiEdit|NotebookEdit", "hooks": [{"type": "command", "command": GUARD_CMD}]})
        save_json(path, s)
    return True


def mig_lock(root, apply):
    """Projects updated by an fw older than 0.5.0 have no baseline for `fw drift`."""
    if lock_path(root).exists():
        return False
    if apply:
        write_lock(root, (root / "framework" / "VERSION").read_text().strip())
    return True


# (version, description, fn(root, apply) -> changed?). Append only; every function must be idempotent.
MIGRATIONS = [
    ("0.4.0", "guard hook on Edit / Write / MultiEdit / NotebookEdit in .claude/settings.json", mig_guard_file_hook),
    ("0.5.0", "baseline of the framework-owned files (.fw/framework.lock.json)", mig_lock),
]


def cmd_migrate(a):
    c = cfg()
    done = dig(c, "framework.migrated") or "0"
    pending = [m for m in MIGRATIONS if vtuple(m[0]) > vtuple(done)]
    for version, desc, fn in pending:
        changed = fn(ROOT, not a.dry_run)
        print(f"{'✔' if changed and not a.dry_run else ('→' if changed else '·')} {version}: {desc}"
              + ("" if changed else " (already in place)"))
    if not pending:
        print(f"no migration pending (migrated up to {done})")
    if not a.dry_run:
        current = (ROOT / "framework" / "VERSION").read_text().strip()
        if c.get("framework", {}).get("migrated") != current:
            c.setdefault("framework", {})["migrated"] = current
            save_json(CONFIG, c)


# --------------------------------------------------------------------------- CLI

def main():
    p = argparse.ArgumentParser(prog="fw", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("doctor", help="check the machine and GitHub access")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_doctor)

    s = sub.add_parser("config", help="read / write .fw/config.json (dotted keys, JSON values)")
    s.add_argument("action", choices=["get", "set"])
    s.add_argument("key", nargs="?")
    s.add_argument("value", nargs="?")
    s.set_defaults(fn=cmd_config)

    s = sub.add_parser("autonomy", help="switch between assisted and fully automatic mode")
    s.add_argument("mode", choices=["assisted", "auto"])
    s.set_defaults(fn=cmd_autonomy)

    s = sub.add_parser("github-setup", help="create/link repo + Project v2, fields, status columns, labels")
    s.add_argument("--repo", help="name or owner/name (default: folder name under your account)")
    s.add_argument("--owner", help="account or organisation (default: authenticated user)")
    s.add_argument("--create-repo", action="store_true")
    s.add_argument("--visibility", choices=["private", "public", "internal"], default="private")
    s.add_argument("--description")
    s.add_argument("--title", help="project title (default: repo name)")
    s.add_argument("--template", help="copy an existing project owner/number (keeps its views)")
    s.add_argument("--new-project", action="store_true", help="ignore the configured project and create one")
    s.add_argument("--project", type=int, help="reuse this existing project number of the owner")
    s.add_argument("--restore-status", action="store_true",
                   help="only re-apply the statuses saved in .fw/local/status-backup.json")
    s.add_argument("--fix-status", action="store_true",
                   help="(re)apply the Backlog/Ready/In progress/In review/Done columns, keeping item statuses")
    s.set_defaults(fn=cmd_github_setup)

    s = sub.add_parser("protect", help="protect the default branch on GitHub (ruleset: PR required, no force push)")
    s.add_argument("--repo", help="owner/name (default: github.repo from the config)")
    s.add_argument("--checks", help="comma-separated required status checks (default: keep the configured ones)")
    s.add_argument("--approvals", type=int, help="required approving reviews (default 0: the agent and you share "
                                                  "one account, and GitHub forbids approving your own PR)")
    s.add_argument("--check", action="store_true", help="only report whether the ruleset exists")
    s.set_defaults(fn=cmd_protect)

    s = sub.add_parser("views-check", help="verify the Board and Roadmap views exist")
    s.set_defaults(fn=cmd_views_check)

    s = sub.add_parser("import-issues", help="add the repo's open issues to the project")
    s.set_defaults(fn=cmd_import_issues)

    s = sub.add_parser("backlog-validate", help="check a backlog JSON file against the story standard")
    s.add_argument("file")
    s.set_defaults(fn=cmd_backlog_validate)

    s = sub.add_parser("backlog-apply", help="create milestones, epics and stories on GitHub (idempotent)")
    s.add_argument("file")
    s.add_argument("--dry-run", action="store_true", help="render the issue bodies without calling GitHub")
    s.set_defaults(fn=cmd_backlog_apply)

    s = sub.add_parser("schedule", help="compute start/target dates from estimates and dependencies")
    s.add_argument("--apply", action="store_true", help="write the dates to the project and milestones")
    s.add_argument("--start", help="YYYY-MM-DD (default: capacity.start_date or today)")
    s.add_argument("--markdown", help="also write a Markdown roadmap to this path")
    s.set_defaults(fn=cmd_schedule)

    s = sub.add_parser("next", help="list the items ready to be worked on, best first")
    s.add_argument("--limit", type=int, default=5)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_next)

    s = sub.add_parser("start", help="→ In progress, start the timer (refuses an item already in progress)")
    s.add_argument("issue", type=int)
    s.add_argument("--force", action="store_true", help="take over an item already in progress / in review")
    s.set_defaults(fn=cmd_start)

    s = sub.add_parser("review", help="→ In review")
    s.add_argument("issue", type=int)
    s.set_defaults(fn=cmd_review)

    s = sub.add_parser("done", help="→ Done: close, record actual hours, unblock dependents, close epic")
    s.add_argument("issue", type=int)
    s.add_argument("--actual", type=float, help="agent hours (default: measured from fw start / review / escalate)")
    s.add_argument("--rounds", type=int, help="review rounds the item needed (1 = approved first time)")
    s.set_defaults(fn=cmd_done)

    s = sub.add_parser("pipeline", help="review pipeline: on/off, or whether the implementer may start a new item")
    s.add_argument("action", nargs="?", choices=["status", "on", "off"], default="status")
    s.add_argument("--wip", type=int, help=f"items allowed in review at once (default {DEFAULT_REVIEW_WIP})")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_pipeline)

    s = sub.add_parser("worktree", help="one git worktree per item, next to the repository (<repo>.worktrees/)")
    s.add_argument("action", choices=["add", "list", "remove"])
    s.add_argument("issue", type=int, nargs="?")
    s.add_argument("--branch", help="branch name (default: feat|fix|chore|hotfix/<n>-<slug>)")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_worktree)

    s = sub.add_parser("rework", help="→ In progress again after changes were requested (resumes the agent timer)")
    s.add_argument("issue", type=int)
    s.set_defaults(fn=cmd_rework)

    s = sub.add_parser("resume", help="interrupted items (in progress / in review) and where /fw-work picks them up")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_resume)

    s = sub.add_parser("untriaged", help="open issues not on the board, labelled triage, or without type/estimate")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_untriaged)

    s = sub.add_parser("release-notes", help="Conventional Commits since the last v* tag → notes and next version")
    s.add_argument("--since", help="tag or ref (default: the latest v* tag)")
    s.add_argument("--current", help="current version (default: from the tag)")
    s.add_argument("--version", help="force the next version")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_release_notes)

    s = sub.add_parser("metrics", help="estimates vs actuals, review rounds and waits of done items (for /fw-retro)")
    s.add_argument("--milestone", help="title or number")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_metrics)

    s = sub.add_parser("set-status", help="move an issue to a status (backlog|ready|in progress|in review|done)")
    s.add_argument("issue", type=int)
    s.add_argument("status")
    s.set_defaults(fn=cmd_set_status)

    s = sub.add_parser("set-field", help="set a project field on an issue")
    s.add_argument("issue", type=int)
    s.add_argument("field")
    s.add_argument("value")
    s.set_defaults(fn=cmd_set_field)

    s = sub.add_parser("status", help="progress summary")
    s.add_argument("--json", action="store_true", help="machine-readable summary (see `fw schema`)")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("schema", help="machine-readable contract: field names, statuses, markers, versions")
    s.add_argument("--json", action="store_true", help="(default) JSON output")
    s.set_defaults(fn=cmd_schema)

    s = sub.add_parser("escalate", help="post a structured question on an issue and label it needs-human")
    s.add_argument("issue", type=int)
    s.add_argument("--kind", choices=ESC_KINDS, default="question")
    s.add_argument("--question", required=True)
    s.add_argument("--option", action="append", help="repeat for each option, recommended first")
    s.add_argument("--recommended", type=int, help="index of the recommended option (0-based)")
    s.add_argument("--multi", action="store_true", help="several options may be chosen")
    s.add_argument("--pr", type=int, help="pull request the question is about")
    s.add_argument("--context", help="extra explanation shown under the question")
    s.add_argument("--source", default="fw-work", help="command that escalated (default fw-work)")
    s.set_defaults(fn=cmd_escalate)

    s = sub.add_parser("answer", help="answer the latest open escalation of an issue")
    s.add_argument("issue", type=int)
    s.add_argument("text")
    s.add_argument("--id", help="escalation id (default: the latest open one)")
    s.set_defaults(fn=cmd_answer)

    s = sub.add_parser("resolve", help="mark an escalation resolved (removes needs-human when none is left)")
    s.add_argument("issue", type=int)
    s.add_argument("--id", help="escalation id (default: the latest open or answered one)")
    s.add_argument("--answer", help="record this answer at the same time")
    s.set_defaults(fn=cmd_resolve)

    s = sub.add_parser("escalations", help="list open / answered escalations (all needs-human issues or one)")
    s.add_argument("--issue", type=int)
    s.add_argument("--all", action="store_true", help="include resolved ones")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_escalations)

    s = sub.add_parser("workflow", help="install a GitHub Actions workflow from framework/templates/workflows")
    s.add_argument("action", choices=["list", "install"])
    s.add_argument("name", nargs="?", help="e.g. ci-node, ci-php, ci-python, ci-go, ci-generic, cloud-run, docs")
    s.add_argument("--force", action="store_true")
    s.add_argument("--env", action="append", metavar="KEY=VALUE", help="set a variable of the workflow's env block")
    s.set_defaults(fn=cmd_workflow)

    s = sub.add_parser("check", help="run the project's lint / typecheck / test / build commands (the quality gate)")
    s.add_argument("steps", nargs="*", help=f"only these ({', '.join(COMMAND_KEYS)}); default: every configured "
                                            f"one of {', '.join(CHECK_STEPS)}")
    s.add_argument("--if-configured", action="store_true", help="skip steps with no command instead of failing")
    s.add_argument("--fail-fast", action="store_true")
    s.add_argument("--json", action="store_true", help="capture output; print results as JSON")
    s.set_defaults(fn=cmd_check)

    s = sub.add_parser("commands", help="show, or detect from the repository, the project's commands")
    s.add_argument("--detect", action="store_true")
    s.add_argument("--apply", action="store_true", help="with --detect: add the missing commands to the config")
    s.set_defaults(fn=cmd_commands)

    s = sub.add_parser("lint-agents", help="check .claude/agents/*.md against the agent quality standard")
    s.set_defaults(fn=cmd_lint_agents)

    s = sub.add_parser("docs-check", help="find broken relative links in docs/, CLAUDE.md, README.md")
    s.set_defaults(fn=cmd_docs_check)

    s = sub.add_parser("install", help="install the framework into an existing project directory")
    s.add_argument("target")
    s.set_defaults(fn=cmd_install)

    s = sub.add_parser("drift", help="framework-owned files changed locally since the last install/update")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_drift)

    s = sub.add_parser("migrate", help="run the pending config/settings migrations (fw update --apply does it)")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(fn=cmd_migrate)

    s = sub.add_parser("update", help="pull framework-owned files from the upstream template")
    s.add_argument("--apply", action="store_true")
    s.add_argument("--upstream")
    s.add_argument("--branch")
    s.set_defaults(fn=cmd_update)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
