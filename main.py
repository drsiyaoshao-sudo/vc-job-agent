"""
VC Job Agent — FastAPI application.
Run with: uvicorn main:app --reload
"""
# load_dotenv FIRST — must run before any module that reads env vars at import time
from dotenv import load_dotenv
load_dotenv()

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from apscheduler.schedulers.background import BackgroundScheduler

from database import Job, JobStatus, create_db, get_session, upsert_job
from notifier import send_health_check, send_weekly_report
from scrapers import scrape_mainstream, scrape_vc_boards, scrape_wellfound
from scorer import rescore_job, score_unscored_jobs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Scheduler ─────────────────────────────────────────────────────────────────

_scheduler = BackgroundScheduler(timezone="America/Toronto")

def _scheduled_scrape():
    """Scrape + score pipeline for scheduled runs."""
    from database import engine
    from sqlmodel import Session as S
    _run_scrape(lambda: S(engine))

# Scrape 4× daily
for _hour in (3, 10, 17, 21):
    _scheduler.add_job(_scheduled_scrape, "cron", hour=_hour, minute=0)

# Daily health check email at 08:00 ET
_scheduler.add_job(send_health_check, "cron", hour=8, minute=0)

# Weekly digest every Monday 08:00 ET
_scheduler.add_job(send_weekly_report, "cron", day_of_week="mon", hour=8, minute=0)


# ── App lifecycle ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db()
    _scheduler.start()
    logger.info("Scheduler started — scraping at 03:00, 10:00, 17:00, 21:00 ET · weekly report Mondays 08:00 ET")
    yield
    _scheduler.shutdown(wait=False)

app = FastAPI(title="VC Job Agent", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Thread pool for running sync scrapers in background
executor = ThreadPoolExecutor(max_workers=4)

# Scrape state
scrape_status = {"running": False, "last_run": None, "last_count": 0, "last_scored": 0}


# ── Template helpers ──────────────────────────────────────────────────────────

def job_to_dict(job: Job) -> dict:
    return {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "url": job.url,
        "source": job.source,
        "description": job.description,
        "salary_range": job.salary_range,
        "is_remote": job.is_remote,
        "posted_date": job.posted_date.isoformat() if job.posted_date else None,
        "scraped_at": job.scraped_at.isoformat() if job.scraped_at else None,
        "match_score": job.match_score,
        "match_headline": job.match_headline,
        "match_pros": json.loads(job.match_pros) if job.match_pros else [],
        "match_cons": json.loads(job.match_cons) if job.match_cons else [],
        "key_requirements": json.loads(job.key_requirements) if job.key_requirements else [],
        "scored_at": job.scored_at.isoformat() if job.scored_at else None,
        "status": job.status,
        "notes": job.notes,
        "applied_date": job.applied_date.isoformat() if job.applied_date else None,
        "follow_up_date": job.follow_up_date.isoformat() if job.follow_up_date else None,
        "contact_name": job.contact_name,
        "contact_email": job.contact_email,
    }


def score_color(score: Optional[int]) -> str:
    if score is None:
        return "gray"
    if score >= 80:
        return "green"
    if score >= 60:
        return "yellow"
    if score >= 40:
        return "orange"
    return "red"


templates.env.globals["score_color"] = score_color
templates.env.globals["JobStatus"] = JobStatus


# ── Background scrape task ────────────────────────────────────────────────────

def _run_scrape(session_factory):
    """Synchronous scrape + score pipeline (runs in thread pool)."""
    scrape_status["running"] = True
    total_new = 0

    try:
        all_jobs: list[dict] = []
        all_jobs.extend(scrape_mainstream())
        all_jobs.extend(scrape_wellfound())
        all_jobs.extend(scrape_vc_boards())

        with session_factory() as session:
            for job_data in all_jobs:
                _, created = upsert_job(session, job_data)
                if created:
                    total_new += 1

            scored = score_unscored_jobs(session)

        scrape_status["last_count"] = total_new
        scrape_status["last_scored"] = scored
        logger.info(f"Scrape complete: {total_new} new jobs, {scored} scored")

    except Exception as e:
        logger.error(f"Scrape pipeline failed: {e}")
    finally:
        scrape_status["running"] = False
        scrape_status["last_run"] = datetime.utcnow().isoformat()


# ── Routes: Pages ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    status: Optional[str] = None,
    source: Optional[str] = None,
    min_score: int = 0,
    sort: str = "score",
    session: Session = Depends(get_session),
):
    query = select(Job)

    if status:
        query = query.where(Job.status == status)
    if source:
        query = query.where(Job.source == source)
    if min_score > 0:
        query = query.where(Job.match_score >= min_score)

    jobs = session.exec(query).all()

    # Sort
    if sort == "score":
        jobs = sorted(jobs, key=lambda j: (j.match_score or -1), reverse=True)
    elif sort == "date":
        jobs = sorted(jobs, key=lambda j: (j.scraped_at or datetime.min), reverse=True)
    elif sort == "company":
        jobs = sorted(jobs, key=lambda j: j.company.lower())

    # Stats
    all_jobs = session.exec(select(Job)).all()
    stats = {
        "total": len(all_jobs),
        "new": sum(1 for j in all_jobs if j.status == JobStatus.NEW),
        "applied": sum(1 for j in all_jobs if j.status == JobStatus.APPLIED),
        "interview": sum(1 for j in all_jobs if j.status == JobStatus.INTERVIEW),
        "excellent": sum(1 for j in all_jobs if (j.match_score or 0) >= 80),
        "good": sum(1 for j in all_jobs if 60 <= (j.match_score or 0) < 80),
        "unscored": sum(1 for j in all_jobs if j.match_score is None),
    }

    sources = sorted(set(j.source for j in all_jobs))

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "jobs": [job_to_dict(j) for j in jobs],
        "stats": stats,
        "sources": sources,
        "filters": {"status": status, "source": source, "min_score": min_score, "sort": sort},
        "scrape_status": scrape_status,
        "statuses": [s.value for s in JobStatus],
    })


