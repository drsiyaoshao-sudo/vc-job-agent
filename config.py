"""
Job Agent configuration — profile, search terms, and target firms.
"""

# ── Siyao's profile used by Claude for job scoring ──────────────────────────
PROFILE = """
Name: Dr. Siyao Shao
Current Role: Chief Technology Officer, RECHO AI Inc. (Montréal, QC, Canada)
Location: Montréal, QC — open to remote or relocation globally.
Target Roles: Venture Capital Investor or Partner (VC and CVC); Founding Engineer at early-stage
  deep-tech startups (Seed–Series B); Principal/Staff Research Engineer; Technical Sales Engineer;
  Field Application Engineer (FAE); Solutions Engineer in hardware/AI/industrial domains

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

FIT SUMMARY
Siyao combines rare technical depth (PhD + patents + hands-on hardware/AI R&D) with
direct commercialization and fundraising experience. He has sat on the founder side,
built teams, closed enterprise pilots, and navigated pre-seed fundraising.

Target role types (in priority order):
1. VC/CVC investor or partner in deep-tech, hardware, AI, climate — ideal fit
2. Founding or staff engineer at Seed–Series B deep-tech startups (hardware, AI, IoT, MEMS)
3. Principal/lead research engineer applying PhD-level expertise in an industrial or startup context
4. Technical sales / solutions / field application engineer bridging deep-tech R&D and customers
   (FAE, Solutions Engineer, Sales Engineer in semiconductor, embedded AI, industrial IoT)
"""

# ── Search queries (used across all scrapers) ────────────────────────────────
SEARCH_QUERIES = [
    # VC / CVC investor roles
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

    # Founding / early-stage engineer (Seed–Series B)
    "founding engineer deep tech startup",
    "founding engineer hardware AI series A",
    "early stage engineer Series B startup",
    "staff engineer hardware startup",

    # Research engineer / scientist
    "principal research engineer AI hardware",
    "staff research engineer machine learning",
    "lead research engineer edge AI embedded",
    "research engineer MEMS sensor",

    # Technical sales / solutions
    "technical sales engineer hardware AI",
    "solutions engineer industrial IoT",
    "sales engineer deep tech startup",
    "technical account manager AI hardware",

    # Field application engineer
    "field application engineer semiconductor",
    "field application engineer embedded AI",
    "FAE hardware startup",
    "application engineer MEMS IoT",
]

# ── Wellfound / AngelList search terms ───────────────────────────────────────
WELLFOUND_QUERIES = [
    "venture capital",
    "investor deep tech",
    "CVC",
    "founding engineer",
    "hardware AI startup",
    "field application engineer",
    "technical sales engineer",
    "research engineer",
]

# ── VC-specific job board URLs ────────────────────────────────────────────────
VC_BOARD_URLS = {
    "jobs_vc": "https://jobs.vc",
}

# ── Direct VC/CVC firm career page URLs to watch ─────────────────────────────
# All URLs verified live. Each firm page is scraped for investor-relevant roles
# (venture, investor, principal, partner, associate, analyst, sourcing, portfolio).
# Hard cap: 20 jobs per firm page.
TARGET_FIRM_URLS: list[dict] = [

    # ── CVC (Corporate Venture Capital) ──────────────────────────────────────
    # Strong alignment with Siyao's deep-tech / hardware / AI / industrial profile
    {"firm": "TDK Ventures",            "url": "https://tdk-ventures.com/careers/"},
    {"firm": "Samsung Next",            "url": "https://www.samsungnext.com/careers"},
    {"firm": "Panasonic Ventures",      "url": "https://www.panasonicventures.com/careers"},
    {"firm": "Shell Ventures",          "url": "https://www.shell.com/careers.html"},
    {"firm": "Honeywell Ventures",      "url": "https://careers.honeywell.com"},
    {"firm": "ABB Technology Ventures", "url": "https://careers.abb/global/en"},
    {"firm": "Qualcomm Ventures",       "url": "https://www.qualcomm.com/company/careers"},
    {"firm": "Bosch Careers",           "url": "https://www.bosch.com/careers/"},
    {"firm": "Siemens Next47",          "url": "https://www.n47.com/"},

    # ── Deep-Tech / Hardware / AI VC ─────────────────────────────────────────
    {"firm": "DCVC",                    "url": "https://www.dcvc.com/careers"},
    {"firm": "In-Q-Tel",                "url": "https://www.iqt.org/careers/"},
    {"firm": "Lux Capital",             "url": "https://www.luxcapital.com/people"},
    {"firm": "Eclipse Ventures",        "url": "https://eclipse.capital/"},
    {"firm": "Root Ventures",           "url": "https://root.vc/"},
    {"firm": "Prelude Ventures",        "url": "https://www.preludeventures.com/team"},
    {"firm": "Obvious Ventures",        "url": "https://obvious.com/"},

    # ── Climate / Energy VC ───────────────────────────────────────────────────
    {"firm": "Energy Impact Partners",  "url": "https://www.energyimpactpartners.com/join-the-team/"},
    {"firm": "Congruent Ventures",      "url": "https://www.congruentvc.com/team"},
    {"firm": "Clean Energy Ventures",   "url": "https://cleanenergyventures.com/about/"},
    {"firm": "Chrysalix Energy VC",     "url": "https://www.chrysalix.com/"},

    # ── Canada-based ──────────────────────────────────────────────────────────
    {"firm": "BDC Capital",             "url": "https://www.bdc.ca/en/bdc-capital"},
    {"firm": "Real Ventures",           "url": "https://realventures.com/"},
    {"firm": "Inovia Capital",          "url": "https://www.inovia.vc/team/"},
    {"firm": "MaRS Discovery District", "url": "https://www.marsdd.com/careers/"},
]

# ── Scraping settings ─────────────────────────────────────────────────────────
RESULTS_PER_QUERY = 20      # Jobs fetched per search query (hard cap per source)
HOURS_OLD = 168             # Only fetch jobs posted in the last 7 days
JOB_SITES = ["linkedin", "indeed"]  # python-jobspy site list

# ── Scoring thresholds ────────────────────────────────────────────────────────
SCORE_EXCELLENT = 80   # Green  — strong VC/CVC match
SCORE_GOOD = 60        # Yellow — good match with minor gaps
SCORE_MODERATE = 40    # Orange — adjacent / worth reviewing
# Below SCORE_MODERATE → red / probably skip
