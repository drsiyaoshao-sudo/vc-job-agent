"""
VC-specific job board scrapers.
Covers: jobs.vc, NFX Guild, Venture Capital Careers, and direct firm career pages.

Two-step approach for firm pages:
  1. Fetch the career landing page, extract candidate job-posting links
  2. Follow each link and scrape the actual job description
"""
from __future__ import annotations

import json
import logging
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from config import INVESTOR_BOARD_URLS, TARGET_FIRM_URLS, VC_BOARD_URLS

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Link text must contain at least one of these to be considered a job posting.
# Covers all 4 target role types: VC/investor, founding/staff engineer,
# research engineer, and FAE/technical sales.
INVESTOR_KEYWORDS = {
    # VC / investor roles
    "venture", "investor", "investment", "associate", "principal",
    "partner", "cvc", "deal", "thesis", "fund", "analyst", "scout",
    "sourcing", "capital", "equity", "portfolio manager",
    # Founding / early-stage engineer roles
    "founding engineer", "founding software", "founding hardware",
    "staff engineer", "staff software", "staff hardware",
    "early stage engineer", "early-stage engineer",
    "senior engineer", "lead engineer", "principal engineer",
    "software engineer", "hardware engineer", "systems engineer",
    # Research engineer roles
    "research engineer", "research scientist", "principal scientist",
    "staff scientist", "mems", "embedded", "edge ai",
    # FAE / technical sales roles
    "field application", "fae", "solutions engineer", "solutions architect",
    "technical sales", "sales engineer", "pre-sales", "application engineer",
    # EIR / operator roles at funds
    "entrepreneur in residence", "eir",
    # Startup stage signals (found in portfolio job descriptions)
    "series a", "series b", "seed stage", "startup",
}

# URL path segments that indicate a specific job posting page
JOB_URL_SIGNALS = {
    "/job/", "/jobs/", "/position/", "/positions/", "/opening/", "/openings/",
    "/role/", "/roles/", "/apply/", "/listing/", "/opportunity/", "/careers/",
    "/lever.co/", "/greenhouse.io/", "/ashbyhq.com/", "/workable.com/",
    "/workday.com/", "/bamboohr.com/", "/recruitee.com/",
}

# URL path segments that indicate navigation / non-job pages — skip these
NAV_URL_BLOCKLIST = {
    "/portfolio", "/team", "/about", "/company", "/sustainability",
    "/partners", "/news", "/media", "/blog", "/press", "/contact",
    "/supply-chain", "/investor-relations", "/legal", "/privacy",
    "/cookie", "/sitemap", "/cdn-cgi", "/wp-content",
}

MAX_JOBS_PER_FIRM = 20


def scrape_vc_boards() -> list[dict]:
    """
    Scrape VC-specific job boards and direct firm career pages.
    Returns list of job dicts.

    Run order (highest signal first):
      1. Direct firm career pages (TARGET_FIRM_URLS — known target VCs/CVCs)
      2. Investor portfolio boards (YC, a16z, First Round, etc.)
      3. jobs.vc board
      4. NFX Guild job board
      5. Venture Capital Careers board
    """
    all_jobs: list[dict] = []
    seen_urls: set[str] = set()

    with httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True) as client:
        # 1. Direct firm career pages — highest priority (known target VCs/CVCs)
        for firm_config in TARGET_FIRM_URLS:
            firm = firm_config.get("firm", "Unknown Firm")
            url  = firm_config.get("url", "")
            if url:
                jobs = _scrape_firm_page(client, firm, url, seen_urls)
                all_jobs.extend(jobs)
                if jobs:
                    logger.info(f"[direct/{firm}] {len(jobs)} jobs found")

        # 2. Investor portfolio boards (YC, a16z, First Round, etc.)
        all_jobs.extend(_scrape_investor_boards(client, seen_urls))

        # 3. jobs.vc board
        all_jobs.extend(_scrape_jobs_vc(client, seen_urls))

        # 4. NFX Guild job board (Next.js JSON)
        all_jobs.extend(_scrape_nfx(client, seen_urls))

        # 5. Venture Capital Careers board
        all_jobs.extend(_scrape_vc_careers(client, seen_urls))

    logger.info(f"[vc_boards] Total jobs scraped: {len(all_jobs)}")
    return all_jobs