@app.get("/job/{job_id}", response_class=HTMLResponse)
def job_detail(
    request: Request,
    job_id: int,
    session: Session = Depends(get_session),
):
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return templates.TemplateResponse("job_detail.html", {
        "request": request,
        "job": job_to_dict(job),
        "statuses": [s.value for s in JobStatus],
        "scrape_status": scrape_status,
    })


@app.get("/tracker", response_class=HTMLResponse)
def tracker(
    request: Request,
    session: Session = Depends(get_session),
):
    active_statuses = [
        JobStatus.REVIEWING, JobStatus.APPLIED,
        JobStatus.INTERVIEW, JobStatus.OFFER,
    ]
    jobs = session.exec(
        select(Job).where(Job.status.in_([s.value for s in active_statuses]))
    ).all()
    jobs = sorted(jobs, key=lambda j: (j.applied_date or date.min), reverse=True)

    today = date.today()
    overdue = [j for j in jobs if j.follow_up_date and j.follow_up_date <= today]

    return templates.TemplateResponse("tracker.html", {
        "request": request,
        "jobs": [job_to_dict(j) for j in jobs],
        "overdue_ids": {j.id for j in overdue},
        "statuses": [s.value for s in JobStatus],
        "scrape_status": scrape_status,
    })


@app.get("/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,
    session: Session = Depends(get_session),
):
    from database import get_settings
    import json
    s = get_settings(session)
    titles_raw = "\n".join(json.loads(s.target_titles or "[]"))
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "scrape_status": scrape_status,
        "settings": s,
        "titles_raw": titles_raw,
    })


