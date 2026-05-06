# BSE_data — Technical Architecture

> Single-user desktop application that scrapes corporate announcements from the
> Bombay Stock Exchange (BSE), downloads their PDF attachments, runs configurable
> regex "flags" against the extracted text, and surfaces the results through
> three independent UIs sharing one Python backend.

---

## 1. Quick Summary

| | |
|---|---|
| **Domain** | Indian equity-market disclosure monitoring |
| **Use case** | Find announcements (e.g. "Investor Meet", "Earnings Call") for a watchlist of scrips, then mine the PDFs for structured data points |
| **Audience** | A single analyst running it locally |
| **Stack** | Python 3.11, FastAPI, SQLite, httpx, pdfplumber, Streamlit, React 19 + Vite + TypeScript |
| **Deployment** | Local; one PowerShell script (`start-dev.ps1`) launches all processes |

---

## 2. System Overview

```
                         ┌─────────────────────┐
                         │  BSE Public APIs    │
                         │ - Announcements API │
                         │ - PDF Attachments   │
                         │ - Scrip Header API  │
                         └──────────┬──────────┘
                                    │ httpx (async)
                                    ▼
   ┌────────────────────────────────────────────────────────────────┐
   │                      backend/server (Python)                   │
   │                                                                │
   │  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐     │
   │  │ scraper_    │  │ processor_   │  │     coordinator    │     │
   │  │   engine    │  │    engine    │  │  (single-run mutex)│     │
   │  └──────┬──────┘  └──────┬───────┘  └─────────┬──────────┘     │
   │         │                │                    │                │
   │         ▼                ▼                    ▼                │
   │  ┌─────────────────────────────────────────────────────┐       │
   │  │ state_manager.EngineState   logger   errors         │       │
   │  └─────────────────────────────────────────────────────┘       │
   │         │                                                      │
   │         ▼                                                      │
   │  ┌──────────────────┐    ┌────────────────────┐                │
   │  │   store.py       │    │  config_store.py   │                │
   │  │ (SQLite ops)     │    │ (JSON file + KV)   │                │
   │  └────────┬─────────┘    └─────────┬──────────┘                │
   │           ▼                        ▼                           │
   │  ┌────────────────┐        ┌──────────────────┐                │
   │  │ announcements  │        │ data/config.json │                │
   │  │ flag_hits      │        └──────────────────┘                │
   │  │ scrape_tag_hits│                                            │
   │  │ run_history    │                                            │
   │  │ settings_kv    │                                            │
   │  │ (SQLite)       │                                            │
   │  └────────────────┘                                            │
   │                                                                │
   │  main.py exposes the engines via FastAPI ◄────┐                │
   └───────────────────────────────────────────────┼────────────────┘
                                                   │ HTTP
                ┌───────────────────────┬──────────┴─────────┐
                │                       │                    │
                ▼                       ▼                    ▼
        ┌──────────────┐         ┌────────────┐      ┌────────────────┐
        │  app.py      │         │  React     │      │ uvicorn /      │
        │ (Streamlit)  │         │  /frontend │      │ direct API     │
        │ port 8501    │         │ port 5173  │      │ port 8000      │
        └──────────────┘         └────────────┘      └────────────────┘
```

**Three independent UIs**, one backend:
1. **Streamlit** (`app.py`) — primary control panel, calls Python modules directly via in-process imports.
2. **React** (`frontend/`) — modern alternative for the filings list, calls FastAPI over HTTP.
3. **FastAPI** (`backend/server/main.py`) — also reachable directly for raw API consumers.

The backend code is the same in all three cases. Streamlit imports the engines and runs them on a daemon thread; React talks to FastAPI; FastAPI calls the same engines.

---

## 3. Repository Layout

