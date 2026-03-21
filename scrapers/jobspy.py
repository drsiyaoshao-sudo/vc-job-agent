"""
LinkedIn / Indeed scraper via python-jobspy.
Returns a list of raw job dicts ready for DB insertion.

python-jobspy requires Python 3.10+.  On Python 3.9 the direct import fails;
we fall back to running the scrape in a subprocess using the dedicated
jobspy310 conda environment (~/.../envs/jobspy310/bin/python).
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
from datetime import datetime

from config import HOURS_OLD, JOB_SITES, RESULTS_PER_QUERY, SEARCH_QUERIES

logger = logging.getLogger(__name__)

# Path to the Python 3.10 interpreter that has python-jobspy installed.
# Adjust if the conda env lives elsewhere.
_JOBSPY310_PYTHON = os.path.expanduser(
    "~/opt/anaconda3/envs/jobspy310/bin/python"
)


def _safe_str(val) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s if s and s.lower() not in ("nan", "none", "") else None


def _scrape_via_subprocess(queries: list[str]) -> list[dict]:
    """
    Run python-jobspy inside the jobspy310 conda env and return results as
    a list of dicts.  Communicates via a temporary JSON file.
    """
    if not os.path.isfile(_JOBSPY310_PYTHON):
        logger.error(
            f"[jobspy] jobspy310 env not found at {_JOBSPY310_PYTHON}. "
            "Create it with: conda create -n jobspy310 python=3.10 && "
            "~/opt/anaconda3/envs/jobspy310/bin/pip install python-jobspy"
        )
        return []

    script = f"""
import json, sys
from jobspy import scrape_jobs
from datetime import datetime

queries = {json.dumps(queries)}
job_sites = {json.dumps(JOB_SITES)}
results_per_query = {RESULTS_PER_QUERY}
hours_old = {HOURS_OLD}

all_jobs = []
seen_urls = set()

for query in queries:
    try:
        df = scrape_jobs(
            site_name=job_sites,
            search_term=query,
            results_wanted=results_per_query,
            hours_old=hours_old,
            country_indeed="worldwide",
            linkedin_fetch_description=True,
            verbose=0,
        )
    except Exception as e:
        print(f"[jobspy] Query {{query!r}} failed: {{e}}", file=sys.stderr)
        continue
    if df is None or df.empty:
        continue
    for _, row in df.iterrows():
        url = str(row.get("job_url") or row.get("job_url_direct") or "").strip()
        if not url or url in seen_urls or url.lower() in ("nan", "none", ""):
            continue
        seen_urls.add(url)
        posted = None
        raw_date = row.get("date_posted")
        if raw_date and str(raw_date).strip() not in ("", "nan", "None"):
            try:
                if isinstance(raw_date, datetime):
                    posted = raw_date.isoformat()
                else:
                    posted = datetime.fromisoformat(str(raw_date)).isoformat()
            except Exception:
                pass
        def safe(v):
            s = str(v).strip() if v is not None else ""
            return s if s and s.lower() not in ("nan", "none") else None
        min_amt = row.get("min_amount")
        salary = f"{{row.get('min_amount')}}\\u2013{{row.get('max_amount')}} {{row.get('currency', '')}}".strip() if safe(min_amt) else None
        is_remote = row.get("is_remote")
        all_jobs.append({{
            "title":        safe(row.get("title")) or "Unknown",
            "company":      safe(row.get("company")) or "Unknown",
            "location":     safe(row.get("location")),
            "url":          url,
            "source":       safe(row.get("site")) or "jobspy",
            "description":  safe(row.get("description")),
            "salary_range": salary,
            "is_remote":    bool(is_remote) if is_remote is not None else None,
            "posted_date":  posted,
        }})

print(json.dumps(all_jobs))
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script)
        script_path = f.name

    try:
        result = subprocess.run(
            [_JOBSPY310_PYTHON, script_path],
            capture_output=True,
            text=True,
            timeout=600,  # 26 queries × ~20s each
        )
        if result.returncode != 0:
            logger.warning(f"[jobspy] subprocess stderr: {result.stderr[:500]}")
        if result.stdout.strip():
            return json.loads(result.stdout.strip())
        return []
    except subprocess.TimeoutExpired:
        logger.warning("[jobspy] subprocess timed out")
        return []
    except Exception as e:
        logger.warning(f"[jobspy] subprocess failed: {e}")
        return []
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass


def scrape_mainstream(queries: list[str] | None = None) -> list[dict]:
    """
    Scrape LinkedIn and Indeed for all target roles.
    Returns list of job dicts compatible with the Job model.
    """
    active_queries = queries if queries is not None else SEARCH_QUERIES

    # Try direct import first (works on Python 3.10+)
    try:
        from jobspy import scrape_jobs
        _have_jobspy = True
    except ImportError:
        _have_jobspy = False

    if not _have_jobspy:
        logger.info("[jobspy] Direct import unavailable (Python 3.9); using jobspy310 subprocess")
        raw = _scrape_via_subprocess(active_queries)
        # Convert posted_date ISO strings back to datetime objects
        for job in raw:
            pd = job.get("posted_date")
            if isinstance(pd, str) and pd:
                try:
                    job["posted_date"] = datetime.fromisoformat(pd)
                except ValueError:
                    job["posted_date"] = None
        logger.info(f"[jobspy] Total unique jobs scraped via subprocess: {len(raw)}")
        return raw

    all_jobs: list[dict] = []
    seen_urls: set[str] = set()

    for query in active_queries:
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
