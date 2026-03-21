"""
Fallback job scorer — no Claude API required.

Three-layer scoring:
  1. Title match   (0-45 pts) — role keywords in the job title across 4 buckets:
                                VC/investor, founding engineer, research engineer, FAE/tech sales
  2. Domain match  (0-35 pts) — deep-tech / VC domain keywords in description
  3. TF-IDF cosine (0-20 pts) — overall text similarity to Siyao's profile

Total maps to 0-100.  Penalties applied for junior roles and roles with no
relevant signals across any of the 4 target buckets.
Used automatically when Claude is unavailable or the API call fails.
"""
from __future__ import annotations

import hashlib as _hashlib
import math
import re
from typing import Optional

_profile_cache: dict = {}   # hash → (tokens, idf)


def _get_profile_vectors(profile_text: str) -> tuple[list, dict]:
    """Cache TF-IDF vectors per unique profile text (by hash)."""
    h = _hashlib.md5(profile_text.encode()).hexdigest()
    if h not in _profile_cache:
        tokens = _tokenize(profile_text)
        freq: dict[str, int] = {}
        for t in tokens:
            freq[t] = freq.get(t, 0) + 1
        idf = {w: 1.0 / (1.0 + math.log(1 + cnt)) for w, cnt in freq.items()}
        _profile_cache[h] = (tokens, idf)
    return _profile_cache[h]


# ── Role-title keywords (checked against job TITLE) ──────────────────────────
# Each entry: (keywords, points, label, bucket)
# Buckets: "vc", "founding", "research", "sales"

TITLE_SIGNALS: list[tuple[list[str], int, str, str]] = [
    # ── Specific compound titles first (avoid false positives from single-word matches) ──

    # ── FAE / technical sales / solutions ────────────────────────────────────
    (["field application engineer", "fae"],                                    43, "Field Application Engineer",  "sales"),
    (["pre-sales engineer", "presales engineer", "pre sales engineer"],        35, "Pre-sales engineer role",     "sales"),
    (["technical sales engineer", "sales engineer"],                           36, "Technical sales engineer",    "sales"),
    (["technical account manager"],                                             33, "Technical account manager",   "sales"),
    (["solutions engineer", "solutions architect"],                             38, "Solutions engineer role",     "sales"),
    (["application engineer"],                                                  38, "Application engineer role",   "sales"),

    # ── Research engineer / scientist (compound phrases before bare 'principal') ─
    (["principal research", "principal scientist", "principal researcher"],    43, "Principal research role",     "research"),
    (["staff research", "staff scientist", "staff researcher"],                40, "Staff research role",         "research"),
    (["lead research", "research lead", "senior research", "sr. research"],    37, "Senior research role",        "research"),
    (["research engineer", "research scientist", "research specialist"],       32, "Research engineer role",      "research"),

    # ── Founding / early-stage engineer ──────────────────────────────────────
    (["founding engineer", "founding software", "founding hardware"],          45, "Founding engineer role",      "founding"),
    (["staff engineer", "staff software", "staff hardware"],                   40, "Staff engineer role",         "founding"),
    (["early stage engineer", "early-stage engineer"],                         38, "Early-stage engineer role",   "founding"),
    (["principal engineer", "senior staff engineer"],                          35, "Principal engineer role",     "founding"),
    (["senior engineer", "lead engineer", "sr. engineer", "sr engineer"],      30, "Senior/lead engineer role",   "founding"),

    # ── VC / investor ────────────────────────────────────────────────────────
    (["general partner", "managing partner", "investment partner"],            45, "Partner-level VC role",       "vc"),
    (["venture partner", "operating partner"],                                 42, "Partner-level VC role",       "vc"),
    (["investment principal", "venture principal"],                            42, "Principal-level VC role",     "vc"),
    (["senior associate", "senior investment", "senior venture"],              38, "Senior Associate VC role",    "vc"),
    (["investment analyst", "venture analyst", "vc analyst", "cvc analyst"],  35, "VC Analyst role",             "vc"),
    (["investment associate", "venture associate", "vc associate"],            35, "VC Associate role",           "vc"),
    (["investor", "vc investor", "cvc investor", "venture investor"],         32, "Investor title",              "vc"),
    (["partner"],                                                              40, "Partner-level VC role",       "vc"),
    (["principal"],                                                            30, "Principal-level VC role",     "vc"),
    (["associate", "analyst"],                                                 28, "Associate/Analyst role",      "vc"),
    (["eir", "entrepreneur in residence"],                                     38, "EIR role",                    "vc"),
    (["technology scout", "tech scout", "deal sourcing"],                      22, "Scout/Sourcing role",         "vc"),
    (["innovation", "technology strategy", "corporate development"],           15, "Innovation/Strategy role",    "vc"),
]

