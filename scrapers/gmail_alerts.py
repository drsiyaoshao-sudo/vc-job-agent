"""
Gmail IMAP scraper for LinkedIn job alert emails.

Setup required (one-time):
  1. Enable IMAP in Gmail: Settings → See all settings → Forwarding and POP/IMAP → Enable IMAP
  2. Use the same GMAIL_USER + GMAIL_APP_PASS already in .env

How it works:
  - Connects to imap.gmail.com:993 over SSL
  - Searches for unread emails from LinkedIn job alert senders
  - Parses each email's HTML body with BeautifulSoup to extract job cards
  - Normalises LinkedIn tracking URLs → clean /jobs/view/{id} URLs
  - Returns standard job dicts (deduplication handled downstream by upsert_job)
  - Marks processed emails as read so they are not re-fetched next run
"""
from __future__ import annotations

import email
import imaplib
import logging
import os
import re
from email.header import decode_header
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

GMAIL_USER     = os.getenv("GMAIL_USER", "")
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASS", "")

# LinkedIn job alert sender addresses (primary + fallback)
LINKEDIN_SENDERS = [
    "jobs-noreply@linkedin.com",          # primary: "New jobs similar to X"
    "jobalerts-noreply@linkedin.com",     # secondary: saved-search alerts
]

LOOKBACK_DAYS      = 7   # scan emails from the last N days
MAX_EMAILS         = 50  # max emails to process per run
MAX_JOBS_PER_EMAIL = 20  # max job cards extracted per email

# Gmail folder — [Gmail]/All Mail catches emails in any tab (Promotions, Updates, etc.)
GMAIL_FOLDER = '"[Gmail]/All Mail"'


# ── URL helpers ────────────────────────────────────────────────────────────────

def _clean_linkedin_url(raw: str) -> Optional[str]:
    """
    Normalise a LinkedIn job URL found in an alert email.

    Handles:
      https://www.linkedin.com/comm/jobs/view/1234567890?...  → /jobs/view/1234567890
      https://www.linkedin.com/jobs/view/1234567890?tracking=...
      Redirect wrappers (e.g. links.email.linkedin.com)
    """
    if not raw:
        return None

    # Follow redirect-wrapper URLs to find the real LinkedIn URL
    # (don't make HTTP requests — just extract from the URL query string)
    if "linkedin.com" not in raw:
        # Some emails wrap the URL: extract the 'url' param
        parsed = urlparse(raw)
        params = parse_qs(parsed.query)
        for key in ("url", "redirect", "dest"):
            if key in params:
                raw = params[key][0]
                break
        else:
            return None

    # Match job ID from various LinkedIn URL patterns
    m = re.search(r"linkedin\.com(?:/comm)?/jobs/view/(\d+)", raw)
    if not m:
        return None

    job_id = m.group(1)
    return f"https://www.linkedin.com/jobs/view/{job_id}"


# ── Email parsing ──────────────────────────────────────────────────────────────

def _decode_header_str(raw_header: str) -> str:
    parts = decode_header(raw_header or "")
    result = []
    for chunk, charset in parts:
        if isinstance(chunk, bytes):
            result.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(chunk)
    return "".join(result)


