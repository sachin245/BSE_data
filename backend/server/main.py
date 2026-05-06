"""
BSE Scraper API — FastAPI backend.

Dev:  uvicorn server.main:app --reload --port 8000
      (Vite dev server proxies /api/* → http://localhost:8000)

Prod: uvicorn server.main:app --host 0.0.0.0 --port 8000
      (serves both the API and the built React app from dist/)
"""

import os
import shutil

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import coordinator
from .config_store import config_mtime, get_config, save_config, validate_startup_config
from .store import (
    flag_hits_by_announcement,
    list_announcements,
    list_run_history,
    reset_announcements,
    reset_run_history,
    scrape_tag_hits_by_announcement,
)
from .logger import backend_logger, frontend_logger

app = FastAPI(title="BSE Scraper API")


@app.on_event("startup")
def _validate_config_on_startup() -> None:
    """Validate config when the app starts up; log any issues."""
    errors = validate_startup_config()
    if errors:
        for e in errors:
            backend_logger.error(f"[config] {e}")
        backend_logger.warning(
            f"Startup config validation found {len(errors)} issue(s) — see errors above"
        )
    else:
        backend_logger.info("Startup config validation passed")

@app.middleware("http")
async def log_requests(request: Request, call_next):
    backend_logger.info(f"Incoming request: {request.method} {request.url.path}")
    response = await call_next(request)
    backend_logger.info(f"Completed request: {request.method} {request.url.path} - Status: {response.status_code}")
    return response

# ─── Config ──────────────────────────────────────────────────────────────────


@app.get("/api/config")
def api_get_config():
    get_config()  # warm cache on first call
    return {"config": get_config(), "mtime": config_mtime()}


@app.post("/api/config")
async def api_save_config(request: Request):
    body = {}
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            body = await request.json()
        except Exception:
            pass
    try:
        merged = save_config(body)
        return {"config": merged, "mtime": config_mtime()}
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


# ─── Status ───────────────────────────────────────────────────────────────────


@app.get("/api/status")
def api_status():
    return coordinator.get_status()


# ─── Run control ──────────────────────────────────────────────────────────────


@app.post("/api/scraper/start")
async def api_scraper_start(request: Request):
    body = await _json_body(request)
    result = await coordinator.start_scraper(body)
    return JSONResponse(status_code=409 if "error" in result else 200, content=result)


@app.post("/api/processor/start")
async def api_processor_start(request: Request):
    body = await _json_body(request)
    result = await coordinator.start_processor(body)
    return JSONResponse(status_code=409 if "error" in result else 200, content=result)


@app.post("/api/quickrun/start")
async def api_quickrun_start(request: Request):
    body = await _json_body(request)
    result = await coordinator.start_quick_run(body)
    return JSONResponse(status_code=409 if "error" in result else 200, content=result)


@app.post("/api/run/stop")
def api_run_stop():
    result = coordinator.stop()
    return JSONResponse(status_code=409 if "error" in result else 200, content=result)


# ─── Data ─────────────────────────────────────────────────────────────────────


@app.get("/api/announcements")
def api_announcements():
    rows = list_announcements()
    hits = flag_hits_by_announcement()
    tag_hits = scrape_tag_hits_by_announcement()
    return [
        {
            "id": r["id"],
            "scripCode": r["scrip_code"],
            "companyName": r["company_name"],
            "segment": r["segment"],
            "subject": r["subject"],
            "headline": r["headline"],
            "category": r["category"],
            "dtFiled": r["dt_filed"],
            "attachmentUrl": r["attachment_url"],
            "attachmentPath": r["attachment_path"],
            "processedAt": r["processed_at"],
            "flagHits": hits.get(r["id"], []),
            "scrapeTagHits": tag_hits.get(r["id"], []),
        }
        for r in rows
    ]


@app.get("/api/history")
def api_history():
    return list_run_history(50)


@app.post("/api/reset")
async def api_reset(request: Request):
    if coordinator.get_active_step():
        return JSONResponse(
            status_code=409, content={"error": "Cannot reset while a run is active."}
        )
    body = await _json_body(request)
    result: dict = {}
    if body.get("announcements"):
        reset_announcements()
        result["announcements"] = True
    if body.get("runHistory"):
        reset_run_history()
        result["runHistory"] = True
    if body.get("pdfs"):
        try:
            shutil.rmtree("data/attachments", ignore_errors=True)
        except Exception:
            pass
        result["pdfs"] = True
    return result


# ─── Frontend Logs ────────────────────────────────────────────────────────────

@app.post("/api/logs")
async def api_receive_frontend_logs(request: Request):
    body = await _json_body(request)
    level = body.get("level", "INFO").upper()
    msg = body.get("message", "No message provided")
    
    if level == "ERROR":
        frontend_logger.error(msg)
    elif level in ["WARN", "WARNING"]:
        frontend_logger.warning(msg)
    else:
        frontend_logger.info(msg)
        
    return JSONResponse(status_code=200, content={"status": "logged"})


# ─── SPA fallback (production) ────────────────────────────────────────────────

_dist = "dist"
if os.path.isdir(_dist):
    _assets = os.path.join(_dist, "assets")
    if os.path.isdir(_assets):
        app.mount("/assets", StaticFiles(directory=_assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        candidate = os.path.join(_dist, full_path)
        if os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(_dist, "index.html"))


# ─── Helpers ──────────────────────────────────────────────────────────────────


async def _json_body(request: Request) -> dict:
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            return await request.json()
        except Exception:
            pass
    return {}
