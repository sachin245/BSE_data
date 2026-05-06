# BSE_data

A single-user desktop app that scrapes corporate announcements from the **Bombay Stock Exchange (BSE)**, downloads their PDF attachments, runs configurable regex "flags" against the extracted text, and surfaces results through three independent UIs sharing one Python backend.

> Built for a solo analyst monitoring Indian equity-market disclosures — fetch a watchlist's filings, mine their PDFs for structured data points (investor-meet dates, earnings-call schedules, management quotes, revenue guidance), and review hits in a clean filings table.

---

## Highlights

- **Scraper engine** — async `httpx` pipeline with exponential backoff for HTTP 429/503, session-cookie warm-up, and PDF magic-byte validation.
- **Processor engine** — extracts text via `pdfplumber`, runs configurable regex flags, stores 80-char snippets around each match.
- **Three UIs, one backend** — Streamlit control panel, React filings viewer, and a raw FastAPI REST API. No logic is duplicated.
- **Quick Run** — single-click chain: scraper → processor on pending records.
- **Resilient by design** — custom error hierarchy distinguishes transient (retry) from permanent (skip) failures, so broken PDFs don't infinite-loop and transient HTTP errors don't get prematurely abandoned.
- **Audit trail** — every run writes a `run_history` row with timing, counts, status, and HTTP error tallies.

---

## Tech Stack

**Backend** — Python 3.11, FastAPI, uvicorn, httpx, pdfplumber, SQLite (WAL mode), Streamlit, pandas
**Frontend** — React 19, Vite 8, TypeScript 6 (strict), ESLint
**Storage** — SQLite (`data/announcements.db`) + JSON config (`data/config.json`) with KV mirror

---

## Architecture (at a glance)

```
   BSE Public APIs (announcements, scrip header, PDF attachments)
                         │
                         ▼
            ┌────────────────────────────┐
            │    backend/server (Python) │
            │  scraper / processor       │
            │  coordinator (run mutex)   │
            │  store (SQLite) + config   │
            └─────────────┬──────────────┘
                          │ HTTP / in-process
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
   Streamlit          React (Vite)      FastAPI
   port 8501          port 5173         port 8000
```

Streamlit calls the engines as Python imports; React talks to FastAPI; FastAPI calls the same engines. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design — modules, data model, concurrency, error handling, and rationale.

---

## Quick Start (Windows)

Prerequisites: **Python 3.11+** and **Node.js 18+**.

```powershell
.\start-dev.ps1
```

The launcher will:
1. Create `.venv` if it doesn't exist and install [backend/requirements.txt](backend/requirements.txt) plus `streamlit pandas`.
2. Run `npm install` in `frontend/` if `node_modules` is absent.
3. Open three console windows for the three services.

After startup:

| Service | URL |
|---|---|
| Streamlit (primary control panel) | http://localhost:8501 |
| React filings viewer | http://localhost:5173 |
| FastAPI backend | http://localhost:8000 |

### Manual launch (any subset)

```powershell
# Backend only
.\.venv\Scripts\uvicorn.exe backend.server.main:app --reload --port 8000

# Streamlit
streamlit run app.py

# React (in /frontend)
npm run dev
```

---

## Project Structure

```
BSE_data/
├── app.py                    # Streamlit primary UI
├── start-dev.ps1             # One-shot launcher (Windows)
├── backend/
│   ├── requirements.txt
│   └── server/
│       ├── main.py           # FastAPI app + routes
│       ├── coordinator.py    # Single-run mutex
│       ├── scraper_engine.py # Fetches BSE announcements + PDFs
│       ├── processor_engine.py # PDF text + regex flags
│       ├── store.py          # SQLite ops
│       ├── config_store.py   # JSON config + KV mirror
│       ├── state_manager.py  # EngineState class
│       ├── logger.py         # Named file-loggers
│       ├── errors.py         # Exception hierarchy
│       └── constants.py      # Tunable values
├── frontend/                 # React + Vite + TypeScript
│   └── src/
│       ├── api.ts            # Typed fetch wrappers
│       └── components/       # FilingsPage / Filters / Table / Detail
├── data/                     # Generated at runtime
│   ├── config.json           # User-editable config
│   ├── announcements.db      # SQLite database
│   └── attachments/<scrip>/<id>.pdf
├── logs/                     # Generated at runtime
└── docs/
    └── ARCHITECTURE.md
```

