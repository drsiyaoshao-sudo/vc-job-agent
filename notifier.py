"""
Notification module.

  score > 90  →  WhatsApp message via CallMeBot (immediate)
  score > 75  →  Email via Gmail SMTP (immediate)
  weekly      →  Digest email of top new jobs + application status
"""
from __future__ import annotations

import logging
import os
import smtplib
import urllib.parse
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx
from sqlmodel import Session, select

from config import SCORE_EXCELLENT, SCORE_GOOD
from database import Job, JobStatus, engine

logger = logging.getLogger(__name__)

# ── Env vars ──────────────────────────────────────────────────────────────────
CALLMEBOT_PHONE  = os.getenv("CALLMEBOT_PHONE", "")      # e.g. 14388850126 (no +)
CALLMEBOT_APIKEY = os.getenv("CALLMEBOT_APIKEY", "")

GMAIL_USER     = os.getenv("GMAIL_USER", "")
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASS", "")
NOTIFY_EMAIL   = os.getenv("NOTIFY_EMAIL", GMAIL_USER)   # send-to address

SCORE_WHATSAPP = 90   # threshold for WhatsApp alert
SCORE_EMAIL    = 75   # threshold for email alert


# ── WhatsApp via CallMeBot ────────────────────────────────────────────────────

def send_whatsapp(message: str) -> bool:
    """
    Send a WhatsApp message via CallMeBot.
    One-time setup: send "I allow callmebot to send me messages" to +34 644 59 79 13
    on WhatsApp to get your API key.
    """
    if not CALLMEBOT_PHONE or not CALLMEBOT_APIKEY:
        logger.warning("[whatsapp] CALLMEBOT_PHONE or CALLMEBOT_APIKEY not set — skipping")
        return False

    encoded = urllib.parse.quote(message)
    url = f"https://api.callmebot.com/whatsapp.php?phone={CALLMEBOT_PHONE}&text={encoded}&apikey={CALLMEBOT_APIKEY}"
    try:
        resp = httpx.get(url, timeout=15)
        if resp.status_code == 200:
            logger.info("[whatsapp] Message sent successfully")
            return True
        logger.warning(f"[whatsapp] Unexpected status {resp.status_code}: {resp.text[:200]}")
        return False
    except Exception as e:
        logger.error(f"[whatsapp] Failed to send: {e}")
        return False


# ── Email via Gmail SMTP ──────────────────────────────────────────────────────

def send_email(subject: str, html_body: str, plain_body: str = "") -> bool:
    """Send an email via Gmail SMTP using an App Password."""
    if not GMAIL_USER or not GMAIL_APP_PASS:
        logger.warning("[email] GMAIL_USER or GMAIL_APP_PASS not set — skipping")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"VC Job Agent <{GMAIL_USER}>"
    msg["To"]      = NOTIFY_EMAIL

    if plain_body:
        msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(GMAIL_USER, GMAIL_APP_PASS)
            smtp.sendmail(GMAIL_USER, NOTIFY_EMAIL, msg.as_string())
        logger.info(f"[email] Sent: {subject}")
        return True
    except Exception as e:
        logger.error(f"[email] Failed to send '{subject}': {e}")
        return False


# ── Job notification helpers ──────────────────────────────────────────────────

def notify_job(job: Job) -> None:
    """
    Dispatch notifications based on match_score:
      > 90 → WhatsApp
      > 75 → email
    """
    score = job.match_score
    if score is None:
        return

    if score > SCORE_WHATSAPP:
        _send_whatsapp_alert(job)

    if score > SCORE_EMAIL:
        _send_email_alert(job)


def _send_whatsapp_alert(job: Job) -> None:
    score  = job.match_score
    stars  = "🌟" * (3 if score >= 95 else 2 if score >= 90 else 1)
    msg = (
        f"{stars} TOP VC MATCH — {score}/100\n\n"
        f"*{job.title}*\n"
        f"🏢 {job.company}\n"
        f"📍 {job.location or 'Location not listed'}\n"
        f"💡 {job.match_headline or ''}\n\n"
        f"🔗 {job.url}"
    )
    send_whatsapp(msg)