# ── Investor portfolio job boards ─────────────────────────────────────────────

def _scrape_investor_boards(client: httpx.Client, seen_urls: set) -> list[dict]:
    """
    Scrape all boards in INVESTOR_BOARD_URLS.
    Each board is a VC-curated listing of early-stage startup jobs.
    """
    jobs: list[dict] = []
    for board_cfg in INVESTOR_BOARD_URLS:
        name = board_cfg.get("board", "Unknown Board")
        url  = board_cfg.get("url", "")
        if not url:
            continue
        board_jobs = _scrape_board_listing(client, name, url, seen_urls)
        jobs.extend(board_jobs)
        if board_jobs:
            logger.info(f"[investor_board/{name}] {len(board_jobs)} jobs found")
    return jobs


def _scrape_board_listing(
    client: httpx.Client,
    board: str,
    url: str,
    seen_urls: set,
) -> list[dict]:
    """
    Generic investor board scraper.
    Fetches the listing page, extracts links whose anchor text matches
    INVESTOR_KEYWORDS, fetches each posting for description, caps at
    MAX_JOBS_PER_FIRM.
    """
    jobs: list[dict] = []
    try:
        resp = client.get(url, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"[investor_board/{board}] Failed to fetch {url}: {e}")
        return jobs

    soup = BeautifulSoup(resp.text, "html.parser")
    base_domain = f"{urlparse(url).scheme}://{urlparse(url).netloc}"

    candidates: list[tuple[str, str]] = []
    seen_hrefs: set[str] = set()

    for a in soup.select("a[href]"):
        href = a.get("href", "").strip()
        text = a.get_text(strip=True)
        if not href or not text or len(text) > 150:
            continue

        # Must match a keyword from any target role bucket
        if not any(kw in text.lower() for kw in INVESTOR_KEYWORDS):
            continue

        full_url = href if href.startswith("http") else urljoin(base_domain, href)
        full_url = full_url.split("?")[0].split("#")[0]  # strip query / anchor

        if full_url in seen_urls or full_url in seen_hrefs or full_url == url:
            continue

        seen_hrefs.add(full_url)
        candidates.append((text, full_url))

    for title, job_url in candidates[:MAX_JOBS_PER_FIRM]:
        seen_urls.add(job_url)
        description = _fetch_job_description(client, job_url)
        jobs.append({
            "title":        title,
            "company":      board,
            "location":     None,
            "url":          job_url,
            "source":       "investor_board",
            "description":  description or None,
            "salary_range": None,
            "is_remote":    None,
            "posted_date":  None,
        })

    return jobs


# ── jobs.vc board ──────────────────────────────────────────────────────────────

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

    for link in soup.select("a[href]"):
        href  = link.get("href", "")
        text  = link.get_text(strip=True)
        tl    = text.lower()
        if not href or not any(kw in tl for kw in INVESTOR_KEYWORDS):
            continue
        job_url = href if href.startswith("http") else f"https://jobs.vc{href}"
        if job_url in seen_urls or len(jobs) >= MAX_JOBS_PER_FIRM:
            continue
        seen_urls.add(job_url)
        jobs.append({
            "title":       text or "Job Role",
            "company":     "Unknown",
            "location":    None,
            "url":         job_url,
            "source":      "jobs_vc",
            "description": None,
            "salary_range": None,
            "is_remote":   None,
            "posted_date": None,
        })

    return jobs


# ── NFX Guild job board ───────────────────────────────────────────────────────

