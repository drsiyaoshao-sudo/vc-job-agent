"""
LinkedIn / Indeed scraper via python-jobspy.
Returns a list of raw job dicts ready for DB insertion.
"""
from __future__ import annotations

import logging
from datetime import datetime

from config import HOURS_OLD, JOB_SITES, RESULTS_PER_QUERY, SEARCH_QUERIES

logger = logging.getLogger(__name__)


def _safe_str(val) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s if s and s.lower() not in ("nan", "none", "") else None


def scrape_mainstream() -> list[dict]:
    """
    Scrape LinkedIn and Indeed for VC/investor roles.
    Returns list of job dicts compatible with the Job model.
    """
    try:
        from jobspy import scrape_jobs
    except ImportError:
        logger.error("python-jobspy not installed. Run: pip install python-jobspy")
        return []

    all_jobs: list[dict] = []
    seen_urls: set[str] = set()

    for query in SEARCH_QUERIES:
        logger.info(f"[jobspy] Searching: '{query}'")
        try:
            df = scrape_jobs(
                site_name=JOB_SITES,
                search_term=query,
                results_wanted=RESULTS_PER_QUERY,
                hours_old=HOURS_OLD,
                country_indeed="worldwide",
                linkedin_fetch_description=True,
                verbose=0,
            )
        except Exception as e:
            logger.warning(f"[jobspy] Query '{query}' failed: {e}")
            continue

        if df is None or df.empty:
            continue

        for _, row in df.iterrows():
            url = _safe_str(row.get("job_url") or row.get("job_url_direct"))
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            # Parse posted date
            posted = None
            raw_date = row.get("date_posted")
            if raw_date and str(raw_date).strip() not in ("", "nan", "None"):
                try:
                    if isinstance(raw_date, datetime):
                        posted = raw_date
                    else:
                        posted = datetime.fromisoformat(str(raw_date))
                except Exception:
                    pass

            source = _safe_str(row.get("site")) or "jobspy"

            all_jobs.append({
                "title": _safe_str(row.get("title")) or "Unknown",
                "company": _safe_str(row.get("company")) or "Unknown",
                "location": _safe_str(row.get("location")),
                "url": url,
                "source": source,
                "description": _safe_str(row.get("description")),
                "salary_range": _safe_str(row.get("min_amount"))
                    and f"{row.get('min_amount')}–{row.get('max_amount')} {row.get('currency', '')}".strip(),
                "is_remote": bool(row.get("is_remote")) if row.get("is_remote") is not None else None,
                "posted_date": posted,
            })

    logger.info(f"[jobspy] Total unique jobs scraped: {len(all_jobs)}")
    return all_jobs