```
BSE_data/
├── app.py                       # Streamlit primary UI
├── start-dev.ps1                # One-shot launcher (Windows)
├── backend/
│   ├── __init__.py
│   ├── requirements.txt         # fastapi, uvicorn, httpx, pdfplumber
│   └── server/
│       ├── __init__.py
│       ├── main.py              # FastAPI app + routes
│       ├── coordinator.py       # Single-run mutex across scraper/processor
│       ├── scraper_engine.py    # Fetches BSE announcements + PDFs
│       ├── processor_engine.py  # Extracts text + runs regex flags
│       ├── store.py             # SQLite operations
│       ├── config_store.py      # JSON config + KV mirror in DB
│       ├── state_manager.py     # EngineState class
│       ├── logger.py            # Named file-loggers factory
│       ├── errors.py            # Custom exception hierarchy
│       └── constants.py         # LogConfig, HttpConfig, BseUrls, PathConfig
├── frontend/                    # React + Vite + TypeScript
│   ├── index.html
│   ├── package.json             # React 19.2, Vite 8.0, TypeScript 6.0
│   ├── tsconfig*.json
│   ├── vite.config.ts           # /api proxy → http://localhost:8000
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── App.css
│       ├── index.css            # CSS variables (design tokens)
│       ├── api.ts               # Typed fetch wrappers + interfaces
│       ├── logger.ts            # Batched POST to /api/logs
│       └── components/
│           ├── FilingsPage.tsx
│           ├── FilingsFilters.tsx
│           ├── FilingsTable.tsx
│           └── FilingDetail.tsx
├── data/                        # Generated at runtime
│   ├── config.json              # User-editable config
│   ├── announcements.db         # SQLite database
│   └── attachments/<scrip>/<id>.pdf
├── logs/                        # Generated at runtime (UTF-8)
│   ├── backend.log
│   ├── streamlit.log
│   └── frontend.log
└── docs/
    └── ARCHITECTURE.md          # ← this file
```

---

## 4. Technology Stack

### Backend
| Library | Why |
|---|---|
| **FastAPI ≥ 0.115** | REST API. Async-native, integrates with `httpx`. |
| **uvicorn[standard]** | ASGI server. |
| **httpx ≥ 0.27** | Async HTTP client for BSE API + PDF download. Cookies + redirect handling. |
| **pdfplumber ≥ 0.11** | PDF text extraction. Falls back gracefully on encrypted/corrupt files. |
| **sqlite3** (stdlib) | Storage. WAL mode, `synchronous=NORMAL`. |
| **streamlit, pandas** | Streamlit UI (installed at runtime by `start-dev.ps1`). |

### Frontend (React)
| Package | Version |
|---|---|
| react / react-dom | 19.2.5 |
| vite | 8.0.10 |
| typescript | 6.0.3 (strict mode enabled) |
| eslint + react-hooks plugin | 10.x |

The dev server proxies `/api/*` to `http://localhost:8000`.

---

## 5. Core Backend Modules

Each module is a single file with no internal sub-packages. Imports flow strictly top-down:
`errors` ← `state_manager` ← `engines` ← `coordinator` ← `main`.

### `errors.py`
Custom exception hierarchy:
- `ScraperError` ← `ScraperRetryableError` (HTTP 429/503/timeout), `ScraperPermanentError` (corrupt PDF, bad magic).
- `ProcessorError` ← `ProcessorPermanentError` (password-protected/corrupt PDF).

The distinction matters in `processor_engine._run`: a `ProcessorPermanentError` calls `mark_processed(rec.id)` so the row won't be retried; a generic `Exception` does **not** mark it, allowing a retry next run.

### `state_manager.py`
`EngineState` class — encapsulates the mutable state dict each engine used to keep at module level.

```python
class EngineState:
    def __init__(self, name: str, logger: Logger): ...
    def initialize(self, template: dict) -> None: ...
    def get(self) -> dict                         # snapshot copy
    def get_all(self) -> dict                     # mutable reference (used by backward-compat alias)
    def update(self, **kwargs) -> None
    def log(self, msg, level='info'|'warn'|'err') # writes to file + UI list
    def get_progress(self, phase, ...) -> float
```

Both engines own one instance and also export `state = _state.get_all()` so the legacy direct-state access in `app.py` (e.g. `scraper_engine.state["running"]`) still works.