def _send_email_alert(job: Job) -> None:
    import json
    pros  = json.loads(job.match_pros)  if job.match_pros  else []
    cons  = json.loads(job.match_cons)  if job.match_cons  else []
    reqs  = json.loads(job.key_requirements) if job.key_requirements else []

    score       = job.match_score
    score_color = "#16a34a" if score >= 80 else "#ca8a04" if score >= 60 else "#ea580c"

    pros_html = "".join(f"<li>✅ {p}</li>" for p in pros)
    cons_html = "".join(f"<li>⚠️ {c}</li>" for c in cons)
    reqs_html = "".join(f"<li>→ {r}</li>" for r in reqs)

    html = f"""
    <div style="font-family:sans-serif;max-width:620px;margin:0 auto;background:#111;color:#e5e7eb;padding:24px;border-radius:12px;">
      <div style="border-bottom:1px solid #374151;padding-bottom:16px;margin-bottom:20px;">
        <h2 style="margin:0;color:#a78bfa;">VC Job Alert</h2>
        <p style="margin:4px 0 0;color:#9ca3af;font-size:13px;">New match above {SCORE_EMAIL}/100 threshold</p>
      </div>

      <div style="display:flex;align-items:center;gap:16px;margin-bottom:20px;">
        <div style="width:60px;height:60px;border-radius:50%;background:{score_color};display:flex;align-items:center;
          justify-content:center;font-size:20px;font-weight:bold;color:#fff;flex-shrink:0;">{score}</div>
        <div>
          <h3 style="margin:0;color:#f9fafb;">{job.title}</h3>
          <p style="margin:2px 0 0;color:#9ca3af;font-size:14px;">{job.company} · {job.location or 'Remote/Unknown'}</p>
          <p style="margin:4px 0 0;color:#d1d5db;font-size:13px;font-style:italic;">{job.match_headline or ''}</p>
        </div>
      </div>

      {"<div style='margin-bottom:16px;'><h4 style='color:#34d399;margin:0 0 6px;font-size:13px;'>WHY IT FITS</h4><ul style='margin:0;padding-left:20px;color:#d1d5db;font-size:14px;'>" + pros_html + "</ul></div>" if pros else ""}
      {"<div style='margin-bottom:16px;'><h4 style='color:#f87171;margin:0 0 6px;font-size:13px;'>CONCERNS</h4><ul style='margin:0;padding-left:20px;color:#d1d5db;font-size:14px;'>" + cons_html + "</ul></div>" if cons else ""}
      {"<div style='margin-bottom:20px;'><h4 style='color:#fbbf24;margin:0 0 6px;font-size:13px;'>ADDRESS IN APPLICATION</h4><ul style='margin:0;padding-left:20px;color:#d1d5db;font-size:14px;'>" + reqs_html + "</ul></div>" if reqs else ""}

      <a href="{job.url}" style="display:inline-block;background:#7c3aed;color:#fff;padding:10px 20px;
        border-radius:8px;text-decoration:none;font-size:14px;font-weight:500;">View Job Posting →</a>

      <p style="margin-top:20px;color:#4b5563;font-size:12px;">
        Source: {job.source} · Scored {datetime.utcnow().strftime('%b %d, %Y')}
      </p>
    </div>
    """

    plain = (
        f"VC Job Alert — {score}/100\n\n"
        f"{job.title} at {job.company}\n"
        f"{job.location or 'Remote/Unknown'}\n\n"
        f"{job.match_headline or ''}\n\n"
        f"Link: {job.url}\n"
    )

    send_email(
        subject=f"[VC Alert {score}/100] {job.title} @ {job.company}",
        html_body=html,
        plain_body=plain,
    )


# ── Weekly report ─────────────────────────────────────────────────────────────