def _get_html_body(msg: email.message.Message) -> str:
    """Extract the HTML part from a (possibly multipart) email."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                charset  = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
    else:
        if msg.get_content_type() == "text/html":
            payload = msg.get_payload(decode=True)
            charset  = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    return ""


def _parse_jobs_from_email(html: str, subject: str) -> list[dict]:
    """
    Parse job cards from a LinkedIn job alert HTML email.

    LinkedIn alert emails wrap each job in a small table.  The table contains:
      - An <a> with the job URL (link text = title + company + location merged)
      - Sibling text nodes that, separately, give title and "Company · Location"

    Strategy:
      1. Find every <a> whose href contains a LinkedIn jobs/view URL.
      2. Walk up to the nearest enclosing <table> (the job card).
      3. Collect all short text snippets in that table.
      4. First snippet → title, second snippet → "Company · Location".
      5. Split the second on \" · \" to separate company from location.
    """
    soup      = BeautifulSoup(html, "html.parser")
    jobs: list[dict] = []
    seen_urls: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if "/jobs/view/" not in href and "/comm/jobs/view/" not in href:
            continue

        clean_url = _clean_linkedin_url(href)
        if not clean_url or clean_url in seen_urls:
            continue

        # Skip logo / image-only links (no meaningful text)
        link_text = a.get_text(separator=" ", strip=True)
        if not link_text or len(link_text) < 4:
            continue
        # Skip the email header "Jobs similar to X at Y" link
        if "similar to" in link_text.lower():
            continue

        # Walk up to the nearest enclosing <table> (the job card)
        card = a
        for _ in range(12):
            if card is None:
                break
            if card.name == "table":
                break
            card = card.parent

        title    = ""
        company  = ""
        location = ""

        if card and card.name == "table":
            # Collect clean text snippets from the card, skipping the merged link text
            full_link_text = re.sub(r"\s+", " ", link_text).strip()
            snippets: list[str] = []
            for el in card.find_all(["span", "p", "td", "a"]):
                t = el.get_text(separator=" ", strip=True)
                t = re.sub(r"\s*Applied on\s+\w+\s+\d+.*", "", t).strip()
                t = re.sub(r"\s*Easy Apply\s*$", "", t).strip()
                t = re.sub(r"\s+", " ", t)
                # Skip: empty, too long, duplicate, or the merged link text itself
                if not t or len(t) < 4 or len(t) > 100:
                    continue
                if t in snippets or t == full_link_text:
                    continue
                snippets.append(t)

            # LinkedIn cards: snippets[0] = title, snippets[1] = "Company · Location"
            if snippets:
                title = snippets[0]
            if len(snippets) > 1:
                co_loc = snippets[1]
                if " · " in co_loc:
                    parts    = co_loc.split(" · ", 1)
                    company  = parts[0].strip()
                    location = parts[1].strip()
                else:
                    company = co_loc
        else:
            # Fallback: split the link text on " · "
            if " · " in link_text:
                parts    = link_text.split(" · ", 1)
                title    = parts[0].strip()
                co_loc   = parts[1].strip()
                co_loc   = re.sub(r"\s*Applied on\s+\w+\s+\d+.*", "", co_loc).strip()
                if " · " in co_loc:
                    sub      = co_loc.split(" · ", 1)
                    company  = sub[0].strip()
                    location = sub[1].strip()
                else:
                    company = co_loc
            else:
                title = link_text

        # Final cleanup
        title    = re.sub(r"\s*Applied on\s+\w+\s+\d+.*", "", title).strip()
        title    = re.sub(r"\s*Easy Apply\s*$", "", title).strip()
        location = re.sub(r"\s*\(Easy Apply\)\s*$", "", location).strip()

        if not title or len(title) < 3:
            continue

        seen_urls.add(clean_url)
        is_remote = location is not None and "remote" in location.lower()
        jobs.append({
            "title":        title,
            "company":      company or "Unknown",
            "location":     location or None,
            "url":          clean_url,
            "source":       "gmail_linkedin",
            "description":  None,
            "salary_range": None,
            "is_remote":    is_remote,
            "posted_date":  None,
        })

        if len(jobs) >= MAX_JOBS_PER_EMAIL:
            break

    return jobs


# ── IMAP connector ─────────────────────────────────────────────────────────────

def scrape_gmail_alerts() -> list[dict]:
    """
    Connect to Gmail via IMAP, fetch unread LinkedIn job alert emails,
    parse job listings, mark emails as read, and return job dicts.
    """
    if not GMAIL_USER or not GMAIL_APP_PASS:
        logger.warning("[gmail] GMAIL_USER or GMAIL_APP_PASS not set — skipping")
        return []

    all_jobs: list[dict] = []

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(GMAIL_USER, GMAIL_APP_PASS)
    except imaplib.IMAP4.error as e:
        logger.warning(f"[gmail] IMAP login failed: {e} — check GMAIL_APP_PASS and that IMAP is enabled")
        return []
    except Exception as e:
        logger.warning(f"[gmail] Connection error: {e}")
        return []

    try:
        mail.select(GMAIL_FOLDER)

        # IMAP date filter: emails since (today - LOOKBACK_DAYS)
        from datetime import datetime, timedelta
        since_date = (datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)).strftime("%d-%b-%Y")

        # Search across all LinkedIn alert senders within the lookback window
        uids_all: list[bytes] = []
        for sender in LINKEDIN_SENDERS:
            criteria = f'(FROM "{sender}" SINCE "{since_date}")'
            status, data = mail.search(None, criteria)
            if status == "OK" and data[0]:
                uids_all.extend(data[0].split())

        if not uids_all:
            logger.info(f"[gmail] No LinkedIn job alert emails in the last {LOOKBACK_DAYS} days")
            return []

        # Deduplicate UIDs (some may appear in multiple searches), newest-first
        seen_uids: set[bytes] = set()
        uids: list[bytes] = []
        for u in reversed(uids_all):
            if u not in seen_uids:
                seen_uids.add(u)
                uids.append(u)

        logger.info(f"[gmail] Found {len(uids)} LinkedIn alert email(s) from last {LOOKBACK_DAYS} days")

        for uid in uids[:MAX_EMAILS]:
            status, raw = mail.fetch(uid, "(RFC822)")
            if status != "OK" or not raw or not raw[0]:
                continue

            raw_email = raw[0][1]
            msg       = email.message_from_bytes(raw_email)
            subject   = _decode_header_str(msg.get("Subject", ""))

            logger.debug(f"[gmail] Processing: {subject!r}")

            # Skip application-status emails — only want discovery/alert emails
            subj_lower = subject.lower()
            if any(skip in subj_lower for skip in (
                "your application", "application was viewed", "application to",
                "you applied", "rejected", "interview request", "offer",
            )):
                logger.debug(f"[gmail] Skipping application-status email: {subject!r}")
                continue

            html = _get_html_body(msg)
            if not html:
                continue

            jobs = _parse_jobs_from_email(html, subject)
            logger.info(f"[gmail] {len(jobs)} jobs parsed from: {subject!r}")
            all_jobs.extend(jobs)

    finally:
        try:
            mail.logout()
        except Exception:
            pass

    logger.info(f"[gmail] Total jobs extracted: {len(all_jobs)}")
    return all_jobs
