#!/usr/bin/env python
"""Run every frontend query in queries/ against the openIMIS backend and save one JSON file per query.

The app is driven in-process through Django's test Client, i.e. through the real URL routing,
middleware, JWT authentication and GraphQL view, exactly like an HTTP request from the frontend.
Only HTTP requests and query strings are used (no graphene imports), so the same script runs
unchanged on Graphene 2 and Graphene 3.

Usage:
    python tools/api_snapshot/snapshot.py --out /tmp/before [--repo PATH]
"""
import argparse
import contextlib
import io
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_QUERIES = HERE / "queries"

# Same values as the README quick start / CI; any variable already set in the environment wins.
ENV_DEFAULTS = {
    "SECRET_KEY": "secret",
    "MODE": "DEV",
    "DB_DEFAULT": "postgresql",
    "DB_HOST": "localhost",
    "DB_PORT": "5432",
    "DB_NAME": "test_imis",
    "DB_TEST_NAME": "test_imis",
    "DB_USER": "postgres",
    "DB_PASSWORD": "YourStrong!Passw0rd",
    "SITE_ROOT": "api",
    "OPENSEARCH_DSL_AUTOSYNC": "False",
    "DJANGO_SETTINGS_MODULE": "openIMIS.settings",
}

# Normalization rules (the only changes made to responses before they are written):
#   1. Values of these keys are replaced by "<volatile>" wherever they appear: they are login
#      tokens or expiry times computed from "now", so they differ on every run by design.
#   2. Nothing else is touched. Lists keep the order returned by the API and values are not
#      rounded or reformatted.
VOLATILE_KEYS = {"token", "refreshToken", "refresh_token", "csrfToken", "refreshExpiresIn",
                 "last_login", "lastLogin"}
VOLATILE = "<volatile>"


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", required=True, help="output folder (created; existing *.json files are replaced)")
    p.add_argument("--repo", default=str(HERE.parent.parent),
                   help="openIMIS backend checkout to snapshot (default: the repo containing this script)")
    p.add_argument("--queries", default=str(DEFAULT_QUERIES), help="folder with *.graphql / *.rest files")
    p.add_argument("--user", default="Admin", help="login (default: Admin)")
    p.add_argument("--password", default="admin123", help="password (default: admin123)")
    p.add_argument("--verbose", action="store_true", help="show the backend's own log output")
    return p.parse_args()


def load_queries(folder):
    queries = []
    for path in sorted(Path(folder).iterdir()):
        if path.suffix not in (".graphql", ".rest"):
            continue
        meta, body = {}, []
        for line in path.read_text().splitlines():
            if line.startswith("#") and not body:
                key, _, value = line.lstrip("# ").partition(":")
                meta[key.strip().lower()] = value.strip()
            else:
                body.append(line)
        queries.append({
            "name": path.stem,
            "kind": "rest" if path.suffix == ".rest" else "graphql",
            "screen": meta.get("screen", ""),
            "source": meta.get("source", ""),
            "variables": json.loads(meta["variables"]) if "variables" in meta else None,
            "body": "\n".join(body).strip() + "\n",
        })
    return queries


