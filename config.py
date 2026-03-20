"""
Job Agent configuration — profile, search terms, and target firms.
"""

# ── Siyao's profile used by Claude for job scoring ──────────────────────────
PROFILE = """
Name: Dr. Siyao Shao
Current Role: Chief Technology Officer, RECHO AI Inc. (Montréal, QC, Canada)
Location: Montréal, QC — open to remote or relocation globally.
Target Role: Venture Capital Investor or Partner (VC and CVC)

BACKGROUND
- Ph.D., Mechanical Engineering — University of Minnesota (2014–2020)
- Current CTO at RECHO AI: architected full-stack MEMS-based reservoir computing platform
  across industrial failure detection, consumer electronics, pest control.
  Raised $1.4M USD pre-seed; secured potential $1M ARR in evaluation contracts.
  Selected for Amazon's inaugural Device Climate Tech Accelerator (14 of 600+ applicants).
- Former Entrepreneur in Residence at TandemLaunch (deep-tech startup studio, 2022–2024):
  tech scouting & market analysis on low-cost ML computing; built & scaled a 5-person
  engineering team in under 2 years; recruited CEO and VP of Engineering.
- NSF I-Corps National Commercialization Fellow — completed full national program.
- Chief Science Officer of Particle4X (spinout from doctoral research).
- 25+ peer-reviewed papers in fluid mechanics, computer vision, machine learning.
- 3 US and international patents (computer vision, optical diagnostics, novel computing hardware).

TECHNICAL SKILLS
- MEMS, reservoir computing, edge AI / TinyML, embedded systems
- Computer vision, deep learning, signal processing
- Python, C/C++

VENTURE & STRATEGY SKILLS (directly relevant for VC)
- Technology scouting and competitive landscape analysis
- IP and patent strategy evaluation
- Deep-tech due diligence (hardware, AI/ML, climate tech, industrial systems)
- Market sizing and commercialization roadmapping
- Startup formation and founding-team assembly
- Pre-seed fundraising (raised $1.4M USD)
- Enterprise business development and investor relations

DOMAINS OF EXPERTISE
- Industrial IoT, climate tech, audio event detection, multiphase flow,
  renewable energy systems, biometrics, edge computing, hardware AI

VC FIT SUMMARY
Siyao combines rare technical depth (PhD + patents + hands-on hardware/AI R&D) with
direct commercialization and fundraising experience. He has sat on the founder side,
built teams, closed enterprise pilots, and navigated pre-seed fundraising — making him
uniquely qualified to evaluate and support deep-tech portfolio companies.
"""

# ── Search queries (used across all scrapers) ────────────────────────────────
SEARCH_QUERIES = [
    "venture capital investor deep tech",
    "venture capital partner hardware AI",
    "CVC investor technology",
    "corporate venture capital associate",
    "deep tech venture investor",
    "investment partner climate tech",
    "hardware venture capital principal",
    "venture capital associate industrial",
    "technology venture investor",
    "venture principal AI hardware",
]

# ── Wellfound / AngelList search terms ───────────────────────────────────────
WELLFOUND_QUERIES = [
    "venture capital",
    "investor deep tech",
    "CVC",
]

# ── VC-specific job board URLs ────────────────────────────────────────────────
VC_BOARD_URLS = {
    "jobs_vc": "https://jobs.vc",
}

# ── Direct VC/CVC firm career page URLs to watch ─────────────────────────────
# Add the career page URL of firms you specifically want to track.
TARGET_FIRM_URLS: list[dict] = [
    # {"firm": "Lux Capital",      "url": "https://www.luxcapital.com/careers"},
    # {"firm": "Breakthrough Energy Ventures", "url": "https://breakthroughenergy.org/our-work/venture/"},
    # {"firm": "DCVC",             "url": "https://www.dcvc.com/careers"},
    # {"firm": "In-Q-Tel",         "url": "https://www.iqt.org/careers/"},
    # {"firm": "BDC Capital",      "url": "https://www.bdc.ca/en/bdc-capital/industrial-innovation"},
    # {"firm": "Real Ventures",    "url": "https://realventures.com"},
]

# ── Scraping settings ─────────────────────────────────────────────────────────
RESULTS_PER_QUERY = 25      # Jobs fetched per search query
HOURS_OLD = 168             # Only fetch jobs posted in the last 7 days
JOB_SITES = ["linkedin", "indeed"]  # python-jobspy site list

# ── Scoring thresholds ────────────────────────────────────────────────────────
SCORE_EXCELLENT = 80   # Green  — strong VC/CVC match
SCORE_GOOD = 60        # Yellow — good match with minor gaps
SCORE_MODERATE = 40    # Orange — adjacent / worth reviewing
# Below SCORE_MODERATE → red / probably skip
