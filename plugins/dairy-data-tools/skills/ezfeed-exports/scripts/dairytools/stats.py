"""Small statistics in plain Python: percentiles, intervals, rates."""

from __future__ import annotations

import math


def clean(values):
    return [v for v in values if v is not None and isinstance(v, (int, float)) and math.isfinite(v)]


def mean(values):
    v = clean(values)
    return math.fsum(v) / len(v) if v else None   # fsum: the same answer on every Python


def median(values):
    return quantile(values, 0.5)


def quantile(values, q):
    """Linear interpolation (R's default, type 7)."""
    v = sorted(clean(values))
    if not v:
        return None
    pos = (len(v) - 1) * q
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def p10_50_90(values):
    v = clean(values)
    return None if not v else {"p10": quantile(v, 0.1), "p50": quantile(v, 0.5), "p90": quantile(v, 0.9), "n": len(v)}


def wilson(k: int, n: int, z: float = 1.96):
    """A share's 95% interval (Wilson), as a fraction."""
    if n == 0:
        return None, None
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, centre - half), min(1.0, centre + half)


def pct(k, n, places=1):
    return None if not n else round(100 * k / n, places)


def ecm_lb(milk, fat_pct, protein_pct):
    """Energy-corrected milk, lb (Tyrrell and Reid, 1965, as DHIA uses it)."""
    if None in (milk, fat_pct, protein_pct):
        return None
    return 0.327 * milk + 12.95 * milk * fat_pct / 100 + 7.65 * milk * protein_pct / 100


def linear_score(scc_thousands):
    """SCC linear score: log2(SCC / 100) + 3, SCC in thousands of cells per mL (4 is 200,000)."""
    if scc_thousands is None or scc_thousands <= 0:
        return None
    return math.log2(scc_thousands / 100) + 3
