#!/usr/bin/env python
"""Compare two snapshot folders written by snapshot.py.

Prints "N queries, N identical, N different" plus a field-by-field diff for every changed query,
writes a self-contained HTML report, and exits with code 1 if anything differs (0 if identical).

Usage:
    python tools/api_snapshot/compare.py /tmp/before /tmp/after [--report report.html]
"""
import argparse
import difflib
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

MAX_CHANGES_SHOWN = 20
MANIFEST = "_manifest.json"


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("before", help="snapshot folder of the old code")
    p.add_argument("after", help="snapshot folder of the new code")
    p.add_argument("--report", help="HTML report path (default: <after>/compare-report.html)")
    p.add_argument("--no-color", action="store_true", help="plain console output")
    return p.parse_args()


def load(folder):
    folder = Path(folder)
    if not folder.is_dir():
        sys.exit(f"error: {folder} is not a folder")
    snaps = {p.stem: json.loads(p.read_text()) for p in sorted(folder.glob("*.json")) if p.name != MANIFEST}
    if not snaps:
        sys.exit(f"error: no snapshot files in {folder}")
    manifest = json.loads((folder / MANIFEST).read_text()) if (folder / MANIFEST).exists() else {}
    return snaps, manifest


def changes(a, b, path="response"):
    """Yield (path, before, after) for every leaf that differs. Lists are compared by position,
    so a re-ordering of results is reported as a change."""
    if isinstance(a, dict) and isinstance(b, dict):
        for k in list(a) + [k for k in b if k not in a]:
            sub = f"{path}.{k}"
            if k not in b:
                yield sub, a[k], "(missing)"
            elif k not in a:
                yield sub, "(missing)", b[k]
            else:
                yield from changes(a[k], b[k], sub)
    elif isinstance(a, list) and isinstance(b, list):
        for i in range(max(len(a), len(b))):
            sub = f"{path}[{i}]"
            if i >= len(b):
                yield sub, a[i], "(missing)"
            elif i >= len(a):
                yield sub, "(missing)", b[i]
            else:
                yield from changes(a[i], b[i], sub)
    elif a != b or type(a) is not type(b):
        yield path, a, b


def same_json(a, b):
    """Equality on the JSON text, so true vs 1 or 1 vs 1.0 count as changes (Python's == says equal)."""
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def failed(snap):
    """A query that errored can't prove anything, even if both sides error the same way."""
    response = snap.get("response")
    return snap.get("http_status") != 200 or (isinstance(response, dict) and bool(response.get("errors")))


def count_values(value):
    """Number of individual data values (leaves) in a response, for the 'values compared' figure."""
    if isinstance(value, dict):
        return sum(count_values(v) for v in value.values())
    if isinstance(value, list):
        return sum(count_values(v) for v in value)
    return 1


def short(value, limit=120):
    text = value if isinstance(value, str) and value == "(missing)" else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def describe(manifest):
    v = manifest.get("versions", {})
    git = manifest.get("git", {})
    parts = []
    if v.get("Django"):
        parts.append(f"Django {v['Django']}")
    if v.get("graphene"):
        parts.append(f"Graphene {v['graphene']}")
    ref = git.get("ref") or git.get("commit")
    if ref:
        parts.append(f"({ref})")
    return " ".join(parts) or "unknown version"


def compare(before, after):
    rows = []
    for name in sorted(set(before) | set(after)):
        a, b = before.get(name), after.get(name)
        meta = a or b
        row = {"name": name, "screen": meta.get("screen", ""), "values": count_values(meta.get("response")),
               "changes": [], "unified": ""}
        if a is None or b is None:
            row["status"] = "only in before" if b is None else "only in after"
        elif same_json(a, b):
            row["status"] = "fails in both" if failed(a) else "identical"
        else:
            row["status"] = "different"
            row["changes"] = list(changes(a.get("response"), b.get("response")))
            if a.get("http_status") != b.get("http_status"):
                row["changes"].insert(0, ("http_status", a.get("http_status"), b.get("http_status")))
            row["unified"] = "".join(difflib.unified_diff(
                json.dumps(a, indent=2, ensure_ascii=False).splitlines(True),
                json.dumps(b, indent=2, ensure_ascii=False).splitlines(True),
                fromfile=f"before/{name}.json", tofile=f"after/{name}.json", n=2))
        rows.append(row)
    return rows


def print_console(rows, before_desc, after_desc, color):
    def c(code, text):
        return f"\033[{code}m{text}\033[0m" if color else text
    same = sum(r["status"] == "identical" for r in rows)
    print(f"Before: {before_desc}\nAfter:  {after_desc}\n")
    for r in rows:
        mark = c("32", "IDENTICAL") if r["status"] == "identical" else c("31;1", r["status"].upper())
        print(f"  {mark:<{20 if color else 9}}  {r['name']:<32} {r['screen']}")
    for r in rows:
        if r["status"] == "identical":
            continue
        print(c("31;1", f"\n--- {r['name']}: {r['status']} ---"))
        for path, a, b in r["changes"][:MAX_CHANGES_SHOWN]:
            print(f"  {path}\n      before: {short(a)}\n      after:  {short(b)}")
        if len(r["changes"]) > MAX_CHANGES_SHOWN:
            print(f"  ... and {len(r['changes']) - MAX_CHANGES_SHOWN} more changed fields")
        if r["unified"]:
            print(c("2", "\n  JSON diff:"))
            for line in r["unified"].splitlines():
                tint = "32" if line.startswith("+") else "31" if line.startswith("-") else "2"
                print("  " + c(tint, line))
    diff = len(rows) - same
    values = sum(r["values"] for r in rows)
    summary = f"\n{len(rows)} queries, {same} identical, {diff} different  ({values} values compared)"
    print(c("32;1" if diff == 0 else "31;1", summary))


