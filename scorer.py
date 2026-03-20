"""
Claude-powered job scoring module.
Uses claude-opus-4-6 with adaptive thinking + structured outputs
to evaluate how well each job matches the candidate's target profile.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

import anthropic
from pydantic import BaseModel
from sqlmodel import Session, select

from database import Job
from notifier import notify_job
from scorer_fallback import score_job_fallback

logger = logging.getLogger(__name__)


def _build_system_prompt(profile_text: str) -> str:
    return f"""You are a career advisor helping evaluate job postings for the following candidate.
Score how well each posting fits their background and target career.

CANDIDATE PROFILE:
{profile_text}

SCORING RUBRIC (0–100):
- 85–100: Excellent match — role squarely fits their target, domain, and seniority.
- 65–84:  Good match — clearly leverages their skills with minor gaps.
- 45–64:  Moderate — adjacent role that could pivot toward their target.
- 20–44:  Weak — mostly irrelevant to their career target.
- 0–19:   Not relevant.

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

    from database import engine, get_settings
    from sqlmodel import Session as _S
    with _S(engine) as _sess:
        _settings = get_settings(_sess)
    from profile import get_profile_text
    _profile = get_profile_text(_settings)
    system = _build_system_prompt(_profile)

    try:
        client = anthropic.Anthropic()
        response = client.messages.parse(
            model="claude-opus-4-6",
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": content}],
            output_format=JobMatchResult,
        )
        result: JobMatchResult = response.parsed_output
        return result
    except Exception as e:
        logger.warning(f"[scorer] Claude failed for job {job.id} ({job.title}): {e} — using fallback scorer")
        fb = score_job_fallback(
            title=job.title,
            company=job.company,
            description=job.description,
            location=job.location,
            profile_text=_profile,
        )
        return JobMatchResult(
            score=fb["score"],
            headline=fb["headline"] + " [fallback]",
            pros=fb["pros"],
            cons=fb["cons"],
            key_requirements=fb["key_requirements"],
        )


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

            # Fire notifications — never let a notification failure crash the scoring loop
            try:
                notify_job(job)
            except Exception as notify_err:
                logger.warning(f"[scorer] Notification failed for job {job.id}: {notify_err}")

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