### `constants.py`
Single source of truth for tunable values. Grouped into classes for namespace:
- `LogConfig.MAX_ENTRIES = 500`, `TRIM_THRESHOLD = 100`
- `HttpConfig.MAX_RETRIES = 5`, `BACKOFF_MIN_SEC = 2`, `BACKOFF_MAX_SEC = 32`, `DEFAULT_TIMEOUT_SEC = 30`, plus `PDF_RETRY_*` knobs
- `BseUrls.HOME`, `API_BASE`, `ATTACH_BASE`, `ANN_REFERER`, `SCRIP_HEADER_API`
- `PathConfig.DATA_DIR`, `ATTACHMENTS_DIR`, `DB_PATH`, `CONFIG_PATH`, `LOGS_DIR`
- `DefaultUserAgent.CHROME`

### `logger.py`
Factory `get_app_logger(name, log_filename)` creates a `logging.Logger` bound to `logs/<filename>`. UTF-8 encoding is set explicitly (Windows defaults to cp1252, which would crash on Unicode characters used in log messages — this was a real bug fixed during the refactor).

Three pre-built loggers are exported:
- `backend_logger` → `logs/backend.log`
- `streamlit_logger` → `logs/streamlit.log`
- `frontend_logger` → `logs/frontend.log`

### `config_store.py`
Manages `data/config.json`. Three-layer merge:
1. **Defaults** in `DEFAULT_CONFIG` (in-code).
2. **File** at `data/config.json` if present.
3. **DB mirror** in `settings_kv` table — fallback if the file is deleted.

Public API:
- `get_config() → dict` (cached, lazy `load_config` on first call)
- `save_config(partial: dict) → dict` — validates regex patterns and tag IDs; writes both file and DB
- `validate_startup_config() → list[str]` — non-fatal startup check called from FastAPI's `on_event("startup")`

### `store.py`
Thin SQLite wrapper. One module-level connection, opened with `check_same_thread=False`, `journal_mode=WAL`, `synchronous=NORMAL`. Schema bootstrapped lazily on first `get_db()`.

Exports the CRUD primitives the engines use: `upsert_announcements_batch`, `set_attachment_path`, `mark_processed`, `list_announcements`, `flag_hits_by_announcement`, `scrape_tag_hits_by_announcement`, `clear_flag_hits_for`, `insert_flag_hit`, `insert_run_history`, `list_run_history`, `reset_announcements`, `reset_run_history`, `settings_kv_set`, `settings_kv_all`.

### `scraper_engine.py`
End-to-end pipeline for fetching announcements:
1. Build candidate scrip list (universe = `[""]` for "all", otherwise watchlist).
2. For each scrip, hit BSE API with backoff on 429/503 → JSON rows.
3. Filter rows by `News_submission_dt` window and watchlist (if not universe).
4. Compile filter-tag regexes (`cfg.filter.tags`) and annotate matches.
5. `upsert_announcements_batch` (skipped if `dryRun`).
6. If `downloadAttachments`, fetch PDFs (after a session cookie warm-up), save to `data/attachments/<scrip>/<id>.pdf`.
7. `_finish(status)` writes a `run_history` row.

The async task is created with `asyncio.create_task(_run(...))` and tracked in state; `stop()` flips `_cancelRequested = True` and the loops bail at the next checkpoint.

### `processor_engine.py`
1. Loads pending or all records via `list_announcements(with_attachment_url=True, unprocessed_only=mode=='pending')`.
2. For each record:
   - Read `attachment_path` if exists, else fetch from `attachment_url` (with BSE session cookie + Referer + retries).
   - Extract text via `pdfplumber` in a thread (`asyncio.to_thread`).
   - For each active flag, run `re.compile(pattern).search(text)`; on hit, store a 80-char snippet around the match.
   - `mark_processed(id)` for both successes and `ProcessorPermanentError`s; **not** for unexpected `Exception`s (so they retry).
3. `_finish(status)` writes a `run_history` row.

### `coordinator.py`
Single-run mutex. Module-level `_active_step: str | None` blocks concurrent scraper, processor, or quick-run starts. The `on_idle` callback chain implements quick-run: scraper→processor sequencing.

