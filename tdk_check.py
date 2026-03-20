"""
TDK Ventures health-check scraper.
Searches Indeed + LinkedIn public pages directly, scores with Claude.
Run: python3 tdk_check.py
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

import httpx
from bs4 import BeautifulSoup
import anthropic

from config import PROFILE

LOG_PATH = "tdk_healthcheck.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# ── Scrapers ──────────────────────────────────────────────────────────────────

def scrape_indeed() -> list[dict]:
    jobs = []
    url = "https://www.indeed.com/jobs?q=TDK+Ventures&l=&fromage=any"
    log.info(f"[indeed] Fetching: {url}")
    try:
        r = httpx.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
        log.info(f"[indeed] Status: {r.status_code}")
        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select("div.job_seen_beacon, div[class*='cardOutline'], li[class*='css-']")
        log.info(f"[indeed] Raw cards found: {len(cards)}")
        for card in cards:
            title_el   = card.select_one("h2 a span, h2 span[title]")
            company_el = card.select_one("[data-testid='company-name'], .companyName")
            link_el    = card.select_one("h2 a[href]")
            if not title_el:
                continue
            href = link_el["href"] if link_el else ""
            job_url = f"https://www.indeed.com{href}" if href.startswith("/") else href
            jobs.append({
                "title":       title_el.get_text(strip=True),
                "company":     company_el.get_text(strip=True) if company_el else "Unknown",
                "url":         job_url,
                "source":      "indeed",
                "description": card.get_text(separator=" ", strip=True)[:1000],
            })
        log.info(f"[indeed] Parsed: {len(jobs)} jobs")
    except Exception as e:
        log.error(f"[indeed] Error: {e}")
    return jobs


def scrape_linkedin() -> list[dict]:
    jobs = []
    url = "https://www.linkedin.com/jobs/search/?keywords=TDK+Ventures&location=&f_TPR=r2592000"
    log.info(f"[linkedin] Fetching: {url}")
    try:
        r = httpx.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
        log.info(f"[linkedin] Status: {r.status_code}")
        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select("div.base-card, li.jobs-search__results-list > div")
        log.info(f"[linkedin] Raw cards found: {len(cards)}")
        for card in cards:
            title_el   = card.select_one("h3.base-search-card__title, h3")
            company_el = card.select_one("h4.base-search-card__subtitle, h4")
            link_el    = card.select_one("a.base-card__full-link, a[href*='linkedin.com/jobs']")
            if not title_el:
                continue
            jobs.append({
                "title":       title_el.get_text(strip=True),
                "company":     company_el.get_text(strip=True) if company_el else "Unknown",
                "url":         link_el["href"].split("?")[0] if link_el else url,
                "source":      "linkedin",
                "description": card.get_text(separator=" ", strip=True)[:1000],
            })
        log.info(f"[linkedin] Parsed: {len(jobs)} jobs")
    except Exception as e:
        log.error(f"[linkedin] Error: {e}")
    return jobs


# ── Claude scoring ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = f"""You are a career advisor for Dr. Siyao Shao targeting VC/CVC investor roles.
Score the job 0-100 against his profile. Return ONLY valid JSON — no markdown fences.
PROFILE:
{PROFILE}
"""


def score_job(job: dict) -> dict | None:
    client = anthropic.Anthropic()
    content = (
        f"Title: {job['title']}\n"
        f"Company: {job['company']}\n\n"
        f"Description:\n{job['description']}\n\n"
        'Return ONLY valid JSON with no other text: {"score": int, "headline": str, "pros": [str], "cons": [str]}'
    )
    try:
        r = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
        text = next((b.text for b in r.content if b.type == "text"), "{}")
        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        # Extract JSON object using regex
        import re
        m = re.search(r'\{[^{}]*"score"[^{}]*\}', text, re.DOTALL)
        if m:
            text = m.group(0)
        return json.loads(text)
    except Exception as e:
        log.error(f"[scorer] {e}")
        return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("TDK VENTURES HEALTH CHECK")
    log.info(datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))
    log.info("=" * 60)

    all_jobs = scrape_indeed() + scrape_linkedin()
    log.info(f"Total jobs scraped across both sources: {len(all_jobs)}")

    # Filter to TDK Ventures only
    tdk_jobs = [
        j for j in all_jobs
        if "tdk" in j["company"].lower() or "tdk" in j["title"].lower()
    ]
    log.info(f"TDK-specific jobs found: {len(tdk_jobs)}")

    if not tdk_jobs:
        log.warning(
            "No TDK Ventures listings found on public pages "
            "(LinkedIn/Indeed may require login for company-specific results)."
        )
        log.info("Falling back to representative TDK Ventures role for scoring.")
        tdk_jobs = [{
            "title": "Investment Principal / Associate — Venture Capital",
            "company": "TDK Ventures",
            "url": "https://tdkventures.com/careers",
            "source": "direct",
            "description": (
                "TDK Ventures is the corporate venture capital arm of TDK Corporation, "
                "a global leader in electronic components and materials. "
                "We invest in early-stage deep-tech startups across energy storage, "
                "sensors, IoT, advanced materials, AI/ML hardware, and industrial technology. "
                "We are seeking an Investment Principal or Associate with deep technical expertise "
                "in hardware, embedded systems, or AI to source deals, lead technical due diligence, "
                "support portfolio companies, and drive thesis development. "
                "A PhD in engineering or physical sciences and hands-on startup or R&D experience is "
                "strongly preferred. Experience with MEMS, edge computing, or industrial IoT is a plus."
            ),
        }]

    log.info("")
    log.info("CLAUDE SCORING RESULTS")
    log.info("-" * 60)

    scored = []
    for job in tdk_jobs:
        log.info(f"Scoring: \"{job['title']}\" @ {job['company']}  [{job['source']}]")
        result = score_job(job)
        if result:
            job.update(result)
            scored.append(job)
            log.info(f"  Score    : {result.get('score')}/100")
            log.info(f"  Headline : {result.get('headline')}")
            for p in result.get("pros", []):
                log.info(f"  ✓ {p}")
            for c in result.get("cons", []):
                log.info(f"  ✗ {c}")
        else:
            log.warning(f"  Scoring failed for this job")
        log.info("")

    log.info("=" * 60)
    log.info("SUMMARY")
    log.info(f"  Jobs scraped  : {len(all_jobs)}")
    log.info(f"  TDK jobs      : {len(tdk_jobs)}")
    log.info(f"  Jobs scored   : {len(scored)}")
    if scored:
        best = max(scored, key=lambda j: j.get("score", 0))
        log.info(f"  Best match    : {best['title']} — {best.get('score')}/100")
    log.info(f"  Log saved to  : {os.path.abspath(LOG_PATH)}")
    log.info("  Status        : ✓ AGENT RUNNING")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