# ── Domain keywords (checked against full text) ───────────────────────────────

DOMAIN_GROUPS: list[tuple[list[str], int, str]] = [
    # Hardware / deep-tech — Siyao's core expertise
    (["mems", "sensors", "semiconductor", "hardware", "embedded", "photonics",
      "advanced materials", "edge ai", "tinyml", "reservoir computing",
      "neuromorphic", "fpga", "asic", "microelectronics"],                    12, "hardware/deep-tech domain"),

    # Energy / climate / industrial
    (["energy storage", "battery", "cleantech", "climate tech", "renewable energy",
      "industrial iot", "industrial automation", "smart grid", "electrification"],
                                                                               10, "climate/energy domain"),

    # AI / ML
    (["artificial intelligence", "machine learning", "deep learning",
      "computer vision", "ai/ml", "ai hardware", "neural network"],           8,  "AI/ML domain"),

    # General IoT / connectivity
    (["iot", "internet of things", "connected devices", "wireless", "5g"],    6,  "IoT/connectivity domain"),

    # CVC / corporate venture
    (["corporate venture", "cvc", "strategic investment", "corporate innovation",
      "technology venture"],                                                   10, "CVC alignment"),

    # Startup ecosystem fit
    (["early stage", "seed stage", "pre-seed", "series a", "due diligence",
      "deal flow", "portfolio companies", "startup", "founder", "commercialization",
      "ip strategy", "patent"],                                                8,  "startup/VC ecosystem"),

    # Canada / remote
    (["canada", "montreal", "toronto", "remote", "global", "hybrid"],         4,  "location fit"),
]

# ── Established big-tech / large-company penalty ─────────────────────────────
# These companies are not aligned with an early-stage hardware-first VC profile.
# Roles there get a 55% score reduction regardless of title match.
BIG_TECH = {
    "google", "deepmind", "meta", "facebook", "instagram", "whatsapp",
    "amazon", "aws", "apple", "netflix", "microsoft", "openai", "anthropic",
    "nvidia", "intel", "qualcomm", "ibm", "oracle", "salesforce",
    "uber", "lyft", "airbnb", "twitter", "x corp", "bytedance", "tiktok",
    "samsung", "lg electronics", "sony", "tesla", "spacex",
    "adobe", "sap", "vmware", "palantir", "snowflake", "databricks",
    "stripe", "square", "block", "paypal", "visa", "mastercard",
    "jpmorgan", "goldman sachs", "morgan stanley", "blackrock",
    "cisco", "broadcom", "amd", "arm",
}

# ── Core signals — if NONE present across any target bucket, apply penalty ───
# A job needs at least one signal from any target role bucket to avoid the penalty.
CORE_SIGNALS = [
    # VC/investor
    "venture", "investment", "investor", "capital", "fund", "portfolio",
    "associate", "principal", "partner", "analyst",
    "eir", "entrepreneur in residence",
    # Founding / early-stage
    "founding", "seed", "series a", "series b", "early stage", "early-stage",
    "startup",
    # Research
    "research engineer", "research scientist", "mems", "embedded", "edge ai",
    # FAE / sales
    "field application", "fae", "solutions engineer", "sales engineer",
    "technical sales", "pre-sales", "application engineer",
]

# Per-bucket: signals that indicate a specific non-VC role type
BUCKET_SIGNALS: dict[str, list[str]] = {
    "founding": ["founding engineer", "staff engineer", "early stage", "series a", "series b",
                 "seed stage", "startup equity", "equity stake", "ownership"],
    "research": ["research engineer", "research scientist", "phd", "publication", "mems",
                 "embedded system", "edge ai", "tinyml", "sensor"],
    "sales":    ["field application", "fae", "solutions engineer", "technical sales",
                 "sales engineer", "pre-sales", "customer", "demo", "poc"],
}

# ── TF-IDF helpers ────────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return [w for w in text.split() if len(w) > 2]


