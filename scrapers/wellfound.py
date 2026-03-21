"""
Wellfound (AngelList) job scraper.
Uses their public search endpoint to find VC/investor roles.
"""
import logging

import httpx
from bs4 import BeautifulSoup

from config import WELLFOUND_QUERIES

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def scrape_wellfound() -> list[dict]:
    """
    Scrape Wellfound jobs search for VC/investor roles.
    Returns list of job dicts.
    """
    all_jobs: list[dict] = []
    seen_urls: set[str] = set()

    with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        for query in WELLFOUND_QUERIES:
            jobs = _fetch_wellfound_page(client, query, seen_urls)
            all_jobs.extend(jobs)

    logger.info(f"[wellfound] Total jobs scraped: {len(all_jobs)}")
    return all_jobs


def _fetch_wellfound_page(client: httpx.Client, query: str, seen_urls: set) -> list[dict]:
    jobs = []
    url = f"https://wellfound.com/jobs?q={query.replace(' ', '+')}"
    try:
        resp = client.get(url)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"[wellfound] Failed to fetch '{query}': {e}")
        return jobs

    soup = BeautifulSoup(resp.text, "html.parser")

    # Wellfound renders via Next.js; try to find job listing cards
    job_cards = soup.select("[data-test='StartupResult'], .job-listing, article")

    if not job_cards:
        # Fallback: look for any <a> tag that looks like a job link
        job_cards = soup.select("a[href*='/jobs/']")

    for card in job_cards:
        href = card.get("href", "")
        if not href:
            a_tag = card.select_one("a[href*='/jobs/']")
            href = a_tag.get("href", "") if a_tag else ""

        if not href or "/jobs/" not in href:
            continue

        job_url = href if href.startswith("http") else f"https://wellfound.com{href}"
        if job_url in seen_urls:
            continue
        seen_urls.add(job_url)

        title_el = card.select_one("h2, h3, .job-title, [class*='title']")
        company_el = card.select_one(".company-name, [class*='company']")

        jobs.append({
            "title": title_el.get_text(strip=True) if title_el else "VC Role",
            "company": company_el.get_text(strip=True) if company_el else "Unknown",
            "location": None,
            "url": job_url,
            "source": "wellfound",
            "description": None,
            "salary_range": None,
            "is_remote": None,
            "posted_date": None,
        })

    return jobs