def send_weekly_report() -> bool:
    """
    Generate and email a weekly digest:
    - Top new jobs from the past 7 days (sorted by score)
    - Current application pipeline status
    """
    with Session(engine) as session:
        cutoff = datetime.utcnow() - timedelta(days=7)

        new_jobs = session.exec(
            select(Job)
            .where(Job.scraped_at >= cutoff)
            .order_by(Job.match_score.desc())  # type: ignore
        ).all()

        active_jobs = session.exec(
            select(Job).where(
                Job.status.in_([  # type: ignore
                    JobStatus.REVIEWING, JobStatus.APPLIED,
                    JobStatus.INTERVIEW, JobStatus.OFFER,
                ])
            )
        ).all()

    if not new_jobs and not active_jobs:
        logger.info("[weekly] Nothing to report — skipping")
        return False

    week_end   = datetime.utcnow().strftime("%b %d, %Y")
    week_start = (datetime.utcnow() - timedelta(days=7)).strftime("%b %d")
    subject    = f"Weekly VC Job Digest — {week_start}–{week_end}"

    html = _build_weekly_html(new_jobs, active_jobs, week_start, week_end)
    plain = _build_weekly_plain(new_jobs, active_jobs)

    return send_email(subject=subject, html_body=html, plain_body=plain)


def _score_badge(score):
    if score is None:
        return "<span style='background:#374151;color:#9ca3af;padding:2px 8px;border-radius:12px;font-size:12px;font-weight:bold;'>–</span>"
    color = "#16a34a" if score >= 80 else "#ca8a04" if score >= 60 else "#ea580c" if score >= 40 else "#dc2626"
    return f"<span style='background:{color};color:#fff;padding:2px 8px;border-radius:12px;font-size:12px;font-weight:bold;'>{score}</span>"


def _job_row(job: Job) -> str:
    badge = _score_badge(job.match_score)
    headline = f"<br><span style='color:#9ca3af;font-size:12px;font-style:italic;'>{job.match_headline}</span>" if job.match_headline else ""
    return f"""
    <tr style='border-bottom:1px solid #1f2937;'>
      <td style='padding:10px 8px;'>
        <a href='{job.url}' style='color:#a78bfa;text-decoration:none;font-weight:500;'>{job.title}</a>
        {headline}
      </td>
      <td style='padding:10px 8px;color:#d1d5db;font-size:13px;'>{job.company}</td>
      <td style='padding:10px 8px;'>{badge}</td>
      <td style='padding:10px 8px;'>
        <span style='background:#1f2937;color:#9ca3af;padding:2px 8px;border-radius:12px;font-size:11px;'>{job.source}</span>
      </td>
    </tr>"""


def _pipeline_row(job: Job) -> str:
    status_colors = {
        "reviewing": "#1d4ed8", "applied": "#065f46",
        "interview": "#92400e", "offer": "#14532d",
    }
    color = status_colors.get(job.status, "#374151")
    followup = f" · follow-up {job.follow_up_date}" if job.follow_up_date else ""
    return f"""
    <tr style='border-bottom:1px solid #1f2937;'>
      <td style='padding:10px 8px;'>
        <a href='{job.url}' style='color:#a78bfa;text-decoration:none;font-weight:500;'>{job.title}</a>
      </td>
      <td style='padding:10px 8px;color:#d1d5db;font-size:13px;'>{job.company}</td>
      <td style='padding:10px 8px;'>
        <span style='background:{color};color:#e5e7eb;padding:2px 8px;border-radius:12px;font-size:11px;'>{job.status}</span>
      </td>
      <td style='padding:10px 8px;color:#6b7280;font-size:12px;'>{job.applied_date or '—'}{followup}</td>
    </tr>"""


