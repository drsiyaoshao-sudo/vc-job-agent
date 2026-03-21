# Job Search Agent

A self-hosted AI-powered job search agent. It scrapes job boards 4× daily, scores every listing against **your own resume** using **Claude Opus 4.6**, and delivers smart notifications via WhatsApp and email. Configure everything from a web UI — no code changes needed after the initial setup.

## Features

- **Automated scraping** — three-stage pipeline runs 4× daily (LinkedIn, Wellfound, jobs.vc, direct firm pages)
- **AI-powered scoring** — Claude Opus 4.6 scores each job 0–100 with pros, cons, and tailored application tips
- **Smart notifications**
  - Score ≥ 90 → instant WhatsApp message (CallMeBot)
  - Score ≥ 75 → instant email alert (Gmail SMTP)
  - Every Monday 8 AM → weekly digest email
  - Every day 8 AM → health check email
- **Setup wizard** — first-run guided setup (name → resume → job targets → dashboard)
- **Web dashboard** — browse jobs by score, source, and status
- **Application tracker** — track every application through reviewing → applied → interview → offer

---

## Quick Start (Docker — recommended)

No Python or dependency installation required.

### 1. Copy and fill in your environment file

```bash
cp .env.example .env
```

Edit `.env` with your credentials (only `ANTHROPIC_API_KEY` is required to start):

```env
ANTHROPIC_API_KEY=sk-ant-...      # platform.anthropic.com

# Optional — WhatsApp alerts for score ≥ 90
CALLMEBOT_PHONE=1XXXXXXXXXX
CALLMEBOT_APIKEY=...

# Optional — email alerts and digests
GMAIL_USER=you@gmail.com
GMAIL_APP_PASS=xxxx xxxx xxxx xxxx
NOTIFY_EMAIL=you@gmail.com
```

### 2. Start the agent

```bash
docker compose up -d
```

### 3. Open the web UI

Go to **http://localhost:8000** — the setup wizard will guide you through:

1. **Your name** — personalises notifications and the dashboard
2. **Your resume** — paste your full resume; Claude reads it fresh on every scoring call
3. **Job targets** — set target titles (drives search queries) and free-text anticipations (guides Claude scoring)
4. **Done** — click **Launch Dashboard**, then **Scrape Jobs** to run the first scrape

Your data is stored in a named Docker volume (`job-agent-data`) and persists across container restarts.

### Stop / restart

```bash
docker compose down    # stop
docker compose up -d   # start again
docker compose logs -f # view logs
```

---

## Manual Setup (Python)

If you prefer to run without Docker:

### 1. Requirements

- Python 3.11+ recommended (3.9+ works but jobspy requires 3.10+)
- Install dependencies:

```bash
pip install -r requirements.txt python-multipart
```

### 2. Configure environment

```bash
cp .env.example .env
# edit .env with your keys
```

### 3. Run

```bash
uvicorn main:app --reload
```

Open **http://localhost:8000** — the setup wizard will appear on first run.

### 4. Run as a background service (macOS)

```bash
launchctl load ~/Library/LaunchAgents/com.jobagent.plist
```

To stop:
```bash
launchctl unload ~/Library/LaunchAgents/com.jobagent.plist
```

Logs: `tail -f ~/job-agent/agent.log`

---

## Customise

### Add target company career pages

After setup, edit `config.py` to add specific firm career pages you want the agent to monitor:

```python
TARGET_FIRM_URLS = [
    {"firm": "Acme Ventures",   "url": "https://acmeventures.com/careers"},
    {"firm": "Deep Tech Fund",  "url": "https://deeptechfund.com/jobs"},
]
```

Restart the app after changing `config.py`.

### Update your profile

Everything else is configurable via the **Settings** page at `/settings` — no restart needed. Changes take effect on the next scoring run.

---

## Scraping Pipeline

Each scheduled run (03:00, 10:00, 17:00, 21:00 ET) runs three stages with a hard cap of **20 jobs per source/query**:

1. **LinkedIn / Indeed** (`scrapers/jobspy.py`) — searches using your target titles from Settings
2. **VC boards + direct firm pages** (`scrapers/vc_boards.py`) — jobs.vc, NFX Guild, Venture Capital Careers, and any URLs in `TARGET_FIRM_URLS`
3. **Gmail alerts** (`scrapers/gmail_alerts.py`) — reads LinkedIn job alert emails from Gmail (optional)

All stages deduplicate by URL — the same job found on multiple sources is stored only once.

---

## Scoring

Every job is scored by **Claude Opus 4.6** against your resume and job anticipations. The model returns a structured result with `score` (0–100), `headline`, `pros`, `cons`, and `key_requirements`.

| Score | Label | Meaning |
|-------|-------|---------|
| 85–100 | Excellent | Squarely fits your stated target; domain and seniority align |
| 65–84 | Good | Fits target with minor gaps in domain, seniority, or location |
| 45–64 | Moderate | Adjacent / transferable; possible pivot toward target |
| 20–44 | Weak | Mostly irrelevant or significantly off seniority |
| 0–19 | Not relevant | Unrelated to your background or goals |

If Claude is unavailable, a keyword + TF-IDF fallback scorer runs automatically (no API cost, instant).

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
| Deployment | Docker / docker compose |

---

Built with [Claude](https://anthropic.com) · [FastAPI](https://fastapi.tiangolo.com) · [jobspy](https://github.com/Bunsly/JobSpy)
