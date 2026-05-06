from . import processor_engine as processor
from . import scraper_engine as scraper

_active_step: str | None = None


def get_active_step() -> str | None:
    return _active_step


def get_status() -> dict:
    return {
        "activeStep": _active_step,
        "scraper": scraper.get_status(),
        "processor": processor.get_status(),
    }


async def start_scraper(payload: dict) -> dict:
    global _active_step
    if _active_step:
        return {"error": f"{_active_step} is already running. Stop it first."}
    _active_step = "scraper"

    async def on_idle():
        global _active_step
        _active_step = None

    try:
        return await scraper.start(payload, on_idle)
    except Exception as e:
        _active_step = None
        return {"error": str(e)}


async def start_processor(payload: dict) -> dict:
    global _active_step
    if _active_step:
        return {"error": f"{_active_step} is already running. Stop it first."}
    _active_step = "processor"

    async def on_idle():
        global _active_step
        _active_step = None

    try:
        return await processor.start(payload, on_idle)
    except Exception as e:
        _active_step = None
        return {"error": str(e)}


async def start_quick_run(payload: dict) -> dict:
    global _active_step
    if _active_step:
        return {"error": f"{_active_step} is already running. Stop it first."}
    _active_step = "quickrun"

    async def on_processor_idle():
        global _active_step
        _active_step = None

    async def on_scraper_idle():
        global _active_step
        s_status = scraper.get_status()
        if s_status["phase"] in ("cancelled", "failed"):
            _active_step = None
            return
        try:
            await processor.start({"mode": "pending"}, on_processor_idle)
        except Exception:
            _active_step = None

    try:
        return await scraper.start(payload, on_scraper_idle)
    except Exception as e:
        _active_step = None
        return {"error": str(e)}


def stop() -> dict:
    if _active_step == "scraper":
        return scraper.stop()
    if _active_step == "processor":
        return processor.stop()
    if _active_step == "quickrun":
        if scraper.get_status()["running"]:
            return scraper.stop()
        if processor.get_status()["running"]:
            return processor.stop()
    return {"error": "Nothing is running."}
