# VC Job Agent

A personal AI-powered job search agent built for **Dr. Siyao Shao**, targeting Venture Capital investor and partner roles. It scrapes job boards 4× daily, scores every listing against a deep-tech VC profile using **Claude Opus 4.6**, and delivers smart notifications via WhatsApp and email.

## Features

- **Automated scraping** — LinkedIn, Indeed, Wellfound, jobs.vc, and direct VC firm career pages
- **AI-powered scoring** — Claude Opus 4.6 scores each job 0–100 with pros, cons, and tailored application tips
- **Smart notifications**
  - Score > 90 → instant WhatsApp message (CallMeBot)
  - Score > 75 → instant email alert (Gmail SMTP)
  - Every Monday 8 AM → weekly digest email
  - Every day 8 AM → health check email confirming the agent is running
- **Web dashboard** — browse jobs by score, source, and status; filter and sort in one click
- **Application tracker** — track every application through reviewing → applied → interview → offer
- **Always-on** — runs as a macOS LaunchAgent; auto-starts on login, auto-restarts on crash

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
launchctl load ~/Library/LaunchAgents/com.siyaoshao.vcjobagent.plist
```

To stop:
```bash
launchctl unload ~/Library/LaunchAgents/com.siyaoshao.vcjobagent.plist
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
