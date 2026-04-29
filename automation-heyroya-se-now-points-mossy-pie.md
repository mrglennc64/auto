# HeyRoya catalog automation — VPS #2 build plan

## Context

HeyRoya already runs two client-side JS tools at heyroya.se (scan-catalog, apply-corrections) that validate music publisher catalogs against CWR rules and merge filled correction worksheets back into a clean catalog. The goal is to port that logic to a real backend on a fresh VPS so that:

1. Publishers can upload catalogs via API, not by pasting CSV into a browser tab.
2. Scans run async and persist (Celery + Postgres + MinIO) so large catalogs don't block the page.
3. The Part 2 correction round-trip becomes a tracked workflow with email notifications, not a manual file-shuffle.
4. A protected internal dashboard lets the operator see job status, download reports, and re-run analyses.

**DNS is live**: `automation.heyroya.se → 187.77.111.16`. Nothing exists on the VPS yet beyond the IP.

The source-of-truth algorithm lives in [docs/internal-tools-spec.md](../../OneDrive/Dokument/st%20ro/roya-demo/docs/internal-tools-spec.md) (530 lines, derived from the live JS at commit 2302819). The match-motor port must produce identical output to the live JS for the canonical fixture `test-15-mixed.csv` (12 issues, score 53, tone=warn).

---

## Locked decisions

