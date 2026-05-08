import asyncio
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Optional

import httpx

from .logger import backend_logger
from .config_store import get_config
from .constants import BseUrls, HttpConfig, PathConfig
from .errors import ScraperError, ScraperPermanentError, ScraperRetryableError
from .state_manager import EngineState
from .store import insert_run_history, set_attachment_path, upsert_announcements_batch

ATTACH_ROOT = PathConfig.ATTACHMENTS_DIR
BSE_API = BseUrls.API_BASE
BSE_ATTACH_BASE = BseUrls.ATTACH_BASE
BSE_HOME = BseUrls.HOME

_state = EngineState("scraper", backend_logger)
_state.initialize({
    "running": False,
    "phase": "idle",
    "startedAt": None,
    "finishedAt": None,
    "rangeFrom": None,
    "rangeTo": None,
    "universe": False,
    "watchlistOnly": False,
    "dryRun": False,
    "totalPages": 0,
    "pagesDone": 0,
    "recordsScanned": 0,
    "matched": 0,
    "newRecords": 0,
    "pdfsOk": 0,
    "pdfsFailed": 0,
    "http429s": 0,
    "http503s": 0,
    "log": [],
    "_settings": None,
    "_records": [],
    "_downloadIdx": 0,
    "_sessionCookies": "",
    "_cancelRequested": False,
    "_task": None,
    "_onIdle": None,
})

state = _state.get_all()

def get_status() -> dict:
    """Get current scraper status."""
    s = _state.get()
    return {
        "running": s["running"],
        "phase": s["phase"],
        "startedAt": s["startedAt"],
        "finishedAt": s["finishedAt"],
        "rangeFrom": s["rangeFrom"],
        "rangeTo": s["rangeTo"],
        "universe": s["universe"],
        "watchlistOnly": s["watchlistOnly"],
        "dryRun": s["dryRun"],
        "totalPages": s["totalPages"],
        "pagesDone": s["pagesDone"],
        "recordsScanned": s["recordsScanned"],
        "matched": s["matched"],
        "newRecords": s["newRecords"],
        "pdfsOk": s["pdfsOk"],
        "pdfsFailed": s["pdfsFailed"],
        "http429s": s["http429s"],
        "http503s": s["http503s"],
        "progress": _state.get_progress(
            s["phase"],
            total_pages=s["totalPages"],
            pages_done=s["pagesDone"],
            total_items=len(s.get("_records", [])),
            items_done=s.get("_downloadIdx", 0),
        ),
        "log": list(s["log"]),
    }


async def start(payload: dict, on_idle: Callable[[], Coroutine]) -> dict:
    """Start a scraper run with the given payload."""
    s = _state.get()
    if s["running"]:
        return {"error": "Scraper is already running."}

    cfg = get_config()
    settings = {**cfg["scraper"], **payload.get("settingsOverride", {})}

    tags_enabled = cfg["filter"].get("tagsEnabled", True)
    active_tags = (
        [t for t in cfg["filter"].get("tags", []) if t.get("isActive")]
        if tags_enabled
        else []
    )

    _state.update(
        running=True,
        phase="fetching",
        startedAt=datetime.now(timezone.utc).isoformat(),
        finishedAt=None,
        rangeFrom=payload.get("from"),
        rangeTo=payload.get("to"),
        universe=bool(payload.get("universe")),
        watchlistOnly=bool(
            payload.get("watchlistOnly", cfg["filter"].get("watchlistOnly", True))
        ),
        dryRun=bool(payload.get("dryRun")),
        totalPages=0,
        pagesDone=0,
        recordsScanned=0,
        matched=0,
        newRecords=0,
        pdfsOk=0,
        pdfsFailed=0,
        http429s=0,
        http503s=0,
        log=[],
        _settings=settings,
        _records=[],
        _downloadIdx=0,
        _sessionCookies="",
        _cancelRequested=False,
        _onIdle=on_idle,
    )

    if tags_enabled and not active_tags:
        _state.log("No active filter tags — all records will be persisted without tag annotations.")
    if not tags_enabled:
        _state.log("Filter tag gating disabled — all records will be persisted.")

    _state.log(
        f"Scraper started — range {payload.get('from')} → {payload.get('to')}, "
        f"mode={'universe' if payload.get('universe') else 'watchlist'}, "
        f"dry-run={_state.get()['dryRun']}"
    )

    task = asyncio.create_task(_run(payload, cfg, settings, active_tags, tags_enabled))
    _state.get_all()["_task"] = task
    return get_status()


def stop() -> dict:
    """Stop the current scraper run."""
    s = _state.get()
    if not s["running"]:
        return {"error": "Scraper is not running."}
    _state.get_all()["_cancelRequested"] = True
    _state.log("Cancel requested", "warn")
    return get_status()