@app.post("/api/settings")
def save_settings(
    owner_name: str = Form(""),
    resume_text: str = Form(""),
    target_titles_raw: str = Form(""),
    job_anticipations: str = Form(""),
    session: Session = Depends(get_session),
):
    from database import get_settings
    import json
    s = get_settings(session)
    if owner_name.strip():
        s.owner_name = owner_name.strip()
    s.resume_text = resume_text.strip()
    titles = [t.strip() for t in target_titles_raw.splitlines() if t.strip()]
    s.target_titles = json.dumps(titles)
    s.job_anticipations = job_anticipations.strip()
    from datetime import datetime
    s.updated_at = datetime.utcnow()
    session.add(s)
    session.commit()
    return RedirectResponse(url="/settings?saved=1", status_code=303)


# ── Routes: API ───────────────────────────────────────────────────────────────

@app.post("/api/scrape")
def trigger_scrape(background_tasks: BackgroundTasks):
    if scrape_status["running"]:
        return JSONResponse({"status": "already_running"})

    from database import engine
    from sqlmodel import Session as S

    def session_factory():
        return S(engine)

    background_tasks.add_task(_run_scrape, session_factory)
    return JSONResponse({"status": "started"})


@app.get("/api/scrape-status")
def get_scrape_status():
    return JSONResponse(scrape_status)


@app.post("/api/score")
def trigger_score(background_tasks: BackgroundTasks):
    """Score all unscored jobs in the database."""
    if scrape_status["running"]:
        return JSONResponse({"status": "already_running"})

    def _run_score():
        from database import engine
        from sqlmodel import Session as S
        scrape_status["running"] = True
        try:
            with S(engine) as session:
                scored = score_unscored_jobs(session)
            scrape_status["last_scored"] = scored
            logger.info(f"Manual score run complete: {scored} jobs scored")
        except Exception as e:
            logger.error(f"Score pipeline failed: {e}")
        finally:
            scrape_status["running"] = False

    background_tasks.add_task(_run_score)
    return JSONResponse({"status": "started"})


@app.post("/api/weekly-report")
def trigger_weekly_report(background_tasks: BackgroundTasks):
    """Manually trigger the weekly digest email (useful for testing)."""
    background_tasks.add_task(send_weekly_report)
    return JSONResponse({"status": "sending"})


@app.post("/api/jobs/{job_id}/update")
def update_job(
    job_id: int,
    status: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    applied_date: Optional[str] = Form(None),
    follow_up_date: Optional[str] = Form(None),
    contact_name: Optional[str] = Form(None),
    contact_email: Optional[str] = Form(None),
    session: Session = Depends(get_session),
):
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if status is not None:
        job.status = status
    if notes is not None:
        job.notes = notes
    if applied_date:
        job.applied_date = date.fromisoformat(applied_date)
    if follow_up_date:
        job.follow_up_date = date.fromisoformat(follow_up_date)
    if contact_name is not None:
        job.contact_name = contact_name
    if contact_email is not None:
        job.contact_email = contact_email

    session.add(job)
    session.commit()
    return RedirectResponse(url=f"/job/{job_id}", status_code=303)


@app.post("/api/jobs/{job_id}/rescore")
def trigger_rescore(
    job_id: int,
    session: Session = Depends(get_session),
):
    job = rescore_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return RedirectResponse(url=f"/job/{job_id}", status_code=303)


@app.delete("/api/jobs/{job_id}")
def delete_job(
    job_id: int,
    session: Session = Depends(get_session),
):
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    session.delete(job)
    session.commit()
    return JSONResponse({"status": "deleted"})


@app.get("/api/stats")
def get_stats(session: Session = Depends(get_session)):
    jobs = session.exec(select(Job)).all()
    return {
        "total": len(jobs),
        "by_status": {s.value: sum(1 for j in jobs if j.status == s.value) for s in JobStatus},
        "by_source": {},
        "score_dist": {
            "excellent": sum(1 for j in jobs if (j.match_score or 0) >= 80),
            "good": sum(1 for j in jobs if 60 <= (j.match_score or 0) < 80),
            "moderate": sum(1 for j in jobs if 40 <= (j.match_score or 0) < 60),
            "weak": sum(1 for j in jobs if 0 < (j.match_score or 0) < 40),
            "unscored": sum(1 for j in jobs if j.match_score is None),
        },
        "scrape_status": scrape_status,
    }