| Area | Choice |
|---|---|
| Scope of first ship | **Full Part 1 + Part 2** end-to-end (scan → correction template → apply → after-report → emails → dashboard) |
| Match-motor source | Port `scan-catalog.html` and `apply-corrections.html` to Python verbatim. Fix 3 documented quirks behind a feature flag so parity tests still pass |
| Object storage | **MinIO** on the same VPS, S3-compatible API, single bucket `heyroya-automation` with subfolders per role |
| Email | **Resend** transactional API |
| Stack | FastAPI + Celery + Redis + PostgreSQL + MinIO + Jinja2 templates (no SPA) |
| Local dev folder | `C:\dev\heyroya-automation\` (outside OneDrive — same convention as `C:\dev\trapmarketing\`) |
| Deploy folder on VPS | `/opt/heyroya-automation/` |
| Auth | `X-API-Key` header for `/api/*`, HTTP Basic on `/dashboard` |

---

## Repository layout (local + VPS share the same tree)

```
heyroya-automation/
├── app/
│   ├── main.py                       FastAPI entry; mounts api + dashboard
│   ├── api/
│   │   ├── catalog.py                POST /api/upload/catalog
│   │   ├── corrections.py            POST /api/upload/corrections
│   │   ├── jobs.py                   GET  /api/jobs/{id}/status, /results, /after
│   │   └── health.py                 GET  /api/health
│   ├── dashboard/
│   │   ├── routes.py                 GET  /dashboard (Basic-auth, Jinja templates)
│   │   └── templates/                dashboard.html, job_detail.html
│   ├── workers/
│   │   ├── celery_app.py             Celery factory; broker=Redis
│   │   ├── analyze.py                analyze_catalog(job_id)  Pipeline 1
│   │   └── correct.py                apply_corrections(correction_job_id)  Pipeline 2
│   ├── engine/                       PURE PYTHON — no HTTP, no DB, no I/O
│   │   ├── csv_io.py                 parse_catalog, parse_worksheet, emit_cleaned, csv_escape
│   │   ├── detect.py                 detect_issues(catalog) → List[Issue]
│   │   ├── apply.py                  apply_decisions(catalog, worksheet) → (cleaned, log, totals)
│   │   ├── score.py                  health_score, tone classification
│   │   ├── report.py                 render_health_report(scan) → HTML/PDF
│   │   └── constants.py              VALID_ROLES, HOME_SOCIETY, FOREIGN_SOCIETIES
│   ├── models/
│   │   ├── db.py                     SQLAlchemy session
│   │   └── schema.py                 jobs, works, issues, correction_jobs, correction_entries,
│   │                                 before_after_diff, files, agreements (NEW)
│   ├── services/
│   │   ├── storage.py                MinIO/boto3 wrapper; put_object, presigned_url
│   │   ├── email.py                  Resend client; send_email_1/2/3 (Swedish bodies from PDF §F)
│   │   └── auth.py                   verify_api_key dependency
│   └── utils/
├── tests/
│   ├── fixtures/
│   │   ├── test-15-mixed.csv                       Canonical input
│   │   └── corrections-worksheet-test-15-filled.csv  Canonical filled response
│   ├── test_detect_parity.py         §5 of spec — exact 12 issues, score 53
│   ├── test_apply_parity.py          §5 of spec — 12 mutations
│   └── test_api_smoke.py             upload → status → results → after, end-to-end
├── alembic/                          migrations
├── config/
│   ├── settings.py                   pydantic-settings; reads env
│   └── celeryconfig.py
├── scripts/
│   ├── deploy.sh                     The runbook from the user's message, parameterized
│   ├── start.sh                      systemctl restart heyroya-{api,worker,beat}
│   └── seed_demo.py                  Inserts test-15-mixed.csv as a demo job
├── systemd/
│   ├── heyroya-api.service
│   ├── heyroya-worker.service
│   └── heyroya-beat.service
├── nginx/
│   └── automation.heyroya.se.conf    From the user's message
├── requirements.txt
├── .env.example                      DATABASE_URL, REDIS_URL, MINIO_*, RESEND_API_KEY, API_KEYS,
│                                     DASHBOARD_USER, DASHBOARD_PASS
└── README.md
```

The `engine/` package is intentionally pure Python with zero framework imports. That's what lets the parity tests (no DB, no HTTP) run identically to the live JS.

---

## Database schema

Per architecture PDF §D, with one addition:

| Table | Purpose |
|---|---|
| `jobs` | id, publisher_id, phase, status, timestamps |
| `works` | id, job_id, external_work_id, title, iswc, isrc, risk_score_before, risk_score_after |
| `issues` | id, job_id, work_id, issue_type, field, current_value, severity, status |
| `correction_jobs` | id, job_id, status, timestamps |
| `correction_entries` | id, correction_job_id, work_id, field, current_value, corrected_value, notes |
| `before_after_diff` | id, job_id, work_id, field, value_before, value_after |
| `reports` | id, job_id, type (before/after), s3_key, created_at |
| `files` | id, job_id, role, s3_key, created_at |
| **`agreements` (new)** | id, job_id, work_id, foreign_writer_name, foreign_society, declaration_type (E/SE/AM), territory |

The `agreements` table closes the foreign-writer gap flagged in spec §4.2 and §7.5 — the live JS only logs the declaration; the new backend persists it and surfaces it in the cleaned-catalog export.

---

## MinIO bucket layout

Single bucket `heyroya-automation`, prefixes by file role (matches the user's runbook):

```
heyroya-automation/
  original_catalogs/{job_id}/{filename}
  correction_templates/{job_id}/{filename}
  corrections_uploaded/{job_id}/{filename}
  reports_before/{job_id}/report.html
  reports_after/{job_id}/report.html
  corrected_catalogs/{job_id}/cleaned.csv
  cwr_exports/{job_id}/{filename}
  logs/{job_id}/{filename}
```

Presigned URLs for download links in emails; lifetime 7 days.

---

## Implementation phases

### Phase 0 — Local skeleton (day 1)
- `git init` `C:\dev\heyroya-automation`
- requirements: `fastapi uvicorn celery redis sqlalchemy alembic boto3 psycopg2-binary jinja2 python-multipart pydantic-settings resend openpyxl weasyprint`
- Wire FastAPI app, health endpoint, settings loader
- Local Postgres + Redis + MinIO via docker-compose for dev
- Smoke test: `curl localhost:8000/api/health` → `{"status":"ok"}`

### Phase 1 — Engine port (days 2-4) — **the critical path**
- Port `scan-catalog.html` JS → `engine/detect.py` + `engine/csv_io.py` + `engine/score.py` + `engine/report.py`
- Port `apply-corrections.html` JS → `engine/apply.py`
- Constants in `engine/constants.py` per spec §3.1
- Write `tests/test_detect_parity.py` and `tests/test_apply_parity.py` against the test-15-mixed fixture
- **Gate**: both tests green with **exact** strings/IDs/scores from spec §5 before moving on
- Then add the 3 quirk fixes behind feature flags (`STRICT_ROLE_TARGETING`, `STRICT_NAME_MATCHING`, `WRITE_AGREEMENTS_TABLE`) so parity tests stay green with flags off

### Phase 2 — DB + storage (days 5-6)
- Alembic migration for the 9 tables
- `services/storage.py` MinIO wrapper + presigned URL helper
- `models/schema.py` SQLAlchemy ORM
- Smoke: insert a job, upload a file to MinIO, fetch a presigned URL

### Phase 3 — API + Celery (days 7-9)
- FastAPI routes per architecture PDF §C: `/api/upload/catalog`, `/api/upload/corrections`, `/api/jobs/{id}/status`, `/api/jobs/{id}/results`, `/api/jobs/{id}/after`
- `X-API-Key` dependency, key list from env
- Celery tasks `analyze_catalog` and `apply_corrections` calling into `engine/`
- `tests/test_api_smoke.py`: upload `test-15-mixed.csv` → poll status → fetch results → upload filled worksheet → fetch `/after` → assert presigned URLs return the cleaned catalog

### Phase 4 — Email + dashboard (days 10-11)
- `services/email.py`: Resend wrapper, three Swedish templates verbatim from PDF §F
- Email triggers: end of `analyze_catalog` (Email 1), start of `apply_corrections` (Email 2), end of `apply_corrections` (Email 3)
- Jinja dashboard at `/dashboard`: list jobs, click → detail page with all download links + per-work issue table
- HTTP Basic via FastAPI dependency

### Phase 5 — VPS deployment (days 12-13)
- Provision VPS #2 per user's runbook (NGINX, certbot, redis, postgres)
- Install MinIO as systemd service, create bucket
- `scripts/deploy.sh` clones repo, sets up venv, runs alembic, installs the 3 systemd units
- NGINX config from user's runbook → `/etc/nginx/sites-available/automation`
- `certbot --nginx -d automation.heyroya.se`
- Firewall: allow only 22/80/443
- Verify: `curl https://automation.heyroya.se/api/health`

### Phase 6 — End-to-end UAT (day 14)
- Upload `test-15-mixed.csv` against the live VPS endpoint with a real API key
- Confirm Email 1 lands at the operator address
- Edit and re-upload `corrections-worksheet-test-15-filled.csv`
- Confirm Email 3 + corrected catalog matches the spec §5 mutation table

---

## Critical files to read / reuse

| Path | Why |
|---|---|
| [docs/internal-tools-spec.md](../../OneDrive/Dokument/st%20ro/roya-demo/docs/internal-tools-spec.md) | Source of truth for the engine. Read fully before starting Phase 1. |
| `c:\Users\carin\OneDrive\Dokument\st ro\roya-demo\frontend\pages\scan-catalog.html` | The live JS scanner. The Phase 1 port reads this directly to match behavior. |
| `c:\Users\carin\OneDrive\Dokument\st ro\roya-demo\frontend\pages\apply-corrections.html` | The live JS applier. Same. |
| `c:\Users\carin\OneDrive\Dokument\st ro\roya-demo\frontend\samples\test-15-mixed.csv` | Canonical regression input — copy into `tests/fixtures/`. |
| `c:\Users\carin\OneDrive\Dokument\st ro\roya-demo\frontend\samples\corrections-worksheet-test-15-filled.csv` | Canonical correction round-trip — copy into `tests/fixtures/`. |
| `C:\dev\trapmarketing\db\migrations\001_init.sql` | Reference for Postgres schema style + migrations pattern (do not import — separate DB). |
| `c:\Users\carin\OneDrive\Dokument\marketing\trapcrm\src\db\schema.sql` | Same; reference only. The new automation owns its own database. |

**Do not reuse**: TrapCRM's SQLite (wrong DB engine for async workers) or its scan-engine.ts (mock Spotify scorer, unrelated to CWR/ISWC validation).

---

## Verification

The plan succeeds when, on the live VPS:

1. **Engine parity** (offline, `pytest tests/`):
   - `test_detect_parity.py` produces exactly the 12-row issue list in spec §5 with `score=53, tone='warn'`.
   - `test_apply_parity.py` produces exactly the 12-row mutation table in spec §5 with `totals={accept:5, reject:0, edit:7}`.

2. **API smoke** (against `https://automation.heyroya.se`):
   ```bash
   curl -H "X-API-Key: $KEY" -F file=@test-15-mixed.csv \
     -F publisher_id=demo \
     https://automation.heyroya.se/api/upload/catalog
   # → {"job_id":"<uuid>","status":"queued"}

   curl -H "X-API-Key: $KEY" \
     https://automation.heyroya.se/api/jobs/<uuid>/status
   # → {"phase":"awaiting_corrections","status":"done"} within ~30s

   curl -H "X-API-Key: $KEY" \
     https://automation.heyroya.se/api/jobs/<uuid>/results
   # → presigned URLs for health_report_before + correction_template
   ```

3. **End-to-end round-trip**: upload filled worksheet, confirm `/api/jobs/<uuid>/after` returns presigned URLs whose contents match spec §5 mutation table.

4. **Email**: Resend dashboard shows three sends per round-trip (analyzed, received, after-ready) in Swedish.

5. **Dashboard**: `https://automation.heyroya.se/dashboard` (HTTP Basic) lists the test job with all five download links.

---

## Explicit non-goals (for this phase)

- No CWR file generation in v1 — only cleaned CSV. CWR export is a follow-up; the `cwr_exports/` MinIO prefix is reserved.
- No public publisher portal — operator-only dashboard. Publishers receive emails with presigned links.
- No external metadata enrichment (MusicBrainz / Discogs / ISRC resolver). The "external lookup match" suggestion remains a placeholder string per spec §3.2.
- No multi-tenant isolation. One operator, one Postgres DB, one MinIO bucket. Multi-publisher comes later via `publisher_id` already on `jobs`.
- No Part 1.5 / partial corrections workflow. A correction CSV is processed once per job; further fixes require a new scan.

---

## Open items (decide during execution, don't block the plan)

1. **PDF rendering**: WeasyPrint vs Playwright/Chromium-headless. WeasyPrint is lighter; Playwright matches the existing browser-print exactly. Default to WeasyPrint and revisit if §6 styling drifts.
2. **API key storage**: env var (simple) vs DB-backed with rotation. Default env-var list for v1; DB-backed in a follow-up.
3. **Worksheet format**: spec §2.2 says backend should accept both `.csv` and `.xlsx` on return. Default to accepting both via `openpyxl`; emit `.xlsx` with the styled template per the live tool.
