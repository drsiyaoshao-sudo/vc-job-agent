"""Scrapers package."""
from .jobspy import scrape_mainstream
from .wellfound import scrape_wellfound
from .vc_boards import scrape_vc_boards
from .gmail_alerts import scrape_gmail_alerts

__all__ = ["scrape_mainstream", "scrape_wellfound", "scrape_vc_boards", "scrape_gmail_alerts"]