def _build_weekly_html(new_jobs, active_jobs, week_start, week_end) -> str:
    top_jobs    = [j for j in new_jobs if (j.match_score or 0) >= 60][:15]
    other_jobs  = [j for j in new_jobs if (j.match_score or 0) < 60][:10]

    top_rows   = "".join(_job_row(j) for j in top_jobs)   or "<tr><td colspan='4' style='padding:12px;color:#6b7280;text-align:center;'>No high-score jobs this week</td></tr>"
    other_rows = "".join(_job_row(j) for j in other_jobs) or "<tr><td colspan='4' style='padding:12px;color:#6b7280;text-align:center;'>None</td></tr>"
    pipeline_rows = "".join(_pipeline_row(j) for j in active_jobs) or "<tr><td colspan='4' style='padding:12px;color:#6b7280;text-align:center;'>No active applications</td></tr>"

    table_style = "width:100%;border-collapse:collapse;font-size:14px;"
    th_style    = "text-align:left;padding:8px;color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.05em;border-bottom:1px solid #374151;"

    return f"""
    <div style="font-family:sans-serif;max-width:700px;margin:0 auto;background:#111;color:#e5e7eb;padding:28px;border-radius:12px;">

      <!-- Header -->
      <div style="border-bottom:1px solid #374151;padding-bottom:20px;margin-bottom:24px;">
        <h2 style="margin:0;color:#a78bfa;font-size:20px;">Weekly VC Job Digest</h2>
        <p style="margin:4px 0 0;color:#9ca3af;font-size:13px;">{week_start} – {week_end} · {len(new_jobs)} new jobs found</p>
      </div>

      <!-- Summary pills -->
      <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:24px;">
        <div style="background:#7c3aed33;border:1px solid #7c3aed55;padding:10px 16px;border-radius:10px;text-align:center;">
          <div style="font-size:22px;font-weight:bold;color:#a78bfa;">{len(new_jobs)}</div>
          <div style="font-size:11px;color:#9ca3af;">New Jobs</div>
        </div>
        <div style="background:#16a34a33;border:1px solid #16a34a55;padding:10px 16px;border-radius:10px;text-align:center;">
          <div style="font-size:22px;font-weight:bold;color:#4ade80;">{sum(1 for j in new_jobs if (j.match_score or 0) >= 80)}</div>
          <div style="font-size:11px;color:#9ca3af;">Score 80+</div>
        </div>
        <div style="background:#92400e33;border:1px solid #92400e55;padding:10px 16px;border-radius:10px;text-align:center;">
          <div style="font-size:22px;font-weight:bold;color:#fbbf24;">{len(active_jobs)}</div>
          <div style="font-size:11px;color:#9ca3af;">In Pipeline</div>
        </div>
      </div>

      <!-- Top matches -->
      <h3 style="color:#f9fafb;font-size:14px;margin:0 0 10px;">🎯 Top Matches (score ≥ 60)</h3>
      <table style="{table_style}">
        <thead><tr>
          <th style="{th_style}">Role</th>
          <th style="{th_style}">Company</th>
          <th style="{th_style}">Score</th>
          <th style="{th_style}">Source</th>
        </tr></thead>
        <tbody>{top_rows}</tbody>
      </table>

      <!-- Other new jobs -->
      <h3 style="color:#f9fafb;font-size:14px;margin:24px 0 10px;">📋 Other New Jobs</h3>
      <table style="{table_style}">
        <thead><tr>
          <th style="{th_style}">Role</th>
          <th style="{th_style}">Company</th>
          <th style="{th_style}">Score</th>
          <th style="{th_style}">Source</th>
        </tr></thead>
        <tbody>{other_rows}</tbody>
      </table>

      <!-- Application pipeline -->
      <h3 style="color:#f9fafb;font-size:14px;margin:24px 0 10px;">📊 Your Application Pipeline</h3>
      <table style="{table_style}">
        <thead><tr>
          <th style="{th_style}">Role</th>
          <th style="{th_style}">Company</th>
          <th style="{th_style}">Status</th>
          <th style="{th_style}">Date</th>
        </tr></thead>
        <tbody>{pipeline_rows}</tbody>
      </table>

      <div style="margin-top:24px;padding-top:20px;border-top:1px solid #374151;text-align:center;">
        <p style="color:#4b5563;font-size:12px;margin:0;">
          VC Job Agent · Powered by Claude · Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
        </p>
      </div>
    </div>
    """