### `main.py`
FastAPI app. Routes are thin pass-throughs to `coordinator` and `store`. Highlights:
- Startup hook calls `validate_startup_config()` and logs any issues (non-fatal).
- HTTP middleware logs every request/response to `backend_logger`.
- SPA fallback at `/{full_path:path}` serves the React `dist/` build if it exists.

---

## 6. Data Model

### SQLite schema (auto-created on first connection)

```sql
announcements                   -- one row per filing
  id              TEXT PRIMARY KEY     -- BSE's NEWSID, or fallback synthesis
  scrip_code      TEXT NOT NULL
  company_name    TEXT
  segment         TEXT                 -- "Equity" | "SME" | etc
  subject         TEXT
  headline        TEXT
  category        TEXT
  dt_filed        TEXT                 -- ISO 8601 UTC
  attachment_url  TEXT
  attachment_path TEXT                 -- local PDF path, NULL until downloaded
  processed_at    TEXT                 -- ISO 8601 UTC, NULL until processor ran
  raw_json        TEXT                 -- the whole BSE JSON row, for debugging
  seen_at         TEXT NOT NULL
INDEX idx_dt_filed, idx_scrip, idx_proc

scrape_tag_hits                 -- regex matches found at scrape time (subject + headline)
  announcement_id  TEXT
  tag_id           TEXT
  tag_label        TEXT
  matched_text     TEXT (capped 240 chars)
  created_at       TEXT
  PRIMARY KEY (announcement_id, tag_id)
  FK announcement_id → announcements ON DELETE CASCADE

flag_hits                       -- regex matches found at process time (PDF body)
  announcement_id  TEXT
  flag_name        TEXT
  snippet          TEXT (capped 240 chars)
  created_at       TEXT
  PRIMARY KEY (announcement_id, flag_name)
  FK announcement_id → announcements ON DELETE CASCADE

run_history                     -- audit log of every scraper/processor run
  id              INTEGER PRIMARY KEY AUTOINCREMENT
  step            TEXT             -- "scraper" | "processor"
  started_at, finished_at TEXT
  range_from, range_to    TEXT     -- scraper only
  pages_fetched, records_scanned, matched, new_records,
  pdfs_ok, pdfs_failed, pdfs_processed, flag_hit_total,
  http_429s, http_503s, elapsed_sec INTEGER
  status          TEXT             -- "ok" | "partial" | "cancelled" | "failed"

settings_kv                     -- mirror of config.json sections
  key        TEXT PRIMARY KEY    -- "scraper" | "filter" | "processor"
  value      TEXT (JSON)
  updated_at TEXT
```

### REST payload shapes

`GET /api/announcements` returns:
```ts
{
  id: string, scripCode: string, companyName: string|null,
  segment: string|null, subject: string, headline: string,
  category: string|null, dtFiled: string|null,
  attachmentUrl: string|null, attachmentPath: string|null,
  processedAt: string|null,
  flagHits: { name: string, snippet: string }[],
  scrapeTagHits: { tagId: string, tagLabel: string, matchedText: string|null }[]
}[]
```

`GET /api/status` returns `{ activeStep, scraper: ScraperStatus, processor: ProcessorStatus }` — see `frontend/src/api.ts` for the full TypeScript types.

---

## 7. Configuration

### Location
`data/config.json` — created on first run by merging defaults with whatever exists in `settings_kv`.

### Structure
```jsonc
{
  "scraper": {
    "rateLimitDelayMs": 1000,         // delay between scrip fetches
    "pageSize": 100,
    "maxRetries": 5,
    "backoffMinSec": 2, "backoffMaxSec": 32,
    "downloadAttachments": false,
    "attachmentTimeoutSec": 30,
    "pageFetchTimeoutSec": 30,
    "userAgent": "Mozilla/5.0 ..."
  },
  "filter": {
    "tagsEnabled": true,
    "tags": [
      { "id": "investor-meet", "label": "Investor Meet",
        "pattern": "investor\\s*meet", "isActive": true },
      // ... 9 defaults: analyst-meet, investor-conference, investor-presentation,
      //                investor-call, earnings-call, conference-call,
      //                schedule-of-analyst, institutional-investor
    ],
    "watchlist": ["500325", "532540", ...],   // scrip codes
    "watchlistOnly": true
  },
  "processor": {
    "flags": [
      { "name": "InvestorMeetDate",
        "pattern": "\\b\\d{1,2}[\\s-](Jan|Feb|...)",
        "active": true, "caseInsensitive": true },
      // ... RevenueGuidance, ManagementParticipants, QuarterReference, AnalystName
    ]
  }
}
```

