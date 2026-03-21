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

TARGET ROLE TYPES (ALL are primary targets — score each appropriately):
1. VC/CVC investor or partner in deep-tech, hardware, AI, or climate tech
2. Founding engineer or staff engineer at Seed–Series B deep-tech startups (hardware, AI, IoT, MEMS)
3. Principal / lead / staff research engineer in MEMS, edge AI, embedded systems, or industrial tech
4. Field Application Engineer (FAE), Solutions Engineer, Technical Sales Engineer, or Pre-Sales Engineer
   in hardware, semiconductor, industrial IoT, or AI domains

SCORING RUBRIC (0–100):
- 85–100: Excellent — squarely fits one of the 4 target types above AND domain/seniority align.
          Examples: VC/CVC deep-tech partner; founding engineer at hardware AI seed startup;
          principal research engineer in MEMS/edge AI; FAE at semiconductor company.
- 65–84:  Good — fits a target type with minor gaps (slightly off domain, seniority, or location).
          Examples: VC associate in adjacent domain; senior engineer at Series C+ startup;
          solutions engineer in adjacent sector; research engineer without senior title;
          EIR at a VC/CVC fund or deep-tech accelerator/studio.
- 45–64:  Moderate — adjacent or transferable (tech scout, product engineer, corporate R&D,
          innovation manager, EIR at non-VC corporate).
- 20–44:  Weak — general engineering without deep-tech, startup, or investor angle.
- 0–19:   Not relevant — unrelated to any of the 4 target types.

IMPORTANT: FAE, solutions engineer, technical sales engineer, and founding/staff engineer roles
in hardware, semiconductor, IoT, or AI should score 65–100 depending on domain fit — they are
PRIMARY targets, NOT secondary or adjacent roles.

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


DAILY_CLAUDE_CAP = 50  # Max Claude API scoring calls per UTC day


def _claude_scored_today(session: Session) -> int:
    """Count jobs scored by Claude (not fallback) since UTC midnight."""
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    jobs = session.exec(select(Job).where(Job.scored_at >= today)).all()
    return sum(1 for j in jobs if "[fallback]" not in (j.match_headline or ""))


def score_unscored_jobs(session: Session) -> int:
    """
    Find all jobs without a match_score and score them with Claude.
    Only processes jobs where match_score IS NULL — already-scored jobs
    (including fallback-scored ones) are never touched.
    Stops when the daily Claude cap is reached.
    Returns the number of jobs scored this run.
    """
    jobs = session.exec(select(Job).where(Job.match_score == None)).all()  # noqa: E711
    if not jobs:
        return 0

    claude_used = _claude_scored_today(session)
    remaining_cap = DAILY_CLAUDE_CAP - claude_used
    if remaining_cap <= 0:
        logger.info(f"[scorer] Daily Claude cap ({DAILY_CLAUDE_CAP}) already reached — skipping {len(jobs)} unscored jobs")
        return 0

    count = 0
    for job in jobs:
        if count >= remaining_cap:
            skipped = len(jobs) - count
            logger.info(f"[scorer] Daily Claude cap ({DAILY_CLAUDE_CAP}) reached — {skipped} jobs deferred to next run")
            break

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
