# VC Job Agent — Developer Notes

## Project Purpose

Personal AI-powered job search agent for **Dr. Siyao Shao**. Scrapes job boards on a schedule,
scores every listing against his profile using Claude Opus 4.6 (with a keyword fallback scorer),
and sends smart notifications.

**Target role types** (in priority order):
1. VC/CVC investor or partner — deep-tech, hardware, AI, climate
2. Founding / staff engineer at Seed–Series B deep-tech startups
3. Principal / lead research engineer (MEMS, edge AI, embedded, industrial)
4. Technical sales / FAE / solutions engineer in hardware, semiconductor, industrial IoT

## Architecture

```
main.py               — FastAPI app + APScheduler (scrape 4×/day, health check daily, digest weekly)
config.py             — Profile, SEARCH_QUERIES, WELLFOUND_QUERIES, TARGET_FIRM_URLS, thresholds
database.py           — SQLModel: Job table + UserSettings table + upsert_job() + get_settings()
scorer.py             — Claude Opus 4.6 scoring via messages.parse() + Pydantic JobMatchResult
                        Falls back to scorer_fallback.py on API failure
scorer_fallback.py    — Keyword + TF-IDF fallback scorer (no API, always works)
profile.py            — Dynamic profile loader: get_profile_text(), get_search_queries()
notifier.py           — WhatsApp (CallMeBot), Gmail SMTP, health-check and weekly digest emails
scrapers/
  jobspy.py           — LinkedIn/Indeed via python-jobspy (requires Python 3.10+)
  wellfound.py        — Wellfound / AngelList scraper
  vc_boards.py        — jobs.vc + NFX + VC Careers + direct firm career pages
  gmail_alerts.py     — Gmail IMAP: reads LinkedIn job alert emails, extracts job listings
health_monitor.py     — 24-hour polling script to verify scheduled scrapes fire on time
tdk_check.py          — Standalone health-check: scrapes TDK Ventures and scores with Claude
```

## Scraping Pipeline — Order of Execution

Each scheduled scrape runs four stages:

1. **LinkedIn / Indeed** (`scrapers/jobspy.py`)
   - Searches via `SEARCH_QUERIES` in `config.py` (26 queries across VC, founding eng, FAE, tech sales, research)
   - **Hard cap: 20 results per query**
   - Requires Python 3.10+; falls back gracefully on Python 3.9

2. **Wellfound** (`scrapers/wellfound.py`)
   - Uses `WELLFOUND_QUERIES` from `config.py`
   - **Hard cap: 20 jobs per query**

3. **VC-specific boards + direct firm pages** (`scrapers/vc_boards.py`)
   - jobs.vc, NFX Guild, Venture Capital Careers boards
   - Direct career pages for all firms in `TARGET_FIRM_URLS`
   - **Hard cap: 20 jobs per source/firm**

4. **Gmail LinkedIn alerts** (`scrapers/gmail_alerts.py`)
   - Connects to `imap.gmail.com:993` using `GMAIL_USER` + `GMAIL_APP_PASS`
   - Searches `[Gmail]/All Mail` for emails from `jobs-noreply@linkedin.com` and `jobalerts-noreply@linkedin.com`
   - Skips application-status emails (subject filter)
   - Lookback: 7 days; cap: 50 emails, 20 jobs per email

All stages deduplicate by URL before DB insertion.

## Scraper Job Caps

Every scraper enforces a **maximum of 20 jobs per source/query**:
- Controls Claude API scoring costs (each scored job = 1 API call)
- Keeps each scheduled run under ~5 minutes
- Avoids overwhelming the dashboard with low-signal results

To change: update `RESULTS_PER_QUERY` in `config.py` (jobspy) and `[:20]` slice guards in `wellfound.py` and `vc_boards.py`.

## Scoring

### Claude scorer (`scorer.py`)
- Model: `claude-opus-4-6` with `thinking={"type": "adaptive"}`
- Structured output via `client.messages.parse()` + Pydantic `JobMatchResult`
- Each job gets: `score` (0–100), `headline`, `pros`, `cons`, `key_requirements`
- Descriptions truncated to 6,000 characters
- Profile loaded dynamically from `UserSettings` DB row via `profile.get_profile_text()`
- On any Claude failure → falls back to keyword scorer

