# VC Job Agent — Developer Notes

## Project Purpose

Personal AI-powered job search agent for **Dr. Siyao Shao**, targeting Venture Capital investor and partner roles (VC and CVC). Scrapes job boards on a schedule, scores every listing against his deep-tech profile using Claude Opus 4.6, and sends smart notifications.

## Architecture

```
main.py          — FastAPI app + APScheduler (scrape 4×/day, health check daily, digest weekly)
config.py        — Profile string, search queries, target firm URLs, score thresholds
database.py      — SQLModel Job table + JobStatus enum + upsert_job()
scorer.py        — Claude Opus 4.6 scoring via messages.parse() + Pydantic JobMatchResult
notifier.py      — WhatsApp (CallMeBot), Gmail SMTP, health-check and weekly digest emails
scrapers/
  jobspy.py      — LinkedIn/Indeed via python-jobspy (requires Python 3.10+)
  wellfound.py   — Wellfound / AngelList scraper
  vc_boards.py   — jobs.vc + direct firm career pages (configured via TARGET_FIRM_URLS)
tdk_check.py     — Standalone health-check: scrapes TDK Ventures and scores with Claude
```

## Scraping Pipeline — Order of Execution

Each scheduled scrape runs three stages in this order:

1. **LinkedIn major VC/CVC company pages** (`scrapers/jobspy.py`)
   - Uses `python-jobspy` to search LinkedIn and Indeed for VC-related roles
   - Iterates through `SEARCH_QUERIES` in `config.py`
   - **Hard cap: 20 results per query** — set `results_wanted=20` in `scrape_jobs()`
   - Requires Python 3.10+; falls back gracefully to empty list on Python 3.9

2. **Direct company career pages** (`scrapers/vc_boards.py` — `_scrape_firm_page`)
   - Clicks into each firm listed in `TARGET_FIRM_URLS` in `config.py`
   - Filters for investor-relevant keywords (venture, investor, principal, partner, etc.)
   - **Hard cap: 20 jobs per firm page**
   - Add target firms by editing `TARGET_FIRM_URLS` in `config.py`

3. **VC-specific job boards** (`scrapers/vc_boards.py` — `_scrape_jobs_vc`, `scrapers/wellfound.py`)
   - Scrapes `jobs.vc` and Wellfound for VC-specific listings
   - **Hard cap: 20 jobs per board**

All three stages deduplicate by URL before DB insertion.

## Scraper Job Caps

Every scraper enforces a **maximum of 20 jobs per source/query**. This is intentional:
- Controls Claude API scoring costs (each scored job = 1 API call)
- Keeps the scheduled run under ~5 minutes
- Avoids overwhelming the dashboard with low-signal results

To change the cap, update `RESULTS_PER_QUERY` in `config.py` (affects jobspy) and the `[:20]` slice guards in `wellfound.py` and `vc_boards.py`.

## Claude Scoring

- Model: `claude-opus-4-6` with `thinking={"type": "adaptive"}`
- Structured output via `client.messages.parse()` with Pydantic `JobMatchResult`
- Each job gets: `score` (0–100), `headline`, `pros` (list), `cons` (list), `key_requirements` (list)
- Descriptions truncated to 6,000 characters before sending to Claude

**Score rubric:**

| Range  | Label    | Meaning                                                    |
|--------|----------|------------------------------------------------------------|
| 85–100 | Excellent | VC/CVC investor/partner in deep-tech, hardware, climate, AI |
| 65–84  | Good      | VC/CVC with slightly different domain or seniority         |
| 45–64  | Moderate  | Adjacent (tech scout, EIR, corporate innovation)           |
| 20–44  | Weak      | Deep-tech operating role, loosely related                  |
| 0–19   | Not relevant | Unrelated to VC or Siyao's background                  |

**Notification thresholds** (set in `notifier.py`):
- Score ≥ 90 → instant WhatsApp alert (CallMeBot)
- Score ≥ 75 → instant email alert (Gmail SMTP)

## Python Version Constraint

The user runs **Python 3.9.7 (Anaconda)**. All files that use union type hints must include:

```python
from __future__ import annotations
```

at the very top (before any other imports, after the module docstring). The `str | None` syntax is a runtime error on Python 3.9 without this import.

`python-jobspy` (Bunsly/JobSpy) requires Python 3.10+. The scraper handles this gracefully with a try/except ImportError that logs a warning and returns an empty list.

## Environment Variables

All secrets live in `.env` (gitignored). Required keys:

```
ANTHROPIC_API_KEY      — Anthropic API key with credits (use the "my-second-key" key ending EAAA)
CALLMEBOT_PHONE        — WhatsApp phone number with country code, no + (e.g. 14388850126)
CALLMEBOT_APIKEY       — CallMeBot API key (activate by messaging +34 644 59 79 13 on WhatsApp)
GMAIL_USER             — Gmail address (dr.siyaoshao@gmail.com)
GMAIL_APP_PASS         — Gmail App Password (not the account password)
NOTIFY_EMAIL           — Destination email for alerts and digests
```

## Running Locally

```bash
cd ~/job-agent
uvicorn main:app --reload
# Open http://localhost:8000
```

## Background Service (macOS)

The agent runs as a LaunchAgent — starts automatically on login, restarts on crash.

```bash
# Start
launchctl load ~/Library/LaunchAgents/com.siyaoshao.vcjobagent.plist

# Stop
launchctl unload ~/Library/LaunchAgents/com.siyaoshao.vcjobagent.plist

# Logs
tail -f ~/job-agent/agent.log
```

## Health Check Script

`tdk_check.py` is a standalone script that scrapes TDK Ventures specifically and scores results with Claude. Used to verify the API key and scoring pipeline are working.

```bash
python3 tdk_check.py
# Output written to tdk_healthcheck.log
```

## Adding Target VC Firms

Edit `TARGET_FIRM_URLS` in `config.py`:

```python
TARGET_FIRM_URLS = [
    {"firm": "Lux Capital",   "url": "https://www.luxcapital.com/careers"},
    {"firm": "DCVC",          "url": "https://www.dcvc.com/careers"},
]
```

The scraper visits each URL, finds investor-role links, and returns up to 20 jobs per page.
