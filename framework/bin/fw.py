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


def canon_status(name):
    n = (name or "").strip().lower()
    return {"todo": "ready", "to do": "ready", "doing": "in progress", "review": "in review"}.get(n, n or "backlog")


def manifest(src_root=ROOT):
    owned, scaffold = [], []
    for line in (src_root / "framework" / "MANIFEST").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        kind, pat = line.split(None, 1)
        (owned if kind == "owned" else scaffold).append(pat)
    return owned, scaffold


def matches(path, patterns):
    return any(fnmatch.fnmatch(path, p) for p in patterns)


def repo_files(root=ROOT):
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
    if g.get("project_id") and g.get("repo") == repo and not a.new_project:
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

    if created:
        wanted = [{"name": n, "color": col, "description": d} for n, col, d in STATUS_OPTIONS]
        ok = graphql("""mutation($f:ID!,$o:[ProjectV2SingleSelectFieldOptionInput!]){
            updateProjectV2Field(input:{fieldId:$f,singleSelectOptions:$o}){
            projectV2Field{ ... on ProjectV2SingleSelectField { id } } } }""",
                     check=False, f=fields[F_STATUS]["id"], o=wanted)
        if ok:
            print("✔ status columns: " + " → ".join(n for n, _, _ in STATUS_OPTIONS))
        else:
            warn("could not customise Status options through the API; defaults (Todo / In Progress / Done) are "
                 "kept and mapped automatically. Optional: add Backlog, Ready and In review in the project settings.")

    for lname, color, desc in LABELS:
        gh("label", "create", lname, "--color", color, "--description", desc, "--force", "-R", repo, check=False)
    print("✔ labels: " + ", ".join(n for n, _, _ in LABELS))

    g.update(owner=owner, owner_type=owner_type, repo=repo, repo_id=r["node_id"], project_id=pid,
             project_number=number, project_url=url, default_branch=r.get("default_branch") or "main")
    save_json(CONFIG, c)
    print(f"✔ saved to {CONFIG.relative_to(ROOT)}\n")
    views_report(pid)


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
        if eff <= 0:
            errors.append(f"{k}: agent_hours must be > 0")
        if rev < 0:
            errors.append(f"{k}: review_hours must be >= 0")
        expected = size_for(eff + rev)
        if expected == "XL" or s.get("size") == "XL":
            errors.append(f"{k}: XL ({eff + rev:g} h) is too big — split it into smaller stories")
        elif s.get("size") and s["size"] != expected:
            warns.append(f"{k}: size {s['size']} but {eff + rev:g} h suggests {expected}")
        if s.get("agent") and agents and s["agent"] not in agents:
            warns.append(f"{k}: agent '{s['agent']}' has no file in .claude/agents/")
        for d in as_list(s.get("depends_on")):
            if d not in stories and ref_number(d, done) is None:
                errors.append(f"{k}: unknown dependency '{d}'")

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
            f"| {eff:g} h | {rev:g} h | {s.get('size') or size_for(eff + rev)} | {s.get('agent') or '—'} |", ""]
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
        issue = create(s, render_story(s, h, deps), [t.lower()] + as_list(s.get("labels")), t, ms, {
            F_PRIO: s.get("priority", "Should"), F_SIZE: s.get("size") or size_for(eff + rev),
            F_EFFORT: eff, F_REVIEW: rev, F_AGENT: s.get("agent")}, "backlog" if deps else "ready")
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
    e = it.get(F_EFFORT)
    return (float(e) if e is not None else DEFAULT_EFFORT) + float(it.get(F_REVIEW) or 0)


def compute_schedule(items, capacity, start=None):
    hpd = float(capacity.get("hours_per_day", 6))
    lanes = max(1, int(capacity.get("parallel_lanes", 1)))
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

    def key(n):
        i = pending[n]
        return (0 if i["status"] in ("in progress", "in review") else 1, PRIO_RANK.get(i.get(F_PRIO), 1), n)

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

    cursor, ends, plan = [0.0] * lanes, {}, {}
    for n in order:
        earliest = max([ends.get(d, 0.0) for d in deps[n]] or [0.0])
        lane = min(range(lanes), key=lambda k: max(cursor[k], earliest))
        s = max(cursor[lane], earliest)
        e = s + effort(pending[n])
        cursor[lane] = ends[n] = e
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