def _finish(status: str) -> None:
    """Mark scraper run as finished."""
    s = _state.get()
    finished_at = datetime.now(timezone.utc).isoformat()
    _state.update(
        finishedAt=finished_at,
        phase=status,
        running=False,
    )
    _state.get_all()["_task"] = None

    elapsed_sec = round(
        (
            datetime.fromisoformat(finished_at)
            - datetime.fromisoformat(s["startedAt"])
        ).total_seconds()
    )
    _state.log(f"Scraper {status} — elapsed {elapsed_sec}s")

    insert_run_history(
        {
            "step": "scraper",
            "started_at": s["startedAt"],
            "finished_at": finished_at,
            "range_from": s["rangeFrom"],
            "range_to": s["rangeTo"],
            "pages_fetched": s["pagesDone"],
            "records_scanned": s["recordsScanned"],
            "matched": s["matched"],
            "new_records": s["newRecords"],
            "pdfs_ok": s["pdfsOk"],
            "pdfs_failed": s["pdfsFailed"],
            "pdfs_processed": 0,
            "flag_hit_total": 0,
            "http_429s": s["http429s"],
            "http_503s": s["http503s"],
            "elapsed_sec": elapsed_sec,
            "status": (
                ("partial" if s["pdfsFailed"] > 0 else "ok")
                if status == "done"
                else ("partial" if status == "cancelled" else "failed")
            ),
        }
    )

    on_idle = s.get("_onIdle")
    _state.get_all()["_onIdle"] = None
    if on_idle:
        asyncio.create_task(on_idle())


async def _run(
    payload: dict,
    cfg: dict,
    settings: dict,
    active_tags: list,
    tags_enabled: bool,
) -> None:
    """Main scraper execution loop."""
    try:
        records = await _load_candidates(
            from_date=payload["from"],
            to_date=payload["to"],
            watchlist=cfg["filter"]["watchlist"],
            watchlist_only=payload.get("watchlistOnly", cfg["filter"].get("watchlistOnly", True)),
            universe=payload.get("universe", False),
            active_tags=active_tags,
            tags_enabled=tags_enabled,
            settings=settings,
        )

        s = _state.get()
        if s["_cancelRequested"]:
            _finish("cancelled")
            return

        if records and not s["dryRun"]:
            upsert_announcements_batch(records)
        _state.update(matched=len(records), newRecords=len(records))
        _state.log(f"Persisted {len(records)} announcement row(s) to data/announcements.db")

        if settings.get("downloadAttachments") and not s["dryRun"] and records:
            _state.update(phase="downloading")
            _state.log(f"Downloading {len(records)} attachment(s)…")
            async with httpx.AsyncClient(follow_redirects=True) as client:
                cookies = await _fetch_bse_session(client, settings["userAgent"])
                _state.get_all()["_sessionCookies"] = cookies
                if _state.get()["_cancelRequested"]:
                    _finish("cancelled")
                    return
                for rec in records:
                    if _state.get()["_cancelRequested"]:
                        break
                    await _download_one(client, rec, settings)
                    _state.get_all()["_downloadIdx"] += 1
                    await asyncio.sleep(0)
            s = _state.get()
            _state.log(f"PDFs: {s['pdfsOk']} ok, {s['pdfsFailed']} failed")

        _finish("done")

    except asyncio.CancelledError:
        _finish("cancelled")
    except Exception as e:
        _state.log(f"Scraper error: {e}", "err")
        _finish("failed")


async def _fetch_bse_session(client: httpx.AsyncClient, user_agent: str) -> str:
    """Establish BSE session and return cookies."""
    try:
        r = await client.get(
            BSE_HOME,
            headers={"User-Agent": user_agent, "Accept": "text/html,*/*;q=0.8"},
            timeout=20.0,
        )
        cookies = "; ".join(f"{k}={v}" for k, v in r.cookies.items())
        if cookies:
            _state.log(f"BSE session established ({len(r.cookies)} cookie(s))")
        else:
            _state.log("BSE session: no cookies set by server (PDFs will be tried without them)")
        return cookies
    except Exception as e:
        _state.log(f"BSE session fetch failed: {e} — continuing without cookies", "warn")
        return ""


