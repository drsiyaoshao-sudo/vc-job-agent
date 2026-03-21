# Job Search Agent — Developer Notes

## Design Philosophy

**The system reads the candidate. The candidate does not fit the system.**

The agent starts from the candidate's actual credentials and asks *which roles fit them*, scoring
each listing accordingly. Three principles follow from this:

1. **Profile is runtime, not compile-time.** `resume_text` and `job_anticipations` load fresh from
   the DB on every scoring call. Edit targets in the `/settings` UI; the next scrape reflects it.
   No redeploy, no file edit.

2. **Scoring rubric is readable, not hardcoded.** Claude's prompt uses the candidate's own stated
   goals and background — a strong match for one person may be irrelevant for another. The keyword
   fallback mirrors the same logic with zero API cost.

3. **Efficiency is first-class.** 20-job cap per scraper. Keyword fallback runs in microseconds.
   Flush removes low-score/stale noise automatically. SQLite + one process — deployable anywhere.

---

## Architecture

```
main.py               — FastAPI app + APScheduler (scrape 4×/day, health check daily, digest weekly)
config.py             — Default profile template, SEARCH_QUERIES, TARGET_FIRM_URLS, thresholds
database.py           — SQLModel: Job + UserSettings; upsert_job(); alter_db() for migrations
scorer.py             — Claude Opus 4.6 scoring via messages.parse() + Pydantic JobMatchResult
                        Falls back to scorer_fallback.py on any API failure
scorer_fallback.py    — Keyword + TF-IDF fallback scorer (no API, always works)
profile.py            — Runtime profile loader: get_profile_text(), get_search_queries()
notifier.py           — WhatsApp (CallMeBot), Gmail SMTP, health-check and weekly digest emails
scrapers/
  jobspy.py           — LinkedIn/Indeed via python-jobspy (requires Python 3.10+; subprocess fallback)
  wellfound.py        — Disabled (Cloudflare blocks scraping); returns []
  vc_boards.py        — jobs.vc + NFX + VC Careers + direct firm career pages
  gmail_alerts.py     — Gmail IMAP: reads LinkedIn job alert emails, extracts listings
health_monitor.py     — 24-hour polling; writes PASS/PARTIAL/FAIL to health_monitor.log
tdk_check.py          — Standalone end-to-end check: scrapes one firm + scores with Claude
```

---

## Setup for a New User

1. Copy `.env.example` → `.env` and fill in your API keys (see Environment Variables below)
2. Run `uvicorn main:app --reload` and open `http://localhost:8000`
3. Go to `/settings` and paste your resume, set your target titles and anticipations
4. Click **Scrape Jobs** in the sidebar to run the first scrape
5. Add specific firm career pages you want monitored to `TARGET_FIRM_URLS` in `config.py`

The `config.py` values are only used on first run (when the DB is empty). After that, everything
is controlled via the `/settings` UI — `config.py` just provides the initial defaults.

---

## Plan → Execute → Operate Workflow

### Plan (before any change)

Ask: *does this belong in the candidate's profile (runtime, DB) or in the scraper/scorer (code)?*

- **Preference shift** (new role type, domain, location) → `/settings` UI. No code change.
- **New scrape source** → add URL to `TARGET_FIRM_URLS` in `config.py`.
- **Scoring calibration** → edit `TITLE_SIGNALS` / `DOMAIN_GROUPS` in `scorer_fallback.py`.
  Rescore via sidebar "Score Unscored" button.
- **Schema change** → add column to `UserSettings` or `Job` in `database.py`, add migration in
  `alter_db()`, call `alter_db()` inside `create_db()`.

### Execute (making the change)

1. All Python files must start with `from __future__ import annotations` (Python 3.9 constraint).
2. Never bypass `alter_db()` for schema changes — existing installs must migrate without data loss.
3. Every new scraper must deduplicate by URL and enforce the 20-job hard cap.
4. Claude scorer always has a fallback path — never let an API failure block a scrape run.
5. Restart the app after any `main.py` or `scorer.py` change:
   ```bash
   # macOS LaunchAgent
   launchctl unload ~/Library/LaunchAgents/com.jobagent.plist
   launchctl load  ~/Library/LaunchAgents/com.jobagent.plist
   # or simply restart uvicorn
   ```

### Operate (day-to-day)

| Action | How |
|--------|-----|
| Update resume / targets | `/settings` UI → Save → takes effect on next score call |
| Trigger scrape manually | Sidebar **Scrape Jobs** button |
| Re-score existing jobs | Sidebar **Score Unscored** button |
| Check Gmail alerts | Sidebar **Check Gmail** button |
| Remove low-signal noise | Sidebar **Flush Low-Score** — deletes `new` jobs scored <50 or scraped >14 days ago |
| Add a target firm | `TARGET_FIRM_URLS` in `config.py`, restart app |
| View lifetime job count | Dashboard **Ever Found** stat card (persists across flushes) |