def cmd_schedule(a):
    c = cfg()
    ctx = gh_ctx()
    items = load_items(ctx)
    start = parse_date(a.start) if a.start else (parse_date(c["capacity"]["start_date"])
                                                 if dig(c, "capacity.start_date") else None)
    plan, cyclic, missing = compute_schedule(items, c.get("capacity", {}), start)
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
    for m, e in sorted(ms_end.items(), key=lambda kv: kv[1]):
        print(f"milestone {titles.get(m)}: {e}")

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
            lines += [f"## {title}", "", "| # | Type | Priority | Effort (h) | Start | Target | Title |",
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
    return sorted(out, key=lambda i: (PRIO_RANK.get(i.get(F_PRIO), 1), i.get(F_START) or "9999", i["number"]))


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


def cmd_start(a):
    ctx = gh_ctx()
    _, it = get_item(ctx, a.issue)
    set_item_field(ctx, project_fields(ctx["project_id"]), it["item_id"], F_STATUS, "in progress")
    t = timers()
    t.setdefault(str(a.issue), dt.datetime.now().isoformat(timespec="seconds"))
    save_json(LOCAL / "timers.json", t)
    print(f"#{a.issue} → In progress ({it['title']})")


def cmd_review(a):
    ctx = gh_ctx()
    _, it = get_item(ctx, a.issue)
    set_item_field(ctx, project_fields(ctx["project_id"]), it["item_id"], F_STATUS, "in review")
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
    started = t.pop(str(a.issue), None)
    if a.actual is not None or started:
        hours = a.actual if a.actual is not None else round(
            (dt.datetime.now() - dt.datetime.fromisoformat(started)).total_seconds() / 3600, 1)
        set_item_field(ctx, fields, it["item_id"], F_ACTUAL, hours)
        print(f"#{a.issue} actual: {hours:g} h (estimated {effort(it):g} h)")
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


def cmd_status(a):
    ctx = gh_ctx()
    items = load_items(ctx)
    work = [i for i in items if i.get(F_TYPE) != "Epic"]
    by = defaultdict(list)
    for i in work:
        by["done" if i["state"] == "CLOSED" else i["status"]].append(i)
    total = sum(effort(i) for i in work)
    done_h = sum(effort(i) for i in by["done"])
    actual = [(effort(i), float(i[F_ACTUAL])) for i in by["done"] if i.get(F_ACTUAL) is not None]
    print(f"Project: {ctx['project_url']}")
    print("Items:   " + ", ".join(f"{k}: {len(v)}" for k, v in sorted(by.items())))
    print(f"Effort:  {done_h:g} / {total:g} h done ({(100 * done_h / total) if total else 0:.0f}%), "
          f"{total - done_h:g} h remaining")
    if actual:
        est, act = sum(x for x, _ in actual), sum(y for _, y in actual)
        print(f"Accuracy: {act:g} h actual vs {est:g} h estimated on {len(actual)} item(s) (ratio {act / est:.2f})")
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

INSTALL_EXCLUDE = (".git/", ".fw/local/", ".fw/state.json", ".fw/backlog/", ".claude/settings.local.json", "site/")


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
        known = {h.get("command") for e in cur for h in e.get("hooks", [])}
        for e in entries:
            if not any(h.get("command") in known for h in e.get("hooks", [])):
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
    save_json(dst / ".fw" / "config.json", conf)
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
    print(run(["git", "diff", "--stat", "HEAD", "FETCH_HEAD", "--", *owned], check=False).stdout.strip()
          or "no difference in framework-owned files")
    if removed:
        print("removed upstream: " + ", ".join(removed))
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
    print("\n✔ framework files updated — review `git diff --staged`, run `fw lint-agents`, then commit.")


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
    s.set_defaults(fn=cmd_github_setup)

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

    for name, fn, hlp in (("start", cmd_start, "→ In progress, start the timer"),
                          ("review", cmd_review, "→ In review")):
        s = sub.add_parser(name, help=hlp)
        s.add_argument("issue", type=int)
        s.set_defaults(fn=fn)

    s = sub.add_parser("done", help="→ Done: close, record actual hours, unblock dependents, close epic")
    s.add_argument("issue", type=int)
    s.add_argument("--actual", type=float, help="actual hours (default: time since `fw start`)")
    s.set_defaults(fn=cmd_done)

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
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("lint-agents", help="check .claude/agents/*.md against the agent quality standard")
    s.set_defaults(fn=cmd_lint_agents)

    s = sub.add_parser("docs-check", help="find broken relative links in docs/, CLAUDE.md, README.md")
    s.set_defaults(fn=cmd_docs_check)

    s = sub.add_parser("install", help="install the framework into an existing project directory")
    s.add_argument("target")
    s.set_defaults(fn=cmd_install)

    s = sub.add_parser("update", help="pull framework-owned files from the upstream template")
    s.add_argument("--apply", action="store_true")
    s.add_argument("--upstream")
    s.add_argument("--branch")
    s.set_defaults(fn=cmd_update)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