def _scrape_nfx(client: httpx.Client, seen_urls: set) -> list[dict]:
    """
    Scrape jobs.nfx.com — NFX Guild portfolio job board.
    Jobs are embedded in __NEXT_DATA__ JSON; keyword filter keeps only
    relevant roles (VC/investor, founding eng, research eng, FAE/sales).
    """
    jobs = []
    base = "https://jobs.nfx.com"
    try:
        resp = client.get(f"{base}/jobs")
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"[nfx] Failed to fetch: {e}")
        return jobs

    soup = BeautifulSoup(resp.text, "html.parser")
    nd = soup.find("script", id="__NEXT_DATA__")
    if not nd:
        logger.warning("[nfx] __NEXT_DATA__ not found")
        return jobs

    try:
        state = json.loads(nd.string)["props"]["pageProps"]["initialState"]
        raw_jobs = state.get("jobs", {}).get("found", [])
    except (KeyError, json.JSONDecodeError) as e:
        logger.warning(f"[nfx] Failed to parse JSON: {e}")
        return jobs

    for item in raw_jobs[:MAX_JOBS_PER_FIRM]:
        title    = item.get("title", "")
        job_url  = item.get("url", "")
        org      = item.get("organization", {}) or {}
        company  = org.get("name", "") if isinstance(org, dict) else ""
        location = None
        locs     = item.get("locations") or item.get("searchableLocations") or []
        if locs and isinstance(locs[0], dict):
            location = locs[0].get("city") or locs[0].get("name")
        elif locs and isinstance(locs[0], str):
            location = locs[0]

        if not title or not job_url:
            continue
        if not any(kw in title.lower() for kw in INVESTOR_KEYWORDS):
            continue
        if job_url in seen_urls:
            continue
        seen_urls.add(job_url)

        # Fetch the actual job description from the external URL
        description = _fetch_job_description(client, job_url)

        jobs.append({
            "title":        title,
            "company":      company or "NFX Portfolio Company",
            "location":     location,
            "url":          job_url,
            "source":       "nfx",
            "description":  description or None,
            "salary_range": None,
            "is_remote":    item.get("workMode", "").lower() == "remote",
            "posted_date":  None,
        })

    logger.info(f"[nfx] {len(jobs)} investor-relevant jobs found")
    return jobs


# ── Venture Capital Careers board ─────────────────────────────────────────────

def _scrape_vc_careers(client: httpx.Client, seen_urls: set) -> list[dict]:
    """
    Scrape venturecapitalcareers.com/jobs — a board dedicated to VC roles.
    Job links follow the pattern /companies/{firm}/jobs/{slug}.
    """
    jobs = []
    base = "https://venturecapitalcareers.com"
    try:
        resp = client.get(f"{base}/jobs")
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"[vcc] Failed to fetch: {e}")
        return jobs

    soup = BeautifulSoup(resp.text, "html.parser")

    # Collect unique job links (pattern: /companies/.../jobs/...)
    seen_slugs: set[str] = set()
    candidates: list[tuple[str, str]] = []
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if "/jobs/" not in href or "/companies/" not in href:
            continue
        slug = href.split("#")[0]
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        title = a.get_text(strip=True)
        if title and len(title) < 120:
            candidates.append((title, f"{base}{slug}" if slug.startswith("/") else slug))

    for title, job_url in candidates[:MAX_JOBS_PER_FIRM]:
        if job_url in seen_urls:
            continue
        seen_urls.add(job_url)

        # Extract company slug from URL: /companies/{slug}/jobs/...
        parts = job_url.split("/companies/")
        company_slug = parts[1].split("/")[0] if len(parts) > 1 else ""
        company = company_slug.replace("-", " ").title() if company_slug else "Unknown"

        description, location = None, None
        try:
            detail = client.get(job_url, timeout=15)
            if detail.status_code == 200:
                dsoup = BeautifulSoup(detail.text, "html.parser")
                # Title from page <title>: "Job Title at Company Name • Location"
                page_title = dsoup.find("title")
                if page_title:
                    pt = page_title.get_text(strip=True)
                    if " at " in pt:
                        title   = pt.split(" at ")[0].strip()
                        company = pt.split(" at ")[1].split("•")[0].strip()
                        loc_part = pt.split("•")
                        if len(loc_part) > 1:
                            location = loc_part[1].strip()
                for tag in dsoup(["script", "style", "nav", "header", "footer"]):
                    tag.decompose()
                main = dsoup.find("main") or dsoup.find("body")
                if main:
                    description = main.get_text(separator=" ", strip=True)[:5000]
        except Exception:
            pass

        jobs.append({
            "title":        title,
            "company":      company,
            "location":     location,
            "url":          job_url,
            "source":       "vc_careers",
            "description":  description,
            "salary_range": None,
            "is_remote":    None,
            "posted_date":  None,
        })

    logger.info(f"[vcc] {len(jobs)} jobs found")
    return jobs


# ── Direct firm career pages ──────────────────────────────────────────────────

