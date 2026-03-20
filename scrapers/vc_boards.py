"""
VC-specific job board scrapers.
Covers: jobs.vc and direct firm career pages (configured in config.py).
"""
import logging

import httpx
from bs4 import BeautifulSoup

from config import TARGET_FIRM_URLS, VC_BOARD_URLS

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Keywords to look for on firm career pages — only grab relevant postings
INVESTOR_KEYWORDS = {
    "venture", "investor", "investment", "associate", "principal",
    "partner", "cvc", "portfolio", "deal", "thesis", "fund",
    "analyst", "scout", "sourcing",
}


def scrape_vc_boards() -> list[dict]:
    """
    Scrape VC-specific job boards and direct firm career pages.
    Returns list of job dicts.
    """
    all_jobs: list[dict] = []
    seen_urls: set[str] = set()

    with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        # 1. jobs.vc
        all_jobs.extend(_scrape_jobs_vc(client, seen_urls))

        # 2. Direct firm career pages
        for firm_config in TARGET_FIRM_URLS:
            firm = firm_config.get("firm", "Unknown Firm")
            url = firm_config.get("url", "")
            if url:
                jobs = _scrape_firm_page(client, firm, url, seen_urls)
                all_jobs.extend(jobs)

    logger.info(f"[vc_boards] Total jobs scraped: {len(all_jobs)}")
    return all_jobs


def _scrape_jobs_vc(client: httpx.Client, seen_urls: set) -> list[dict]:
    """Scrape jobs.vc for VC-related openings."""
    jobs = []
    url = "https://jobs.vc"
    try:
        resp = client.get(url)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"[jobs.vc] Failed to fetch: {e}")
        return jobs

    soup = BeautifulSoup(resp.text, "html.parser")
    links = soup.select("a[href]")

    for link in links:
        href = link.get("href", "")
        text = link.get_text(strip=True).lower()
        if not href or not any(kw in text for kw in INVESTOR_KEYWORDS):
            continue

        job_url = href if href.startswith("http") else f"https://jobs.vc{href}"
        if job_url in seen_urls:
            continue
        seen_urls.add(job_url)

        jobs.append({
            "title": link.get_text(strip=True) or "VC Role",
            "company": "Unknown",
            "location": None,
            "url": job_url,
            "source": "jobs_vc",
            "description": None,
            "salary_range": None,
            "is_remote": None,
            "posted_date": None,
        })

    return jobs


def _scrape_firm_page(
    client: httpx.Client,
    firm: str,
    base_url: str,
    seen_urls: set,
) -> list[dict]:
    """Scrape a specific VC firm's career page for investor roles."""
    jobs = []
    try:
        resp = client.get(base_url)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"[direct/{firm}] Failed to fetch {base_url}: {e}")
        return jobs

    soup = BeautifulSoup(resp.text, "html.parser")

    # Try common job listing patterns
    candidates = (
        soup.select(".job, .position, .opening, .career-item, [class*='job'], [class*='career']")
        or soup.select("li, article")
    )

    for el in candidates:
        text = el.get_text(strip=True).lower()
        if not any(kw in text for kw in INVESTOR_KEYWORDS):
            continue

        a_tag = el.select_one("a[href]") or (el if el.name == "a" else None)
        if not a_tag:
            continue

        href = a_tag.get("href", "")
        job_url = href if href.startswith("http") else f"{base_url.rstrip('/')}/{href.lstrip('/')}"
        if not href or job_url in seen_urls:
            continue
        seen_urls.add(job_url)

        title = el.select_one("h1, h2, h3, h4, .title, .role")
        jobs.append({
            "title": title.get_text(strip=True) if title else el.get_text(strip=True)[:100],
            "company": firm,
            "location": None,
            "url": job_url,
            "source": "direct",
            "description": None,
            "salary_range": None,
            "is_remote": None,
            "posted_date": None,
        })

    return jobs