async def _download_one(
    client: httpx.AsyncClient, rec: dict, settings: dict
) -> None:
    """Download a single PDF attachment."""
    url = rec.get("attachmentUrl")
    if not url:
        _state.get_all()["pdfsFailed"] = _state.get()["pdfsFailed"] + 1
        return

    dir_path = os.path.join(ATTACH_ROOT, rec["scripCode"])
    os.makedirs(dir_path, exist_ok=True)
    out_path = os.path.join(dir_path, f"{rec['id']}.pdf")

    if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        set_attachment_path(rec["id"], out_path)
        _state.get_all()["pdfsOk"] = _state.get()["pdfsOk"] + 1
        return

    try:
        headers = {
            "User-Agent": settings["userAgent"],
            "Referer": BSE_HOME,
            "Origin": "https://www.bseindia.com",
            "Accept": "application/pdf,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        s = _state.get()
        if s["_sessionCookies"]:
            headers["Cookie"] = s["_sessionCookies"]

        r = await client.get(
            url, headers=headers, timeout=float(settings.get("attachmentTimeoutSec", 30))
        )
        ct = r.headers.get("content-type", "").lower()
        if not r.is_success or "application/pdf" not in ct:
            _state.get_all()["pdfsFailed"] = _state.get()["pdfsFailed"] + 1
            _state.log(f"pdf fail ({r.status_code} {ct}) — {rec['id']}", "warn")
            return

        buf = r.content
        if buf[:4] != b"%PDF":
            _state.get_all()["pdfsFailed"] = _state.get()["pdfsFailed"] + 1
            _state.log(f"pdf fail (bad magic) — {rec['id']}", "warn")
            return

        with open(out_path, "wb") as f:
            f.write(buf)
        set_attachment_path(rec["id"], out_path)
        _state.get_all()["pdfsOk"] = _state.get()["pdfsOk"] + 1
    except Exception as e:
        _state.get_all()["pdfsFailed"] = _state.get()["pdfsFailed"] + 1
        _state.log(f"pdf error — {rec['id']}: {e}", "err")


async def _fetch_bse_page(scrip: str, from_date: str, to_date: str, settings: dict) -> list:
    """Fetch one page of announcements from BSE API."""
    params = {
        "strCat": "-1",
        "strPrevDate": from_date,
        "strScrip": scrip,
        "strSearch": "P",
        "strToDate": to_date,
        "strType": "C",
        "subcategory": "-1",
    }
    headers = {
        "User-Agent": settings["userAgent"],
        "Referer": BSE_HOME,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }
    timeout = float(settings.get("pageFetchTimeoutSec", 30))
    max_retries = int(settings.get("maxRetries", 5))
    backoff_min = float(settings.get("backoffMinSec", 2))
    backoff_max = float(settings.get("backoffMaxSec", 32))

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for attempt in range(max_retries):
            try:
                r = await client.get(BSE_API, params=params, headers=headers, timeout=timeout)
            except Exception:
                if attempt < max_retries - 1:
                    await asyncio.sleep(backoff_min)
                continue

            if r.status_code in (429, 503):
                wait = min(backoff_max, backoff_min * (2 ** attempt))
                _state.log(
                    f"HTTP {r.status_code} (scrip {scrip or 'all'}) — backoff {wait}s", "warn"
                )
                if r.status_code == 429:
                    _state.get_all()["http429s"] = _state.get()["http429s"] + 1
                else:
                    _state.get_all()["http503s"] = _state.get()["http503s"] + 1
                await asyncio.sleep(wait)
                continue

            if not r.is_success:
                _state.log(f"BSE API {r.status_code} for scrip \"{scrip or 'all'}\"", "warn")
                return []

            data = r.json()
            return data.get("Table") or data.get("table") or []

    return []


async def _fetch_scrip_name(scrip_code: str, settings: dict) -> str:
    if not scrip_code:
        return ""
    url = (
        f"https://api.bseindia.com/BseIndiaAPI/api/getScripHeaderData/w"
        f"?Scrip_Cd={scrip_code}"
    )
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            r = await client.get(
                url,
                headers={
                    "User-Agent": settings["userAgent"],
                    "Referer": BSE_HOME,
                    "Accept": "application/json, */*;q=0.8",
                },
                timeout=10.0,
            )
        if not r.is_success:
            return ""
        data = r.json()
        table = data.get("Table")
        row = (table[0] if isinstance(table, list) and table else None) or data.get("Header") or data or {}
        return str(
            row.get("Scrip_Name") or row.get("SCRIP_NAME") or
            row.get("Company_Name") or row.get("COMPANY_NAME") or
            row.get("CompanyName") or ""
        ).strip()
    except Exception:
        return ""


def _normalize_attachment_url(raw: str) -> str:
    if not raw:
        return ""
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    if raw.startswith("/"):
        return f"https://www.bseindia.com{raw}"
    return f"{BSE_ATTACH_BASE}{raw}"


def _bse_date_to_dt(s: str) -> Optional[datetime]:
    for fmt in ("%d %b %Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
    return None


async def _load_candidates(
    from_date: str,
    to_date: str,
    watchlist: list,
    watchlist_only: bool,
    universe: bool,
    active_tags: list,
    tags_enabled: bool,
    settings: dict,
) -> list:
    from_bse = from_date.replace("-", "")
    to_bse = to_date.replace("-", "")
    from_dt = datetime.fromisoformat(from_date).replace(tzinfo=timezone.utc)
    to_dt = datetime.fromisoformat(to_date).replace(
        hour=23, minute=59, second=59, tzinfo=timezone.utc
    )

    wl = set(watchlist)
    compiled = []
    for t in active_tags:
        try:
            compiled.append(
                {"id": t["id"], "label": t["label"], "re": re.compile(t["pattern"], re.IGNORECASE)}
            )
        except re.error:
            _state.log(f'tag "{t["label"]}" has invalid pattern — skipped', "warn")

    scrips = [""] if universe else list(wl)
    _state.update(totalPages=len(scrips), pagesDone=0)
    _state.log(f"Fetching BSE feed for {len(scrips)} scrip(s) in range {from_date} → {to_date}…")

    out = []
    for i, scrip in enumerate(scrips):
        if _state.get()["_cancelRequested"]:
            break

        rows = await _fetch_bse_page(scrip, from_bse, to_bse, settings)
        s = _state.get()
        _state.update(
            recordsScanned=s["recordsScanned"] + len(rows),
            pagesDone=i + 1,
        )

        stride = max(1, len(scrips) // 20)
        if (i + 1) % stride == 0 or (i + 1) == len(scrips):
            s = _state.get()
            _state.log(
                f"scrip {i + 1}/{len(scrips)} · scanned={s['recordsScanned']:,}"
            )

        for a in rows:
            scrip_code = str(a.get("SCRIP_CD") or "").strip()
            if not universe and watchlist_only and scrip_code not in wl:
                continue

            dt = _bse_date_to_dt(str(a.get("News_submission_dt") or ""))
            if dt is None or dt < from_dt or dt > to_dt:
                continue

            subject = str(a.get("NEWSSUB") or "")
            headline = str(a.get("HEADLINE") or a.get("NEWSSUB") or "")
            ann_id = (
                str(a["NEWSID"])
                if a.get("NEWSID")
                else f"{scrip_code}-{str(a.get('News_submission_dt') or '').replace(' ', '').replace(':', '')}"
            )

            matched_tags = []
            if tags_enabled and compiled:
                haystack = f"{subject} {headline}"
                for c in compiled:
                    m = c["re"].search(haystack)
                    if m:
                        matched_tags.append(
                            {"tagId": c["id"], "tagLabel": c["label"], "matchedText": m.group(0)}
                        )

            raw_attachment = str(a.get("ATTACHMENTNAME") or a.get("NSURL") or "").strip()
            company_name = str(
                a.get("SLONGNAME") or a.get("LONG_NAME") or
                a.get("COMPANY_NAME") or a.get("Scrip_Name") or a.get("Scripname") or
                a.get("ScripName") or a.get("scrip_name") or a.get("Company") or
                a.get("company_name") or ""
            ).strip()

            out.append(
                {
                    "id": ann_id,
                    "scripCode": scrip_code,
                    "companyName": company_name,
                    "segment": str(a.get("Sgmt") or "Equity"),
                    "subject": subject,
                    "headline": headline,
                    "category": str(a.get("CATEGORYNAME") or ""),
                    "dtFiled": dt.isoformat(),
                    "attachmentUrl": _normalize_attachment_url(raw_attachment),
                    "rawJson": json.dumps(a),
                    "matchedTags": matched_tags,
                }
            )

        if not universe and i < len(scrips) - 1:
            await asyncio.sleep(settings.get("rateLimitDelayMs", 1000) / 1000)

    _state.log(f"BSE fetch complete — {len(out)} record(s) matched after filtering")

    missing = list({r["scripCode"] for r in out if not r["companyName"]})
    if missing:
        _state.log(f"Resolving company name for {len(missing)} scrip(s) via BSE details API…")
        name_cache: dict[str, str] = {}
        for code in missing:
            if _state.get()["_cancelRequested"]:
                break
            name = await _fetch_scrip_name(code, settings)
            if name:
                name_cache[code] = name
            await asyncio.sleep(settings.get("rateLimitDelayMs", 1000) / 1000)
        for r in out:
            if not r["companyName"] and r["scripCode"] in name_cache:
                r["companyName"] = name_cache[r["scripCode"]]
        resolved = sum(1 for c in missing if c in name_cache)
        _state.log(f"Company name resolved for {resolved}/{len(missing)} scrip(s)")

    return out