def normalize(value):
    if isinstance(value, dict):
        return {k: (VOLATILE if k in VOLATILE_KEYS and v is not None else normalize(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    return value


def versions():
    out = {}
    for pkg in ("Django", "graphene", "graphene-django"):
        try:
            out[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            out[pkg] = None
    return out


def git_describe(repo):
    def run(*cmd):
        try:
            return subprocess.check_output(["git", "-C", repo, *cmd], text=True, stderr=subprocess.DEVNULL).strip()
        except (OSError, subprocess.CalledProcessError):
            return None
    return {"commit": run("rev-parse", "--short", "HEAD"),
            "ref": run("describe", "--tags", "--all", "--always", "--dirty")}


def main():
    args = parse_args()
    t0 = time.perf_counter()
    for k, v in ENV_DEFAULTS.items():
        os.environ.setdefault(k, v)
    out = Path(args.out).resolve()
    queries = load_queries(Path(args.queries).resolve())
    repo = Path(args.repo).resolve()
    project = repo / "openIMIS"
    if not (project / "manage.py").exists():
        sys.exit(f"error: {project}/manage.py not found; pass --repo <openIMIS backend checkout>")
    os.chdir(project)
    sys.path.insert(0, str(project))

    quiet = not args.verbose
    sink = io.StringIO()
    with contextlib.ExitStack() as stack:
        if quiet:
            stack.enter_context(contextlib.redirect_stdout(sink))
            stack.enter_context(contextlib.redirect_stderr(sink))
        import django
        django.setup()
    if quiet:
        logging.disable(logging.CRITICAL)
    from django.test import Client

    # Module packages are editable installs bound to one checkout: make sure this Python
    # really runs the code of --repo and not some other worktree.
    import core
    core_path = Path(core.__file__).resolve()
    if repo not in core_path.parents:
        sys.exit(f"error: this Python loads openIMIS modules from {core_path.parent.parent}, not from {repo}.\n"
                 f"Run snapshot.py with {repo}/.venv/bin/python (see tools/api_snapshot/README.md).")
    t_setup = time.perf_counter() - t0

    site_root = os.environ["SITE_ROOT"].strip("/")
    api = f"/{site_root}" if site_root else ""
    graphql_url = f"{api}/graphql"
    # DEBUG mode only accepts localhost-style hosts, so present ourselves as localhost.
    client = Client(HTTP_HOST="localhost")

    def post_graphql(query, variables=None, token=None):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
        payload = {"query": query}
        if variables is not None:
            payload["variables"] = variables
        with contextlib.redirect_stdout(sink) if quiet else contextlib.nullcontext():
            return client.post(graphql_url, data=json.dumps(payload), content_type="application/json", **headers)

    # Log in the way the frontend does: the tokenAuth mutation (the only mutation this tool runs).
    login = post_graphql("mutation authenticate($username: String!, $password: String!) "
                         "{ tokenAuth(username: $username, password: $password) { token } }",
                         {"username": args.user, "password": args.password})
    try:
        token = login.json()["data"]["tokenAuth"]["token"]
    except (ValueError, KeyError, TypeError):
        sys.exit(f"error: login as {args.user!r} failed (HTTP {login.status_code}): {login.content[:500]!r}")
    client.cookies.clear()  # authenticate with the Authorization header only

    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.json"):
        old.unlink()

    results = []
    t_queries = time.perf_counter()
    for q in queries:
        start = time.perf_counter()
        if q["kind"] == "rest":
            method, _, path = q["body"].strip().partition(" ")
            if method.upper() != "GET":
                sys.exit(f"error: {q['name']}: only GET is allowed in .rest files")
            with contextlib.redirect_stdout(sink) if quiet else contextlib.nullcontext():
                resp = client.get(f"{api}{path.strip()}", HTTP_AUTHORIZATION=f"Bearer {token}")
        else:
            if q["body"].lstrip().startswith("mutation"):
                sys.exit(f"error: {q['name']}: mutations are not allowed")
            resp = post_graphql(q["body"], q["variables"], token)
        elapsed = time.perf_counter() - start
        try:
            body = resp.json()
        except ValueError:
            body = {"non_json_body": resp.content.decode("utf-8", "replace")}
        errors = body.get("errors") if isinstance(body, dict) else None
        record = {
            "query": q["name"],
            "screen": q["screen"],
            "http_status": resp.status_code,
            "response": normalize(body),
        }
        (out / f"{q['name']}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
        ok = resp.status_code == 200 and not errors
        results.append({"query": q["name"], "ok": ok, "seconds": round(elapsed, 3)})
        flag = "ok " if ok else "ERR"
        print(f"  {flag} {q['name']:<32} HTTP {resp.status_code}  {elapsed * 1000:6.0f} ms"
              + (f"  errors: {errors[0].get('message') if errors else ''}" if errors else ""))

    total = time.perf_counter() - t0
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git": git_describe(str(repo)),
        "versions": versions(),
        "python": sys.version.split()[0],
        "user": args.user,
        "queries": len(queries),
        "failed": [r["query"] for r in results if not r["ok"]],
        "timings_seconds": {"django_setup": round(t_setup, 2),
                            "login": round(t_queries - t_setup - t0, 2),
                            "queries": round(time.perf_counter() - t_queries, 2),
                            "total": round(total, 2)},
    }
    (out / "_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    v = manifest["versions"]
    print(f"\nSnapshot of {len(queries)} queries -> {out}  "
          f"(Django {v['Django']}, graphene {v['graphene']}, {manifest['git']['ref']})  in {total:.1f}s")
    if manifest["failed"]:
        print(f"WARNING: {len(manifest['failed'])} queries returned errors: {', '.join(manifest['failed'])}")


if __name__ == "__main__":
    main()
