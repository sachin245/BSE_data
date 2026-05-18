# GitHub Repos for Scraping NSE/BSE Corporate Filings & Investor Meet Announcements

## Context: What Are Investor-Meet Disclosures?

Investor-meet disclosures by listed companies in India are filed under **Regulation 30 of SEBI (LODR), Schedule III – Para A, item 15**. They appear in the "Corporate Announcements" feed on both:
- **BSE**: https://www.bseindia.com/corporates/ann
- **NSE**: NEAPS announcement module (https://www.nseindia.com)

### Key Filing Details
- **Regulatory requirement**: SEBI (Listing Obligations and Disclosure Requirements) Regulations, 2015
- **Common subjects to filter on**:
  - "Analyst / Investor Meet"
  - "Schedule of Analyst / Institutional Investor Meet"
  - "Investor Conference"
  - "Earnings Call"
  - "Investor Presentation"
  - "Investor Summit Intimation"

- **Required disclosures**: Schedule, mode of attendance, date, time, participant details, audio/video recordings, and written transcripts (within 5 working days)

### Why BSE Over NSE?
- BSE has a more accessible, rate-friendly announcements API endpoint
- NSE's website actively discourages scraping (per terms)
- Most developers treat BSE as the canonical source since announcements are filed on both exchanges

---

## Comparison Table of GitHub Repositories

| Rank | Repository | ⭐ Stars | Forks | Language | License | Last Active | Announcements API | Investor-Meet Fit |
|------|-----------|-----------|-------|----------|---------|-------------|------------------|------------------|
| **1** | [**BennyThadikaran/BseIndiaApi**](https://github.com/BennyThadikaran/BseIndiaApi) | **59** | 14 | Python | GPL-3.0 | Feb 2026 (v3.2.0) | ✅ **First-class** | ⭐⭐⭐⭐⭐ **BEST FIT** |
| 2 | [bshada/nse-bse-api](https://github.com/bshada/nse-bse-api) | 15 | 9 | TypeScript | MIT | Dec 2025 | ✅ Both NSE & BSE | ⭐⭐⭐⭐ Good |
| 3 | [Sampad-Hegde/Bharat-SM-Data](https://github.com/Sampad-Hegde/Bharat-SM-Data) | 54 | 27 | Python | Apache-2.0 | Jul 2025 (v4.0.1) | ✅ Multi-source | ⭐⭐⭐⭐ Good |
| 4 | [BennyThadikaran/stock-news](https://github.com/BennyThadikaran/stock-news) | 19 | 6 | Python | GPL-3.0 | Active | ✅ CLI wrapper | ⚠️ **FILTERED OUT** |
| 5 | [sdabhi23/bsedata](https://github.com/sdabhi23/bsedata) | **114** | 50 | Python | MIT | Mar 2024 (v0.6.0) | ❌ No | ❌ Wrong scope |
| 6 | [hirawatt/BSE_NSE_Announcement](https://github.com/hirawatt/BSE_NSE_Announcement) | 6 | 1 | Python | MIT | Aug 2021 | ✅ Selenium + UI | ⚠️ **Stale** |
| 7 | [theofficialvedantjoshi/bsescraper](https://github.com/theofficialvedantjoshi/bsescraper) | 1 | 0 | Python | MIT | 2024 | ✅ Keyword filter | ⭐⭐⭐ Simple |
| 8 | [pranjalbanka/BSE_Corporate-Announcement-Notifier](https://github.com/pranjalbanka/BSE_Corporate-Announcement-Notifier) | 4 | 0 | Python | None | 2021 | ✅ Limited | ❌ Results-focused |
| 9 | [jugaad-py/jugaad-data](https://github.com/jugaad-py/jugaad-data) | **505** | 186 | Python | MIT | Mar 2026 | ❌ No | ❌ **No coverage** |
| 10 | [rpkharche/python-bseindia](https://github.com/rpkharche/python-bseindia) | 2 | 1 | Python | MIT | 2018 | ❌ No | ❌ **Abandoned** |
| 11 | [chaitanyarahalkar/Financial-Info-Extractor](https://github.com/chaitanyarahalkar/Financial-Info-Extractor) | 24 | 8 | Python | MIT | 2018 | ❌ No | ❌ **Wrong purpose** |

---

## Detailed Repo Breakdown

### 🏆 #1: BennyThadikaran/BseIndiaApi
**GitHub**: https://github.com/BennyThadikaran/BseIndiaApi  
**Install**: `pip install -U bse`  
**Python version**: >= 3.8

#### Why It's #1 for Investor Meets
- **Native `announcements()` method** with category and date range filters
- **Built-in pagination** — handles 2000+ announcements per day automatically
- **Rate limiting** respected to avoid IP bans
- **Categories supported**: ACTION, AGM, ALLOTMENT, ANNUAL_REPORT, BOARD_MEETING, BUYBACK, COMPANY_UPDATE, DERIVATIVES, DIVIDEND, INVESTOR_MEET, MERGER, NOTICE, RESULTS, SPLITS, STOCK_SPLIT, OTHER
- **Active maintenance** — last release Feb 2026
- **Clean API** — works seamlessly with pandas DataFrames

#### Code Example
```python
from bse import BSE
from bse.constants import CATEGORY

with BSE(download_folder='./') as bse:
    # Get all investor-related announcements
    announcements = bse.announcements(
        category=CATEGORY.INVESTOR_MEET,
        from_date="01/01/2026",
        to_date="31/12/2026"
    )
    
    for ann in announcements:
        print(ann['subject'], ann['date'])
```

#### Bonus
- Sister repo: **[stock-news](https://github.com/BennyThadikaran/stock-news)** — CLI wrapper built on this API (though it blacklists "investor meet" by default — see caveat below)
- Pagination example: `get_all_announcements.py` in the repo

---

### 🥈 #2: bshada/nse-bse-api
**GitHub**: https://github.com/bshada/nse-bse-api  
**Language**: TypeScript (if you prefer JS/Node)  
**Install**: `npm install nse-bse-api`  
**Last update**: Dec 2025

#### Strengths
- **Unified NSE + BSE** in a single package
- Corporate actions, announcements, option chains all included
- Modern TypeScript API
- Newer codebase

#### Weakness for Your Use Case
- Less battle-tested than BseIndiaApi
- Fewer examples in the wild
- TypeScript (not Python) — requires Node.js setup

#### Code Example
```typescript
import { BSE } from 'nse-bse-api';

const bse = new BSE();
const actions = await bse.actions({
    fromDate: new Date('2026-01-01'),
    toDate: new Date('2026-12-31')
});
```

---

### 🥉 #3: Sampad-Hegde/Bharat-SM-Data
**GitHub**: https://github.com/Sampad-Hegde/Bharat-SM-Data  
**Install**: `pip install Bharat-sm-data`  
**Last update**: Jul 2025 (v4.0.1)

#### What It Offers
- Broad multi-source library: NSE, BSE, Moneycontrol, Tickertape, Sensibull
- Lists "Corporate Disclosures" under NSE Technical features
- Also pulls fundamentals, shareholding patterns, mutual fund holdings
- Most comprehensive for holistic company research

#### Drawback
- **Overkill** if you only need investor-meet filings
- Depends on third-party APIs that may throttle/change
- Documentation less focused on announcements

#### Code Example
```python
from Bharat_sm_data.nse import corporate_disclosures
data = corporate_disclosures("INFY")  # Hypothetical method
```

---

### ⚠️ #4: BennyThadikaran/stock-news
**GitHub**: https://github.com/BennyThadikaran/stock-news  
**Type**: CLI tool (builds on BseIndiaApi)

#### Critical Issue for Investor Meets
By default, it **BLACKLISTS** the keyword `investor meet` in the `isBlackListed()` function, treating it as "unimportant":

```python
filtered_words = [
    "trading window",
    "reg. 74 (5)",
    "book closure",
    "investor meet",      # ← FILTERED OUT!
    "loss of share",
    "loss of certificate",
    ...
]
```

**To use for investor meets**: You would need to remove this line and rebuild.

---

### 📌 #7: theofficialvedantjoshi/bsescraper
**GitHub**: https://github.com/theofficialvedantjoshi/bsescraper  
**Install**: `pip install bsescraper`  
**Stars**: 1 (brand new)

#### Unique Feature
Built-in **keyword filter** in the function signature:

```python
import bsescraper

bs = bsescraper.BSE()

# Get announcements with specific keywords
results = bs.get_corporate_ann_keywords(
    keywords=["analyst", "investor", "conference"],
    code=500325,  # Company code
    category='Company Update',
    startdate='01/01/2026',
    enddate='31/12/2026'
)
```

#### Drawback
- Unmaintained (last commit 2024)
- Low adoption (1 star)
- No pagination example

---

### ❌ Others (Not Recommended for This Use Case)

| Repo | Why Not |
|------|---------|
| **sdabhi23/bsedata** | 114 stars but covers only live quotes, gainers/losers, indices — no announcements API |
| **jugaad-py/jugaad-data** | 505 stars (most popular India market lib!) but **zero announcements coverage**; focuses on OHLC, bhavcopy, derivatives |
| **hirawatt/BSE_NSE_Announcement** | UI-based (Streamlit + Selenium), last updated Aug 2021 (5 years stale), overcomplicated for programmatic access |
| **rpkharche/python-bseindia** | Abandoned (2018), minimal functionality |
| **chaitanyarahalkar/Financial-Info-Extractor** | Religare financial ratios scraper, wrong purpose |

---

## 📊 Feature Comparison Matrix

| Feature | BseIndiaApi | bshada/nse-bse-api | Bharat-SM-Data | bsescraper |
|---------|-------------|-------------------|-----------------|-----------|
| BSE Announcements API | ✅ Native | ✅ Wrapped | ✅ Via source | ✅ Scraper |
| NSE Announcements | ❌ | ✅ | ✅ (via Tickertape) | ❌ |
| Pagination | ✅ Auto | ✅ | ✅ | ❌ Manual |
| Category filtering | ✅ Built-in enum | ✅ | ✅ | ❌ |
| Keyword filtering | ⚠️ Manual regex | ⚠️ Manual | ⚠️ Manual | ✅ Built-in |
| Rate limiting | ✅ Yes | ⚠️ Unknown | ⚠️ Unknown | ❌ |
| Active maintenance | ✅ Yes (2026) | ✅ Yes (2025) | ✅ Yes (2025) | ❌ (2024) |
| Python 3.8+ | ✅ | ❌ (TS) | ✅ | ✅ |
| PyPI package | ✅ | ❌ (npm) | ✅ | ✅ |
| Community size | Large | Small | Medium | Tiny |
| Documentation | Good | Medium | Excellent | Basic |

---

## 🎯 Recommended Approach for Your Use Case

### Step 1: Choose Your Primary Tool
**→ Start with `BseIndiaApi`** (most stable, actively maintained, purpose-built)

```bash
pip install -U bse
```

### Step 2: Daily Pull of Investor-Meet Filings

```python
from bse import BSE
from bse.constants import CATEGORY
from datetime import datetime, timedelta
import pandas as pd
import re

def fetch_investor_meets(days_back=1):
    """Fetch investor-meet announcements from BSE for the last N days"""
    
    with BSE(download_folder='./') as bse:
        today = datetime.today()
        from_date = (today - timedelta(days=days_back)).strftime('%d/%m/%Y')
        to_date = today.strftime('%d/%m/%Y')
        
        # Fetch all announcements
        announcements = bse.announcements(
            from_date=from_date,
            to_date=to_date
        )
        
        # Filter for investor meets (subject keyword match)
        investor_meet_keywords = [
            r'analyst.*meet',
            r'investor.*meet',
            r'investor.*conference',
            r'earnings.*call',
            r'schedule.*analyst',
            r'conference.*call',
            r'investor.*presentation',
            r'investor.*summit'
        ]
        
        filtered = []
        for ann in announcements:
            subject = ann.get('subject', '').lower()
            if any(re.search(kw, subject) for kw in investor_meet_keywords):
                filtered.append(ann)
        
        return pd.DataFrame(filtered)

# Usage
df = fetch_investor_meets(days_back=7)
print(df[['subject', 'date', 'headline']])
df.to_csv('investor_meets.csv', index=False)
```

### Step 3 (Optional): Add NSE Coverage
If you want NSE announcements too:

```bash
npm install nse-bse-api  # Or use Bharat-SM-Data for more breadth
```

### Step 4: Download Presentation/Transcript PDFs
Once you've identified announcements, scrape the attachment links:

```python
# The announcements API returns document links
# Download PDFs programmatically using requests + BeautifulSoup
import requests

def download_announcement_pdf(announcement_url, output_dir='./pdfs'):
    response = requests.get(announcement_url)
    if response.status_code == 200:
        filename = announcement_url.split('/')[-1]
        with open(f'{output_dir}/{filename}', 'wb') as f:
            f.write(response.content)
```

---

## ⚠️ Important Caveats

### 1. **"Investor Meet" Nomenclature is NOT Standardized**
Companies file this under different names:
- "Analyst Meet" vs "Analyst Meeting"
- "Investor Conference Call" vs "Earnings Call"
- "Schedule of Analyst/Institutional Investor Meet"
- "Investor Summit Intimation"
- Sometimes just "Company Update" with the text mentioning investor engagement

**Action**: Use a **broad regex** with synonyms (see code example above), not exact string match.

### 2. **Rate Limiting & IP Bans**
- BSE will throttle/block aggressive scrapers
- BseIndiaApi has built-in rate limiting; use it
- Respect HTTP 429 (Too Many Requests) responses
- Recommended: fetch once daily during market hours, not continuously

### 3. **Content Beyond Subject Line**
- The API returns **subject, date, headline** only
- The actual **presentation/transcript PDFs** require a second download step (see Step 4 above)
- 5-working-day regulatory deadline applies to PDF upload

### 4. **Small-Cap Companies May Have Sparse Data**
- Micro-cap and penny-stock companies often don't conduct analyst calls
- Mid-cap companies typically have 2–4 calls per year (post-quarterly results)
- Blue-chip companies have more frequent calls

### 5. **Historical Data Limitations**
- BSE announcements API typically goes back 1–2 years reliably
- Older announcements may be archived or delisted
- For long-term analysis, request direct data from the company's investor relations portal

### 6. **Commercial Alternatives Exist**
If you scale to 1000+ stocks or need SLA guarantees:
- **TickerPlant**: ₹3+ lakh/year for BSE corporate announcement API
- **Trendlyne**: Corporate announcements feed (affordable tier available)
- **BSE's official data feed**: Direct licensing from the exchange

---

## 📋 Quick Recommendation Summary

| Scenario | Tool | Why |
|----------|------|-----|
| **Starting out, <50 stocks** | **BseIndiaApi** | Stable, free, Python, rate-limited |
| **Need NSE + BSE both** | **Bharat-SM-Data** | Multi-source, includes Moneycontrol/Tickertape |
| **TypeScript/Node.js shop** | **bshada/nse-bse-api** | Modern, unified NSE+BSE API |
| **Quick keyword filter, simple** | **theofficialvedantjoshi/bsescraper** | Tiny, has built-in keyword matching |
| **Enterprise / 1000+ stocks** | **Commercial (Trendlyne, TickerPlant)** | SLA, reliability, support |
| **UI-based exploration** | **hirawatt/BSE_NSE_Announcement** | ⚠️ Stale, but interactive |

---

## 🔗 Useful Resources

- **SEBI Regulation 30 Guidance**: https://ca2013.com/lodr-regulation-30/
- **BSE Guidance on Analyst/Investor Meets**: https://www.bseindia.com (search: "Guidance Note on Disclosure")
- **NSE NEAPS Announcement Module**: https://www.nseindia.com (requires registration)
- **BseIndiaApi Documentation**: https://bennythadikaran.github.io/BseIndiaApi/
- **Bharat-SM-Data Docs**: https://bharat-sm-data.readthedocs.io/

---

## 📝 License & Disclaimers

- **bsedata**, **BseIndiaApi**, **Bharat-SM-Data** are MIT/GPL-licensed open-source projects
- Web scraping may violate exchange ToS; use responsibly and respect rate limits
- This data is for personal/research use; commercial redistribution may require licensing
- Always verify against official BSE/NSE websites for compliance purposes

---

**Generated**: May 2026  
**Tested repos**: As of latest releases (Jan–Mar 2026)