### Keyword fallback scorer (`scorer_fallback.py`)
- No API dependency — always works
- Three layers: title keywords (0–45 pts) + domain keywords (0–35 pts) + TF-IDF cosine (0–20 pts)
- MD5-keyed vector cache; respects dynamic profile changes
- Activated automatically when Claude is unavailable or via `scorer_method = "keyword"` in settings

**Score rubric:**

| Range  | Label        | Meaning                                                                                      |
|--------|--------------|----------------------------------------------------------------------------------------------|
| 85–100 | Excellent    | VC/CVC investor/partner in deep-tech/hardware/AI/climate; OR founding/staff engineer at deep-tech Seed–Series B |
| 65–84  | Good         | VC/CVC slightly off domain/seniority; principal research engineer; FAE/solutions/tech sales in hardware or AI |
| 45–64  | Moderate     | Adjacent role: EIR, tech scout, product engineer, corporate innovation, research scientist    |
| 20–44  | Weak         | Generic engineering role without deep-tech or startup angle                                  |
| 0–19   | Not relevant | Unrelated to Siyao's background                                                              |

**Notification thresholds** (set in `notifier.py`, overridable in DB `UserSettings`):
- Score ≥ 90 → instant WhatsApp alert (CallMeBot)
- Score ≥ 75 → instant email alert (Gmail SMTP)

## User Settings (Web UI)

Visit `/settings` to update without editing files:
- **Profile Identity** — name
- **Resume / Profile** — full resume text used by Claude and fallback scorer
- **Job Targets** — target titles (one per line) and free-text anticipations

Changes take effect on the next scrape/score run. Profile is loaded fresh per scoring call.

## Python Version Constraint

The project runs on **Python 3.9.7 (Anaconda)**. All files using union type hints must include:

```python
from __future__ import annotations
```

at the very top (after the module docstring, before other imports). The `str | None` syntax is a
runtime error on Python 3.9 without this.

`python-jobspy` requires Python 3.10+. Handled with a try/except ImportError that returns `[]`.

## Environment Variables

All secrets in `.env` (gitignored):

```
ANTHROPIC_API_KEY      — Anthropic API key (use the "my-second-key" ending EAAA)
CALLMEBOT_PHONE        — WhatsApp phone number with country code, no + (e.g. 14388850126)
CALLMEBOT_APIKEY       — CallMeBot API key (activate by messaging +34 644 59 79 13 on WhatsApp)
GMAIL_USER             — Gmail address (dr.siyaoshao@gmail.com)
GMAIL_APP_PASS         — Gmail App Password (not the account password)
NOTIFY_EMAIL           — Destination email for alerts and digests
```

## Running Locally

This app runs on **port 8000**. If running a second FastAPI app on the same machine, use a different port:

```bash
uvicorn main:app --reload --port 8000          # this app
uvicorn other_app:app --reload --port 8001     # second app
```

## Background Service (macOS)

The agent runs as a LaunchAgent — starts on login, restarts on crash, binds to port 8000.

```bash
# Start
launchctl load ~/Library/LaunchAgents/com.siyaoshao.vcjobagent.plist

# Stop
launchctl unload ~/Library/LaunchAgents/com.siyaoshao.vcjobagent.plist

# Logs
tail -f ~/job-agent/agent.log
```

## Health Monitor

`health_monitor.py` polls `/api/scrape-status` every 30 min for 24 hours and writes a structured
log to `health_monitor.log`. Detects whether scheduled scrapes fire and complete successfully.

```bash
python3 health_monitor.py
# Writes verdict (PASS / PARTIAL / FAIL) to health_monitor.log
```

`tdk_check.py` is a quicker standalone check — scrapes TDK Ventures and scores with Claude to
verify the full pipeline is working end-to-end.

```bash
python3 tdk_check.py
# Output written to tdk_healthcheck.log
```

## Adding Target Firms

Edit `TARGET_FIRM_URLS` in `config.py`:

```python
{"firm": "Lux Capital", "url": "https://www.luxcapital.com/careers"},
```

The scraper visits each URL, finds investor-role links, and returns up to 20 jobs per page.

## Backlog

### [BACKLOG] Nginx reverse proxy for multi-app hosting
Currently using separate ports (8000, 8001) when running two FastAPI apps on the same machine.
**Future improvement:** nginx reverse proxy so both apps are reachable on port 80, with a single
SSL termination point.
- Route `/jobs/` → job-agent on 8000
- Route `/other/` → second app on 8001
- Enables HTTPS via a single cert (Let's Encrypt / certbot)
- Useful when sharing URLs externally or deploying to a VPS