### Validation
- **At save** (`save_config`): every regex in `filter.tags` and `processor.flags` is `re.compile()`-checked; duplicate tag IDs raise.
- **At startup** (`validate_startup_config`, called from FastAPI's startup hook): same regex checks plus required-field assertions, but failures only log warnings — they do not block boot.

### Persistence model
The file is the source of truth; the DB `settings_kv` table is a redundant copy. If both diverge, the file wins on next `load_config()`. If the file is deleted, the DB rebuilds it.

---

## 8. API Reference

| Method | Path | Body | Returns | Codes |
|---|---|---|---|---|
| GET  | `/api/config` | — | `{ config, mtime }` | 200 |
| POST | `/api/config` | partial config | `{ config, mtime }` | 200, 400 (invalid regex) |
| GET  | `/api/status` | — | `RunStatus` | 200 |
| POST | `/api/scraper/start` | `{ from, to, watchlistOnly?, universe?, dryRun?, settingsOverride? }` | `ScraperStatus` | 200, 409 (busy) |
| POST | `/api/processor/start` | `{ mode: "all"\|"pending" }` | `ProcessorStatus` | 200, 409 |
| POST | `/api/quickrun/start` | scraper payload | `ScraperStatus` | 200, 409 |
| POST | `/api/run/stop` | — | `RunStatus` | 200, 409 (idle) |
| GET  | `/api/announcements` | — | `Announcement[]` | 200 |
| GET  | `/api/history` | — | `RunHistoryEntry[]` (last 50) | 200 |
| POST | `/api/reset` | `{ announcements?, runHistory?, pdfs? }` | `{ <flag>: true }` | 200, 409 |
| POST | `/api/logs` | `{ level, message }` | `{ status: "logged" }` | 200 |
| GET  | `/{full_path}` | — | `dist/<path>` or `dist/index.html` (SPA fallback) | 200, 404 |

---

## 9. Concurrency Model

### Single-run mutex
`coordinator._active_step` (a module-level `str | None`) gates all three start endpoints. While set to `"scraper"`, `"processor"`, or `"quickrun"`, every start call returns an `error`. The mutex is released by the engine's `_finish` → `on_idle` callback chain.

```
start_scraper(payload)
  ┌── _active_step = "scraper"
  ├── scraper.start(payload, on_idle=lambda: _active_step = None)
  └── (returns immediately; the run continues in an asyncio task)
```

For a quick-run, `on_scraper_idle` chains into `processor.start({mode:"pending"}, on_processor_idle)` so the user gets one button → both phases.

### Per-engine state
Each engine owns one `EngineState` instance (`_state`). All mutations go through `_state.update(**kwargs)` or `_state.log(msg, level)`. The `state = _state.get_all()` alias gives Streamlit and tests a stable dict reference whose keys reflect updates in real time.

### Async task lifecycle
`scraper.start` and `processor.start` use `asyncio.create_task(_run(...))` and track the task on `_state.get_all()["_task"]`. `stop()` does **not** cancel the task; it sets `_cancelRequested = True` and lets the loop bail at the next checkpoint. This guarantees `_finish` always runs and the audit `run_history` row is always written.

### Streamlit ↔ asyncio bridge
`app.py` runs the async coroutines on a daemon thread:
```python
def _target():
    asyncio.run(coro_factory())
    _job_state["running"] = False
threading.Thread(target=_target, daemon=True).start()
```

Streamlit reruns the script on every interaction, but the engine state lives in `EngineState` instances that survive between reruns because they're module globals.

---

## 10. Error Handling

### Categories
| Type | Source | Action |
|---|---|---|
| `ScraperRetryableError` | HTTP 429/503, transient network | Backoff + retry inside `_fetch_bse_page` (up to `maxRetries`) |
| `ScraperPermanentError` | Bad PDF magic, non-PDF content-type | Increment `pdfsFailed`, log warn, move on |
| `ProcessorPermanentError` | Password-protected / corrupt PDF, missing URL | Increment `pdfErrors`, **call `mark_processed` so the row is not retried** |
| Generic `Exception` | Anything unexpected | Log err, increment failure counter, **do NOT call `mark_processed`** (allows retry next run) |
| `asyncio.CancelledError` | Stop request mid-task | `_finish("cancelled")` |

### HTTP backoff
- Exponential: `wait = min(backoff_max, backoff_min * 2**attempt)`.
- 429 and 503 are tracked separately in the run-history audit.
- For the BSE PDF endpoint, distinct retry waits: 8 s for 429, 4 s for 503.

### What never raises
The two `_fetch_bse_session` helpers swallow exceptions and continue without cookies, since the BSE PDF endpoint usually works without them anyway.

---

## 11. Logging

Two layers:

### File logging (Python `logging` module)
Three named loggers, one file each, UTF-8 encoded:
- `backend_logger` — every API request/response, every engine event.
- `streamlit_logger` — user actions in the Streamlit UI.
- `frontend_logger` — relayed from React via `POST /api/logs`.

Format: `%(asctime)s - [%(levelname)s] - %(name)s - %(message)s`.

### In-memory UI log
Each `EngineState` instance maintains a list of `{ts, msg, level}` entries (capped at `LogConfig.MAX_ENTRIES = 500`). The `get_status()` snapshot includes this list, so the Streamlit/React UIs can show real-time progress without polling the file.

### React → backend log forwarding
`frontend/src/logger.ts` queues entries and flushes every 1 s via `POST /api/logs`. On `beforeunload` it switches to `navigator.sendBeacon`. Failed POSTs log a single `console.warn` and silence further attempts to avoid loops.

### What's not implemented
- Log rotation (files grow unbounded; manual cleanup).
- Log shipping (no remote sink).

---

## 12. Frontends

### Streamlit (`app.py`) — primary
Three pages selected by sidebar radio:

| Page | Function | What it does |
|---|---|---|
| **Filings** | `page_filings()` | DataFrame of all announcements with text/segment/matched filters; detail panel with PDF link |
| **Admin** | `page_admin()` | Quick Run + individual Scraper/Processor buttons; live phase, progress, log tail; date-range picker |
| **Config** | `page_config()` | Edit scraper rate-limit + page size; toggle/edit processor flags |

Threading model: each start spawns a daemon thread that calls `asyncio.run(coordinator.<start>(...))`. The page uses `st.rerun()` to refresh state.

### React (`frontend/`) — supplemental
Single-page filings view that mirrors Streamlit's Filings tab. Component tree:

```
App
├── header (title + subtitle)
└── FilingsPage           ← owns data + filter + selection state
    ├── FilingsFilters    ← search/segment/matched-only
    ├── FilingsTable      ← clickable rows
    └── FilingDetail      ← modal panel with PDF link, Esc/backdrop close
```

State is `useState` only (no Redux/React Query). Filtering is client-side (`useMemo`). API calls go through the typed wrapper in `frontend/src/api.ts`. Strict TypeScript enabled.

### FastAPI (`backend/server/main.py`) — REST
Reachable directly at `:8000`. Used by the React app via Vite's `/api` proxy and by any external consumer.

---

## 13. External Integrations

### BSE Announcements API
```
GET https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w
    ?strScrip=<code or empty for all>
    &strPrevDate=YYYYMMDD&strToDate=YYYYMMDD
    &strCat=-1&subcategory=-1&strSearch=P&strType=C
Headers: User-Agent, Referer=https://www.bseindia.com/, Accept: application/json
Returns: { Table: [...], ... }
```

Rows we extract: `NEWSID, SCRIP_CD, NEWSSUB, HEADLINE, CATEGORYNAME, COMPANY_NAME, News_submission_dt, ATTACHMENTNAME, NSURL, Sgmt`.

### BSE Scrip Header API (fallback for missing company name)
```
GET https://api.bseindia.com/BseIndiaAPI/api/getScripHeaderData/w?Scrip_Cd=<code>
```

### BSE PDF Attachments
```
GET https://www.bseindia.com/xml-data/corpfiling/AttachLive/<filename>
```

Requires a session cookie obtained from a prior `GET https://www.bseindia.com/`. The scraper warms up the session before the download loop. Validation: `Content-Type` must contain `application/pdf` AND the body must start with `%PDF`.

---

## 14. Development Workflow

### One-shot launch
```powershell
.\start-dev.ps1
```
Creates `.venv` if missing, installs `backend/requirements.txt` + `streamlit pandas`, runs `npm install` if `node_modules` is absent, then opens three console windows:
- FastAPI on `:8000`
- React (Vite) on `:5173`
- Streamlit on `:8501`

### Manual launch (any subset)
```powershell
# Backend only
.\.venv\Scripts\uvicorn.exe backend.server.main:app --reload --port 8000

# Streamlit
streamlit run app.py

# React (in /frontend)
npm run dev
```

### Verification scripts
The refactor produced these runnable smoke tests (executed via `./.venv/Scripts/python.exe -c "..."`):

1. **Module-import + state-manager round-trip** — instantiate `EngineState`, assert get/update/log/get_progress all work, validate error subclasses.
2. **FastAPI startup** — `TestClient(app)` hits `/api/config`, `/api/status`, `/api/announcements`, `/api/history` and asserts 200.
3. **Scraper end-to-end (mocked)** — `unittest.mock.patch` on `_fetch_bse_page` to return synthetic rows, run with `dryRun=True`, assert phase transitions and counters.
4. **Processor end-to-end (mocked)** — `patch` on `list_announcements`, `_extract_text`, `mark_processed`, `insert_flag_hit`; one row succeeds, one raises `ProcessorPermanentError`, both end up `mark_processed`'d.

These are not formal pytest suites — they're shell one-liners. Adding a `tests/` package with proper pytest is an extension point.

### Frontend verification
```powershell
cd frontend
npx tsc -b --noEmit          # strict type-check
npm run lint                  # ESLint with react-hooks rules
npm run build                 # Vite production build
```

---

## 15. File-by-File Cheat Sheet

| File | Lines | Role |
|---|---:|---|
| `app.py` | ~340 | Streamlit UI — Filings/Admin/Config tabs |
| `start-dev.ps1` | 69 | Windows launcher |
| `backend/requirements.txt` | 4 | Python deps |
| `backend/server/main.py` | ~210 | FastAPI routes + startup hooks + SPA fallback |
| `backend/server/coordinator.py` | 92 | Single-run mutex + quick-run chaining |
| `backend/server/scraper_engine.py` | ~575 | Announcements fetch + PDF download |
| `backend/server/processor_engine.py` | ~390 | PDF extract + regex flag matching |
| `backend/server/store.py` | ~280 | SQLite ops |
| `backend/server/config_store.py` | ~245 | JSON config + KV mirror + validation |
| `backend/server/state_manager.py` | ~120 | `EngineState` class |
| `backend/server/logger.py` | 28 | Named-logger factory |
| `backend/server/errors.py` | 27 | Exception hierarchy |
| `backend/server/constants.py` | 50 | Tunable constants |
| `frontend/src/main.tsx` | 10 | React entry |
| `frontend/src/App.tsx` | 22 | Shell + page mount |
| `frontend/src/api.ts` | ~155 | Typed API client |
| `frontend/src/logger.ts` | ~95 | Batched log forwarder |
| `frontend/src/components/FilingsPage.tsx` | ~115 | Page state + data fetch |
| `frontend/src/components/FilingsFilters.tsx` | ~45 | Filter inputs |
| `frontend/src/components/FilingsTable.tsx` | ~65 | Table renderer |
| `frontend/src/components/FilingDetail.tsx` | ~115 | Modal panel |
| `frontend/src/App.css` | ~325 | Component styles |
| `frontend/src/index.css` | 112 | CSS variables (light/dark) |

---

## 16. Key Design Decisions & Rationale

### Why three UIs?
- **Streamlit** — fastest path for the analyst's daily workflow; rich pandas/plotly support if reports get added.
- **FastAPI** — raw API for scripted/headless use and as the data layer for…
- **React** — modern UI when richer interactions are needed (the filings table is more responsive than Streamlit's `st.dataframe`).

All three call the same engines; no logic is duplicated.

### Why SQLite + a JSON config file?
- Single-user, single-machine app — Postgres/Redis would be overkill.
- SQLite WAL mode handles the rare concurrent reads (Streamlit while a scraper runs).
- The JSON file is human-editable for power users; the `settings_kv` table is a redundant safety net.

### Why `EngineState` instead of module-level dicts?
The original code had ~50-key mutable dicts at module scope. That made:
- testing impossible without monkey-patching globals,
- thread-safety reasoning hard,
- code duplicated across the two engines.

Encapsulating in a class with `update`/`log`/`get_progress` methods removed ~150 lines of duplication and made the engines symmetric. The `state = _state.get_all()` alias preserves backward-compat for `app.py`.

### Why custom error types?
The two interesting axes are:
1. Should we **retry** automatically? → `Retryable` vs not.
2. Should we **mark the row processed** anyway, to skip it next run? → `Permanent` vs not.

Plain `Exception` collapses both, leading to either infinite-retry loops (on truly broken PDFs) or premature give-up (on transient HTTP errors).

### Why `mark_processed` on `ProcessorPermanentError`?
Otherwise the same broken PDF gets fetched and parsed again on every "pending" run forever. Marking it processed lets `mode=all` re-attempt it on demand without polluting the default workflow.

### Why no test suite (yet)?
Time/scope. The refactor produced runnable end-to-end smoke tests as inline `python -c` snippets and verified everything green. Promoting them to `pytest` files is a clean extension and a separate task.

---

## 17. Known Limitations & Extension Points

| Limitation | Where | Possible fix |
|---|---|---|
| Single-user, single-process | `coordinator._active_step` | Pull state into Redis if multi-user is needed |
| No log rotation | `logger.py` (FileHandler, not RotatingFileHandler) | Switch to `RotatingFileHandler` with size cap |
| Sequential scrip fetch | `scraper_engine._load_candidates` (one scrip at a time) | `asyncio.gather` with a semaphore would speed up watchlists of 100+ |
| No tests | n/a | Add `tests/` with pytest + pytest-asyncio |
| BSE rate limits unknown | `HttpConfig.BACKOFF_*` are guesses | Telemetry on `http_429s`/`http_503s` would inform tuning |
| Hardcoded SPA fallback path | `main.py:_dist = "dist"` | Move to `PathConfig` |
| No CSRF/auth on API | `main.py` | Acceptable for localhost-only; revisit if exposed |
| React app is read-only | `frontend/src/components` | Adding admin controls / config editor is straight Tier-2 work |

---

## 18. Glossary

| Term | Meaning |
|---|---|
| **Scrip code** | BSE's stock identifier — a 6-digit number (e.g. `500325` = Reliance Industries) |
| **Filing / Announcement** | A regulatory disclosure submitted by a listed company. Equivalent terms in the codebase. |
| **Tag** | A regex matched at scrape time against the announcement's *subject + headline* (cheap; no PDF needed). Identifies the kind of filing (e.g. "Investor Meet"). |
| **Flag** | A regex matched at process time against the *PDF body text* (expensive; requires download + extraction). Identifies structured data points inside the announcement (e.g. dates, names, numbers). |
| **Watchlist** | List of scrip codes the user cares about. `watchlistOnly=true` filters the BSE feed to just these. |
| **Universe** | Opposite of watchlist — fetch announcements for *all* scrips in the date range. |
| **Quick Run** | Scraper followed by processor, chained automatically. Single-button workflow. |
| **Pending records** | Announcements where `processed_at IS NULL`. The processor's default mode targets only these. |
| **Phase** | An engine's lifecycle stage: `idle → fetching → downloading → done` (scraper) or `idle → extracting → done` (processor). Plus `cancelled` and `failed` terminal states. |

---

*Last updated: 2026-05-06.  Maintained alongside the codebase — when the design changes, update this file in the same commit.*
