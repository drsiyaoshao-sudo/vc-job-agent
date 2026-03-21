"""
Job Agent configuration — profile, search terms, and target firms.

Edit these values to match your own background and job targets, or update
everything from the web UI at /settings without touching this file.
"""

# ── Candidate profile (fallback — overridden by UserSettings.resume_text) ────
# Paste your resume or a summary here.  Claude reads this verbatim when scoring.
# The /settings UI lets you update it without editing code.
PROFILE = """
Name: [Your Name]
Current Role: [Your current title and company]
Location: [City, Country — remote preferences]
Target Role: [What you're looking for]

BACKGROUND
- [Degree, field, institution, year]
- [Most recent role: what you built, what you achieved]
- [Prior role: key accomplishment]

TECHNICAL SKILLS
- [Skill area 1]
- [Skill area 2]

DOMAIN EXPERTISE
- [Domain 1], [Domain 2], [Domain 3]

SUMMARY
[2–3 sentences on why you are a strong candidate for your target role type.]
"""

# ── Search queries (used by LinkedIn / Indeed scraper) ───────────────────────
# These are the literal search strings sent to job boards.
# Override at runtime via UserSettings.target_titles → profile.get_active_queries().
SEARCH_QUERIES = [
    "software engineer",
    "product manager",
    "data scientist",
]

# ── Wellfound / AngelList search terms ───────────────────────────────────────
WELLFOUND_QUERIES = [
    "software engineer",
    "product manager",
]

# ── VC-specific job board URLs ────────────────────────────────────────────────
VC_BOARD_URLS = {
    "jobs_vc": "https://jobs.vc",
}

# ── Direct firm career page URLs to watch ────────────────────────────────────
# Each entry is scraped for relevant job links on every run.
# Hard cap: 20 jobs per firm page.
#
# Example:
#   {"firm": "Acme Corp",  "url": "https://acme.com/careers"},
TARGET_FIRM_URLS: list[dict] = []

# ── Scraping settings ─────────────────────────────────────────────────────────
RESULTS_PER_QUERY = 20      # Jobs fetched per search query (hard cap per source)
HOURS_OLD = 168             # Only fetch jobs posted in the last 7 days
JOB_SITES = ["linkedin", "indeed"]  # python-jobspy site list

# ── Scoring thresholds ────────────────────────────────────────────────────────
SCORE_EXCELLENT = 80   # Green  — strong match
SCORE_GOOD = 60        # Yellow — good match with minor gaps
SCORE_MODERATE = 40    # Orange — adjacent / worth reviewing
# Below SCORE_MODERATE → red / probably skip
