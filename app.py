"""
BSE Investor-Meet Scraper & Analyser — Streamlit UI
=====================================================
Single-file front-end.  All business logic lives in backend.server.

Run (from the BSE_Data/ directory):
    streamlit run app.py

Or via start-dev.ps1 from the parent directory.
"""

import asyncio
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

# ── Working-directory fix: backend.server uses relative paths for DB/config
_HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(_HERE)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from backend.server import coordinator, scraper_engine, processor_engine, config_store, store
from backend.server.logger import streamlit_logger


# ═══════════════════════════════════════════════════════════════════════════
# MODULE-LEVEL JOB STATE  (persists across Streamlit reruns)
# ═══════════════════════════════════════════════════════════════════════════

_job_state: dict = {"running": False, "thread": None}


# ═══════════════════════════════════════════════════════════════════════════
# BACKGROUND EXECUTION HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _is_busy() -> bool:
    return _job_state["running"] or bool(coordinator.get_active_step())


def run_in_background(coro_factory) -> None:
    """Spawn coro_factory() in a daemon thread via asyncio.run()."""
    if _is_busy():
        st.warning("A job is already running — stop it first.")
        return

    def _target():
        asyncio.run(coro_factory())
        _job_state["running"] = False

    _job_state["running"] = True
    t = threading.Thread(target=_target, daemon=True)
    _job_state["thread"] = t
    t.start()


async def _launch_scraper(payload: dict) -> None:
    await coordinator.start_scraper(payload)
    while scraper_engine.state["running"]:
        await asyncio.sleep(0.2)


async def _launch_processor(payload: dict) -> None:
    await coordinator.start_processor(payload)
    while processor_engine.state["running"]:
        await asyncio.sleep(0.2)


async def _launch_quick_run(payload: dict) -> None:
    await coordinator.start_quick_run(payload)
    while coordinator.get_active_step() is not None:
        await asyncio.sleep(0.2)


# ═══════════════════════════════════════════════════════════════════════════
# RENDERING HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _phase_label(phase: str | None) -> str:
    labels = {
        "idle":        "Idle",
        "fetching":    "Fetching pages…",
        "downloading": "Downloading PDFs…",
        "extracting":  "Extracting text…",
        "done":        "Done",
        "ok":          "Completed",
        "cancelled":   "Cancelled",
        "failed":      "Failed",
    }
    return labels.get(phase or "idle", phase or "idle")


def _render_log(log: list) -> None:
    if not log:
        return
    with st.expander("Log", expanded=False):
        lines = "\n".join(
            f"[{e['ts']}] {e['msg']}" for e in reversed(log[-100:])
        )
        st.code(lines, language=None)


def _render_scraper_status(s: dict) -> None:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Phase",       _phase_label(s.get("phase")))
    col2.metric("Pages",       f"{s.get('pagesDone', 0)} / {s.get('totalPages', 0)}")
    col3.metric("Matched",     s.get("matched", 0))
    col4.metric("New records", s.get("newRecords", 0))
    st.progress(min(1.0, float(s.get("progress", 0.0))))
    if s.get("pdfsOk") or s.get("pdfsFailed"):
        c1, c2 = st.columns(2)
        c1.metric("PDFs OK",     s.get("pdfsOk",     0))
        c2.metric("PDFs failed", s.get("pdfsFailed", 0))
    _render_log(s.get("log", []))


def _render_processor_status(p: dict) -> None:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Phase",     _phase_label(p.get("phase")))
    col2.metric("Mode",      p.get("mode") or "—")
    col3.metric("Processed", f"{p.get('processed', 0)} / {p.get('totalRecords', 0)}")
    col4.metric("Flag hits", p.get("flagHits", 0))
    st.progress(min(1.0, float(p.get("progress", 0.0))))
    _render_log(p.get("log", []))


# ═══════════════════════════════════════════════════════════════════════════
# FIRST-LAUNCH BANNER  (FR-C06)
# ═══════════════════════════════════════════════════════════════════════════