def write_html(path, rows, before_desc, after_desc):
    same = sum(r["status"] == "identical" for r in rows)
    diff = len(rows) - same
    values = sum(r["values"] for r in rows)
    ok = diff == 0
    headline = (f"All {len(rows)} frontend queries return identical data" if ok
                else f"{diff} of {len(rows)} frontend queries return different data")
    e = html.escape
    table = "\n".join(
        f"<tr><td>{e(r['screen'])}</td><td class=mono>{e(r['name'])}</td><td class=num>{r['values']}</td>"
        f"<td><span class='pill {'ok' if r['status'] == 'identical' else 'bad'}'>"
        f"{'✓ identical' if r['status'] == 'identical' else '✗ ' + e(r['status'])}</span></td></tr>" for r in rows)
    details = ""
    for r in rows:
        if r["status"] == "identical":
            continue
        items = "".join(f"<tr><td class=mono>{e(p)}</td><td class=mono>{e(short(a, 200))}</td>"
                        f"<td class=mono>{e(short(b, 200))}</td></tr>"
                        for p, a, b in r["changes"][:MAX_CHANGES_SHOWN])
        more = (f"<p>… and {len(r['changes']) - MAX_CHANGES_SHOWN} more changed fields</p>"
                if len(r["changes"]) > MAX_CHANGES_SHOWN else "")
        details += (f"<h3>{e(r['screen'])} <span class=mono>({e(r['name'])})</span></h3>"
                    + (f"<table><tr><th>Field</th><th>Before</th><th>After</th></tr>{items}</table>{more}"
                       if items else "")
                    + (f"<details><summary>Raw JSON diff</summary><pre>{e(r['unified'])}</pre></details>"
                       if r["unified"] else f"<p>{e(r['status'])}</p>"))
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>openIMIS API comparison</title>
<style>
body {{ font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
       margin: 2rem auto; max-width: 1100px;
       color: #1f2937; padding: 0 1rem; }}
.banner {{ border-radius: 12px; padding: 1.5rem 2rem; color: #fff; background: {'#15803d' if ok else '#b91c1c'}; }}
.banner h1 {{ margin: 0 0 .4rem; font-size: 2rem; }}
.banner p {{ margin: 0; font-size: 1.1rem; opacity: .95; }}
.stats {{ display: flex; gap: 1rem; margin: 1.5rem 0; }}
.stat {{ flex: 1; background: #f3f4f6; border-radius: 10px; padding: 1rem; text-align: center; }}
.stat b {{ display: block; font-size: 2rem; }}
.versions {{ display: grid; grid-template-columns: 6rem 1fr; gap: .3rem 1rem; margin-bottom: 1.5rem; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 1.5rem; }}
th, td {{ text-align: left; padding: .45rem .6rem; border-bottom: 1px solid #e5e7eb; vertical-align: top; }}
th {{ background: #f9fafb; }}
.mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .85rem; word-break: break-all; }}
.num {{ text-align: right; }}
.pill {{ border-radius: 999px; padding: .15rem .7rem; font-weight: 600; white-space: nowrap; }}
.pill.ok {{ background: #dcfce7; color: #166534; }} .pill.bad {{ background: #fee2e2; color: #991b1b; }}
pre {{ background: #111827; color: #e5e7eb; padding: 1rem; border-radius: 8px; overflow-x: auto; font-size: .8rem; }}
footer {{ color: #6b7280; font-size: .85rem; }}
</style></head><body>
<div class="banner"><h1>{'✓' if ok else '✗'} {e(headline)}</h1>
<p>The same real frontend queries were run against the old and the new backend on the same demo database.</p></div>
<div class="stats"><div class="stat"><b>{len(rows)}</b>queries</div><div class="stat"><b>{same}</b>identical</div>
<div class="stat"><b>{diff}</b>different</div><div class="stat"><b>{values}</b>values compared</div></div>
<div class="versions"><b>Before</b><span>{e(before_desc)}</span><b>After</b><span>{e(after_desc)}</span></div>
<table><tr><th>Screen</th><th>Query</th><th class=num>Values</th><th>Result</th></tr>
{table}
</table>
{'<h2>Differences</h2>' + details if details else ''}
<footer>Generated {generated} by tools/api_snapshot/compare.py</footer>
</body></html>
"""
    Path(path).write_text(doc)


def main():
    args = parse_args()
    before, before_manifest = load(args.before)
    after, after_manifest = load(args.after)
    rows = compare(before, after)
    before_desc, after_desc = describe(before_manifest), describe(after_manifest)
    print_console(rows, before_desc, after_desc, color=not args.no_color and sys.stdout.isatty())
    report = Path(args.report) if args.report else Path(args.after) / "compare-report.html"
    write_html(report, rows, before_desc, after_desc)
    print(f"HTML report: {report}")
    sys.exit(0 if all(r["status"] == "identical" for r in rows) else 1)


if __name__ == "__main__":
    main()
