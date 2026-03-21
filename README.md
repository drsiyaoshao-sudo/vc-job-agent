# VC Job Agent

A personal AI-powered job search agent built for **Dr. Siyao Shao**, targeting four primary role types: VC/CVC investor, founding engineer, principal research engineer, and FAE/solutions engineer. It scrapes job boards 4× daily, scores every listing against a deep-tech profile using **Claude Opus 4.6**, and delivers smart notifications via WhatsApp and email.

## Features

- **Automated scraping** — four-stage pipeline runs 4× daily (see [Scraping Pipeline](#scraping-pipeline))
- **AI-powered scoring** — Claude Opus 4.6 scores each job 0–100 with pros, cons, and tailored application tips (see [Score Logic](#score-logic))
- **Smart notifications**
  - Score ≥ 90 → instant WhatsApp message (CallMeBot)
  - Score ≥ 75 → instant email alert (Gmail SMTP)
  - Every Monday 8 AM → weekly digest email
  - Every day 8 AM → health check email confirming the agent is running
- **Web dashboard** — browse jobs by score, source, and status; filter and sort in one click
- **Application tracker** — track every application through reviewing → applied → interview → offer
- **Always-on** — runs as a macOS LaunchAgent; auto-starts on login, auto-restarts on crash

## Scraping Pipeline

Each scheduled run executes five stages in order, with a hard cap of **20 jobs per source/query** to control scoring costs and keep runs under 5 minutes. Direct VC/CVC firm pages run **first** — the highest-signal source for roles that match the target profile exactly.

### Stage 1 — Direct VC/CVC firm career pages (`scrapers/vc_boards.py`)

Visits each firm URL in `TARGET_FIRM_URLS` in `config.py` directly. These are known target firms — roles here have the highest alignment with the candidate profile.

| Category | Firms |
|----------|-------|
| **CVC — deep-tech / hardware / AI** | TDK Ventures, Samsung Next, Panasonic Ventures, Shell Ventures, Honeywell Ventures, ABB Technology Ventures, Qualcomm Ventures, Bosch Careers, Siemens Next47 |
| **Deep-tech / hardware VC** | DCVC, In-Q-Tel, Lux Capital, Eclipse Ventures, Root Ventures, Prelude Ventures, Obvious Ventures |
| **Climate / energy VC** | Energy Impact Partners, Congruent Ventures, Clean Energy Ventures, Chrysalix Energy VC |
| **Canada-based** | BDC Capital, Real Ventures, Inovia Capital, MaRS Discovery District |

Source tag: `direct` · Results per firm: **20 max**

### Stage 2 — Investor portfolio job boards (`scrapers/vc_boards.py`)

VC-curated boards where portfolio companies post roles directly. High signal for founding engineer, staff engineer, research engineer, and FAE/solutions roles at Seed–Series B companies.

| Board | Focus |
|-------|-------|
| Work at a Startup (YC) | YC portfolio — largest curated early-stage board |
| a16z Jobs | Andreessen Horowitz portfolio |
| First Round Jobs | First Round Capital portfolio |
| Sequoia Jobs | Sequoia Capital portfolio |
| Greylock Jobs | Greylock portfolio |
| Initialized Capital Jobs | Initialized Capital portfolio |
| Lux Capital Talent | Lux Capital portfolio (deep-tech) |
| Climatebase | Climate tech roles across VCs |
| MCJ Collective | Climate / energy startup roles |
| Hardware Club Jobs | Hardware-focused startup roles |

Source tag: `investor_board` · Results per board: **20 max**

### Stage 3 — LinkedIn / Indeed (`scrapers/jobspy.py`)

Searches LinkedIn and Indeed using 26 queries covering all 4 target role types. Requires Python 3.10+; runs via `jobspy310` conda env subprocess on Python 3.9.

**VC / CVC investor roles (10 queries):**
```
venture capital investor deep tech
venture capital partner hardware AI
CVC investor technology
corporate venture capital associate
deep tech venture investor
investment partner climate tech
hardware venture capital principal
venture capital associate industrial
technology venture investor
venture principal AI hardware
```

**Founding / early-stage engineer — Seed–Series B (4 queries):**
```
founding engineer deep tech startup
founding engineer hardware AI series A
early stage engineer Series B startup
staff engineer hardware startup
```

**Principal / staff research engineer (4 queries):**
```
principal research engineer AI hardware
staff research engineer machine learning
lead research engineer edge AI embedded
research engineer MEMS sensor
```

**FAE / technical sales / solutions engineer (8 queries):**
```
technical sales engineer hardware AI
solutions engineer industrial IoT
sales engineer deep tech startup
technical account manager AI hardware
field application engineer semiconductor
field application engineer embedded AI
FAE hardware startup
application engineer MEMS IoT
```

Results per query: **20 max** · Source tag: `linkedin` / `indeed`

### Stage 4 — Wellfound (`scrapers/wellfound.py`)

Currently **disabled** — Cloudflare blocks automated access. Returns `[]`; kept in pipeline for future re-enablement.

### Stage 4b — VC job boards (`scrapers/vc_boards.py`)

Scrapes VC-focused job boards and visits each firm URL in `TARGET_FIRM_URLS` in `config.py`.

**Job boards:**

| Board | URL |
|-------|-----|
| jobs.vc | https://jobs.vc |

**Target firms (24 firms):**

| Category | Firms |
|----------|-------|
| **CVC — deep-tech / hardware / AI** | TDK Ventures, Samsung Next, Panasonic Ventures, Shell Ventures, Honeywell Ventures, ABB Technology Ventures, Qualcomm Ventures, Bosch Careers, Siemens Next47 |
| **Deep-tech / hardware VC** | DCVC, In-Q-Tel, Lux Capital, Eclipse Ventures, Root Ventures, Prelude Ventures, Obvious Ventures |
| **Climate / energy VC** | Energy Impact Partners, Congruent Ventures, Clean Energy Ventures, Chrysalix Energy VC |
| **Canada-based** | BDC Capital, Real Ventures, Inovia Capital, MaRS Discovery District |

Keyword filter covers all 4 target role types + EIR (not just VC titles). Results per firm: **20 max** · Source tag: `direct`

### Stage 5 — Gmail LinkedIn job alerts (`scrapers/gmail_alerts.py`)

Reads LinkedIn job-alert emails via IMAP. Lookback: 7 days; cap: 50 emails, 20 jobs per email. Source tag: `gmail`

All stages deduplicate by URL. The same job found on multiple sources is stored only once.

---

## Score Logic

Every job is scored by **Claude Opus 4.6** with adaptive thinking against Dr. Shao's full profile. The model returns a structured JSON object with `score`, `headline`, `pros`, `cons`, and `key_requirements`. A keyword + TF-IDF fallback scorer runs automatically if the Claude API is unavailable (fallback-scored jobs are tagged `[fallback]` in the headline).

**Daily Claude API cap: 50 scoring calls per UTC day.** Already-scored jobs are never rescored by the automatic pipeline. The cap resets at midnight UTC.

### Target Role Types (all primary — score 65–100 when domain/seniority align)

| # | Role Type | Examples |
|---|-----------|----------|
| 1 | **VC/CVC investor or partner** | deep-tech, hardware, AI, climate; Associate → Partner |
| 2 | **Founding / staff engineer** | Seed–Series B deep-tech startups (hardware, AI, IoT, MEMS) |
| 3 | **Principal / lead research engineer** | MEMS, edge AI, embedded systems, industrial tech |
| 4 | **FAE / Solutions / Technical Sales Engineer** | hardware, semiconductor, industrial IoT, AI |

**Also primary:** EIR (Entrepreneur in Residence) at VC/CVC funds and deep-tech accelerators/studios.

### Scoring Rubric (0–100)

| Score | Label | Criteria |
|-------|-------|----------|
| **85–100** | Excellent | Squarely fits one of the 4 target types; domain and seniority align |
| **65–84** | Good | Fits a target type with minor gaps (domain, seniority, or location); EIR at VC/CVC |
| **45–64** | Moderate | Adjacent / transferable: tech scout, product engineer, corporate R&D, EIR at non-VC |
| **20–44** | Weak | Generic engineering without deep-tech or startup angle |
| **0–19** | Not relevant | Unrelated to any of the 4 target types |

### Big-Tech Penalty

Roles at large established companies (Google, Meta, Amazon, Apple, Netflix, Microsoft, OpenAI, Anthropic, Nvidia, Intel, Qualcomm, Samsung, Tesla, etc.) score **20–35 points lower** than an equivalent role at a startup or VC firm. These companies are not aligned with an early-stage, hardware-first, deep-tech profile. The fallback scorer applies a 55% score reduction.

### Notification thresholds

| Score | Action |
|-------|--------|
| ≥ 90 | Instant WhatsApp alert via CallMeBot |
| ≥ 75 | Instant email alert via Gmail |
| Any | Stored in dashboard for manual review |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| AI scoring | Claude Opus 4.6 (Anthropic) with adaptive thinking |
| Backend | Python · FastAPI · SQLModel · SQLite |
| Scraping | jobspy (LinkedIn/Indeed) · httpx · BeautifulSoup |
| Scheduling | APScheduler (4×/day scrape, daily health check, weekly digest) |
| Notifications | CallMeBot WhatsApp API · Gmail SMTP |
| Frontend | Jinja2 · Tailwind CSS · Alpine.js |

## Project Structure

```
job-agent/
├── main.py              # FastAPI app + APScheduler
├── config.py            # Profile, SEARCH_QUERIES, TARGET_FIRM_URLS, thresholds
├── database.py          # SQLite schema (SQLModel) + alter_db() migrations
├── scorer.py            # Claude Opus 4.6 scoring + daily cap enforcement
├── scorer_fallback.py   # Keyword + TF-IDF fallback scorer (no API)
├── profile.py           # Runtime profile loader
├── notifier.py          # WhatsApp + email notifications
├── health_monitor.py    # 24-hour polling monitor (PASS/PARTIAL/FAIL)
├── tdk_check.py         # Quick end-to-end health check
├── scrapers/
│   ├── jobspy.py        # LinkedIn & Indeed (via python-jobspy)
│   ├── wellfound.py     # Wellfound (disabled — Cloudflare)
│   ├── vc_boards.py     # VC boards + direct firm career pages
│   └── gmail_alerts.py  # Gmail IMAP LinkedIn alert emails
└── templates/           # Jinja2 HTML templates
    ├── base.html
    ├── dashboard.html
    ├── job_detail.html
    ├── settings.html
    └── tracker.html
```

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
ANTHROPIC_API_KEY=...        # platform.anthropic.com

# WhatsApp (score ≥ 90)
# Activate: send "I allow callmebot to send me messages" to +34 644 59 79 13 on WhatsApp
CALLMEBOT_PHONE=1XXXXXXXXXX
CALLMEBOT_APIKEY=...

# Email (score ≥ 75, daily check-in, weekly digest)
# App password: myaccount.google.com → Security → App Passwords
GMAIL_USER=you@gmail.com
GMAIL_APP_PASS=xxxx xxxx xxxx xxxx
NOTIFY_EMAIL=you@gmail.com
```

**Credential backup rule:** After updating `.env`, immediately mirror to the master key store:

```bash
cp ~/job-agent/.env ~/.job-agent-keys && chmod 600 ~/.job-agent-keys
```

Before any branch switch, verify `.env` is intact:

```bash
diff ~/job-agent/.env ~/.job-agent-keys
# If empty/missing: cp ~/.job-agent-keys ~/job-agent/.env
```

### 3. Run (development)

```bash
cd ~/job-agent
uvicorn main:app --reload
```

Open **http://localhost:8000**

### 4. Run as a background service (auto-start on login)

```bash
launchctl load ~/Library/LaunchAgents/com.siyaoshao.vcjobagent.plist
```

---

## Schedule

| Time | Action |
|------|--------|
| 03:00, 10:00, 17:00, 21:00 ET | Scrape all sources + score new jobs with Claude |
| Daily 08:00 ET | Health check email |
| Monday 08:00 ET | Weekly digest email |

---

## CLI Reference — Diagnostics & Fixes

All commands run from `~/job-agent` with the conda base env active (Python 3.9).

### Service management

```bash
# Start background service
launchctl load ~/Library/LaunchAgents/com.siyaoshao.vcjobagent.plist

# Stop background service
launchctl unload ~/Library/LaunchAgents/com.siyaoshao.vcjobagent.plist

# Restart (required after editing main.py, scorer.py, or config.py)
launchctl unload ~/Library/LaunchAgents/com.siyaoshao.vcjobagent.plist
launchctl load  ~/Library/LaunchAgents/com.siyaoshao.vcjobagent.plist

# Check if service is running
launchctl list | grep vcjobagent

# View live logs
tail -f ~/job-agent/agent.log

# View last 100 lines of logs
tail -100 ~/job-agent/agent.log
```

### API key / credential checks

```bash
# Verify ANTHROPIC_API_KEY is valid (expects HTTP 200, not 401)
source ~/job-agent/.env && \
  curl -s -o /dev/null -w "%{http_code}" \
    https://api.anthropic.com/v1/models \
    -H "x-api-key: $ANTHROPIC_API_KEY" \
    -H "anthropic-version: 2023-06-01"
# Should print: 200

# Restore .env from master backup if keys are missing
cp ~/.job-agent-keys ~/job-agent/.env

# Mirror current .env to master backup
cp ~/job-agent/.env ~/.job-agent-keys && chmod 600 ~/.job-agent-keys
```

### Database inspection

```bash
# Count total jobs by status
sqlite3 ~/job-agent/jobs.db "SELECT status, COUNT(*) FROM job GROUP BY status;"

# Count scored vs unscored jobs
sqlite3 ~/job-agent/jobs.db \
  "SELECT CASE WHEN match_score IS NULL THEN 'unscored' ELSE 'scored' END AS state, COUNT(*) FROM job GROUP BY state;"

# Count fallback-scored jobs (Claude API was unavailable when these were scored)
sqlite3 ~/job-agent/jobs.db \
  "SELECT COUNT(*) FROM job WHERE match_headline LIKE '%[fallback]%';"

# How many Claude API calls used today (UTC)
sqlite3 ~/job-agent/jobs.db \
  "SELECT COUNT(*) FROM job WHERE scored_at >= date('now') AND (match_headline NOT LIKE '%[fallback]%');"

# Top 20 jobs by score
sqlite3 ~/job-agent/jobs.db \
  "SELECT match_score, title, company FROM job WHERE match_score IS NOT NULL ORDER BY match_score DESC LIMIT 20;"

# Jobs added in the last 24 hours
sqlite3 ~/job-agent/jobs.db \
  "SELECT COUNT(*) FROM job WHERE scraped_at >= datetime('now', '-1 day');"

# Lifetime job count
sqlite3 ~/job-agent/jobs.db \
  "SELECT total_jobs_ever FROM usersettings LIMIT 1;"
```

### Rescoring fallback jobs

Fallback-scored jobs were scored without Claude (API unavailable). Reset them so the next scheduled run rescores with Claude:

```bash
# Step 1 — Preview: how many fallback jobs exist
sqlite3 ~/job-agent/jobs.db \
  "SELECT COUNT(*) FROM job WHERE match_headline LIKE '%[fallback]%';"

# Step 2 — Reset fallback jobs to unscored (sets match_score = NULL)
sqlite3 ~/job-agent/jobs.db \
  "UPDATE job SET match_score=NULL, match_headline=NULL, match_pros=NULL, match_cons=NULL,
   key_requirements=NULL, scored_at=NULL
   WHERE match_headline LIKE '%[fallback]%';"

# Step 3 — Trigger scoring via the web UI "Score Unscored" button,
#           or wait for the next scheduled run (03:00/10:00/17:00/21:00 ET).
#           Up to 50 jobs are scored per run (daily Claude cap).
```

### Triggering actions manually

Use the web dashboard sidebar buttons, or call the API endpoints directly:

```bash
BASE=http://localhost:8000

# Trigger a scrape run
curl -s -X POST $BASE/api/scrape

# Score all unscored jobs (up to today's remaining Claude cap)
curl -s -X POST $BASE/api/score-unscored

# Check Gmail alerts
curl -s -X POST $BASE/api/check-gmail

# Flush low-score / stale jobs (deletes 'new' status jobs scored <50 or scraped >14 days ago)
curl -s -X POST $BASE/api/flush-low-score

# Force re-score a specific job (bypasses cap, always uses Claude)
curl -s -X POST $BASE/api/rescore/JOB_ID
```

### Health checks

```bash
# Quick end-to-end check: scrape TDK Ventures + score with Claude
cd ~/job-agent && python3 tdk_check.py

# Full 24-hour pipeline monitor (PASS / PARTIAL / FAIL verdict)
cd ~/job-agent && python3 health_monitor.py

# View health monitor log
tail -50 ~/job-agent/health_monitor.log
```

### Common fixes

**App won't start / port already in use:**
```bash
lsof -i :8000        # find the PID
kill -9 <PID>
launchctl load ~/Library/LaunchAgents/com.siyaoshao.vcjobagent.plist
```

**Scoring stopped (API key invalid):**
```bash
# 1. Check logs for 401 errors
grep -i "401\|authentication\|could not resolve" ~/job-agent/agent.log | tail -20

# 2. Regenerate key at platform.anthropic.com and update .env
# 3. Back up immediately
cp ~/job-agent/.env ~/.job-agent-keys && chmod 600 ~/.job-agent-keys
# 4. Restart service
launchctl unload ~/Library/LaunchAgents/com.siyaoshao.vcjobagent.plist
launchctl load  ~/Library/LaunchAgents/com.siyaoshao.vcjobagent.plist
```

**All jobs scored with fallback (check if Claude API was down):**
```bash
grep "\[scorer\] Claude failed" ~/job-agent/agent.log | tail -20
```

**Daily cap already hit, need to score more today:**
The cap resets at midnight UTC. Wait for the next run (03:00/10:00/17:00/21:00 ET) or use the `/api/rescore/JOB_ID` endpoint to force-score individual high-priority jobs.

---

## Customise

### Add target VC firms

Edit `TARGET_FIRM_URLS` in `config.py`:

```python
{"firm": "Lux Capital", "url": "https://www.luxcapital.com/careers"},
```

Restart the service after saving.

### Change notification thresholds

```python
# notifier.py
SCORE_WHATSAPP = 90   # WhatsApp alert threshold
SCORE_EMAIL    = 75   # Email alert threshold
```

### Change daily Claude scoring cap

```python
# scorer.py
DAILY_CLAUDE_CAP = 50  # Max Claude API scoring calls per UTC day
```

---

## Notification Examples

**WhatsApp alert (score ≥ 90)**
```
🌟🌟 TOP MATCH — 93/100

*Principal, Deep Tech Investments*
🏢 Samsung Next
📍 Remote
💡 Strong CVC deep-tech role — hardware + AI focus

🔗 https://...
```

**Daily health check email** — confirms agent is running, shows new jobs found in the last 24h and active application pipeline.

**Weekly digest** — every Monday, a full summary of top matches and pipeline status.

---

Built with [Claude](https://anthropic.com) · [FastAPI](https://fastapi.tiangolo.com) · [jobspy](https://github.com/Bunsly/JobSpy)