def _maybe_show_config_banner() -> None:
    """Show an info banner when no config file exists yet (first launch)."""
    config_path = Path(_HERE) / "data" / "config.json"
    if not config_path.exists():
        st.info(
            "**First launch detected** — default configuration has been created at "
            "`data/config.json`.  \n"
            "Please open the **Config** tab to review and customise:\n"
            "- Watchlist scrip codes\n"
            "- Filter tags (Step 1)\n"
            "- Processor flags (Step 2)\n"
            "- Scraper rate-limit and timeout settings",
            icon="ℹ️",
        )


# ═══════════════════════════════════════════════════════════════════════════
# TAB 1 — FILINGS
# ═══════════════════════════════════════════════════════════════════════════

def page_filings() -> None:
    st.header("Filings")

    announcements = store.list_announcements()
    if not announcements:
        st.info("No filings in the database yet. Run the scraper from the Admin tab.")
        return

    flag_hits   = store.flag_hits_by_announcement()
    scrape_hits = store.scrape_tag_hits_by_announcement()

    rows = []
    for a in announcements:
        aid        = a["id"]
        match_tags = ", ".join(h["tagLabel"] for h in scrape_hits.get(aid, []))
        flag_names = ", ".join(h["name"]     for h in flag_hits.get(aid,   []))
        rows.append(
            {
                "id":           aid,
                "Filed":        (a.get("dt_filed") or "")[:10],
                "Scrip":        a.get("scrip_code",   ""),
                "Segment":      a.get("segment")      or "",
                "Company":      a.get("company_name") or "",
                "Subject":      a.get("subject")      or "",
                "Match tags":   match_tags,
                "Flag hits":    flag_names,
                "_scrape_hits": scrape_hits.get(aid, []),
                "_flag_hits":   flag_hits.get(aid,   []),
                "_headline":    a.get("headline")       or "",
                "_url":         a.get("attachment_url") or "",
            }
        )

    df_full = pd.DataFrame(rows)

    fc1, fc2, fc3 = st.columns([3, 2, 2])
    query        = fc1.text_input("Search (company / subject / scrip)", key="fil_query")
    seg_opt      = fc2.selectbox("Segment", ["All", "Mainboard", "SME"], key="fil_seg")
    matched_only = fc3.checkbox("Matched only", key="fil_matched")

    df = df_full.copy()
    if query:
        q = query.lower()
        mask = (
            df["Company"].str.lower().str.contains(q, na=False)
            | df["Subject"].str.lower().str.contains(q, na=False)
            | df["Scrip"].str.lower().str.contains(q, na=False)
        )
        df = df[mask]
    if seg_opt != "All":
        df = df[df["Segment"].str.upper() == seg_opt.upper()]
    if matched_only:
        df = df[df["Match tags"].str.len() > 0]

    st.caption(f"Showing {len(df)} of {len(df_full)} filings")
    display_cols = ["Filed", "Scrip", "Segment", "Company", "Subject", "Match tags", "Flag hits"]
    st.dataframe(df[display_cols], use_container_width=True, hide_index=True)

    if len(df) > 0:
        st.divider()
        st.subheader("Detail view")
        options   = [f"{r['Filed']} | {r['Scrip']} | {r['Subject'][:60]}" for _, r in df.head(50).iterrows()]
        sel_label = st.selectbox("Select a filing", options, key="fil_detail_sel")
        sel_idx   = options.index(sel_label) if sel_label in options else 0
        row       = df.iloc[sel_idx]

        dc1, dc2 = st.columns([1, 1])
        with dc1:
            st.markdown(f"**Company:** {row['Company']}")
            st.markdown(f"**Scrip:** {row['Scrip']} ({row['Segment']})")
            st.markdown(f"**Filed:** {row['Filed']}")
        with dc2:
            st.markdown(f"**Match Tags:** {row['Match tags']}")
            st.markdown(f"**Flag Hits:** {row['Flag hits']}")
            pdf_url = f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{row['id']}.pdf"
            st.link_button("📄 View PDF on BSE", pdf_url)
        
        st.info(f"**Subject:** {row['Subject']}")

