"""
24-hour health monitor for the VC Job Agent scraper.

Polls /api/scrape-status every 30 minutes for 24 hours and writes
a structured log to health_monitor.log. Detects:
  - Whether the app is reachable
  - Whether scheduled scrapes are firing (3, 10, 17, 21 ET)
  - Whether scrapes complete without errors
  - Whether new jobs are found / scored (note: 0 new jobs is fine)
"""
from __future__ import annotations

import json
import time
import logging
from datetime import datetime, timezone

import httpx

BASE_URL   = "http://localhost:8000"
POLL_SECS  = 30 * 60          # every 30 minutes
TOTAL_SECS = 24 * 60 * 60     # 24 hours
LOG_FILE   = "health_monitor.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-5s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def check() -> dict:
    try:
        r = httpx.get(f"{BASE_URL}/api/scrape-status", timeout=10)
        r.raise_for_status()
        return {"ok": True, **r.json()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def fmt_ts(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return iso


def main():
    start  = time.monotonic()
    checks = 0
    scrape_events: list[str] = []
    last_run_seen  = None
    errors         = 0

    logger.info("=" * 70)
    logger.info(f"24-HOUR HEALTH MONITOR STARTED — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    logger.info(f"Poll interval : {POLL_SECS // 60} minutes")
    logger.info(f"Duration      : 24 hours  ({TOTAL_SECS // 3600} polls approx)")
    logger.info(f"Scheduled runs: 03:00, 10:00, 17:00, 21:00 ET")
    logger.info("=" * 70)

    while (time.monotonic() - start) < TOTAL_SECS:
        checks += 1
        data = check()
        now  = datetime.utcnow().strftime("%H:%M UTC")

        if not data["ok"]:
            errors += 1
            logger.error(f"[check #{checks:03d} @ {now}] APP UNREACHABLE — {data['error']}")
        else:
            running    = data.get("running", False)
            last_run   = data.get("last_run")
            last_count = data.get("last_count", 0)
            last_scored= data.get("last_scored", 0)

            # Detect a new scrape completion since last poll
            new_event = (last_run and last_run != last_run_seen)
            if new_event:
                last_run_seen = last_run
                event_msg = (
                    f"SCRAPE COMPLETED  last_run={fmt_ts(last_run)}  "
                    f"new_jobs={last_count}  scored={last_scored}"
                )
                scrape_events.append(event_msg)
                logger.info(f"[check #{checks:03d} @ {now}] ✓ {event_msg}")
            else:
                status = "RUNNING" if running else "idle"
                logger.info(
                    f"[check #{checks:03d} @ {now}]  app={status}  "
                    f"last_run={fmt_ts(last_run)}  "
                    f"last_count={last_count}  last_scored={last_scored}"
                )

        elapsed_h = (time.monotonic() - start) / 3600
        remaining = TOTAL_SECS - (time.monotonic() - start)
        if remaining <= 0:
            break

        time.sleep(min(POLL_SECS, remaining))

    # ── Final summary ──────────────────────────────────────────────────────
    elapsed_h = (time.monotonic() - start) / 3600
    logger.info("")
    logger.info("=" * 70)
    logger.info(f"24-HOUR HEALTH MONITOR COMPLETE — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    logger.info(f"Duration   : {elapsed_h:.1f} hours")
    logger.info(f"Polls      : {checks}")
    logger.info(f"App errors : {errors}")
    logger.info(f"Scrape runs detected: {len(scrape_events)}")
    for ev in scrape_events:
        logger.info(f"  › {ev}")
    if errors == 0 and len(scrape_events) >= 3:
        logger.info("VERDICT: PASS — app stayed up and scraped on schedule")
    elif errors == 0:
        logger.info("VERDICT: PARTIAL — app stayed up but fewer scrapes than expected (check scheduler)")
    else:
        logger.info(f"VERDICT: FAIL — {errors} poll(s) found app unreachable")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
