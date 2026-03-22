# Job Search Agent — Master Document

## Design Philosophy

**The system reads the candidate. The candidate does not fit the system.**

Most job boards ask you to compress yourself into a category. This agent inverts that contract:
it starts from Siyao's actual credentials — deep-tech PhD, MEMS researcher, TandemLaunch EIR,
hardware startup operator — and asks *which roles fit him*, scoring each one accordingly.

Three operating principles flow from this:

**1. Profile is runtime, not compile-time.**
`resume_text` and `job_anticipations` load fresh from the DB on every scoring call. Edit targets
in the UI; the next scrape reflects the change immediately. No redeploy, no file edit.

**2. Scoring rubric is readable business logic.**
The 4-bucket rubric lives in plain English inside the Claude system prompt and in
`scorer_fallback.py`. When priorities shift (EIR is a good role; FAE is a primary target, not
adjacent), one line changes and the entire scoring pipeline updates.

**3. Efficiency is first-class.**
20-job hard cap per scraper. Keyword fallback runs in microseconds with no API cost. Flush
removes low-score and stale jobs automatically. `total_jobs_ever` preserves lifetime history
without keeping junk rows. SQLite + one process + no vector DB — stays deployable on a MacBook.

---

## Target Role Types

All four are primary targets — scored 65–100 when domain/seniority align:

| # | Role Type | Examples |
|---|-----------|---------|
| 1 | **VC/CVC investor or partner** | deep-tech, hardware, AI, climate; Associate → Partner |
| 2 | **Founding / staff engineer** | Seed–Series B deep-tech startups (hardware, AI, IoT, MEMS) |
| 3 | **Principal / lead research engineer** | MEMS, edge AI, embedded systems, industrial tech |
| 4 | **FAE / Solutions / Technical Sales Engineer** | hardware, semiconductor, industrial IoT, AI |

**Also primary:** EIR (Entrepreneur in Residence) at VC/CVC funds and deep-tech accelerators/studios.

---

## Architecture

```
main.py               — FastAPI app; scheduling via system cron (no in-process scheduler)
config.py             — Profile, SEARCH_QUERIES, WELLFOUND_QUERIES, TARGET_FIRM_URLS, thresholds
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
health_monitor.py     — 24-hour polling script; writes PASS/PARTIAL/FAIL to health_monitor.log
tdk_check.py          — Standalone end-to-end health check: scrapes TDK Ventures + scores
```

---

## Plan → Execute → Operate Workflow

### Plan (before any change)

Ask: *does this belong in the candidate's profile (runtime, DB) or in the scraper/scorer architecture (code)?*

- **Preference shift** (new role type, domain, seniority level, location) → edit `UserSettings` via `/settings` UI. No code change needed.
- **New scrape source** → add URL to `TARGET_FIRM_URLS` in `config.py`. The existing pipeline picks it up.
- **Scoring calibration** → edit `TITLE_SIGNALS` / `DOMAIN_GROUPS` in `scorer_fallback.py` and the rubric in `scorer.py`. Rescore via sidebar "Score Unscored" button.
- **Schema change** → add column to `UserSettings` or `Job` in `database.py`, add migration in `alter_db()`, call `alter_db()` inside `create_db()`.

### Execute (making the change)