def _tfidf_vec(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    tf: dict[str, float] = {}
    for t in tokens:
        tf[t] = tf.get(t, 0) + 1
    n = len(tokens) or 1
    return {w: (c / n) * idf.get(w, 1.0) for w, c in tf.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    dot   = sum(a.get(w, 0.0) * v for w, v in b.items())
    mag_a = math.sqrt(sum(v * v for v in a.values())) or 1e-9
    mag_b = math.sqrt(sum(v * v for v in b.values())) or 1e-9
    return dot / (mag_a * mag_b)


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_job_fallback(
    title: str,
    company: str,
    description: Optional[str],
    location: Optional[str] = None,
    profile_text: Optional[str] = None,
) -> dict:
    """
    Score a job using keyword + cosine similarity.
    Returns: {score, headline, pros, cons, key_requirements, method='fallback'}
    """
    if profile_text is None:
        from config import PROFILE
        profile_text = PROFILE
    profile_tokens, idf = _get_profile_vectors(profile_text)

    title_l    = title.lower()
    full_text  = f"{title} {company} {description or ''} {location or ''}".lower()
    pros: list[str] = []
    cons: list[str] = []

    # ── Layer 1: title match (0-45) ───────────────────────────────────────────
    title_pts = 0
    matched_bucket = None
    for keywords, pts, label, bucket in TITLE_SIGNALS:
        if any(kw in title_l for kw in keywords):
            title_pts = pts
            matched_bucket = bucket
            pros.append(f"Title matches {label}")
            break  # use best matching tier only

    # ── Layer 2: domain keywords (0-35, capped) ───────────────────────────────
    domain_pts = 0
    for keywords, pts, label in DOMAIN_GROUPS:
        hits = [kw for kw in keywords if kw in full_text]
        if hits:
            domain_pts += pts
            pros.append(f"{label}: {', '.join(hits[:3])}")
    domain_pts = min(domain_pts, 35)

    # ── Layer 3: TF-IDF cosine (0-20) ────────────────────────────────────────
    job_tokens  = _tokenize(full_text)
    job_vec     = _tfidf_vec(job_tokens, idf)
    profile_vec = _tfidf_vec(profile_tokens, idf)
    cosine_pts  = min(_cosine(job_vec, profile_vec) * 200, 20)  # scale up then cap

    raw = title_pts + domain_pts + cosine_pts  # max theoretical = 100

    # ── Penalties ─────────────────────────────────────────────────────────────
    # Apply penalty only if no signals from ANY target bucket are present
    has_core_signal = any(sig in full_text for sig in CORE_SIGNALS)
    if not has_core_signal:
        raw *= 0.25
        cons.append("No signals from any target role bucket (VC, founding eng, research, FAE/sales)")

    company_l = company.lower()
    if any(bt in company_l for bt in BIG_TECH):
        raw *= 0.45
        cons.append("Large established company — not aligned with early-stage hardware-first profile")

    if any(t in title_l for t in ["intern", "internship", "junior", "entry level", "entry-level"]):
        raw *= 0.6
        cons.append("Junior/entry-level title — below target seniority")

    if not pros:
        cons.append("No keyword overlap with target role profile")

    score = max(0, min(100, round(raw)))

    # ── Headline ──────────────────────────────────────────────────────────────
    bucket_labels = {
        "vc":       ("VC/CVC investor", "investor"),
        "founding": ("founding/staff engineer", "founding eng"),
        "research": ("research engineer", "research eng"),
        "sales":    ("FAE/solutions/sales engineer", "FAE/sales"),
    }
    bucket_label, bucket_short = bucket_labels.get(matched_bucket, ("role", "role"))

    if score >= 80:
        headline = f"Strong {bucket_label} match — {title} at {company}"
    elif score >= 60:
        headline = f"Good {bucket_label} fit — {title} at {company}"
    elif score >= 40:
        headline = f"Moderate overlap with {bucket_short} profile — {title} at {company}"
    else:
        headline = f"Low relevance to target career — {title} at {company}"

    _key_reqs = {
        "vc": [
            "Verify this is an investor/investment role (not an operating position)",
            "Confirm seniority level aligns with Associate→Principal→Partner tier",
            "Check domain focus aligns with deep-tech, hardware, or climate thesis",
        ],
        "founding": [
            "Confirm early-stage / Seed–Series B context (not post-IPO or large corp)",
            "Check equity / ownership component",
            "Verify deep-tech or hardware/AI domain alignment",
        ],
        "research": [
            "Confirm senior/principal/staff seniority (not entry-level research)",
            "Check domain aligns with MEMS, edge AI, embedded, or industrial systems",
            "Verify R&D independence and publication/patent track expected",
        ],
        "sales": [
            "Confirm technical depth (not pure account management)",
            "Check hardware, semiconductor, or industrial IoT customer base",
            "Verify pre-sales / solutions architecture responsibilities",
        ],
    }
    key_reqs = _key_reqs.get(matched_bucket, [
        "Assess alignment with VC, founding eng, research eng, or FAE/sales targets",
    ])

    return {
        "score":            score,
        "headline":         headline,
        "pros":             pros[:4],
        "cons":             cons[:3],
        "key_requirements": key_reqs,
        "method": "fallback",
    }
