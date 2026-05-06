import json
import os
import re
from datetime import datetime, timezone
from typing import Optional

from .store import settings_kv_all, settings_kv_set

CONFIG_PATH = "data/config.json"

_DEFAULT_FILTER_TAGS = [
    {"id": "analyst-meet",           "label": "Analyst Meet",           "pattern": r"analyst\s*(meet|/\s*investor)",  "isActive": True},
    {"id": "investor-meet",          "label": "Investor Meet",          "pattern": r"investor\s*meet",                 "isActive": True},
    {"id": "investor-conference",    "label": "Investor Conference",    "pattern": r"investor\s*conference",           "isActive": True},
    {"id": "investor-presentation",  "label": "Investor Presentation",  "pattern": r"investor\s*presentation",         "isActive": True},
    {"id": "investor-call",          "label": "Investor Call",          "pattern": r"investor\s*call",                 "isActive": True},
    {"id": "earnings-call",          "label": "Earnings Call",          "pattern": r"earnings\s*call",                 "isActive": True},
    {"id": "conference-call",        "label": "Conference Call",        "pattern": r"conference\s*call",               "isActive": True},
    {"id": "schedule-of-analyst",    "label": "Schedule of Analyst",    "pattern": r"schedule\s+of\s+analyst",         "isActive": True},
    {"id": "institutional-investor", "label": "Institutional Investor", "pattern": r"institutional\s+investor",        "isActive": True},
]

DEFAULT_CONFIG: dict = {
    "scraper": {
        "rateLimitDelayMs": 1000,
        "pageSize": 100,
        "maxRetries": 5,
        "backoffMinSec": 2,
        "backoffMaxSec": 32,
        "downloadAttachments": False,
        "attachmentTimeoutSec": 30,
        "pageFetchTimeoutSec": 30,
        "userAgent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
    },
    "filter": {
        "tags": _DEFAULT_FILTER_TAGS,
        "tagsEnabled": True,
        "watchlist": [
            "500325", "532540", "500180", "500209", "532174",
            "500875", "500696", "500570", "500112", "532555",
        ],
        "watchlistOnly": True,
    },
    "processor": {
        "flags": [
            {
                "name": "InvestorMeetDate",
                "pattern": r"\b\d{1,2}[\s-](Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b",
                "active": True,
                "caseInsensitive": True,
            },
            {
                "name": "RevenueGuidance",
                "pattern": r"guidance\s+(of|at)\s+(?:Rs|INR|USD)",
                "active": True,
                "caseInsensitive": True,
            },
            {
                "name": "ManagementParticipants",
                "pattern": r"(CEO|CFO|MD|Director)\s*[-:]\s*[A-Z][a-z]+",
                "active": True,
                "caseInsensitive": False,
            },
            {
                "name": "QuarterReference",
                "pattern": r"Q[1-4]\s*FY\s*\d{2,4}",
                "active": True,
                "caseInsensitive": True,
            },
            {
                "name": "AnalystName",
                "pattern": r"analyst[s]?\s*[-:]\s*[A-Z][a-z]+",
                "active": False,
                "caseInsensitive": True,
            },
        ],
    },
}

_cached: Optional[dict] = None


def _read_file() -> Optional[dict]:
    if not os.path.exists(CONFIG_PATH):
        return None
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[config] could not parse {CONFIG_PATH}: {e}")
        return None


def _write_file(cfg: dict) -> None:
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, CONFIG_PATH)


def _merge_with_defaults(cfg: Optional[dict]) -> dict:
    cfg = cfg or {}
    filter_in = dict(cfg.get("filter", {}))
    filter_in.pop("regex", None)  # drop legacy field
    merged = {
        "scraper": {**DEFAULT_CONFIG["scraper"], **cfg.get("scraper", {})},
        "filter": {
            **DEFAULT_CONFIG["filter"],
            **filter_in,
            "tagsEnabled": filter_in.get("tagsEnabled", DEFAULT_CONFIG["filter"]["tagsEnabled"]),
        },
        "processor": {**DEFAULT_CONFIG["processor"], **cfg.get("processor", {})},
    }
    tags = merged["filter"].get("tags")
    if not isinstance(tags, list) or len(tags) == 0:
        merged["filter"]["tags"] = _DEFAULT_FILTER_TAGS
    return merged


