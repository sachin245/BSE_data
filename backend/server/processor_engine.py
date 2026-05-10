import asyncio
import io
import os
import re
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Optional

import httpx

from .logger import backend_logger
from .config_store import get_config
from .constants import BseUrls, DefaultUserAgent, HttpConfig
from .errors import ProcessorError, ProcessorPermanentError
from .state_manager import EngineState
from .store import (
    clear_flag_hits_for,
    insert_flag_hit,
    insert_run_history,
    list_announcements,
    mark_processed,
)

BSE_HOME = BseUrls.HOME
BSE_ANN_REFERER = BseUrls.ANN_REFERER
PDF_UA = DefaultUserAgent.CHROME

_state = EngineState("processor", backend_logger)
_state.initialize({
    "running": False,
    "phase": "idle",
    "startedAt": None,
    "finishedAt": None,
    "mode": None,
    "totalRecords": 0,
    "processed": 0,
    "flagHits": 0,
    "pdfErrors": 0,
    "log": [],
    "_records": [],
    "_flags": [],
    "_idx": 0,
    "_task": None,
    "_cancelRequested": False,
    "_onIdle": None,
    "_sessionCookies": "",
    "_sessionReady": False,
    "_http_client": None,
})

state = _state.get_all()


def get_status() -> dict:
    """Get current processor status."""
    s = _state.get()
    return {
        "running": s["running"],
        "phase": s["phase"],
        "startedAt": s["startedAt"],
        "finishedAt": s["finishedAt"],
        "mode": s["mode"],
        "totalRecords": s["totalRecords"],
        "processed": s["processed"],
        "flagHits": s["flagHits"],
        "pdfErrors": s["pdfErrors"],
        "progress": _state.get_progress(
            s["phase"],
            total_items=s["totalRecords"],
            items_done=s["_idx"],
        ),
        "log": list(s["log"]),
    }


async def start(payload: dict, on_idle: Callable[[], Coroutine]) -> dict:
    """Start a processor run with the given payload."""
    s = _state.get()
    if s["running"]:
        return {"error": "Processor is already running."}

    cfg = get_config()
    flags = [
        {
            "name": f["name"],
            "pattern": f["pattern"],
            "flags": re.IGNORECASE if f.get("caseInsensitive") else 0,
        }
        for f in cfg["processor"]["flags"]
        if f.get("active") and f.get("pattern")
    ]

    if not flags:
        return {
            "error": "No active flags. Enable at least one flag in the Processor settings."
        }

    mode = "all" if payload.get("mode") == "all" else "pending"
    records = list_announcements(
        with_attachment_url=True,
        unprocessed_only=(mode == "pending"),
    )

    _state.update(
        running=True,
        phase="extracting",
        startedAt=datetime.now(timezone.utc).isoformat(),
        finishedAt=None,
        mode=mode,
        totalRecords=len(records),
        processed=0,
        flagHits=0,
        pdfErrors=0,
        log=[],
        _records=records,
        _flags=flags,
        _idx=0,
        _cancelRequested=False,
        _onIdle=on_idle,
        _sessionCookies="",
        _sessionReady=False,
    )

    _state.log(
        f"Processor started — mode={mode}, {len(records)} record(s), {len(flags)} active flag(s)"
    )

    if not records:
        _state.log("Nothing to process — no rows with an attachment URL.", "warn")
        _finish("done")
        return get_status()

    if mode == "all":
        clear_flag_hits_for([r["id"] for r in records])
        _state.log("Cleared previous flag hits for full reprocess.")

    task = asyncio.create_task(_run())
    _state.get_all()["_task"] = task
    return get_status()


def stop() -> dict:
    """Stop the current processor run."""
    s = _state.get()
    if not s["running"]:
        return {"error": "Processor is not running."}
    _state.get_all()["_cancelRequested"] = True
    _state.log("Cancel requested", "warn")
    return get_status()


def _finish(status: str) -> None:
    """Mark processor run as finished."""
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
    _state.log(f"Processor {status} — elapsed {elapsed_sec}s, {s['flagHits']} flag hit(s)")

    insert_run_history(
        {
            "step": "processor",
            "started_at": s["startedAt"],
            "finished_at": finished_at,
            "range_from": None,
            "range_to": None,
            "pages_fetched": 0,
            "records_scanned": s["totalRecords"],
            "matched": s["processed"],
            "new_records": 0,
            "pdfs_ok": 0,
            "pdfs_failed": 0,
            "pdfs_processed": s["processed"],
            "flag_hit_total": s["flagHits"],
            "http_429s": 0,
            "http_503s": 0,
            "elapsed_sec": elapsed_sec,
            "status": (
                ("partial" if s["pdfErrors"] > 0 else "ok")
                if status == "done"
                else ("partial" if status == "cancelled" else "failed")
            ),
        }
    )

    on_idle = s.get("_onIdle")
    _state.get_all()["_onIdle"] = None
    if on_idle:
        asyncio.create_task(on_idle())


