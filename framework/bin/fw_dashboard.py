"""Renderers for `fw dashboard`: terminal text and a self-contained HTML page.

Pure functions of the data built by `fw.dashboard_data()` — no network, no external assets.
Everything coming from GitHub (titles, labels, URLs) is escaped before it reaches the page.
"""
import datetime as dt
import html

HEALTH = {"done": ("✔", "done", 32), "on track": ("✔", "ok", 32), "at risk": ("!", "warn", 33),
          "late": ("✘", "bad", 31), "no due date": ("·", "muted", 90)}


def pct(done, total):
    return 0 if not total else round(100 * done / total)


def num(x):
    return f"{x:g}" if isinstance(x, (int, float)) else "—"


# --------------------------------------------------------------------------- terminal

def bar(frac, width=20):
    full = max(0, min(width, round(frac * width)))
    return "█" * full + "░" * (width - full)


def render_text(d, color=False):
    def c(text, code):
        return f"\033[{code}m{text}\033[0m" if color else text

    p = d["progress"]
    out = [c(f"━━ {d['project']} — {d['today']} ━━", 1)]
    out.append(f"Progress   {bar(p['hours_done'] / p['hours'] if p['hours'] else 0)} "
               f"{pct(p['hours_done'], p['hours']):>3}%  {p['done']}/{p['items']} items · "
               f"{num(p['hours_done'])}/{num(p['hours'])} h"
               + (f" · planned end {p['projected_end']}" if p["projected_end"] else ""))
    v = d["velocity"]
    if v["hours_per_week"]:
        out.append(f"Pace       {num(v['hours_per_week'])} h/week over the last 4 weeks"
                   + (f" → at this pace, done by {v['forecast_end']}" if v["forecast_end"] else ""))
    if d["milestones"]:
        out += ["", c("Milestones", 1)]
        width = max(len(m["title"]) for m in d["milestones"])
        for m in d["milestones"]:
            icon, _, code = HEALTH[m["health"]]
            out.append(f"  {m['title']:<{width}}  {bar(m['hours_done'] / m['hours'] if m['hours'] else 0, 14)} "
                       f"{pct(m['hours_done'], m['hours']):>3}%  {m['done']}/{m['items']}"
                       + (f"  due {m['due']}" if m["due"] else "")
                       + (f"  planned {m['target']}" if m["target"] else "")
                       + "  " + c(f"{icon} {m['health']}", code))
    if d["epics"]:
        out += ["", c("Epics", 1)]
        for e in d["epics"]:
            out.append(f"  {bar(e['hours_done'] / e['hours'] if e['hours'] else 0, 10)} "
                       f"{pct(e['hours_done'], e['hours']):>3}%  #{e['number']} {e['title']}  ({e['done']}/{e['items']})")
    f = d["flow"]
    out += ["", "Flow       " + " · ".join(f"{k} {n}" for k, n in f.items())]
    for i in d["hotfixes"]:
        out.append(c(f"Hotfix     #{i['number']} {i['title']} [{i['status']}]", 31))
    for i in d["in_flight"]:
        out.append(f"In flight  #{i['number']} {i['title']} [{i['status']}]")
    for i in d["needs_you"]:
        out.append(c(f"Needs you  #{i['number']} {i['title']}", 33))
    pl = d["pipeline"]
    if pl.get("enabled"):
        out.append(f"Pipeline   {pl['reason']}")
    if d["upcoming"]:
        out += ["", c("Next up", 1)]
        for i in d["upcoming"][:6]:
            out.append(f"  {i['start']} → {i['target'] or '?'}  #{i['number']} {i['title']}"
                       + (f"  ({i['agent']})" if i.get("agent") else ""))
    e = d["estimates"]
    if e["ratio"] is not None:
        rr = e["review_rounds"]
        out += ["", f"Estimates  actual/estimate {e['ratio']:.2f} on {e['measured']} item(s)"
                + (f" · {num(rr['average'])} review rounds avg" if rr else "")
                + (f" · median wait {num(e['wait']['median'])} h" if e["wait"] else "")]
    if d["custom"]:
        out += ["", c("Project metrics", 1)]
        for m in d["custom"]:
            if m.get("error"):
                out.append(f"  {m['title']}: " + c(f"error — {m['error']}", 31))
                continue
            mark = "" if "ok" not in m else ("  " + (c("✔", 32) if m["ok"] else c("✘", 31)))
            out.append(f"  {m['title']}: {num(m['value'])}{(' ' + m['unit']) if m.get('unit') else ''}"
                       + (f" (target {num(m['target'])})" if m.get("target") is not None else "") + mark)
    out += ["", "HTML version: framework/bin/fw dashboard --html --open"]
    return "\n".join(out)


# --------------------------------------------------------------------------- HTML