def _is_job_posting_url(href: str, base_url: str) -> bool:
    """
    Return True if this URL looks like an individual job posting
    rather than a navigation or site-structure link.
    """
    if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("javascript:"):
        return False

    full = urljoin(base_url, href)
    path = urlparse(full).path.lower()

    # Skip obvious non-job paths
    if any(block in path for block in NAV_URL_BLOCKLIST):
        return False

    # Prefer paths that contain a known job-posting signal
    if any(signal in full.lower() for signal in JOB_URL_SIGNALS):
        return True

    # Accept if it's a sub-path of the base career URL with a slug
    base_path = urlparse(base_url).path.rstrip("/")
    if path.startswith(base_path) and path != base_path and path.count("/") > path.count(base_path.split("/")[-1]):
        return True

    return False


def _fetch_job_description(client: httpx.Client, url: str) -> str:
    """Fetch a job posting page and extract the meaningful text."""
    try:
        resp = client.get(url, timeout=15)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove boilerplate elements
        for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
            tag.decompose()

        # Try to find the main job content block
        content = (
            soup.find("main")
            or soup.find("article")
            or soup.find(id=lambda x: x and "job" in x.lower())
            or soup.find(class_=lambda x: x and any(kw in " ".join(x) for kw in ["job", "position", "role", "description", "content"]))
            or soup.find("body")
        )
        if content:
            return content.get_text(separator=" ", strip=True)[:5000]
    except Exception:
        pass
    return ""


def _scrape_firm_page(
    client: httpx.Client,
    firm: str,
    base_url: str,
    seen_urls: set,
) -> list[dict]:
    """
    Two-step scrape:
      Step 1 — fetch the career landing page, find links to individual job postings
      Step 2 — fetch each posting page to get the title and full description
    """
    jobs = []

    # ── Step 1: fetch listing page ────────────────────────────────────────────
    try:
        resp = client.get(base_url, timeout=15)
        if resp.status_code != 200:
            logger.warning(f"[direct/{firm}] HTTP {resp.status_code} for {base_url}")
            return jobs
    except Exception as e:
        logger.warning(f"[direct/{firm}] Failed to fetch {base_url}: {e}")
        return jobs

    soup = BeautifulSoup(resp.text, "html.parser")
    base_domain = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"

    # Collect candidate job-posting links
    candidates: list[tuple[str, str]] = []  # (title_text, absolute_url)

    for a in soup.select("a[href]"):
        href      = a.get("href", "").strip()
        link_text = a.get_text(strip=True)
        tl        = link_text.lower()

        if not _is_job_posting_url(href, base_url):
            continue

        # Must mention a target role keyword in the link text (VC, eng, FAE, research, etc.)
        if not any(kw in tl for kw in INVESTOR_KEYWORDS):
            continue

        # Skip very long strings (likely nav paragraphs, not job titles)
        if len(link_text) > 120:
            continue

        full_url = urljoin(base_domain if href.startswith("/") else base_url, href)
        full_url = full_url.split("?")[0].split("#")[0]  # strip query/anchor

        if full_url in seen_urls:
            continue

        candidates.append((link_text, full_url))

    # Deduplicate by URL, preserve order
    seen_candidates: set[str] = set()
    unique: list[tuple[str, str]] = []
    for title, url in candidates:
        if url not in seen_candidates:
            seen_candidates.add(url)
            unique.append((title, url))

    if not unique:
        logger.debug(f"[direct/{firm}] No job posting links found on {base_url}")
        return jobs

    # ── Step 2: fetch each individual posting ─────────────────────────────────
    for title_text, job_url in unique[:MAX_JOBS_PER_FIRM]:
        seen_urls.add(job_url)
        description = _fetch_job_description(client, job_url)

        # Try to get a better title from the posting page itself
        title = title_text
        if description:
            try:
                detail_soup = BeautifulSoup(
                    client.get(job_url, timeout=15).text, "html.parser"
                )
                h = detail_soup.find(["h1", "h2"])
                if h and len(h.get_text(strip=True)) < 120:
                    title = h.get_text(strip=True)
            except Exception:
                pass

        jobs.append({
            "title":        title,
            "company":      firm,
            "location":     None,
            "url":          job_url,
            "source":       "direct",
            "description":  description or None,
            "salary_range": None,
            "is_remote":    None,
            "posted_date":  None,
        })

    return jobs
