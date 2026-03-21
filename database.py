"""
SQLite database setup using SQLModel.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, Session, SQLModel, create_engine, select, text

import os
_db_file = os.getenv("JOB_AGENT_DB", "jobs.db")
DATABASE_URL = f"sqlite:///./{_db_file}"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


class JobStatus(str, Enum):
    NEW = "new"
    REVIEWING = "reviewing"
    APPLIED = "applied"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class Job(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    # Core fields
    title: str
    company: str
    location: Optional[str] = None
    url: str = Field(unique=True, index=True)
    source: str  # e.g. "linkedin", "indeed", "wellfound", "jobs_vc", "direct"
    description: Optional[str] = None
    salary_range: Optional[str] = None
    is_remote: Optional[bool] = None
    posted_date: Optional[datetime] = None
    scraped_at: datetime = Field(default_factory=datetime.utcnow)

    # Claude scoring
    match_score: Optional[int] = None        # 0–100
    match_headline: Optional[str] = None     # one-line summary
    match_pros: Optional[str] = None         # JSON-encoded list[str]
    match_cons: Optional[str] = None         # JSON-encoded list[str]
    key_requirements: Optional[str] = None   # JSON-encoded list[str]
    scored_at: Optional[datetime] = None

    # Application tracking
    status: str = Field(default=JobStatus.NEW)
    notes: Optional[str] = None
    applied_date: Optional[date] = None
    follow_up_date: Optional[date] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None


class UserSettings(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_name: str = Field(default="Job Seeker")
    resume_text: str = Field(default="")          # full resume / profile text
    target_titles: str = Field(default="[]")      # JSON list[str] of target job titles
    job_anticipations: str = Field(default="")    # free-text: domains, preferences, seniority
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    total_jobs_ever: int = Field(default=0)       # lifetime count; preserved across flushes
    setup_complete: bool = Field(default=False)   # False triggers setup wizard on first run
    setup_step: int = Field(default=0)            # last completed step (0–4)


def alter_db():
    """Add new columns to existing tables without dropping data."""
    with engine.connect() as conn:
        existing = [r[1] for r in conn.execute(text("PRAGMA table_info(usersettings)"))]
        if "total_jobs_ever" not in existing:
            conn.execute(text("ALTER TABLE usersettings ADD COLUMN total_jobs_ever INTEGER DEFAULT 0"))
            # Initialise to current job count so the lifetime total is correct from migration
            count = conn.execute(text("SELECT COUNT(*) FROM job")).scalar() or 0
            conn.execute(text(f"UPDATE usersettings SET total_jobs_ever = {count}"))
        if "setup_complete" not in existing:
            conn.execute(text("ALTER TABLE usersettings ADD COLUMN setup_complete INTEGER DEFAULT 0"))
            # Existing installs are already set up — mark them complete
            conn.execute(text("UPDATE usersettings SET setup_complete = 1"))
        if "setup_step" not in existing:
            conn.execute(text("ALTER TABLE usersettings ADD COLUMN setup_step INTEGER DEFAULT 0"))
            conn.execute(text("UPDATE usersettings SET setup_step = 4"))
        conn.commit()


def create_db():
    SQLModel.metadata.create_all(engine)
    alter_db()


def get_session():
    with Session(engine) as session:
        yield session


def get_settings(session: Session) -> "UserSettings":
    """Return the single settings row, creating it with defaults if missing."""
    from config import PROFILE, SEARCH_QUERIES
    settings = session.exec(select(UserSettings)).first()
    if not settings:
        import json
        settings = UserSettings(
            owner_name="Job Seeker",
            resume_text=PROFILE.strip(),
            target_titles=json.dumps(SEARCH_QUERIES[:6]),
            job_anticipations="Describe the types of roles, domains, and seniority you are targeting.",
        )
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return settings


def upsert_job(session: Session, job_data: dict) -> tuple[Job, bool]:
    """
    Insert a new job or skip if URL already exists.
    Returns (job, created) where created=True if it was newly inserted.
    Increments UserSettings.total_jobs_ever on each new insertion.
    """
    existing = session.exec(select(Job).where(Job.url == job_data["url"])).first()
    if existing:
        return existing, False

    job = Job(**job_data)
    session.add(job)

    # Increment lifetime counter
    settings = session.exec(select(UserSettings)).first()
    if settings:
        settings.total_jobs_ever += 1
        session.add(settings)

    session.commit()
    session.refresh(job)
    return job, True
