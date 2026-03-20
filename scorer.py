"""
Claude-powered job scoring module.
Uses claude-opus-4-6 with adaptive thinking + structured outputs
to evaluate how well each job matches Siyao's VC/CVC target profile.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

import anthropic
from pydantic import BaseModel
from sqlmodel import Session, select

from config import PROFILE
from database import Job
from notifier import notify_job

logger = logging.getLogger(__name__)

client = anthropic.Anthropic()

SYSTEM_PROMPT = f"""You are a career advisor helping Dr. Siyao Shao evaluate job postings for
Venture Capital investor and partner roles. Your job is to score how well a posting fits his
background and target career.

CANDIDATE PROFILE:
{PROFILE}

SCORING RUBRIC (0–100):
- 85–100: Excellent match — VC/CVC investor or partner role squarely in deep-tech, hardware,
          climate, AI/ML, or industrial domains; seniority (Associate → Partner) fits his background.
- 65–84:  Good match — VC/CVC role with slightly different domain or seniority, but clearly
          leverages his technical due-diligence skills and founder experience.
- 45–64:  Moderate — adjacent role (e.g., technology scout, innovation/strategy at a corporate,
          EIR at a fund) or a non-VC investor role that could pivot toward VC.
- 20–44:  Weak — mostly irrelevant to a VC career; maybe a deep-tech operating role.
- 0–19:   Not relevant — unrelated to VC/investing or Siyao's background entirely.

Return ONLY valid JSON — no markdown, no extra text.
"""


class JobMatchResult(BaseModel):
    score: int
    headline: str       # ≤ 15 words: "Strong CVC deep-tech role at Samsung Next — hardware focus"
    pros: list[str]     # 2–4 bullets: why it fits
    cons: list[str]     # 1–3 bullets: gaps or concerns
    key_requirements: list[str]  # 2–3 things to address in the application


def score_job(job: Job) -> JobMatchResult | None:
    """
    Score a single job using Claude. Returns None on failure.
    """
    if not job.description:
        # Score title+company only when there's no description
        content = f"Job Title: {job.title}\nCompany: {job.company}\nLocation: {job.location or 'Unknown'}"
    else:
        # Truncate very long descriptions to keep costs reasonable
        desc = job.description[:6000]
        content = (
            f"Job Title: {job.title}\n"
            f"Company: {job.company}\n"
            f"Location: {job.location or 'Unknown'}\n\n"
            f"DESCRIPTION:\n{desc}"
        )

    try:
        response = client.messages.parse(
            model="claude-opus-4-6",
            max_tokens=1024,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
            output_format=JobMatchResult,
        )
        result: JobMatchResult = response.parsed_output
        return result
    except Exception as e:
        logger.error(f"[scorer] Failed to score job {job.id} ({job.title}): {e}")
        return None


def score_unscored_jobs(session: Session) -> int:
    """
    Find all jobs without a match_score and score them with Claude.
    Returns the number of jobs scored.
    """
    jobs = session.exec(select(Job).where(Job.match_score == None)).all()  # noqa: E711
    count = 0
    for job in jobs:
        result = score_job(job)
        if result:
            job.match_score = result.score
            job.match_headline = result.headline
            job.match_pros = json.dumps(result.pros)
            job.match_cons = json.dumps(result.cons)
            job.key_requirements = json.dumps(result.key_requirements)
            job.scored_at = datetime.utcnow()
            session.add(job)
            session.commit()
            session.refresh(job)
            count += 1
            logger.info(f"[scorer] Scored '{job.title}' at {job.company}: {result.score}/100")

            # Fire notifications based on score (WhatsApp >90, email >75)
            notify_job(job)

    return count


def rescore_job(session: Session, job_id: int) -> Job | None:
    """Force re-score a specific job."""
    job = session.get(Job, job_id)
    if not job:
        return None
    result = score_job(job)
    if result:
        job.match_score = result.score
        job.match_headline = result.headline
        job.match_pros = json.dumps(result.pros)
        job.match_cons = json.dumps(result.cons)
        job.key_requirements = json.dumps(result.key_requirements)
        job.scored_at = datetime.utcnow()
        session.add(job)
        session.commit()
        session.refresh(job)
    return job