async def _run() -> None:
    """Main processor execution loop."""
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            _state.get_all()["_http_client"] = client
            s = _state.get()
            for rec in s["_records"]:
                if _state.get()["_cancelRequested"]:
                    break

                try:
                    _state.log(f"Extracting text from record {rec['id']}...")
                    text = await _extract_text(rec["attachment_path"], rec["attachment_url"], client)
                    hits = 0
                    s = _state.get()
                    for flag in s["_flags"]:
                        compiled = re.compile(flag["pattern"], flag["flags"] | re.DOTALL)
                        m = compiled.search(text)
                        if m:
                            start_idx = max(0, m.start() - 40)
                            snippet = (
                                text[start_idx : m.end() + 40]
                                .replace("\n", " ")
                                .replace("\r", " ")
                            )
                            snippet = re.sub(r"\s+", " ", snippet).strip()
                            insert_flag_hit(rec["id"], flag["name"], snippet)
                            _state.log(f"  - Hit: {flag['name']}")
                            hits += 1

                    s = _state.get()
                    _state.update(
                        flagHits=s["flagHits"] + hits,
                        processed=s["processed"] + 1,
                    )
                    mark_processed(rec["id"])
                except ProcessorPermanentError as e:
                    s = _state.get()
                    _state.update(pdfErrors=s["pdfErrors"] + 1)
                    _state.log(f"extract failed (permanent) — {rec['id']}: {e}", "err")
                    mark_processed(rec["id"])
                except Exception as e:
                    s = _state.get()
                    _state.update(pdfErrors=s["pdfErrors"] + 1)
                    _state.log(f"extract failed — {rec['id']}: {e}", "err")
                finally:
                    s = _state.get()
                    _state.update(_idx=s["_idx"] + 1)
                    if s["_idx"] % 5 == 0 or s["_idx"] == s["totalRecords"]:
                        s = _state.get()
                        _state.log(
                            f"processed {s['_idx']}/{s['totalRecords']} "
                            f"· hits={s['flagHits']}"
                        )
                    await asyncio.sleep(0)

        if _state.get()["_cancelRequested"]:
            _finish("cancelled")
        else:
            _finish("done")

    except asyncio.CancelledError:
        _finish("cancelled")
    except Exception as e:
        _state.log(f"Processor error: {e}", "err")
        _finish("failed")
    finally:
        _state.get_all()["_http_client"] = None


async def _ensure_bse_session(client: httpx.AsyncClient) -> None:
    """Establish BSE session for PDF downloads."""
    s = _state.get()
    if s["_sessionReady"]:
        return
    try:
        r = await client.get(
            BSE_HOME,
            headers={"User-Agent": PDF_UA, "Accept": "text/html,*/*;q=0.8"},
            timeout=20.0,
        )
        cookies = "; ".join(f"{k}={v}" for k, v in r.cookies.items())
        _state.get_all()["_sessionCookies"] = cookies
        _state.get_all()["_sessionReady"] = True
        if cookies:
            _state.log(f"BSE session established ({len(r.cookies)} cookie(s))")
        else:
            _state.log("BSE session: no cookies returned — PDFs will be tried without them", "warn")
    except Exception as e:
        _state.log(f"BSE session fetch failed: {e} — continuing without cookies", "warn")
        _state.get_all()["_sessionReady"] = True


async def _fetch_pdf_buffer(url: str, client: httpx.AsyncClient) -> bytes:
    """Fetch a PDF buffer from URL with retries."""
    await _ensure_bse_session(client)

    headers = {
        "User-Agent": PDF_UA,
        "Referer": BSE_ANN_REFERER,
        "Origin": "https://www.bseindia.com",
        "Accept": "application/pdf,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    s = _state.get()
    if s["_sessionCookies"]:
        headers["Cookie"] = s["_sessionCookies"]

    for attempt in range(2):
        r = await client.get(url, headers=headers, timeout=30.0)

        if r.status_code in (429, 503):
            wait = 8.0 if r.status_code == 429 else 4.0
            _state.log(f"HTTP {r.status_code} on PDF fetch — waiting {wait}s before retry", "warn")
            await asyncio.sleep(wait)
            continue

        if not r.is_success:
            raise ProcessorError(f"HTTP {r.status_code} — {url}")

        ct = r.headers.get("content-type", "").lower()
        if "application/pdf" not in ct:
            preview = r.text.replace("\n", " ").strip()[:300]
            raise ProcessorPermanentError(
                f'Expected application/pdf but got "{ct}". '
                f"Server response: {preview or '(empty body)'}"
            )

        buf = r.content
        if buf[:4] != b"%PDF":
            preview = buf[:200].decode("utf-8", errors="replace").replace("\n", " ").strip()
            raise ProcessorPermanentError(
                f"Response content-type is pdf but body does not start with %PDF. "
                f"First 200 bytes: {preview}"
            )

        return buf

    raise ProcessorError(f"PDF fetch failed after retries — {url}")


def _extract_text_from_bytes(data: bytes) -> str:
    """Extract text from PDF bytes."""
    try:
        import pdfplumber
    except ImportError:
        raise ProcessorError(
            "pdfplumber is not installed. Run: pip install pdfplumber"
        )

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = []
            for page in pdf.pages:
                text = page.extract_text() or ""
                pages.append(text)
            return "\n".join(pages)
    except Exception as e:
        msg = str(e).lower()
        if "password" in msg or "encrypt" in msg:
            raise ProcessorPermanentError("PDF is password-protected")
        if "syntax" in msg or "invalid" in msg or "corrupt" in msg:
            raise ProcessorPermanentError("PDF is corrupted or not a valid PDF")
        raise


async def _extract_text(
    file_path: Optional[str],
    url: Optional[str],
    client: httpx.AsyncClient,
) -> str:
    """Extract text from PDF (local file or URL)."""
    if file_path and os.path.exists(file_path):
        try:
            with open(file_path, "rb") as f:
                data = f.read()
        except OSError as e:
            raise ProcessorPermanentError(f"file not readable ({e.strerror}): {file_path}")
    elif url:
        _state.log(f"no local file — fetching from URL: {url}")
        try:
            data = await _fetch_pdf_buffer(url, client)
        except ProcessorPermanentError:
            raise
        except Exception as e:
            raise ProcessorError(f"URL fetch failed: {e}")
    else:
        raise ProcessorPermanentError("no local file and no attachment URL")

    return await asyncio.to_thread(_extract_text_from_bytes, data)
