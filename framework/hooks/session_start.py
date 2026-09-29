#!/usr/bin/env python3
"""SessionStart hook: a few lines of context so every session knows where the project stands.

Local only (no network) so it stays instant. Whatever is printed is added to Claude's context.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

try:
    c = json.loads((ROOT / ".fw" / "config.json").read_text(encoding="utf-8"))
except (OSError, ValueError):
    c = {}

if not c.get("initialized"):
    print("[framework] This project is NOT initialized yet. Before any other work, suggest running /fw-init "
          "(new project or adoption of an existing codebase).")
else:
    g = c.get("github", {})
    agents = sorted(p.stem for p in (ROOT / ".claude" / "agents").glob("*.md"))
    print(f"[framework] project={c.get('name', ROOT.name)} language={c.get('language', 'en')} "
          f"issues={c.get('issue_language', c.get('language', 'en'))} autonomy={c.get('autonomy', 'assisted')}")
    print(f"[framework] repo={g.get('repo')} board={g.get('project_url')}")
    print(f"[framework] agents={', '.join(agents) or 'none'} roles={json.dumps(c.get('roles', {}))}")
    print("[framework] commands: /fw-status, /fw-work, /fw-backlog <request>, /fw-plan, /fw-docs")