---

## Configuration

User-editable file at [data/config.json](data/config.json) (created on first run). Three sections:

- **`scraper`** — rate-limit delay, page size, retry/backoff, attachment download toggle, user-agent.
- **`filter`** — regex *tags* matched against subject + headline at scrape time, plus a watchlist of scrip codes.
- **`processor`** — regex *flags* matched against PDF body text at process time.

> **Tag vs Flag** — *Tags* are cheap regex hits on the headline (no PDF needed). *Flags* are heavier regex hits on the extracted PDF body, used to pull out structured data points like dates, names, or guidance numbers.

All regexes are validated on save and at startup. Full schema and defaults are documented in [docs/ARCHITECTURE.md §7](docs/ARCHITECTURE.md).

---

## API Reference

| Method | Path | Purpose |
|---|---|---|
| GET  | `/api/config` | Current config + mtime |
| POST | `/api/config` | Save partial config (validates regex) |
| GET  | `/api/status` | Engine state for both scraper & processor |
| POST | `/api/scraper/start` | Start scraper run |
| POST | `/api/processor/start` | Start processor (`mode: all\|pending`) |
| POST | `/api/quickrun/start` | Scraper → processor chain |
| POST | `/api/run/stop` | Cooperative cancel |
| GET  | `/api/announcements` | All filings with flag/tag hits |
| GET  | `/api/history` | Last 50 runs |
| POST | `/api/reset` | Wipe announcements / history / PDFs |
| POST | `/api/logs` | Forward frontend log lines |

Returns 409 on start endpoints when the single-run mutex is held. Full payload shapes in [frontend/src/api.ts](frontend/src/api.ts).

---

## Data Model

Five SQLite tables (auto-created on first connection):

- **`announcements`** — one row per filing (BSE NEWSID, scrip, subject, headline, attachment path, processed_at, raw JSON).
- **`scrape_tag_hits`** — regex matches on subject + headline at scrape time.
- **`flag_hits`** — regex matches on PDF body at process time, with snippets.
- **`run_history`** — audit log of every run (timing, counts, HTTP error tallies, status).
- **`settings_kv`** — redundant copy of `config.json` sections.

Schema details in [docs/ARCHITECTURE.md §6](docs/ARCHITECTURE.md).

---

## Logging

Three UTF-8 file loggers in `logs/`:

- `backend.log` — every API request/response, every engine event
- `streamlit.log` — Streamlit user actions
- `frontend.log` — React logs forwarded via `POST /api/logs`

Each engine also keeps an in-memory rolling log (capped at 500 entries) surfaced through `/api/status` for live UI updates.

---

## Frontend Verification

```powershell
cd frontend
npx tsc -b --noEmit   # strict type-check
npm run lint          # ESLint with react-hooks rules
npm run build         # Vite production build
```

---

## Known Limitations

- Single-user, single-process (the `_active_step` mutex is module-level).
- No log rotation — files grow unbounded.
- Scrip fetch is sequential; large watchlists could parallelize with `asyncio.gather` + semaphore.
- No authentication on the API — fine for localhost, revisit before exposing.
- Smoke tests only (inline `python -c` snippets); no `pytest` suite yet.

Full list with suggested fixes in [docs/ARCHITECTURE.md §17](docs/ARCHITECTURE.md).

---

## Glossary

| Term | Meaning |
|---|---|
| **Scrip code** | BSE 6-digit stock identifier (e.g. `500325` = Reliance Industries) |
| **Filing / Announcement** | A regulatory disclosure submitted by a listed company |
| **Tag** | Regex matched at scrape time against subject + headline (cheap) |
| **Flag** | Regex matched at process time against PDF body text (expensive) |
| **Watchlist** | Scrip codes the user cares about; `watchlistOnly=true` filters the feed |
| **Quick Run** | Scraper followed by processor, chained automatically |
| **Pending record** | Announcement where `processed_at IS NULL` |

---

## License

Not specified.
