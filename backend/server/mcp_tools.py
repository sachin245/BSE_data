from . import coordinator, store, config_store
from datetime import datetime, timedelta

def list_announcements_tool():
    """List recent BSE announcements/filings from the database."""
    rows = store.list_announcements()
    hits = store.flag_hits_by_announcement()
    tag_hits = store.scrape_tag_hits_by_announcement()
    
    results = []
    for r in rows[:50]:  # Limit to 50 for MCP response size
        results.append({
            "id": r["id"],
            "scripCode": r["scrip_code"],
            "companyName": r["company_name"],
            "subject": r["subject"],
            "dtFiled": r["dt_filed"],
            "flagHits": [h["name"] for h in hits.get(r["id"], [])],
            "tags": [h["tagLabel"] for h in tag_hits.get(r["id"], [])]
        })
    return results

async def start_quick_run_tool(days: int = 7):
    """Start a Quick Run (Scraper + Processor) for the last N days."""
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")
    
    payload = {
        "mode": "pending",
        "from": start_date,
        "to": end_date
    }
    return await coordinator.start_quick_run(payload)

def get_system_status_tool():
    """Check the current status of background scraping and processing jobs."""
    return coordinator.get_status()

def get_config_tool():
    """Retrieve the current configuration for scraper and processor flags."""
    return {
        "config": config_store.get_config(),
        "flags": config_store.get_regex_flags()
    }