1. All Python files must start with `from __future__ import annotations` (Python 3.9 constraint).
2. Never bypass `alter_db()` for schema changes — existing installs must migrate without data loss.
3. Every new scraper must deduplicate by URL and enforce the 20-job hard cap.
4. Claude scorer always has a fallback path — never let an API failure block a scrape run.
5. Restart the LaunchAgent after any `main.py` or `scorer.py` change (in-memory state resets):
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.siyaoshao.vcjobagent.plist
   launchctl load  ~/Library/LaunchAgents/com.siyaoshao.vcjobagent.plist
   ```

### Operate (day-to-day)

| Action | How |
|--------|-----|
| Update resume / targets | `/settings` UI → save → takes effect on next score call |
| Trigger scrape manually | Sidebar "Scrape Jobs" button |
| Re-score existing jobs | Sidebar "Score Unscored" button |
| Check Gmail alerts | Sidebar "Check Gmail" button |
| Remove low-signal noise | Sidebar "Flush Low-Score" button — deletes `status=new` jobs scored <50 or scraped >14 days ago |
| Add a target firm | `TARGET_FIRM_URLS` in `config.py`, restart app |
| View lifetime job count | Dashboard "Ever Found" stat card (persists across flushes) |

---

## Scraping Pipeline

Each scheduled scrape (4×/day) runs four stages in order:

1. **LinkedIn / Indeed** (`scrapers/jobspy.py`)
   - Searches via `SEARCH_QUERIES` in `config.py` (covers all 4 role types)
   - Hard cap: 20 results per query
   - Requires Python 3.10+; runs via `jobspy310` conda env subprocess on Python 3.9

2. **Wellfound** (`scrapers/wellfound.py`)
   - Currently disabled — Cloudflare blocks automated access
   - Returns `[]`; kept in pipeline for future re-enablement

3. **VC boards + direct firm pages** (`scrapers/vc_boards.py`)
   - jobs.vc, NFX Guild, Venture Capital Careers boards
   - Direct career pages for all firms in `TARGET_FIRM_URLS`
   - `INVESTOR_KEYWORDS` filter covers all 4 role types + EIR (not just VC titles)
   - Hard cap: 20 jobs per source/firm

4. **Gmail LinkedIn alerts** (`scrapers/gmail_alerts.py`)
   - IMAP to `imap.gmail.com:993`; reads emails from LinkedIn jobs-noreply addresses
   - Lookback: 7 days; cap: 50 emails, 20 jobs per email

All stages deduplicate by URL. `upsert_job()` increments `UserSettings.total_jobs_ever` on each new insertion.

---

## Scoring

### Claude scorer (`scorer.py`)
- Model: `claude-opus-4-6` with `thinking={"type": "adaptive"}`
- Structured output via `client.messages.parse()` + Pydantic `JobMatchResult`
- Each job: `score` (0–100), `headline`, `pros`, `cons`, `key_requirements`
- Description truncated to 6,000 characters; profile loaded fresh from `UserSettings` per call
- Any failure → automatic fallback to keyword scorer

### Keyword fallback scorer (`scorer_fallback.py`)
- No API dependency — always runs
- Three layers: title keywords (0–45 pts) + domain keywords (0–35 pts) + TF-IDF cosine (0–20 pts)
- MD5-keyed vector cache per unique profile text

### Score rubric

| Range  | Label        | Meaning |
|--------|--------------|---------|
| 85–100 | Excellent    | Squarely fits one of the 4 target types; domain and seniority align |
| 65–84  | Good         | Fits a target type with minor gaps; EIR at VC/CVC fund or deep-tech studio |
| 45–64  | Moderate     | Adjacent / transferable: tech scout, product engineer, corporate R&D, EIR at non-VC |
| 20–44  | Weak         | Generic engineering without deep-tech or startup angle |
| 0–19   | Not relevant | Unrelated to Siyao's background |

### Notification thresholds
- Score ≥ 90 → instant WhatsApp (CallMeBot)
- Score ≥ 75 → instant email (Gmail SMTP)

---

## Database

`UserSettings` — single-row config table. Fields that drive runtime behavior:

| Field | Purpose |
|-------|---------|
| `resume_text` | Full resume; sent to Claude and used by fallback TF-IDF |
| `target_titles` | JSON list; generates search queries |
| `job_anticipations` | Free text; appended to Claude system prompt |
| `total_jobs_ever` | Lifetime insertion counter; survives flush operations |

Schema migrations: add column + default in `alter_db()` inside `database.py`, never via ORM auto-migrate.

---

## Python Version Constraint

Runs on **Python 3.9.7 (Anaconda base)**. Every file must include:

```python
from __future__ import annotations
```

at the top. `str | None` union syntax is a runtime error on 3.9 without it.

`python-jobspy` requires Python 3.10+ → runs via `~/opt/anaconda3/envs/jobspy310/bin/python` subprocess.

---

## Environment Variables

Secrets in `.env` (gitignored):

```
ANTHROPIC_API_KEY      — Anthropic API key
CALLMEBOT_PHONE        — WhatsApp phone with country code, no +
CALLMEBOT_APIKEY       — CallMeBot API key
GMAIL_USER             — Gmail address
GMAIL_APP_PASS         — Gmail App Password
NOTIFY_EMAIL           — Destination for alerts and digests
```

---

## Credential Management Rule

**The `.env` file in the repo is ephemeral. The canonical key store is `~/.job-agent-keys`.**

### Rules (apply every time keys are touched)

1. **After setting or updating any key in `.env`, immediately mirror it to the master file:**
   ```bash
   cp ~/job-agent/.env ~/.job-agent-keys
   chmod 600 ~/.job-agent-keys
   ```

2. **Before starting work on any branch or after any `git checkout`, verify `.env` is intact:**
   ```bash
   diff ~/job-agent/.env ~/.job-agent-keys
   ```
   If `.env` is empty or missing keys, restore:
   ```bash
   cp ~/.job-agent-keys ~/job-agent/.env
   ```

3. **Never carry `.env` across repos.** Each repo cloned from this one starts with an empty
   `.env.example`. Keys from `~/.job-agent-keys` are copied in manually after clone — never
   assumed to exist.

4. **`~/.job-agent-keys` is never committed, never shared, never referenced in code.**
   It lives outside all git working trees. The repo's `.gitignore` already excludes `.env`;
   `~/.job-agent-keys` is outside the repo entirely.

### Why this rule exists

The Anthropic API key and Gmail App Password were lost when the repo `.env` was modified
during a branch comparison session. Because there was no out-of-repo backup, the keys had
to be regenerated. This rule prevents that from recurring.

---

## Background Service (macOS)

```bash
# Start
launchctl load ~/Library/LaunchAgents/com.siyaoshao.vcjobagent.plist

