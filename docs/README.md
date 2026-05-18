# SME Indicators Agent

A real-time intelligence platform that tracks leading indicators for Indian SME-listed companies on BSE (Emerge) and NSE SME segments. The system scrapes corporate filings, parses financial and textual data, computes sector-level health scores, and visualises them on an interactive dashboard.

---

## Table of Contents

1. [What This App Does](#what-this-app-does)
2. [Architecture Overview](#architecture-overview)
3. [Data Pipeline](#data-pipeline)
4. [Indicators Computed](#indicators-computed)
5. [Database Schema](#database-schema)
6. [Current Status](#current-status)
7. [Roadmap & Open Tasks](#roadmap--open-tasks)
8. [EC2 Deployment](#ec2-deployment)
9. [AWS Deployment Plan](#aws-deployment-plan)
10. [Local Setup](#local-setup)
11. [Environment Variables](#environment-variables)
12. [Running the Pipeline](#running-the-pipeline)

---

## What This App Does

Indian SME companies listed on BSE Emerge and NSE SME file quarterly results, annual reports, and ad-hoc announcements with the exchanges. These filings contain forward-looking signals — order book commentary, capex plans, export outlook, credit stress — that are buried in PDFs and XBRL XMLs and rarely aggregated at scale.

This platform:

- **Scrapes** BSE and NSE APIs daily for new corporate filings (announcements + financial results)
- **Parses** each filing: extracts structured financials from XBRL/XML files and business signals from PDFs via keyword scanning
- **Computes** six sector-level leading indicators plus a composite health score on a 0–100 scale
- **Visualises** everything on a React dashboard (served by FastAPI) with sector heatmaps, trend lines, company drill-downs, and a searchable filings feed

The result is a daily pulse-check on SME sector health before the broader market catches up.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                     agent.py (CLI)                       │
│            --scrape | --parse | --compute                │
└──────────┬──────────────┬──────────────┬────────────────┘
           │              │              │
    ┌──────▼──────┐ ┌─────▼──────┐ ┌────▼───────────────┐
    │ BSE Scraper │ │ NSE Scraper│ │  Indicator Engine   │
    │ (REST API)  │ │(Playwright)│ │  (indicators/)      │
    └──────┬──────┘ └─────┬──────┘ └────────────────────┘
           │              │
    ┌──────▼──────────────▼──────┐
    │        raw_filings          │
    │        (DuckDB)             │
    └──────┬──────────────┬──────┘
           │              │
    ┌──────▼──────┐ ┌─────▼──────┐
    │ PDF Parser  │ │XBRL Parser │
    │(PyMuPDF +   │ │ (lxml)     │
    │ pdfplumber) │ │            │
    └──────┬──────┘ └─────┬──────┘
           │              │
    ┌──────▼──────┐ ┌─────▼──────┐
    │filing_signals│ │ financials │
    └──────┬──────┘ └─────┬──────┘
           └──────┬────────┘
                  │
          ┌───────▼───────┐
          │  indicators   │
          │  (0-100 score)│
          └───────┬───────┘
                  │
          ┌───────▼───────┐
          │  FastAPI      │
          │  (REST API +  │
          │  React SPA)   │
          └───────────────┘
```

### Component Breakdown

| Component | File | Responsibility |
|---|---|---|
| CLI Orchestrator | `agent.py` | Runs scrape → parse → compute pipeline end-to-end |
| Configuration | `config.py` | All constants: API URLs, indicator weights, NLP keywords |
| BSE Scraper | `scrapers/bse_scraper.py` | Fetches announcements and financial results from BSE REST API |
| NSE Scraper | `scrapers/nse_scraper.py` | Fetches from NSE API using Playwright for bot-detection bypass |
| PDF Parser | `parsers/pdf_parser.py` | Downloads PDFs, extracts text and tables, flags business signals |
| XBRL Parser | `parsers/xbrl_parser.py` | Parses XBRL/XML financial disclosures (revenue, EBITDA, PAT, debt) |
| Indicator Engine | `indicators/engine.py` | Aggregates signals and financials into 6 sector indicators + composite |
| Database Layer | `storage/database.py` | DuckDB schema, upsert operations, generic query interface |
| Sector Classifier | `storage/sectors.py` | Keyword-based sector tagging; backfills sector into all tables |
| REST API | `api/main.py` + `api/routers/` | FastAPI app serving data endpoints and the React SPA |
| React SPA | `frontend/src/` | Interactive dashboard: heatmaps, trend lines, company drill-down |
| Legacy Dashboard | `dashboard/app.py` | Streamlit UI (superseded by React SPA, kept for reference) |

---

## Data Pipeline

### Step 1 — Scrape

```bash
python agent.py --scrape --days 90
```

- **BSE Scraper** hits `https://api.bseindia.com/BseIndiaAPI/api` for:
  - `/AnnSubCategoryGetData/w` — corporate announcements
  - `/getFinancialResults/w` — quarterly/annual results
  - Falls back to HTML scraping if API is unavailable
- **NSE Scraper** uses Playwright to launch a headless Chrome browser, harvests session cookies from NSE's homepage (required to bypass bot detection), then hits `https://www.nseindia.com/api/corp-announcements` with pagination
- Each filing is deduplicated via an MD5 hash of `(exchange, company_code, filing_date, headline)` and upserted into `raw_filings`

### Step 2 — Parse

```bash
python agent.py --parse
```

Two parsers run in sequence on unprocessed filings:

- **PDF Parser**: Downloads PDFs to `data/pdfs/` cache → extracts full text (PyMuPDF) and tables (pdfplumber) → scans for NLP keyword categories (order_book, capex, credit_stress, export, headcount) → writes boolean signal flags to `filing_signals`
- **XBRL Parser**: Derives the XBRL/XML URL from the filing's PDF URL → fetches and parses XML with lxml → extracts revenue, EBITDA, PAT, total debt and period metadata → writes to `financials`

### Step 3 — Compute

```bash
python agent.py --compute
```

The indicator engine reads `financials` and `filing_signals`, groups by sector, computes six indicators (each normalised 0–100), and writes a composite weighted score to `indicators`.

---

## Indicators Computed

All indicators are normalised to a **0–100 scale**. Higher is always better (stress metrics are inverted).

| Indicator | Weight | Source | How It's Computed |
|---|---|---|---|
| Revenue Momentum | 25% | `financials` | Quarter-on-quarter revenue growth rate, normalised |
| Margin Pressure | 20% | `financials` | EBITDA / Revenue trend; higher = expanding margins |
| Order Book Signal | 20% | `filing_signals` | % of filings in past 90 days mentioning order book keywords |
| Credit Stress | 15% | `filing_signals` | % mentioning stress keywords, **inverted** so higher = less stress |
| Capex Intentions | 10% | `filing_signals` | % of filings mentioning capex / expansion keywords |
| Export Outlook | 10% | `filing_signals` | % mentioning export / forex / global keywords |
| **Composite Score** | 100% | All above | Weighted average of the six indicators |

**NLP Keyword Categories** (defined in `config.py`):

| Category | Sample Keywords |
|---|---|
| Order Book | "order book", "order inflow", "order pipeline", "order backlog" |
| Capex | "capital expenditure", "capex", "capacity expansion", "new plant" |
| Credit Stress | "npa", "default", "debt restructuring", "liquidity crunch", "stressed" |
| Export | "export", "foreign exchange", "forex", "overseas", "global markets" |
| Headcount | "hiring", "headcount", "workforce expansion", "recruitment" |

---

## Database Schema

Currently backed by **DuckDB** (embedded, file-based at `data/sme_indicators.duckdb`). No external database server is required for local development.

### `raw_filings`
Stores every filing scraped from BSE and NSE.

| Column | Type | Description |
|---|---|---|
| id | VARCHAR (PK) | MD5 deduplication hash |
| exchange | VARCHAR | "BSE" or "NSE" |
| company_code | VARCHAR | Exchange ticker/code |
| company_name | VARCHAR | Registered company name |
| filing_date | DATE | Date of filing |
| category | VARCHAR | "Announcement" or "Results" |
| headline | VARCHAR | Filing subject line |
| pdf_url | VARCHAR | Direct link to filing PDF |
| raw_json | TEXT | Full raw API response (JSON string) |
| scraped_at | TIMESTAMP | Ingestion timestamp |

### `financials`
Parsed quarterly/annual financial data from XBRL files.

| Column | Type | Description |
|---|---|---|
| filing_id | VARCHAR (FK) | Links to raw_filings.id |
| revenue | DOUBLE | Total revenue (INR, in filing units) |
| ebitda | DOUBLE | Operating profit |
| pat | DOUBLE | Profit after tax |
| total_debt | DOUBLE | Total borrowings |
| period_end | DATE | Financial period end date |
| period_type | VARCHAR | "Q" (quarterly) or "A" (annual) |
| parsed_at | TIMESTAMP | Parsing timestamp |

### `filing_signals`
Boolean NLP flags extracted from filing PDFs.

| Column | Type | Description |
|---|---|---|
| filing_id | VARCHAR (FK) | Links to raw_filings.id |
| order_book | BOOLEAN | Mentions order book / inflows |
| capex | BOOLEAN | Mentions capital expenditure |
| credit_stress | BOOLEAN | Mentions credit / liquidity stress |
| export | BOOLEAN | Mentions exports / forex |
| headcount | BOOLEAN | Mentions hiring / headcount |
| raw_text_excerpt | TEXT | First 5,000 chars of extracted text |
| parsed_at | TIMESTAMP | Parsing timestamp |

### `indicators`
Sector-level aggregated indicator scores.

| Column | Type | Description |
|---|---|---|
| sector | VARCHAR | Sector classification |
| revenue_momentum | DOUBLE | 0–100 score |
| margin_pressure | DOUBLE | 0–100 score |
| order_book_signal | DOUBLE | 0–100 score |
| credit_stress | DOUBLE | 0–100 score (inverted) |
| capex_intentions | DOUBLE | 0–100 score |
| export_outlook | DOUBLE | 0–100 score |
| composite_score | DOUBLE | Weighted composite 0–100 |
| as_of_date | DATE | Computation date |
| computed_at | TIMESTAMP | Computation timestamp |

---

## Current Status

### Completed

- [x] BSE scraper (REST API + HTML fallback)
- [x] NSE scraper (Playwright session, paginated)
- [x] PDF parser (PyMuPDF text + pdfplumber tables + keyword scanning)
- [x] XBRL parser (lxml-based, namespace-aware financial extraction)
- [x] Indicator engine (6 indicators, weighted composite, 0-100 normalisation)
- [x] DuckDB schema and upsert layer
- [x] Streamlit dashboard (heatmap, trend lines, filings table, refresh button)
- [x] CLI orchestrator (`agent.py` with `--scrape`, `--parse`, `--compute`, `--days`)
- [x] PDF caching to disk
- [x] Deduplication via MD5 hash

### In Progress / Known Gaps

- [ ] XBRL URL derivation is fragile (`.pdf → .xml` heuristic — fails for non-standard URLs)
- [ ] PDF batch limit is hardcoded at 200 filings per run (scalability bottleneck)
- [ ] No OCR for scanned/image PDFs (many older filings are image-only)
- [ ] Sector classification not yet implemented (filings are not tagged by sector)
- [ ] NSE Playwright session not cached across runs (re-launches browser every execution)
- [ ] No alerting or monitoring on pipeline failures
- [ ] No authentication on the Streamlit dashboard
- [ ] Financial extraction from PDF tables is heuristic-based, not production-grade

---

## Roadmap & Open Tasks

### Phase 1 — Data Quality (Next Up)

- [ ] **Sector tagging**: Map BSE/NSE company codes to NIC sector classifications using a reference table (BSE provides a downloadable master list)
- [ ] **OCR for scanned PDFs**: Integrate `pytesseract` or AWS Textract for image-based PDFs
- [ ] **Robust XBRL URL resolution**: Query BSE/NSE filing metadata APIs for the actual XBRL attachment URL instead of guessing from PDF URL
- [ ] **Playwright session caching**: Persist NSE cookies to disk with expiry handling to avoid relaunching Chrome on every run
- [ ] **Remove the 200-filing batch cap**: Process all pending filings per run, or implement a proper job queue

### Phase 2 — Infrastructure & Productionisation

- [ ] **Migrate from DuckDB to PostgreSQL (RDS)**: Required for multi-process writes and persistent cloud storage (see AWS Deployment Plan below)
- [ ] **Scheduler**: Replace manual CLI runs with a cron job or AWS EventBridge scheduled trigger
- [ ] **Containerise with Docker**: Package the pipeline and dashboard as separate Docker containers
- [ ] **CI/CD pipeline**: GitHub Actions for linting, testing, and automated Docker builds
- [ ] **Unit and integration tests**: Currently zero test coverage

### Phase 3 — Feature Expansion

- [ ] **Company-level drill-down**: Dashboard currently shows sector aggregates only; add per-company view
- [ ] **Historical backtesting**: Validate whether composite score leads actual earnings/price moves
- [ ] **Alerts**: Email / Slack notifications when a sector score crosses a threshold
- [ ] **LLM-powered summarisation**: Use an LLM to generate a one-paragraph narrative from each filing instead of just keyword flags
- [ ] **Peer comparison**: Show a company's indicators relative to its sector median
- [ ] **API layer**: Expose indicator data as a REST API (FastAPI) for downstream consumers

### Phase 4 — Scale

- [ ] **Real-time streaming**: Move from daily batch to event-driven (trigger parse immediately when a new filing is scraped)
- [ ] **Distributed scraping**: Run BSE and NSE scrapers in parallel workers (Celery / AWS SQS)
- [ ] **Vector search**: Embed filing text chunks into a vector DB for semantic similarity and trend detection
- [ ] **Dashboard authentication**: Add user login (Streamlit auth or reverse proxy with OAuth)

---

## EC2 Deployment

The app currently runs on an AWS EC2 instance managed via systemd + nginx.

### Connection details

| | |
|---|---|
| **IP address** | `98.81.94.194` |
| **SSH key** | `C:\Users\ResolveWave\Documents\GitHub\ec2-access.pem` |
| **SSH user** | `ubuntu` |
| **App directory** | `~/SME_indicators` |
| **Service** | `sme-api` (systemd) |
| **Internal port** | `8000` (uvicorn, nginx proxies port 80/443) |
| **Public URL** | `http://98.81.94.194` |

### Connect via SSH

```bash
ssh -i "C:\Users\ResolveWave\Documents\GitHub\ec2-access.pem" ubuntu@98.81.94.194
```

On macOS/Linux, set key permissions first:
```bash
chmod 400 ec2-access.pem
```

### Redeploy after a code change

```bash
ssh -i "C:\Users\ResolveWave\Documents\GitHub\ec2-access.pem" ubuntu@98.81.94.194 "
  cd ~/SME_indicators &&
  git pull origin main &&
  source venv/bin/activate &&
  pip install -r requirements.txt -q &&
  sudo systemctl restart sme-api
"
```

### Service management

```bash
# Check status
sudo systemctl status sme-api

# View live logs
sudo journalctl -u sme-api -f

# Restart
sudo systemctl restart sme-api
```

### Set the OpenAI key on EC2

```bash
ssh -i "C:\Users\ResolveWave\Documents\GitHub\ec2-access.pem" ubuntu@98.81.94.194
nano ~/SME_indicators/.env
# Add: OPENAI_API_KEY=sk-...your-key...
sudo systemctl restart sme-api
```

---

## AWS Deployment Plan

The target architecture deploys the pipeline as a scheduled batch job on AWS, with a managed database and a publicly accessible dashboard.

```
┌─────────────────────────────────────────────────────────────┐
│                        AWS Cloud                             │
│                                                              │
│  ┌──────────────┐    ┌─────────────────────────────────┐    │
│  │  EventBridge │───►│  ECS Fargate Task (pipeline)    │    │
│  │  (daily cron)│    │  agent.py --scrape --parse      │    │
│  └──────────────┘    │          --compute               │    │
│                       └────────────────┬────────────────┘    │
│                                        │                     │
│                              ┌─────────▼──────────┐         │
│                              │  Amazon RDS         │         │
│                              │  (PostgreSQL)       │         │
│                              │  - raw_filings      │         │
│                              │  - financials       │         │
│                              │  - filing_signals   │         │
│                              │  - indicators       │         │
│                              └─────────┬──────────┘         │
│                                        │                     │
│  ┌──────────────────────────────────────▼──────────────┐    │
│  │  ECS Fargate Service (dashboard)                     │    │
│  │  streamlit run dashboard/app.py                      │    │
│  │  ◄── ALB (HTTPS) ◄── Route 53 (custom domain)       │    │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌───────────────┐  │
│  │  S3 Bucket   │    │  CloudWatch  │    │  Secrets Mgr  │  │
│  │  (PDF cache) │    │  (logs +     │    │  (DB creds,   │  │
│  │              │    │   alerts)    │    │   API keys)   │  │
│  └──────────────┘    └──────────────┘    └───────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### AWS Services Required

| Service | Purpose | Notes |
|---|---|---|
| **ECS Fargate** | Run pipeline and dashboard containers | Serverless; no EC2 to manage |
| **ECR** | Store Docker images | One repo for pipeline, one for dashboard |
| **Amazon RDS (PostgreSQL)** | Replace DuckDB for persistent, multi-process storage | `db.t3.micro` sufficient to start |
| **Amazon S3** | Persistent PDF cache (replace local `data/pdfs/`) | PDF files can be large; S3 scales cheaply |
| **EventBridge Scheduler** | Trigger daily pipeline run | Cron expression: `cron(0 2 * * ? *)` (2 AM IST) |
| **Application Load Balancer** | HTTPS termination for dashboard | With ACM certificate |
| **Route 53** | Custom domain for dashboard | Optional but recommended |
| **AWS Secrets Manager** | Store DB credentials, API keys | Never hardcode secrets |
| **CloudWatch Logs** | Centralised logging for pipeline and dashboard | Set up log groups per container |
| **CloudWatch Alarms** | Alert on pipeline failures or error spikes | SNS → email/Slack |

### Database Migration Steps (DuckDB → PostgreSQL on RDS)

1. **Provision RDS instance**
   - Engine: PostgreSQL 15
   - Instance class: `db.t3.micro` (upgrade later)
   - Multi-AZ: off initially, enable for production
   - Storage: 20 GB gp3 (auto-scaling enabled)
   - VPC: same as ECS tasks; no public access

2. **Update `storage/database.py`**
   - Replace `duckdb.connect()` with `psycopg2` / `sqlalchemy` connection
   - Connection string from environment variable: `DATABASE_URL`
   - Add connection pooling (`pgbouncer` or `sqlalchemy` pool)

3. **Run schema migration**
   - Port `init_db()` CREATE TABLE statements to PostgreSQL syntax
   - Add indexes on frequently queried columns:
     - `raw_filings(filing_date, exchange)`
     - `financials(filing_id, period_end)`
     - `indicators(sector, as_of_date)`

4. **Migrate PDF storage to S3**
   - Replace `data/pdfs/` local cache with `boto3` S3 reads/writes
   - Key pattern: `s3://sme-indicators-pdfs/{exchange}/{company_code}/{filename}`

5. **Store credentials in Secrets Manager**
   - Secret keys: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
   - Access via `boto3.client('secretsmanager')` at startup

### Deployment Steps (ECS Fargate)

1. Write `Dockerfile.pipeline` and `Dockerfile.dashboard`
2. Push images to ECR
3. Create ECS cluster (Fargate launch type)
4. Create two ECS task definitions: `sme-pipeline` and `sme-dashboard`
5. Create ECS service for the dashboard (desired count: 1, behind ALB)
6. Create EventBridge rule targeting the pipeline task definition
7. Configure CloudWatch log groups and alarms
8. Set all environment variables via ECS task definition secrets (pointing to Secrets Manager ARNs)

### Estimated Monthly AWS Cost (starting footprint)

| Service | Estimated Cost |
|---|---|
| RDS db.t3.micro (PostgreSQL) | ~$15/month |
| ECS Fargate — dashboard (0.25 vCPU, 0.5 GB, always-on) | ~$10/month |
| ECS Fargate — pipeline (1 vCPU, 2 GB, ~5 min/day) | ~$1/month |
| S3 (PDF storage, ~10 GB) | ~$0.25/month |
| ALB | ~$18/month |
| CloudWatch, ECR, misc | ~$5/month |
| **Total** | **~$50/month** |

---

## Local Setup

### Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.11+ | `python --version` to check |
| Node.js | 18+ | Required for the React frontend |
| npm | 9+ | Comes with Node.js |
| Git | any | |
| Playwright browsers | — | Installed via `playwright install chromium` |

### 1 — Clone and set up Python

```bash
git clone https://github.com/sachin245/SME_indicators.git
cd SME_indicators

python -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows

pip install -r requirements.txt
playwright install chromium
```

### 2 — Set up the React frontend

```bash
cd frontend
npm install
cd ..
```

### 3 — Initialise the database

```bash
python -c "from storage.database import init_db; init_db()"
```

Creates `data/sme_indicators.duckdb` with the four tables.

---

## Environment Variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env       # macOS / Linux
# copy .env.example .env   # Windows
```

| Variable | Description | Default |
|---|---|---|
| `DB_PATH` | Path to SQLite database file | `data/sme_indicators.db` |
| `PDF_CACHE_DIR` | Local PDF cache directory | `data/pdfs/` |
| `REQUEST_DELAY` | Seconds between HTTP requests | `1.5` |
| `OPENAI_API_KEY` | OpenAI key — enables GPT-4o-mini extraction (signals + financials in one call) | _(unset — falls back to regex)_ |
| `PDF_WORKERS` | Parallel threads for PDF download + extraction | `10` |
| `USE_AI_PARSER` | Set to `false` to force regex/pdfplumber even when key is present | `true` |
| `BATCH_SIZE` | Max filings processed per parser run | `500` |
| `EXTRA_CORS_ORIGINS` | Comma-separated extra CORS origins | _(empty)_ |

---

## Running Locally

### Step 1 — Run the data pipeline

```bash
# Activate your venv first
source venv/bin/activate

# Full pipeline — scrape BSE/NSE, parse PDFs/XBRL, compute indicators
python agent.py --scrape --parse --compute --days 90

# Individual stages
python agent.py --scrape --days 30   # scrape only, last 30 days
python agent.py --parse              # parse all unprocessed filings
python agent.py --compute            # recompute indicators from existing data
```

### Step 2 — Start the API server

```bash
# From the repo root (venv activated)
uvicorn api.main:app --host 0.0.0.0 --port 8002 --reload
```

The API is now available at `http://localhost:8002/api/...`

### Step 3a — Frontend dev server (hot-reload, recommended for development)

```bash
cd frontend
npm run dev
```

Open `http://localhost:5173` in your browser. The Vite dev server proxies all
`/api` requests to `http://localhost:8002`, so the API and UI talk to each other
automatically.

### Step 3b — Serve the built SPA via FastAPI (production-like)

```bash
cd frontend
npm run build
cd ..
uvicorn api.main:app --host 0.0.0.0 --port 8002
```

Open `http://localhost:8002` — FastAPI serves the compiled React SPA from
`frontend/dist/` and the API under `/api/`.

> **Role split:** the React SPA at `http://localhost:8002/` is **read-only**
> — it visualises the data but never mutates it. To pull or refresh data, run
> the **Streamlit admin console** (`streamlit run dashboard/app.py`). See the
> [Streamlit Admin](#streamlit-admin) section below.

---

## Streamlit Admin

The Streamlit app at `dashboard/app.py` is the operator-facing console. Use it
to trigger scrapes, parse PDFs/XBRL, recompute indicators, and inspect data
freshness. Charts and end-user views live in the React SPA — Streamlit is
deliberately scoped to data ops.

### Run locally (in-process pipeline)

```bash
source venv/bin/activate
streamlit run dashboard/app.py
```

Opens at `http://localhost:8501`. In **local mode** the admin app calls
`agent.py` functions directly in a background thread, so it shares the same
DuckDB file as your local API server.

What you get:

- Per-stage buttons: **Scrape**, **Parse**, **Compute**, **Full pipeline**
- Configurable scrape lookback (7–365 days)
- **Parser toggle: OpenAI (`gpt-4o-mini`) ↔ regex/pdfplumber** — flip per run from the sidebar; falls back to regex automatically if `OPENAI_API_KEY` is unset
- Live status panel with auto-refresh every 5s while the pipeline runs
- Freshness panel: total filings, parse coverage %, latest filing, last scrape, last compute
- Tabbed previews of `indicators`, `raw_filings`, `financials` for QA

### Run against a remote API (e.g. EC2)

```bash
SME_ADMIN_API_URL=http://98.81.94.194 streamlit run dashboard/app.py
```

In **remote mode** the admin app calls `POST /api/pipeline/run` and polls
`/api/pipeline/status` on the configured server, so a single operator can
trigger refreshes on the deployed instance from their laptop. Per-stage
buttons are disabled in remote mode (the API only exposes the full
pipeline) — use the CLI on the server for stage-level control.

---

## Raspberry Pi Deployment

Tested on a Raspberry Pi 4 running Raspberry Pi OS (64-bit kernel, 32-bit
armhf user space). Uses PM2 to keep the API server running and an nginx
reverse proxy for clean port-80 access.

### Prerequisites on the Pi

```bash
# Python 3.11+
sudo apt update && sudo apt install -y python3.11 python3.11-venv python3-pip

# Node.js 18 (for building the frontend once)
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs

# PM2 (process manager)
sudo npm install -g pm2

# nginx
sudo apt install -y nginx

# libopenblas (required by numpy on armhf)
# If you cannot sudo-install on the Pi, extract the .deb manually:
mkdir -p ~/.local/openblas
cd ~/.local/openblas
apt-get download libopenblas0-pthread:armhf
dpkg -x libopenblas0-pthread_*.deb .
```

### 1 — Deploy the code

```bash
# On the Pi (or via SSH)
mkdir -p ~/apps
cd ~/apps
git clone https://github.com/sachin245/SME_indicators.git sme-indicators
cd sme-indicators

python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.pi.txt   # Pi-specific deps (no Playwright)
```

> The Pi build uses `requirements.pi.txt` which omits Playwright (NSE scraper
> won't run on the Pi, but BSE scraping, parsing, and the dashboard all work).

### 2 — Build the frontend (do this once, or after each update)

```bash
cd ~/apps/sme-indicators/frontend
npm install
npm run build
cd ..
```

### 3 — Initialise the database

```bash
source venv/bin/activate
python -c "from storage.database import init_db; init_db()"
```

### 4 — Start the API server with PM2

The repo includes `ecosystem.config.cjs` pre-configured for the Pi:

```bash
# From ~/apps/sme-indicators
pm2 start ecosystem.config.cjs
pm2 save                     # persist across reboots
pm2 startup                  # follow the printed instruction to enable autostart
```

The API runs on port **6002**. Check it with:

```bash
pm2 status
curl http://localhost:6002/api/health
```

### 5 — Configure nginx reverse proxy

```bash
sudo nano /etc/nginx/sites-available/sme-indicators
```

Paste:

```nginx
server {
    listen 80;
    server_name _;          # replace with your Pi's hostname or IP if needed

    location / {
        proxy_pass         http://127.0.0.1:6002;
        proxy_http_version 1.1;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_read_timeout 120s;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/sme-indicators \
           /etc/nginx/sites-enabled/sme-indicators
sudo rm -f /etc/nginx/sites-enabled/default   # disable default site
sudo nginx -t && sudo systemctl reload nginx
```

The dashboard is now available at `http://<pi-ip-address>/` on your local network.

### 6 — Schedule the pipeline (cron)

```bash
crontab -e
```

Add (runs the full pipeline at 6 AM every day):

```
0 6 * * * cd ~/apps/sme-indicators && source venv/bin/activate && \
  python agent.py --scrape --parse --compute --days 7 >> logs/cron.log 2>&1
```

### Updating the Pi after a code change

```bash
cd ~/apps/sme-indicators
git pull
source venv/bin/activate
pip install -r requirements.pi.txt   # if dependencies changed

cd frontend && npm install && npm run build && cd ..

pm2 restart sme-indicators
```

---

## Project Structure

```
SME_indicators/
├── agent.py                  # CLI orchestrator (scrape / parse / compute)
├── config.py                 # Constants, weights, keywords
├── requirements.txt          # Python deps (dev / server)
├── requirements.pi.txt       # Pi-specific deps (no Playwright)
├── ecosystem.config.cjs      # PM2 config for Raspberry Pi
├── .env.example              # Environment variable template
├── scrapers/
│   ├── bse_scraper.py        # BSE REST API scraper
│   └── nse_scraper.py        # NSE scraper (Playwright headless browser)
├── parsers/
│   ├── pdf_parser.py         # PDF text extraction + keyword signals
│   └── xbrl_parser.py        # XBRL/XML financial data extraction
├── indicators/
│   └── engine.py             # Indicator computation + normalisation (0-100)
├── storage/
│   ├── database.py           # DuckDB schema + upsert layer
│   └── sectors.py            # Keyword-based sector classifier
├── api/
│   ├── main.py               # FastAPI app, CORS, static SPA serving
│   ├── db.py                 # Query execution + type coercion
│   └── routers/              # /api/indicators, /filings, /financials, etc.
├── frontend/
│   ├── src/                  # React 18 + TypeScript SPA
│   │   ├── pages/            # Overview, SectorDetail, CompanyBrowser, …
│   │   ├── components/       # Heatmap, LineChart, Gauge, …
│   │   ├── api/              # Typed fetch wrappers
│   │   └── hooks/            # useFilters (global date/exchange state)
│   ├── package.json
│   └── vite.config.ts        # Dev proxy → localhost:8002
└── dashboard/
    └── app.py                # Legacy Streamlit UI (superseded by React SPA)
```

---

## Contributing

1. Fork the repo and create a feature branch
2. Make changes with tests where applicable
3. Open a pull request against `main`

---

*Built to surface forward-looking signals from Indian SME filings before the market does.*
