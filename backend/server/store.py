import json
import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = "data/announcements.db"
_db: sqlite3.Connection | None = None


def get_db() -> sqlite3.Connection:
    global _db
    if _db is not None:
        return _db
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("PRAGMA foreign_keys = ON")
    _init_schema(conn)
    _db = conn
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS announcements (
          id              TEXT PRIMARY KEY,
          scrip_code      TEXT NOT NULL,
          company_name    TEXT,
          segment         TEXT,
          subject         TEXT,
          headline        TEXT,
          category        TEXT,
          dt_filed        TEXT,
          attachment_url  TEXT,
          attachment_path TEXT,
          processed_at    TEXT,
          raw_json        TEXT,
          seen_at         TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_dt_filed ON announcements(dt_filed);
        CREATE INDEX IF NOT EXISTS idx_scrip    ON announcements(scrip_code);
        CREATE INDEX IF NOT EXISTS idx_proc     ON announcements(processed_at);

        CREATE TABLE IF NOT EXISTS scrape_tag_hits (
          announcement_id TEXT NOT NULL,
          tag_id          TEXT NOT NULL,
          tag_label       TEXT NOT NULL,
          matched_text    TEXT,
          created_at      TEXT NOT NULL,
          PRIMARY KEY (announcement_id, tag_id),
          FOREIGN KEY (announcement_id) REFERENCES announcements(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS flag_hits (
          announcement_id TEXT NOT NULL,
          flag_name       TEXT NOT NULL,
          snippet         TEXT NOT NULL,
          created_at      TEXT NOT NULL,
          PRIMARY KEY (announcement_id, flag_name),
          FOREIGN KEY (announcement_id) REFERENCES announcements(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS run_history (
          id              INTEGER PRIMARY KEY AUTOINCREMENT,
          step            TEXT NOT NULL,
          started_at      TEXT NOT NULL,
          finished_at     TEXT,
          range_from      TEXT,
          range_to        TEXT,
          pages_fetched   INTEGER DEFAULT 0,
          records_scanned INTEGER DEFAULT 0,
          matched         INTEGER DEFAULT 0,
          new_records     INTEGER DEFAULT 0,
          pdfs_ok         INTEGER DEFAULT 0,
          pdfs_failed     INTEGER DEFAULT 0,
          pdfs_processed  INTEGER DEFAULT 0,
          flag_hit_total  INTEGER DEFAULT 0,
          http_429s       INTEGER DEFAULT 0,
          http_503s       INTEGER DEFAULT 0,
          elapsed_sec     INTEGER DEFAULT 0,
          status          TEXT
        );

        CREATE TABLE IF NOT EXISTS settings_kv (
          key        TEXT PRIMARY KEY,
          value      TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
    """)
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_announcements_batch(records: list) -> None:
    db = get_db()
    now = _now()
    with db:
        for r in records:
            db.execute(
                """INSERT INTO announcements
                     (id, scrip_code, company_name, segment, subject, headline, category,
                      dt_filed, attachment_url, attachment_path, processed_at, raw_json, seen_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     company_name    = COALESCE(NULLIF(excluded.company_name, ''), announcements.company_name),
                     attachment_url  = excluded.attachment_url,
                     attachment_path = COALESCE(excluded.attachment_path, announcements.attachment_path),
                     raw_json        = COALESCE(excluded.raw_json, announcements.raw_json),
                     seen_at         = excluded.seen_at""",
                (
                    r["id"], r["scripCode"], r.get("companyName") or None,
                    r.get("segment") or None, r.get("subject", ""), r.get("headline", ""),
                    r.get("category") or None, r.get("dtFiled") or None,
                    r.get("attachmentUrl") or None, r.get("attachmentPath") or None,
                    r.get("processedAt") or None, r.get("rawJson") or None, now,
                ),
            )
            for h in r.get("matchedTags", []):
                db.execute(
                    """INSERT INTO scrape_tag_hits
                         (announcement_id, tag_id, tag_label, matched_text, created_at)
                       VALUES (?,?,?,?,?)
                       ON CONFLICT(announcement_id, tag_id) DO UPDATE SET
                         tag_label    = excluded.tag_label,
                         matched_text = excluded.matched_text""",
                    (r["id"], h["tagId"], h["tagLabel"], (h.get("matchedText") or "")[:240], now),
                )


def set_attachment_path(ann_id: str, path: str) -> None:
    db = get_db()
    with db:
        db.execute("UPDATE announcements SET attachment_path = ? WHERE id = ?", (path, ann_id))


def mark_processed(ann_id: str) -> None:
    db = get_db()
    with db:
        db.execute("UPDATE announcements SET processed_at = ? WHERE id = ?", (_now(), ann_id))


_LIST_COLS = (
    "id, scrip_code, company_name, segment, subject, headline, "
    "category, dt_filed, attachment_url, attachment_path, processed_at, seen_at"
)


def list_announcements(
    *,
    with_attachment: bool = False,
    with_attachment_url: bool = False,
    unprocessed_only: bool = False,
) -> list[dict]:
    sql = f"SELECT {_LIST_COLS} FROM announcements WHERE 1=1"
    if with_attachment:
        sql += " AND attachment_path IS NOT NULL"
    if with_attachment_url:
        sql += " AND attachment_url IS NOT NULL"
    if unprocessed_only:
        sql += " AND processed_at IS NULL"
    sql += " ORDER BY dt_filed DESC"
    return [dict(r) for r in get_db().execute(sql).fetchall()]


def scrape_tag_hits_by_announcement() -> dict[str, list]:
    rows = get_db().execute(
        "SELECT announcement_id, tag_id, tag_label, matched_text FROM scrape_tag_hits"
    ).fetchall()
    out: dict[str, list] = {}
    for r in rows:
        out.setdefault(r["announcement_id"], []).append(
            {"tagId": r["tag_id"], "tagLabel": r["tag_label"], "matchedText": r["matched_text"]}
        )
    return out


def clear_flag_hits_for(announcement_ids: list[str]) -> None:
    if not announcement_ids:
        return
    db = get_db()
    chunk_size = 999
    with db:
        for i in range(0, len(announcement_ids), chunk_size):
            chunk = announcement_ids[i : i + chunk_size]
            placeholders = ",".join("?" * len(chunk))
            db.execute(f"DELETE FROM flag_hits WHERE announcement_id IN ({placeholders})", chunk)


def insert_flag_hit(announcement_id: str, flag_name: str, snippet: str) -> None:
    db = get_db()
    with db:
        db.execute(
            """INSERT OR REPLACE INTO flag_hits
                 (announcement_id, flag_name, snippet, created_at)
               VALUES (?,?,?,?)""",
            (announcement_id, flag_name, snippet[:240], _now()),
        )


def flag_hits_by_announcement() -> dict[str, list]:
    rows = get_db().execute(
        "SELECT announcement_id, flag_name, snippet FROM flag_hits"
    ).fetchall()
    out: dict[str, list] = {}
    for r in rows:
        out.setdefault(r["announcement_id"], []).append(
            {"name": r["flag_name"], "snippet": r["snippet"]}
        )
    return out


def insert_run_history(row: dict) -> int:
    db = get_db()
    with db:
        cur = db.execute(
            """INSERT INTO run_history
                 (step, started_at, finished_at, range_from, range_to,
                  pages_fetched, records_scanned, matched, new_records,
                  pdfs_ok, pdfs_failed, pdfs_processed, flag_hit_total,
                  http_429s, http_503s, elapsed_sec, status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                row["step"], row["started_at"], row.get("finished_at"),
                row.get("range_from"), row.get("range_to"),
                row.get("pages_fetched", 0), row.get("records_scanned", 0),
                row.get("matched", 0), row.get("new_records", 0),
                row.get("pdfs_ok", 0), row.get("pdfs_failed", 0),
                row.get("pdfs_processed", 0), row.get("flag_hit_total", 0),
                row.get("http_429s", 0), row.get("http_503s", 0),
                row.get("elapsed_sec", 0), row.get("status"),
            ),
        )
    return cur.lastrowid


def list_run_history(limit: int = 50) -> list[dict]:
    rows = get_db().execute(
        "SELECT * FROM run_history ORDER BY started_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def reset_announcements() -> None:
    db = get_db()
    with db:
        db.execute("DELETE FROM announcements")


def reset_run_history() -> None:
    db = get_db()
    with db:
        db.execute("DELETE FROM run_history")


def settings_kv_set(key: str, value) -> None:
    db = get_db()
    with db:
        db.execute(
            """INSERT INTO settings_kv (key, value, updated_at)
               VALUES (?,?,?)
               ON CONFLICT(key) DO UPDATE SET
                 value = excluded.value,
                 updated_at = excluded.updated_at""",
            (key, json.dumps(value), _now()),
        )


def settings_kv_all() -> dict:
    rows = get_db().execute("SELECT key, value FROM settings_kv").fetchall()
    return {r["key"]: json.loads(r["value"]) for r in rows}