# ═══════════════════════════════════════════════════════════════════════════
# TAB 2 — ADMIN
# ═══════════════════════════════════════════════════════════════════════════

def page_admin() -> None:
    st.header("Admin Control")
    
    st.subheader("Date Range Settings")
    default_start = datetime.now() - timedelta(days=30)
    default_end = datetime.now()
    
    dc1, dc2 = st.columns(2)
    start_date = dc1.date_input("Start Date", value=default_start)
    end_date = dc2.date_input("End Date", value=default_end)
    
    st.divider()
    
    st.subheader("Quick Run")
    st.write("Run both Scraper and Processor sequentially for pending records.")
    if st.button("🚀 Start Quick Run", disabled=_is_busy()):
        streamlit_logger.info(f"User initiated Quick Run from {start_date} to {end_date}")
        run_in_background(lambda: _launch_quick_run({
            "mode": "pending",
            "from": start_date.strftime("%Y-%m-%d"),
            "to": end_date.strftime("%Y-%m-%d")
        }))
    
    st.divider()
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Scraper")
        if st.button("🔍 Start Scraper", disabled=_is_busy()):
            streamlit_logger.info(f"User initiated Scraper from {start_date} to {end_date}")
            run_in_background(lambda: _launch_scraper({
                "watchlistOnly": True,
                "from": start_date.strftime("%Y-%m-%d"),
                "to": end_date.strftime("%Y-%m-%d")
            }))
        _render_scraper_status(scraper_engine.state)
        
    with col2:
        st.subheader("Processor")
        if st.button("⚙️ Start Processor", disabled=_is_busy()):
            streamlit_logger.info("User initiated Processor")
            run_in_background(lambda: _launch_processor({"mode": "pending"}))
        _render_processor_status(processor_engine.state)

    if _is_busy():
        if st.button("🛑 Stop All Processes", type="primary"):
            streamlit_logger.warning("User manually stopped all processes")
            coordinator.stop()
            st.rerun()

# ═══════════════════════════════════════════════════════════════════════════
# TAB 3 — CONFIG
# ═══════════════════════════════════════════════════════════════════════════

def page_config() -> None:
    st.header("Configuration")
    cfg = config_store.get_config()
    
    with st.expander("Scraper Settings", expanded=True):
        rate_limit = st.number_input("Rate Limit Delay (ms)", value=cfg["scraper"]["rateLimitDelayMs"])
        page_size = st.number_input("Page Size", value=cfg["scraper"]["pageSize"])
        if st.button("Save Scraper Settings"):
            config_store.save_config({"scraper": {"rateLimitDelayMs": rate_limit, "pageSize": page_size}})
            st.success("Saved!")

    with st.expander("Processor Flags", expanded=True):
        flags = config_store.get_regex_flags()
        new_flags = []
        for i, f in enumerate(flags):
            c1, c2, c3 = st.columns([3, 5, 1])
            name = c1.text_input(f"Name {i}", value=f["name"], key=f"fn_{i}")
            pattern = c2.text_input(f"Pattern {i}", value=f["pattern"], key=f"fp_{i}")
            active = c3.checkbox("Active", value=f["active"], key=f"fa_{i}")
            new_flags.append({"name": name, "pattern": pattern, "active": active, "caseInsensitive": f.get("caseInsensitive", True)})
        
        if st.button("Save Flags"):
            config_store.save_regex_flags(new_flags)
            st.success("Flags saved!")

# ═══════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def main() -> None:
    st.set_page_config(page_title="BSE Data Control", layout="wide")
    st.sidebar.title("BSE Control Panel")
    
    _maybe_show_config_banner()
    
    page = st.sidebar.radio("Navigation", ["Filings", "Admin", "Config"])
    
    if page == "Filings":
        page_filings()
    elif page == "Admin":
        page_admin()
    elif page == "Config":
        page_config()

if __name__ == "__main__":
    main()