---

## Scraping Pipeline

Each scheduled scrape (4×/day) runs four stages:

1. **LinkedIn / Indeed** (`scrapers/jobspy.py`)
   - Searches via `SEARCH_QUERIES` from `config.py` (overridden by `UserSettings.target_titles`)
   - Hard cap: 20 results per query
   - Requires Python 3.10+; runs via a `jobspy310` conda env subprocess on Python 3.9

2. **Wellfound** (`scrapers/wellfound.py`)
   - Currently disabled — Cloudflare blocks access. Returns `[]`.

3. **VC boards + direct firm pages** (`scrapers/vc_boards.py`)
   - jobs.vc, NFX Guild, Venture Capital Careers
   - Direct career pages in `TARGET_FIRM_URLS`
   - `INVESTOR_KEYWORDS` filter covers investor, engineering, research, and FAE/sales titles
   - Hard cap: 20 jobs per source/firm

4. **Gmail LinkedIn alerts** (`scrapers/gmail_alerts.py`)
   - IMAP to Gmail; reads LinkedIn jobs-noreply emails
   - Lookback: 7 days; cap: 50 emails, 20 jobs per email

All stages deduplicate by URL. `upsert_job()` increments `UserSettings.total_jobs_ever` on each insertion.

---

## Scoring

### Claude scorer (`scorer.py`)
- Model: `claude-opus-4-6` with `thinking={"type": "adaptive"}`
- Structured output via `client.messages.parse()` + Pydantic `JobMatchResult`
- Each job: `score` (0–100), `headline`, `pros`, `cons`, `key_requirements`
- Profile loaded fresh from `UserSettings` on every call — edits take immediate effect
- Any failure → automatic fallback to keyword scorer

### Keyword fallback scorer (`scorer_fallback.py`)
- No API dependency — always runs
- Three layers: title keywords (0–45 pts) + domain keywords (0–35 pts) + TF-IDF cosine (0–20 pts)
- Tuned for VC/investor, founding engineer, research engineer, and FAE/sales role buckets by default
- Customise `TITLE_SIGNALS` and `DOMAIN_GROUPS` to match a different candidate profile

### Score rubric

| Range  | Label        | Meaning |
|--------|--------------|---------|
| 85–100 | Excellent    | Squarely fits stated target; domain and seniority align |
| 65–84  | Good         | Fits target with minor gaps in domain, seniority, or location |
| 45–64  | Moderate     | Adjacent / transferable; possible pivot toward target |
| 20–44  | Weak         | Mostly irrelevant or significantly off seniority |
| 0–19   | Not relevant | Unrelated to candidate's background or goals |

### Notification thresholds
- Score ≥ 90 → instant WhatsApp (CallMeBot)
- Score ≥ 75 → instant email (Gmail SMTP)

---

## Database

`UserSettings` — single-row config. Key runtime fields:

| Field | Purpose |
|-------|---------|
| `resume_text` | Full resume; sent to Claude and used for TF-IDF fallback |
| `target_titles` | JSON list; generates LinkedIn/Indeed search queries |
| `job_anticipations` | Free text; appended to Claude system prompt |
| `total_jobs_ever` | Lifetime counter; survives flush operations |

Schema migrations: add column + default in `alter_db()` in `database.py`. Never use ORM auto-migrate.

---

## Python Version Constraint

Runs on **Python 3.9+**. Every file must include:

```python
from __future__ import annotations
```

`python-jobspy` requires Python 3.10+ → isolated via `jobspy310` conda env and called by subprocess.

---

## Environment Variables

```
ANTHROPIC_API_KEY      — Anthropic API key
CALLMEBOT_PHONE        — WhatsApp phone with country code, no +
CALLMEBOT_APIKEY       — CallMeBot API key
GMAIL_USER             — Gmail address
GMAIL_APP_PASS         — Gmail App Password
NOTIFY_EMAIL           — Destination for alerts and digests
```

---

## Background Service (macOS)

```bash
launchctl load   ~/Library/LaunchAgents/com.jobagent.plist   # start
launchctl unload ~/Library/LaunchAgents/com.jobagent.plist   # stop
tail -f ~/job-agent/agent.log                                 # logs
```

App runs on **port 8000** by default.

---

## Adding Target Firms

```python
# config.py
TARGET_FIRM_URLS = [
    {"firm": "Acme Ventures", "url": "https://acmeventures.com/careers"},
]
```

The scraper visits the URL, follows links matching `INVESTOR_KEYWORDS`, returns up to 20 jobs.