# Stop
launchctl unload ~/Library/LaunchAgents/com.siyaoshao.vcjobagent.plist

# Logs
tail -f ~/job-agent/agent.log
tail -f ~/job-agent/cron.log   # cron trigger confirmations
```

App runs on **port 8000**. Second app on same machine → use port 8001.

## Scheduling

Scrapes are triggered by **system cron**, not in-process APScheduler.
APScheduler's background thread was silently dying and missing scheduled slots.

```
crontab -e   # view/edit the schedule
```

Current schedule (all times ET / America/Toronto):

| Cron | Endpoint | Purpose |
|------|----------|---------|
| `0 3,10,17,21 * * *` | `POST /api/scrape` | Scrape + score 4×/day |
| `0 8 * * *` | `POST /api/health-check` | Daily health-check email |
| `0 8 * * 1` | `POST /api/weekly-report` | Monday digest email |

To change the schedule: `crontab -e`. To add a new HTTP-triggerable action, add a
`POST` endpoint in `main.py` and a corresponding cron line.

---

## Health Checks

```bash
# 24-hour pipeline monitor (PASS / PARTIAL / FAIL verdict)
python3 health_monitor.py

# Quick end-to-end check: scrape TDK Ventures + score with Claude
python3 tdk_check.py
```

---

## Adding Target Firms

Edit `TARGET_FIRM_URLS` in `config.py`:

```python
{"firm": "Lux Capital", "url": "https://www.luxcapital.com/careers"},
```

The scraper visits the URL, follows links matching `INVESTOR_KEYWORDS`, and returns up to 20 jobs.

---

## Backlog

### [BACKLOG] Nginx reverse proxy
Route `/jobs/` → port 8000 and a second app → port 8001 under a single SSL cert.
Useful for external sharing or VPS deployment.