def e(x):
    return html.escape(str(x if x is not None else ""), quote=True)


def link(i):
    label = f"#{i['number']}"
    return f'<a href="{e(i["url"])}">{label}</a>' if i.get("url", "").startswith("https://") else label


def progress(done, total, cls=""):
    p = pct(done, total)
    return (f'<div class="bar {cls}" role="progressbar" aria-valuenow="{p}" aria-valuemin="0" '
            f'aria-valuemax="100"><span style="width:{p}%"></span></div>')


def burnup_svg(points):
    if len(points) < 2:
        return '<p class="muted">Not enough history yet — the chart appears after the first week.</p>'
    w, h, pad_l, pad_b, pad_t = 640, 220, 44, 28, 10
    top = max(p["scope"] for p in points) or 1
    x = lambda k: pad_l + k * (w - pad_l - 24) / (len(points) - 1)  # noqa: E731
    y = lambda v: pad_t + (h - pad_t - pad_b) * (1 - v / top)  # noqa: E731
    scope = " ".join(f"{x(k):.1f},{y(p['scope']):.1f}" for k, p in enumerate(points))
    done = " ".join(f"{x(k):.1f},{y(p['done']):.1f}" for k, p in enumerate(points))
    area = f"{x(0):.1f},{y(0):.1f} {done} {x(len(points) - 1):.1f},{y(0):.1f}"
    step = max(1, len(points) // 6)
    labels = "".join(f'<text x="{x(k):.1f}" y="{h - 8}" text-anchor="middle">{e(p["week"][5:])}</text>'
                     for k, p in enumerate(points)
                     if (k % step == 0 and len(points) - 1 - k >= step / 2) or k == len(points) - 1)
    grid = "".join(f'<line x1="{pad_l}" x2="{w - 8}" y1="{y(top * f):.1f}" y2="{y(top * f):.1f}"/>'
                   f'<text x="{pad_l - 6}" y="{y(top * f) + 4:.1f}" text-anchor="end">{top * f:g}</text>'
                   for f in (0, 0.5, 1))
    return (f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="Burn-up: scope and done hours per week">'
            f'<g class="grid">{grid}</g><g class="axis">{labels}</g>'
            f'<polygon class="done-area" points="{area}"/>'
            f'<polyline class="scope" points="{scope}"/><polyline class="done" points="{done}"/></svg>'
            '<p class="legend"><span class="k scope"></span>scope (h) <span class="k done"></span>done (h)</p>')


def timeline(items, today=None):
    rows = [i for i in items if i.get("start")]
    if not rows:
        return '<p class="muted">Nothing scheduled — run <code>fw schedule --apply</code>.</p>'
    d0 = min(dt.date.fromisoformat(i["start"]) for i in rows)
    d1 = max(dt.date.fromisoformat(i["target"] or i["start"]) for i in rows)
    span = max(1, (d1 - d0).days + 1)
    out = []
    t = dt.date.fromisoformat(today) if today else None
    marker = (f'<span class="today" style="left:{100 * (t - d0).days / span:.2f}%" title="today"></span>'
              if t and d0 <= t <= d1 else "")
    for i in rows:
        s = (dt.date.fromisoformat(i["start"]) - d0).days
        n = (dt.date.fromisoformat(i["target"] or i["start"]) - dt.date.fromisoformat(i["start"])).days + 1
        out.append(f'<div class="trow"><div class="tlabel">{link(i)} {e(i["title"])}</div><div class="ttrack">'
                   f'<span class="tbar {e(i["status"].replace(" ", "-"))}" style="left:{100 * s / span:.2f}%;'
                   f'width:{max(1.5, 100 * n / span):.2f}%" title="{e(i["start"])} → {e(i["target"])}"></span>'
                   f'{marker}</div></div>')
    return (f'<div class="tscale"><span>{e(d0)}</span><span>{e(d1)}</span></div>' + "".join(out))


def item_list(items, empty):
    if not items:
        return f'<p class="muted">{e(empty)}</p>'
    return "<ul class='items'>" + "".join(
        f'<li>{link(i)} {e(i["title"])} <span class="pill {e(i["status"].replace(" ", "-"))}">{e(i["status"])}</span>'
        + (f' <span class="muted">{e(i["agent"])}</span>' if i.get("agent") else "") + "</li>" for i in items) + "</ul>"


def tile(label, value, sub="", cls=""):
    return (f'<div class="tile {cls}"><div class="tl">{e(label)}</div><div class="tv">{e(value)}</div>'
            f'<div class="ts">{e(sub)}</div></div>')


CSS = """
:root{--bg:#f7f7f5;--card:#fff;--fg:#1d1d1f;--muted:#6b6b70;--line:#e4e4e0;--accent:#2f6fde;--accent-soft:#2f6fde22;
--ok:#1f8a4c;--warn:#b7791f;--bad:#c53030;--track:#ececE8}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--card:#1e1e21;--fg:#ececef;--muted:#9a9aa2;--line:#2e2e33;
--accent:#6ea0ff;--accent-soft:#6ea0ff26;--ok:#4cc38a;--warn:#e0a84a;--bad:#f07171;--track:#2a2a2e}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 48px}a{color:var(--accent);text-decoration:none}
header{display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:16px}
h1{font-size:22px;margin:0}h2{font-size:15px;margin:0 0 12px}.muted{color:var(--muted)}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin-bottom:16px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:16px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.tl{font-size:12px;color:var(--muted)}.tv{font-size:22px;font-weight:600;margin-top:2px}.ts{font-size:12px;color:var(--muted)}
.tile.ok .tv{color:var(--ok)}.tile.bad .tv{color:var(--bad)}
.bar{height:10px;background:var(--track);border-radius:6px;overflow:hidden}
.bar span{display:block;height:100%;background:var(--accent);border-radius:6px}.bar.big{height:16px;margin:8px 0 4px}
table{width:100%;border-collapse:collapse}td,th{padding:7px 6px;border-top:1px solid var(--line);text-align:left;vertical-align:middle}
th{font-weight:500;color:var(--muted);font-size:12px;border-top:0}td.n{white-space:nowrap;text-align:right}
.pill{display:inline-block;font-size:11px;padding:1px 8px;border-radius:10px;background:var(--track);color:var(--muted)}
.pill.ok,.pill.done{background:#1f8a4c22;color:var(--ok)}.pill.warn{background:#b7791f22;color:var(--warn)}
.pill.bad{background:#c5303022;color:var(--bad)}.pill.in-progress,.pill.in-review{background:var(--accent-soft);color:var(--accent)}
.flow{display:flex;height:14px;border-radius:7px;overflow:hidden;margin:6px 0 8px}
.flow span{display:block}.f-backlog{background:#a0a0a8}.f-ready{background:#8fb3f0}.f-in-progress{background:var(--accent)}
.f-in-review{background:#9b6ee8}.f-done{background:var(--ok)}
.legend{font-size:12px;color:var(--muted);margin:6px 0 0}.k{display:inline-block;width:10px;height:10px;border-radius:2px;margin:0 4px 0 10px}
.k.scope{background:var(--muted)}.k.done{background:var(--accent)}
ul.items{list-style:none;padding:0;margin:0}ul.items li{padding:5px 0;border-top:1px solid var(--line)}
ul.items li:first-child{border-top:0}
svg.chart{width:100%;height:auto;overflow:visible}svg .grid line{stroke:var(--line)}svg text{fill:var(--muted);font-size:11px}
svg .scope{fill:none;stroke:var(--muted);stroke-width:2;stroke-dasharray:4 3}svg .done{fill:none;stroke:var(--accent);stroke-width:2.5}
svg .done-area{fill:var(--accent-soft)}
.tscale{display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-left:40%}
.trow{display:flex;align-items:center;gap:8px;padding:3px 0}.tlabel{width:40%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ttrack{position:relative;flex:1;height:12px;background:var(--track);border-radius:6px}
.today{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--bad);opacity:.6}
.tbar{position:absolute;top:0;height:100%;border-radius:6px;background:#8fb3f0}.tbar.in-progress,.tbar.in-review{background:var(--accent)}
@media (max-width:600px){.tlabel{width:50%}.tscale{margin-left:50%}}
"""


def render_html(d):
    p, v, est = d["progress"], d["velocity"], d["estimates"]
    done_pct = pct(p["hours_done"], p["hours"])
    tiles = [tile("Progress", f"{done_pct}%", f"{num(p['hours_done'])} / {num(p['hours'])} h"),
             tile("Items done", f"{p['done']} / {p['items']}", "stories, tasks and bugs"),
             tile("Planned end", p["projected_end"] or "—", "from the roadmap"),
             tile("Pace", f"{num(v['hours_per_week'])} h/wk", "last 4 weeks"),
             tile("Forecast", v["forecast_end"] or "—", "at the current pace")]
    if est["ratio"] is not None:
        tiles.append(tile("Actual / estimate", f"{est['ratio']:.2f}", f"agent time, {est['measured']} item(s)",
                          "ok" if 0.7 <= est["ratio"] <= 1.3 else "bad"))
    if d["needs_you"]:
        tiles.append(tile("Needs you", len(d["needs_you"]), "decisions or actions", "bad"))
    for m in d["custom"]:
        value = "error" if m.get("error") else f"{num(m['value'])}{(' ' + m['unit']) if m.get('unit') else ''}"
        sub = m.get("error") or (f"target {num(m['target'])}" if m.get("target") is not None else m.get("detail") or "")
        tiles.append(tile(m["title"], value, sub, "bad" if m.get("error") or m.get("ok") is False
                          else ("ok" if m.get("ok") else "")))

    ms_rows = "".join(
        f'<tr><td>{e(m["title"])}</td><td style="width:34%">{progress(m["hours_done"], m["hours"])}</td>'
        f'<td class="n">{pct(m["hours_done"], m["hours"])}% · {m["done"]}/{m["items"]}</td>'
        f'<td class="n">{e(m["due"] or "—")}</td><td class="n">{e(m["target"] or "—")}</td>'
        f'<td><span class="pill {HEALTH[m["health"]][1]}">{e(m["health"])}</span></td></tr>' for m in d["milestones"])
    milestones = (f'<table><tr><th>Milestone</th><th>Progress</th><th></th><th>Due</th><th>Planned</th><th></th></tr>'
                  f'{ms_rows}</table>' if ms_rows else '<p class="muted">No milestone yet.</p>')
    epics = "".join(f'<tr><td>{link(x)} {e(x["title"])}</td><td style="width:34%">{progress(x["hours_done"], x["hours"])}'
                    f'</td><td class="n">{x["done"]}/{x["items"]}</td></tr>' for x in d["epics"])
    total = sum(d["flow"].values()) or 1
    flow = "".join(f'<span class="f-{k.replace(" ", "-")}" style="width:{100 * n / total:.2f}%" title="{e(k)}: {n}">'
                   "</span>" for k, n in d["flow"].items() if n)
    flow_legend = " · ".join(f"{e(k)} <b>{n}</b>" for k, n in d["flow"].items())
    sizes = "".join(f'<tr><td>{e(k)}</td><td class="n">{g["items"]}</td><td class="n">{num(g["estimate"])} h</td>'
                    f'<td class="n">{num(g["actual"])} h</td><td class="n">{num(g["ratio"])}</td></tr>'
                    for k, g in (est.get("by_size") or {}).items())
    rr, wait = est.get("review_rounds"), est.get("wait")
    estimates = ("<p class='muted'>No measured item yet — numbers appear as stories are done.</p>" if est["ratio"] is None
                 else (f"<p>Review rounds: <b>{num(rr['average'])}</b> on average, {rr['first_time_approved']}/"
                       f"{rr['items']} approved first time.</p>" if rr else "")
                 + (f"<p>Waiting on you: median <b>{num(wait['median'])} h</b>, max {num(wait['max'])} h.</p>"
                    if wait else "")
                 + (f"<table><tr><th>Size</th><th>Items</th><th>Estimated</th><th>Actual</th><th>Ratio</th></tr>"
                    f"{sizes}</table>" if sizes else ""))
    pl = d["pipeline"]
    pipeline = (f'<p class="muted">Review pipeline: {e(pl["reason"])}</p>' if pl.get("enabled") else "")
    proj = (f'<a href="{e(d["project_url"])}">board</a> · ' if str(d.get("project_url") or "").startswith("https://")
            else "")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(d['project'])} — dashboard</title><style>{CSS}</style></head><body><main>
