# VC Job Agent

A self-hosted AI-powered job search agent. It scrapes job boards 4× daily, scores every listing against your own profile using **Claude Opus 4.6**, and delivers smart notifications via WhatsApp and email. Configure your resume and target roles once via the web UI — Claude reads them fresh on every scoring run.

## Features

- **Automated scraping** — three-stage pipeline runs 4× daily (see [Scraping Pipeline](#scraping-pipeline))
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

Each scheduled run executes three stages in order, with a hard cap of **20 jobs per source/query** to control scoring costs and keep runs under 5 minutes.

### Stage 1 — LinkedIn major VC/CVC pages (`scrapers/jobspy.py`)

Searches LinkedIn and Indeed using the queries defined in `config.py` (`SEARCH_QUERIES`). Covers broad VC/CVC investor role searches across all companies.

```
"venture capital investor deep tech"
"CVC investor technology"
"hardware venture capital principal"
... (10 queries total)
```

Results per query: **20 max** · Source tag: `linkedin` / `indeed`

### Stage 2 — Direct company career pages (`scrapers/vc_boards.py`)

Visits each firm URL listed in `TARGET_FIRM_URLS` in `config.py` and extracts investor-relevant job postings directly from the firm's own career page. This catches roles that never appear on job boards.

```python
TARGET_FIRM_URLS = [
    {"firm": "Lux Capital",   "url": "https://www.luxcapital.com/careers"},
    {"firm": "DCVC",          "url": "https://www.dcvc.com/careers"},
]
```

Filters by investor keywords: `venture, investor, investment, associate, principal, partner, cvc, portfolio, analyst, sourcing`.

Results per firm: **20 max** · Source tag: `direct`

### Stage 3 — VC-specific job boards (`scrapers/vc_boards.py`, `scrapers/wellfound.py`)

Scrapes VC-focused job boards that aggregate investor roles across many firms.

| Board | URL |
|-------|-----|
| jobs.vc | https://jobs.vc |
| Wellfound | https://wellfound.com |

Results per board: **20 max** · Source tag: `jobs_vc` / `wellfound`

All three stages deduplicate by URL before storing to the database — the same job found on multiple sources is stored only once.

---

## Score Logic

Every job is scored by **Claude Opus 4.6** with adaptive thinking against Dr. Shao's full profile. The model returns a structured JSON object with `score`, `headline`, `pros`, `cons`, and `key_requirements`.

### Scoring Rubric (0–100)

| Score | Label | Criteria |
|-------|-------|----------|
| **85–100** | Excellent | VC/CVC investor or partner role squarely in deep-tech, hardware, climate, AI/ML, or industrial domains; seniority (Associate → Partner) fits his background |
| **65–84** | Good | VC/CVC role with a slightly different domain or seniority, but clearly leverages his technical due-diligence skills and founder experience |
| **45–64** | Moderate | Adjacent role — technology scout, EIR at a fund, corporate innovation/strategy — or a non-VC investor role that could pivot toward VC |
| **20–44** | Weak | Mostly irrelevant to a VC career; perhaps a deep-tech operating/engineering role |
| **0–19** | Not relevant | Unrelated to VC/investing or Dr. Shao's background entirely |

### What Claude weighs heavily

- Deep-tech investment thesis alignment (hardware, MEMS, edge AI, climate, industrial IoT)
- Seniority match (Associate → Principal → Partner)
- CVC vs. independent VC distinction (CVC valued for TDK, Samsung Next, Bosch Ventures, etc.)
- Founder/operator experience valued by the firm
- Geographic fit (remote-friendly or Montréal/North America/global)

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
| Scheduling | APScheduler |
| Notifications | CallMeBot WhatsApp API · Gmail SMTP |
| Frontend | Jinja2 · Tailwind CSS · Alpine.js |

## Project Structure

```
job-agent/
├── main.py              # FastAPI app + scheduler
├── config.py            # Profile, search terms, firm URLs
├── database.py          # SQLite schema (SQLModel)
├── scorer.py            # Claude API job scoring
├── notifier.py          # WhatsApp + email notifications
├── scrapers/
│   ├── jobspy.py        # LinkedIn & Indeed (via jobspy)
│   ├── wellfound.py     # Wellfound scraper
│   └── vc_boards.py     # VC-specific boards + direct firm pages
└── templates/           # Jinja2 HTML templates
    ├── dashboard.html
    ├── job_detail.html
    └── tracker.html
```

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

# WhatsApp (score > 90)
# Activate: send "I allow callmebot to send me messages" to +34 644 59 79 13 on WhatsApp
CALLMEBOT_PHONE=1XXXXXXXXXX
CALLMEBOT_APIKEY=...

# Email (score > 75, daily check-in, weekly digest)
# App password: myaccount.google.com → Security → App Passwords
GMAIL_USER=you@gmail.com
GMAIL_APP_PASS=xxxx xxxx xxxx xxxx
NOTIFY_EMAIL=you@gmail.com
```

### 3. Run

```bash
cd ~/job-agent
uvicorn main:app --reload
```

Open **http://localhost:8000**

### 4. Run as a background service (auto-start on login)

```bash
launchctl load ~/Library/LaunchAgents/com.jobagent.plist
```

To stop:
```bash
launchctl unload ~/Library/LaunchAgents/com.jobagent.plist
```

Logs: `tail -f ~/job-agent/agent.log`

## Schedule

| Time | Action |
|------|--------|
| 03:00, 10:00, 17:00, 21:00 ET | Scrape all sources + score new jobs with Claude |
| Daily 08:00 ET | Health check email |
| Monday 08:00 ET | Weekly digest email |

## Customise

### Add target VC firms

Edit `config.py`:

```python
TARGET_FIRM_URLS = [
    {"firm": "Lux Capital",   "url": "https://www.luxcapital.com/careers"},
    {"firm": "DCVC",          "url": "https://www.dcvc.com/careers"},
    {"firm": "BDC Capital",   "url": "https://www.bdc.ca/en/bdc-capital"},
]
```

### Change scoring thresholds

```python
# notifier.py
SCORE_WHATSAPP = 90   # WhatsApp alert threshold
SCORE_EMAIL    = 75   # Email alert threshold
```

## Notification Examples

**WhatsApp alert (score > 90)**
```
🌟🌟 TOP VC MATCH — 93/100

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
