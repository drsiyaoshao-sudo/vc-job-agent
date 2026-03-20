"""
Fallback job scorer — no Claude API required.

Three-layer scoring:
  1. Title match   (0-45 pts) — investor role keywords in the job title
  2. Domain match  (0-35 pts) — deep-tech / VC domain keywords in description
  3. TF-IDF cosine (0-20 pts) — overall text similarity to Siyao's profile

Total maps to 0-100.  Penalties applied for junior roles and missing VC signals.
Used automatically when Claude is unavailable or the API call fails.
Scores are labelled "[fallback]" in the headline so you know the source.
"""
from __future__ import annotations

import math
import re
from typing import Optional

from config import PROFILE

# ── Role-title keywords (checked against job TITLE) ──────────────────────────
# Each entry: (keywords, points_if_matched)

TITLE_SIGNALS: list[tuple[list[str], int, str]] = [
    (["general partner", "managing partner", "investment partner", "partner"], 45, "Partner-level VC role"),
    (["principal", "investment principal", "venture principal"],               42, "Principal-level VC role"),
    (["senior associate", "senior investment", "senior venture"],              38, "Senior Associate VC role"),
    (["investment analyst", "venture analyst", "vc analyst", "cvc analyst"],  35, "VC Analyst role"),
    (["investment associate", "venture associate", "vc associate"],            35, "VC Associate role"),
    (["investor", "vc investor", "cvc investor", "venture investor"],         32, "Investor title"),
    (["associate", "analyst"],                                                 28, "Associate/Analyst role"),
    (["eir", "entrepreneur in residence"],                                     25, "EIR role"),
    (["technology scout", "tech scout", "deal sourcing"],                      22, "Scout/Sourcing role"),
    (["innovation", "technology strategy", "corporate development"],           15, "Innovation/Strategy role"),
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

# ── Core VC signals — if NONE present, apply penalty ─────────────────────────
CORE_VC_SIGNALS = [
    "venture", "investment", "investor", "capital", "fund", "portfolio",
    "associate", "principal", "partner", "analyst",
]

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


# Pre-compute profile IDF once at import time
_PROFILE_TOKENS  = _tokenize(PROFILE)
_PROFILE_FREQ: dict[str, int] = {}
for _t in _PROFILE_TOKENS:
    _PROFILE_FREQ[_t] = _PROFILE_FREQ.get(_t, 0) + 1
_IDF = {w: 1.0 / (1.0 + math.log(1 + cnt)) for w, cnt in _PROFILE_FREQ.items()}


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_job_fallback(
    title: str,
    company: str,
    description: Optional[str],
    location: Optional[str] = None,
) -> dict:
    """
    Score a job using keyword + cosine similarity.
    Returns: {score, headline, pros, cons, key_requirements, method='fallback'}
    """
    title_l    = title.lower()
    full_text  = f"{title} {company} {description or ''} {location or ''}".lower()
    pros: list[str] = []
    cons: list[str] = []

    # ── Layer 1: title match (0-45) ───────────────────────────────────────────
    title_pts = 0
    for keywords, pts, label in TITLE_SIGNALS:
        if any(kw in title_l for kw in keywords):
            title_pts = pts
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
    job_vec     = _tfidf_vec(job_tokens, _IDF)
    profile_vec = _tfidf_vec(_PROFILE_TOKENS, _IDF)
    cosine_pts  = min(_cosine(job_vec, profile_vec) * 200, 20)  # scale up then cap

    raw = title_pts + domain_pts + cosine_pts  # max theoretical = 100

    # ── Penalties ─────────────────────────────────────────────────────────────
    if not any(sig in full_text for sig in CORE_VC_SIGNALS):
        raw *= 0.25
        cons.append("No investor/VC signals found — likely not a VC role")

    if any(t in title_l for t in ["intern", "internship", "junior", "entry level", "entry-level"]):
        raw *= 0.6
        cons.append("Junior/entry-level title — below Siyao's CTO/EIR seniority")

    if not pros:
        cons.append("No keyword overlap with VC or deep-tech profile")

    score = max(0, min(100, round(raw)))

    # ── Headline ──────────────────────────────────────────────────────────────
    if score >= 80:
        headline = f"Strong VC/CVC match — {title} at {company}"
    elif score >= 60:
        headline = f"Good investor role fit — {title} at {company}"
    elif score >= 40:
        headline = f"Moderate overlap with VC profile — {title} at {company}"
    else:
        headline = f"Low relevance to VC career target — {title} at {company}"

    return {
        "score":            score,
        "headline":         headline,
        "pros":             pros[:4],
        "cons":             cons[:3],
        "key_requirements": [
            "Verify this is an investor/investment role (not an operating position)",
            "Confirm seniority level aligns with Associate→Principal→Partner tier",
            "Check domain focus aligns with deep-tech, hardware, or climate thesis",
        ],
        "method": "fallback",
    }
