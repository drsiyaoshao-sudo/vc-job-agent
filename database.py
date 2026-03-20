"""
SQLite database setup using SQLModel.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, Session, SQLModel, create_engine, select

DATABASE_URL = "sqlite:///./jobs.db"
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


def create_db():
    SQLModel.metadata.create_all(engine)


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
            owner_name="Siyao Shao",
            resume_text=PROFILE.strip(),
            target_titles=json.dumps([
                "Venture Capital Associate",
                "Investment Associate",
                "VC Analyst",
                "Investment Analyst",
                "Venture Principal",
                "CVC Associate",
            ]),
            job_anticipations="VC and CVC investor roles in deep-tech, hardware, AI, climate tech. "
                              "Open to Associate through Principal level. "
                              "Prefer early-stage funds and corporate venture arms.",
        )
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return settings


def upsert_job(session: Session, job_data: dict) -> tuple[Job, bool]:
    """
    Insert a new job or skip if URL already exists.
    Returns (job, created) where created=True if it was newly inserted.
    """
    existing = session.exec(select(Job).where(Job.url == job_data["url"])).first()
    if existing:
        return existing, False

    job = Job(**job_data)
    session.add(job)
    session.commit()
    session.refresh(job)
    return job, True
