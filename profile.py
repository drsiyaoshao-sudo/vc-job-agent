"""
Dynamic profile loader.

Returns the active user profile from the DB UserSettings row.
Falls back to config.py defaults when no DB session is available.
Used by scorer.py and scorer_fallback.py so that changing your
resume in the web UI immediately affects future scoring.
"""
from __future__ import annotations

import json
import re

from config import PROFILE, SEARCH_QUERIES


def get_profile_text(settings=None) -> str:
    """Return the active resume/profile text."""
    if settings and settings.resume_text.strip():
        return settings.resume_text.strip()
    return PROFILE.strip()


def get_search_queries(settings=None) -> list[str]:
    """
    Build search queries from target titles + job anticipations.
    Falls back to config SEARCH_QUERIES when no settings or empty titles.
    """
    if not settings:
        return SEARCH_QUERIES

    titles: list[str] = []
    try:
        titles = json.loads(settings.target_titles or "[]")
    except (ValueError, TypeError):
        pass

    anticipations = (settings.job_anticipations or "").strip()

    if not titles and not anticipations:
        return SEARCH_QUERIES

    queries: list[str] = []

    # One query per title combined with short anticipation snippet
    domain_hint = ""
    if anticipations:
        # Pull first 3-4 content words from anticipations as domain hint
        words = [w for w in re.findall(r"[a-zA-Z]{4,}", anticipations) if w.lower() not in
                 {"open", "role", "roles", "level", "with", "that", "this", "from", "into", "also"}]
        domain_hint = " ".join(words[:3])

    for title in titles[:8]:  # cap at 8 queries
        q = title.strip()
        if domain_hint:
            q = f"{q} {domain_hint}"
        queries.append(q)

    # Always add a fallback VC query if list is short
    if len(queries) < 3:
        queries.extend(SEARCH_QUERIES[:3])

    return queries