def _sync_to_db(cfg: dict) -> None:
    settings_kv_set("scraper", cfg["scraper"])
    settings_kv_set("filter", cfg["filter"])
    settings_kv_set("processor", cfg["processor"])


def load_config() -> dict:
    global _cached
    file_cfg = _read_file()
    db_cfg = settings_kv_all()
    db_has_data = bool(db_cfg)

    if file_cfg:
        cfg = _merge_with_defaults(file_cfg)
        _sync_to_db(cfg)
    elif db_has_data:
        cfg = _merge_with_defaults(db_cfg)
        _write_file(cfg)
    else:
        cfg = _merge_with_defaults(None)
        _write_file(cfg)
        _sync_to_db(cfg)

    _cached = cfg
    return cfg


def get_config() -> dict:
    return _cached if _cached is not None else load_config()


def save_config(partial: dict) -> dict:
    current = get_config()
    merged = _merge_with_defaults(
        {
            "scraper":   {**current["scraper"],   **partial.get("scraper", {})},
            "filter":    {**current["filter"],    **partial.get("filter", {})},
            "processor": {**current["processor"], **partial.get("processor", {})},
        }
    )

    for f in merged["processor"]["flags"]:
        if not f.get("pattern"):
            continue
        flags = re.IGNORECASE if f.get("caseInsensitive") else 0
        try:
            re.compile(f["pattern"], flags)
        except re.error as e:
            raise ValueError(f'Flag "{f["name"]}" has invalid pattern: {e}')

    seen_ids: set = set()
    for t in merged["filter"]["tags"]:
        if not t.get("id") or not t.get("label"):
            raise ValueError("filter tag missing id/label")
        if t["id"] in seen_ids:
            raise ValueError(f'duplicate filter tag id: {t["id"]}')
        seen_ids.add(t["id"])
        try:
            re.compile(t["pattern"], re.IGNORECASE)
        except re.error as e:
            raise ValueError(f'filter tag "{t["label"]}" has invalid pattern: {e}')

    _write_file(merged)
    _sync_to_db(merged)
    global _cached
    _cached = merged
    return merged


def config_mtime() -> Optional[str]:
    if not os.path.exists(CONFIG_PATH):
        return None
    mtime = os.path.getmtime(CONFIG_PATH)
    return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()


def get_regex_flags() -> list[dict]:
    """Helper for legacy UI to get processor flags."""
    return get_config()["processor"]["flags"]


def save_regex_flags(flags: list[dict]) -> dict:
    """Helper for legacy UI to save processor flags."""
    return save_config({"processor": {"flags": flags}})


def validate_startup_config() -> list[str]:
    """Validate config at startup. Returns list of error strings (empty if valid)."""
    errors: list[str] = []
    try:
        cfg = get_config()
    except Exception as e:
        return [f"Failed to load config: {e}"]

    # Validate scraper section
    scraper = cfg.get("scraper", {})
    if scraper.get("rateLimitDelayMs", 0) < 0:
        errors.append("scraper.rateLimitDelayMs must be >= 0")
    if scraper.get("maxRetries", 0) < 0:
        errors.append("scraper.maxRetries must be >= 0")
    if not scraper.get("userAgent"):
        errors.append("scraper.userAgent is required")

    # Validate filter regex patterns compile
    for tag in cfg.get("filter", {}).get("tags", []):
        try:
            re.compile(tag.get("pattern", ""), re.IGNORECASE)
        except re.error as e:
            errors.append(f'filter tag "{tag.get("label", "?")}" invalid pattern: {e}')

    # Validate processor regex patterns compile
    for f in cfg.get("processor", {}).get("flags", []):
        if not f.get("pattern"):
            continue
        flags_arg = re.IGNORECASE if f.get("caseInsensitive") else 0
        try:
            re.compile(f["pattern"], flags_arg)
        except re.error as e:
            errors.append(f'processor flag "{f.get("name", "?")}" invalid pattern: {e}')

    return errors
