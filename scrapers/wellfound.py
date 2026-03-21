"""
Wellfound (AngelList) job scraper.

NOTE: Wellfound's Cloudflare protection blocks automated scraping.
This module is kept for future use but currently returns empty results.
LinkedIn / Indeed (via jobspy310 subprocess) covers the same search space.
"""
from __future__ import annotations

import logging

from config import WELLFOUND_QUERIES  # noqa: F401  (keep import for other modules)

logger = logging.getLogger(__name__)


def scrape_wellfound() -> list[dict]:
    """Returns empty list — Wellfound scraping blocked by Cloudflare."""
    logger.info("[wellfound] Skipped — Cloudflare bot protection active")
    return []