<header><h1>{e(d['project'])}</h1><div class="muted">{proj}{e(d.get('repo') or '')} · {e(d['autonomy'])} mode ·
framework {e(d['framework_version'])} · generated {e(d['generated'].replace('T', ' '))}</div></header>
<div class="card"><h2>Overall progress — {done_pct}%</h2>{progress(p['hours_done'], p['hours'], 'big')}
<div class="muted">{p['done']} of {p['items']} items · {num(p['hours_done'])} of {num(p['hours'])} hours done</div></div>
<div class="tiles">{''.join(tiles)}</div>
<div class="card"><h2>Milestones</h2>{milestones}</div>
<div class="grid2">
<div class="card"><h2>Burn-up</h2>{burnup_svg(d['burnup'])}</div>
<div class="card"><h2>Flow</h2><div class="flow">{flow}</div><div class="muted">{flow_legend}</div>{pipeline}
<h2 style="margin-top:16px">Hotfixes</h2>{item_list(d['hotfixes'], 'None.')}
<h2 style="margin-top:16px">In flight</h2>{item_list(d['in_flight'], 'Nothing in progress.')}
<h2 style="margin-top:16px">Needs you</h2>{item_list(d['needs_you'], 'Nothing waiting for you.')}</div>
</div>
<div class="card"><h2>Next up</h2>{timeline(d['upcoming'], d['today'])}</div>
<div class="grid2">
<div class="card"><h2>Epics</h2>{f'<table>{epics}</table>' if epics else '<p class="muted">No epic yet.</p>'}</div>
<div class="card"><h2>Estimates</h2>{estimates}</div>
</div>
</main></body></html>
"""
