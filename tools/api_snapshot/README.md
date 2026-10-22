# API snapshot: "nothing broke for the frontend"

Runs the **same 30 real queries the openIMIS React frontend sends** against two versions of this backend
(on the same demo database) and shows whether the responses are identical.

- `snapshot.py`: runs every query in [`queries/`](queries/) in-process through the real Django app
  (Django test `Client` → `/api/graphql`, URL routing, middleware, JWT auth, GraphQL view) and writes one JSON file per query.
  It only sends HTTP requests with query strings, never imports graphene, so it runs unchanged on Graphene 2 and Graphene 3.
  Read-only: the only mutation is the frontend's own `tokenAuth` login.
- `compare.py`: compares two snapshot folders, prints `N queries, N identical, N different` plus field-by-field and JSON diffs,
  writes a one-page HTML report, and exits `1` if anything differs (`0` if identical).
- [`baseline/`](baseline/): snapshot of tag `baseline-django42-green` (Django 4.2.30, Graphene 2.1.9) on the `test_imis` demo DB.

## Live demo (about 15 seconds on stage)

One-time prep before the demo: one git worktree **plus its own virtualenv** per version. Two venvs are required because
Graphene 2 and Graphene 3 can't be installed side by side, and the openIMIS modules are editable installs bound to one checkout
(`snapshot.py` refuses to run if the Python it's launched with loads modules from a different checkout than `--repo`).

```bash
# from this repo (checked out on a branch that has tools/api_snapshot, e.g. main once merged), with the demo DB running
MIGRATION_BRANCH=<the Django 5.2 / Graphene 3 branch>
git fetch origin
git worktree add --detach ~/oi-before baseline-django42-green
git worktree add --detach ~/oi-after "origin/$MIGRATION_BRANCH"
for d in ~/oi-before ~/oi-after; do (
  cd "$d" && uv venv -p 3.11 .venv &&
  uv pip install --python .venv "setuptools<81" -r requirements.txt &&
  cd script && ../.venv/bin/python modules-requirements.py ../openimis.json > modules-requirements.txt &&
  uv pip install --python ../.venv -r modules-requirements.txt
) done
# warm-up (first run compiles .pyc files, ~13 s; later runs ~5 s). Also run migrate here if the new branch adds migrations.
~/oi-before/.venv/bin/python tools/api_snapshot/snapshot.py --repo ~/oi-before --out /tmp/before
~/oi-after/.venv/bin/python  tools/api_snapshot/snapshot.py --repo ~/oi-after  --out /tmp/after
```

On stage:

```bash
~/oi-before/.venv/bin/python tools/api_snapshot/snapshot.py --repo ~/oi-before --out /tmp/before   # old code, ~5 s
~/oi-after/.venv/bin/python  tools/api_snapshot/snapshot.py --repo ~/oi-after  --out /tmp/after    # new code, ~5 s
python3 tools/api_snapshot/compare.py /tmp/before /tmp/after --report /tmp/api-report.html         # < 1 s
xdg-open /tmp/api-report.html   # the slide
```

Shortcut: compare the new code directly with the committed baseline, `python3 tools/api_snapshot/compare.py tools/api_snapshot/baseline /tmp/after`.

Single checkout instead of worktrees (slower, needs a reinstall in between): copy `tools/api_snapshot` somewhere outside
the repo first (the tag doesn't contain it), then `git checkout baseline-django42-green`, reinstall the requirements,
snapshot to `/tmp/before`; `git checkout $MIGRATION_BRANCH`, reinstall, snapshot to `/tmp/after`; compare.

Without worktrees the same commands work from this checkout with its own venv:
`python tools/api_snapshot/snapshot.py --out /tmp/now`.

### Settings

Environment variables default to the README/CI values (`DB_NAME=test_imis`, `DB_USER=postgres`, `DB_PASSWORD='YourStrong!Passw0rd'`,
`SITE_ROOT=api`, `MODE=DEV`, `OPENSEARCH_DSL_AUTOSYNC=False`, ...); anything already exported wins.
Login defaults to the demo admin `Admin` / `admin123` (`--user`, `--password`). `--verbose` shows the backend's own log output.

## The queries

`queries/NN_name.graphql` holds the query text exactly as the frontend builds it (same projections, filters, ordering
and page size of 10), with a header naming the screen and the frontend source file/function (`openimis-fe-*_js`, `develop`)
and, if any, `# Variables: {...}`. Identifiers are fixed demo-DB records so detail pages return real data
(insuree `070707070`, claim `CIA00001` with 4 items and 7 services, etc.). `01_core_current_user.rest` is the one REST call:
the frontend loads the logged-in user and their rights with `GET /api/core/users/current_user/` right after `tokenAuth`.

| Area | Queries |
|---|---|
| Login / permissions | current user + rights (REST), module permissions, roles list |
| Insured persons | search list, detail page, enquiry, insuree's policies, remaining benefits (eligibility) |
| Families | search list, detail page, members table |
| Policies | search list, detail page |
| Claims | search list (health facility view), detail page with services and items |
| Contributions | search list, detail page, contributions of a policy |
| Payments | search list (the demo DB has no payments, so this checks the empty-page shape) |
| Locations | regions, districts of a region, the user's districts |
| Health facilities | search list, detail page |
| Products | search list (full product fragment), single product by id |
| Medical | items list, services list, service detail (with linked services/items), item detail |

All 30 return HTTP 200 without GraphQL errors on `baseline-django42-green`; none were dropped.

## Normalization rules

Responses are saved exactly as returned, with one rule: the values of the keys `token`, `refreshToken`, `refresh_token`,
`csrfToken`, `refreshExpiresIn`, `last_login` and `lastLogin` are replaced by `"<volatile>"` (login tokens and expiry times
computed from "now"). None of these appear in the current query set; the rule is a safety net. Nothing is sorted,
rounded or reformatted, so a change in ordering, types (e.g. `"4"` vs `4`), `null`s or error messages is reported.
`compare.py` compares JSON values (key order inside an object is ignored; list order is not). `_manifest.json`
(versions, git ref, timings) is shown in the report header but never compared.

## Proof it works (measured on `baseline-django42-green`)

- **Determinism**: two snapshots of the same code → `30 queries, 30 identical, 0 different (3754 values compared)`, exit 0.
- **Catches a change**: temporarily changing one line of app code (`ClaimGQLType.resolve_attachments_count` returning
  `count() + 1`) → `30 queries, 29 identical, 1 different`; only `15_claim_detail` flagged, with
  `response.data.claim.attachmentsCount: 0 → 1`, exit 1.
- **Timing**: snapshot ~4.5–6.5 s wall (Django start-up ~1.5 s, `tokenAuth` login ~2 s for password hashing, 30 queries ~1 s);
  compare < 0.2 s. Before + after + compare ≈ 10–13 s.