def _build_weekly_plain(new_jobs, active_jobs) -> str:
    lines = [
        f"WEEKLY VC JOB DIGEST — {len(new_jobs)} new jobs\n",
        "=" * 50,
        "\nTOP MATCHES (score ≥ 60):",
    ]
    top = [j for j in new_jobs if (j.match_score or 0) >= 60][:15]
    for j in top:
        lines.append(f"  [{j.match_score}/100] {j.title} @ {j.company}  →  {j.url}")

    lines += ["\nAPPLICATION PIPELINE:"]
    for j in active_jobs:
        lines.append(f"  [{j.status.upper()}] {j.title} @ {j.company}  (applied: {j.applied_date or 'N/A'})")

    return "\n".join(lines)


# ── Daily health check ────────────────────────────────────────────────────────

def send_health_check() -> bool:
    """
    Send a daily 8 AM status email confirming the agent is alive,
    with a snapshot of today's activity and pipeline.
    """
    now = datetime.utcnow()
    cutoff_24h = now - timedelta(hours=24)

    with Session(engine) as session:
        all_jobs    = session.exec(select(Job)).all()
        new_today   = [j for j in all_jobs if j.scraped_at and j.scraped_at >= cutoff_24h]
        top_today   = sorted([j for j in new_today if (j.match_score or 0) >= 60],
                             key=lambda j: j.match_score or 0, reverse=True)[:5]
        pipeline    = [j for j in all_jobs if j.status in (
                           JobStatus.REVIEWING, JobStatus.APPLIED,
                           JobStatus.INTERVIEW, JobStatus.OFFER)]
        unscored    = sum(1 for j in all_jobs if j.match_score is None)
        excellent   = sum(1 for j in all_jobs if (j.match_score or 0) >= 80)

    date_str = now.strftime("%A, %b %d %Y")
    time_str = now.strftime("%H:%M UTC")

    # Build top-jobs rows
    rows = ""
    for j in top_today:
        color = "#16a34a" if (j.match_score or 0) >= 80 else "#ca8a04"
        rows += f"""
        <tr style='border-bottom:1px solid #1f2937;'>
          <td style='padding:8px;'>
            <a href='http://localhost:8000/job/{j.id}'
               style='color:#a78bfa;text-decoration:none;font-size:13px;'>{j.title}</a>
            <div style='color:#6b7280;font-size:11px;'>{j.company}</div>
          </td>
          <td style='padding:8px;text-align:center;'>
            <span style='background:{color};color:#fff;padding:2px 8px;border-radius:10px;
              font-size:12px;font-weight:bold;'>{j.match_score}</span>
          </td>
          <td style='padding:8px;color:#6b7280;font-size:12px;'>{j.source}</td>
        </tr>"""

    if not rows:
        rows = "<tr><td colspan='3' style='padding:10px;color:#6b7280;text-align:center;font-size:13px;'>No high-score jobs scraped in the last 24 h</td></tr>"

    pipeline_rows = ""
    for j in pipeline:
        status_color = {"reviewing":"#1d4ed8","applied":"#065f46","interview":"#92400e","offer":"#14532d"}.get(j.status,"#374151")
        pipeline_rows += f"""
        <tr style='border-bottom:1px solid #1f2937;'>
          <td style='padding:8px;color:#d1d5db;font-size:13px;'>{j.title}</td>
          <td style='padding:8px;color:#9ca3af;font-size:12px;'>{j.company}</td>
          <td style='padding:8px;'>
            <span style='background:{status_color};color:#e5e7eb;padding:2px 8px;
              border-radius:10px;font-size:11px;'>{j.status}</span>
          </td>
        </tr>"""

    if not pipeline_rows:
        pipeline_rows = "<tr><td colspan='3' style='padding:10px;color:#6b7280;text-align:center;font-size:13px;'>No active applications</td></tr>"

    th = "text-align:left;padding:6px 8px;color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.05em;border-bottom:1px solid #374151;"

    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;background:#111;color:#e5e7eb;padding:24px;border-radius:12px;">

      <!-- Header -->
      <div style="display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #374151;padding-bottom:16px;margin-bottom:20px;">
        <div>
          <h2 style="margin:0;color:#a78bfa;font-size:18px;">VC Job Agent — Daily Check-in</h2>
          <p style="margin:4px 0 0;color:#6b7280;font-size:12px;">{date_str} · {time_str}</p>
        </div>
        <div style="background:#16a34a;color:#fff;padding:6px 14px;border-radius:20px;font-size:13px;font-weight:600;">
          ✓ Running
        </div>
      </div>

      <!-- Stats row -->
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px;">
        <div style="flex:1;min-width:100px;background:#1f2937;border-radius:10px;padding:12px;text-align:center;">
          <div style="font-size:22px;font-weight:bold;color:#a78bfa;">{len(new_today)}</div>
          <div style="font-size:11px;color:#9ca3af;">New (24 h)</div>
        </div>
        <div style="flex:1;min-width:100px;background:#1f2937;border-radius:10px;padding:12px;text-align:center;">
          <div style="font-size:22px;font-weight:bold;color:#4ade80;">{excellent}</div>
          <div style="font-size:11px;color:#9ca3af;">Score 80+</div>
        </div>
        <div style="flex:1;min-width:100px;background:#1f2937;border-radius:10px;padding:12px;text-align:center;">
          <div style="font-size:22px;font-weight:bold;color:#fbbf24;">{len(pipeline)}</div>
          <div style="font-size:11px;color:#9ca3af;">In Pipeline</div>
        </div>
        <div style="flex:1;min-width:100px;background:#1f2937;border-radius:10px;padding:12px;text-align:center;">
          <div style="font-size:22px;font-weight:bold;color:#d1d5db;">{len(all_jobs)}</div>
          <div style="font-size:11px;color:#9ca3af;">Total Jobs</div>
        </div>
      </div>

      <!-- Top new jobs -->
      <h3 style="color:#f9fafb;font-size:13px;margin:0 0 8px;">🎯 Top New Matches (last 24 h)</h3>
      <table style="width:100%;border-collapse:collapse;margin-bottom:20px;">
        <thead><tr>
          <th style="{th}">Role</th>
          <th style="{th}">Score</th>
          <th style="{th}">Source</th>
        </tr></thead>
        <tbody>{rows}</tbody>
      </table>

      <!-- Pipeline -->
      <h3 style="color:#f9fafb;font-size:13px;margin:0 0 8px;">📋 Active Applications</h3>
      <table style="width:100%;border-collapse:collapse;margin-bottom:20px;">
        <thead><tr>
          <th style="{th}">Role</th>
          <th style="{th}">Company</th>
          <th style="{th}">Status</th>
        </tr></thead>
        <tbody>{pipeline_rows}</tbody>
      </table>

      <!-- Footer -->
      <div style="text-align:center;padding-top:16px;border-top:1px solid #374151;">
        <a href="http://localhost:8000"
           style="display:inline-block;background:#7c3aed;color:#fff;padding:8px 20px;
             border-radius:8px;text-decoration:none;font-size:13px;font-weight:500;">
          Open Dashboard →
        </a>
        {"<p style='color:#ef4444;font-size:12px;margin-top:10px;'>⚠ " + str(unscored) + " jobs still unscored — Claude may need attention</p>" if unscored > 10 else ""}
      </div>
    </div>
    """

    plain = (
        f"VC Job Agent — Daily Check-in ({date_str})\n"
        f"Status: RUNNING ✓\n\n"
        f"New jobs (24h): {len(new_today)}\n"
        f"Score 80+: {excellent}\n"
        f"In pipeline: {len(pipeline)}\n"
        f"Total: {len(all_jobs)}\n\n"
        f"Dashboard: http://localhost:8000\n"
    )

    return send_email(
        subject=f"✓ VC Job Agent running — {len(new_today)} new jobs today ({date_str})",
        html_body=html,
        plain_body=plain,
    )

    return "\n".join(lines)
