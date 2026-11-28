"""Small statistics in plain Python (standard library only): percentiles, intervals, rates, contingency tests,
rank tests, Mantel-Haenszel stratified risk ratios, and Kaplan-Meier survival estimators."""

from __future__ import annotations

import math
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_EVEN

Z_95 = 1.959963984540054  # qnorm(0.975)


def clean(values):
    return [v for v in values if v is not None and isinstance(v, (int, float)) and not isinstance(v, bool)
            and math.isfinite(v)]


def mean(values):
    v = clean(values)
    return math.fsum(v) / len(v) if v else None   # fsum: the same answer on every Python


def median(values):
    return quantile(values, 0.5)


def quantile(values, q: float):
    """Linear interpolation (R's default, type 7)."""
    if not (0.0 <= q <= 1.0):
        raise ValueError(f"q must be between 0 and 1, got {q}")
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


def signif(x: float | None, digits: int = 2) -> float | None:
    """Round to `digits` significant figures with decimal round-half-to-even (matching R's `signif()`)."""
    if x is None or not math.isfinite(x):
        return None
    if x == 0.0:
        return 0.0
    if digits <= 0:
        raise ValueError("digits must be positive")
    d = Decimal(f"{x:.15g}")
    exp = d.adjusted() - digits + 1
    return float(d.quantize(Decimal(f"1e{exp}"), rounding=ROUND_HALF_EVEN))


def wilson(k: int, n: int, z: float = Z_95):
    """A share's 95% interval (Wilson), as a fraction."""
    if n < 0 or k < 0 or k > n:
        raise ValueError(f"wilson requires 0 <= k <= n, got k={k}, n={n}")
    if n == 0:
        return None, None
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, centre - half), min(1.0, centre + half)


def pct(k, n, places=1):
    return None if not n else round(100 * k / n, places)


def share(k: int, n: int, places: int = 3) -> float | None:
    return None if not n else round(k / n, places)


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


# --- distributions & hypothesis tests (pure stdlib) ------------------------------------------------------------------

def normal_sf(z: float) -> float:
    """Upper-tail probability P(Z > z) for a standard normal variable."""
    if math.isnan(z):
        return math.nan
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def _gamma_p_series(a: float, x: float) -> float:
    """Lower regularized incomplete gamma P(a, x) via series expansion (best for x < a + 1)."""
    if x <= 0.0:
        return 0.0
    gln = math.lgamma(a)
    ap = a
    term = 1.0 / a
    total = term
    for _ in range(2000):
        ap += 1.0
        term *= x / ap
        total += term
        if abs(term) <= abs(total) * 1e-15:
            return total * math.exp(-x + a * math.log(x) - gln)
    raise RuntimeError(f"_gamma_p_series failed to converge for a={a}, x={x}")


def _gamma_q_cf(a: float, x: float) -> float:
    """Upper regularized incomplete gamma Q(a, x) via Lentz continued fraction (best for x >= a + 1)."""
    gln = math.lgamma(a)
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b if b != 0.0 else 1.0 / tiny
    h = d
    for i in range(1, 2000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) <= 1e-15:
            return math.exp(-x + a * math.log(x) - gln) * h
    raise RuntimeError(f"_gamma_q_cf failed to converge for a={a}, x={x}")


def chisq_sf(x: float, df: int) -> float:
    """Upper-tail survival function P(Chi2_df >= x), matching R's `pchisq(x, df, lower.tail = FALSE)`."""
    if df <= 0:
        raise ValueError("df must be positive")
    if math.isnan(x):
        return math.nan
    if x <= 0.0:
        return 1.0
    if math.isinf(x):
        return 0.0
    if df == 1:
        return math.erfc(math.sqrt(x / 2.0))
    if df == 2:
        return math.exp(-x / 2.0)
    a = df / 2.0
    z = x / 2.0
    val = (1.0 - _gamma_p_series(a, z)) if z < a + 1.0 else _gamma_q_cf(a, z)
    return min(1.0, max(0.0, val))


def chisq_quantile(p: float, df: int) -> float:
    """Lower-tail quantile q such that P(Chi2_df <= q) = p (matching R's `qchisq(p, df)`)."""
    if df <= 0:
        raise ValueError("df must be positive")
    if not (0.0 <= p < 1.0):
        raise ValueError(f"p must be in [0, 1), got {p}")
    if p == 0.0:
        return 0.0
    target_sf = 1.0 - p
    # Bracket [lo, hi] where chisq_sf(lo) >= target_sf >= chisq_sf(hi).
    lo = 0.0
    hi = max(float(df), 1.0)
    while chisq_sf(hi, df) > target_sf:
        lo = hi
        hi *= 2.0
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if chisq_sf(mid, df) > target_sf:
            lo = mid
        else:
            hi = mid
        if hi - lo <= 1e-12 * max(1.0, hi):
            break
    return 0.5 * (lo + hi)


def poisson_ci(k: int, exposure: float, alpha: float = 0.05) -> tuple[float | None, float | None]:
    """Exact Garwood/chi-square Poisson rate CI for `k` events over `exposure` (matching R's `qchisq` formula)."""
    if k < 0:
        raise ValueError(f"k must be non-negative, got {k}")
    if exposure <= 0:
        return None, None
    lo = 0.0 if k == 0 else chisq_quantile(alpha / 2.0, 2 * k) / (2.0 * exposure)
    hi = chisq_quantile(1.0 - alpha / 2.0, 2 * k + 2) / (2.0 * exposure)
    return lo, hi


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float | None, float | None]:
    """Exact Clopper-Pearson binomial confidence interval (pure stdlib via bisection on binomial tail)."""
    if n < 0 or k < 0 or k > n:
        raise ValueError(f"clopper_pearson requires 0 <= k <= n, got k={k}, n={n}")
    if n == 0:
        return None, None

    def binom_tail_upper(p: float, k_min: int) -> float:
        # P(X >= k_min) for X ~ Bin(n, p)
        if p <= 0.0:
            return 1.0 if k_min <= 0 else 0.0
        if p >= 1.0:
            return 1.0 if k_min <= n else 0.0
        lp = math.log(p)
        lq = math.log(1.0 - p)
        ln_n = math.lgamma(n + 1)
        return sum(math.exp(ln_n - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * lp + (n - i) * lq)
                   for i in range(k_min, n + 1))

    if k == 0:
        lo = 0.0
    else:
        a, b = 0.0, k / n
        for _ in range(80):
            m = 0.5 * (a + b)
            if binom_tail_upper(m, k) < alpha / 2.0:
                a = m
            else:
                b = m
        lo = 0.5 * (a + b)

    if k == n:
        hi = 1.0
    else:
        a, b = k / n, 1.0
        for _ in range(80):
            m = 0.5 * (a + b)
            # P(X <= k) = 1 - P(X >= k+1)
            if (1.0 - binom_tail_upper(m, k + 1)) > alpha / 2.0:
                a = m
            else:
                b = m
        hi = 0.5 * (a + b)
    return lo, hi


def chisq_goodness_of_fit(observed: list[int], expected_weights: list[float]) -> tuple[float, float]:
    """Pearson chi-square goodness-of-fit test against expected weights (matching R's `chisq.test(x, p=...)`)."""
    pairs = [(o, w) for o, w in zip(observed, expected_weights) if w > 0]
    total = sum(o for o, _ in pairs)
    w_sum = sum(w for _, w in pairs)
    if len(pairs) < 2 or total <= 0 or w_sum <= 0:
        return 0.0, math.nan
    stat = 0.0
    for o, w in pairs:
        exp = total * (w / w_sum)
        stat += (o - exp) ** 2 / exp
    return stat, chisq_sf(stat, len(pairs) - 1)


def chisq_contingency(rows: list[tuple[int, int]], *, correct: bool | None = None) -> tuple[float, float]:
    """Pearson chi-square statistic and p-value for a k x 2 contingency table.

    When `correct` is None, applies Yates' continuity correction for 2x2 tables only (matching R's `chisq.test`).
    """
    r = len(rows)
    if r < 2:
        return 0.0, 1.0
    row_totals = [a + b for a, b in rows]
    c0 = sum(a for a, _ in rows)
    c1 = sum(b for _, b in rows)
    n = c0 + c1
    if n == 0 or c0 == 0 or c1 == 0 or any(rt == 0 for rt in row_totals):
        return 0.0, 1.0
    use_yates = (r == 2) if correct is None else bool(correct and r == 2)
    stat = 0.0
    for (a, b), rt in zip(rows, row_totals):
        for obs, ct in ((a, c0), (b, c1)):
            exp = rt * ct / n
            diff = abs(obs - exp)
            if use_yates:
                diff = max(0.0, diff - 0.5)
            stat += (diff * diff) / exp
    return stat, chisq_sf(stat, r - 1)


def _log_hypergeom(k: int, r1: int, r2: int, c1: int) -> float:
    n = r1 + r2
    c2 = n - c1
    return (math.lgamma(r1 + 1) + math.lgamma(r2 + 1) + math.lgamma(c1 + 1) + math.lgamma(c2 + 1)
            - math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(r1 - k + 1)
            - math.lgamma(c1 - k + 1) - math.lgamma(r2 - c1 + k + 1))


def fisher_exact_2x2(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher's exact test p-value for a 2x2 table [[a, b], [c, d]], matching R's `fisher.test`."""
    if min(a, b, c, d) < 0:
        raise ValueError(f"fisher_exact_2x2 cells must be non-negative, got ({a}, {b}, {c}, {d})")
    r1 = a + b
    r2 = c + d
    c1 = a + c
    n = r1 + r2
    lo = max(0, r1 + c1 - n)
    hi = min(r1, c1)
    if lo == hi:
        return 1.0
    log_p_obs = _log_hypergeom(a, r1, r2, c1)
    tol = math.log(1.0 + 1e-7)
    p = 0.0
    for k in range(lo, hi + 1):
        lp = _log_hypergeom(k, r1, r2, c1)
        if lp <= log_p_obs + tol:
            p += math.exp(lp)
    return min(1.0, p)


def mantel_haenszel_rr(strata: list[tuple[int, int, int, int]]) -> dict[str, float | None]:
    """Mantel-Haenszel pooled Risk Ratio across 2x2 strata `(a, b, c, d)` with Greenland-Robins 95% CI and MH test.

    Each stratum is `(exposed_cases, exposed_noncases, ref_cases, ref_noncases)`.
    """
    num = 0.0
    den = 0.0
    var_num = 0.0
    mh_num = 0.0
    mh_var = 0.0
    for a, b, c, d in strata:
        if min(a, b, c, d) < 0:
            raise ValueError("stratum cells must be non-negative")
        n1 = a + b
        n0 = c + d
        m1 = a + c
        m0 = b + d
        t = n1 + n0
        if t == 0 or n1 == 0 or n0 == 0:
            continue
        num += a * n0 / t
        den += c * n1 / t
        var_num += (n1 * n0 * m1 - a * c * t) / (t * t)
        if t > 1:
            mh_num += a - (n1 * m1) / t
            mh_var += (n1 * n0 * m1 * m0) / (t * t * (t - 1.0))
    if den <= 0.0:
        return {"rr": None, "rr_lower": None, "rr_upper": None, "p_value": None}
    rr = num / den
    if num > 0.0 and var_num > 0.0:
        se = math.sqrt(var_num / (num * den))
        lo = round(rr * math.exp(-Z_95 * se), 2)
        hi = round(rr * math.exp(Z_95 * se), 2)
    else:
        lo = hi = None
    p = chisq_sf((mh_num * mh_num) / mh_var, 1) if mh_var > 0.0 else None
    return {"rr": round(rr, 2), "rr_lower": lo, "rr_upper": hi, "p_value": signif(p, 2) if p is not None else None}


def _average_ranks(values: list[float]) -> tuple[list[float], list[int]]:
    """1-based average ranks and tie group sizes."""
    n = len(values)
    order = sorted(range(n), key=values.__getitem__)
    ranks = [0.0] * n
    ties: list[int] = []
    i = 0
    while i < n:
        j = i + 1
        while j < n and values[order[j]] == values[order[i]]:
            j += 1
        avg_rank = 0.5 * (i + 1 + j)
        for k in range(i, j):
            ranks[order[k]] = avg_rank
        if j - i > 1:
            ties.append(j - i)
        i = j
    return ranks, ties


def wilcoxon_ranksum(x: list[float], y: list[float], *, correct: bool = True) -> float | None:
    """Two-sided normal-approximation Wilcoxon rank-sum p-value (matching R's `wilcox.test(..., exact = FALSE)`).

    Note: when all observations across both groups are tied (variance 0), returns `1.0` (R returns `NaN`).
    """
    xs = clean(x)
    ys = clean(y)
    nx, ny = len(xs), len(ys)
    if nx == 0 or ny == 0:
        return None
    n = nx + ny
    ranks, ties = _average_ranks(xs + ys)
    w = math.fsum(ranks[:nx]) - nx * (nx + 1) / 2.0
    z = w - nx * ny / 2.0
    tie_sum = sum(t * t * t - t for t in ties)
    sigma2 = (nx * ny / 12.0) * ((n + 1) - tie_sum / (n * (n - 1))) if n > 1 else 0.0
    if sigma2 <= 0.0:
        return 1.0
    sigma = math.sqrt(sigma2)
    if correct:
        if z > 0:
            z = max(0.0, z - 0.5)
        elif z < 0:
            z = min(0.0, z + 0.5)
    return min(1.0, 2.0 * normal_sf(abs(z) / sigma))


def kruskal_wallis(groups: list[list[float]]) -> float | None:
    """Kruskal-Wallis test p-value across k >= 2 groups (matching R's `kruskal.test`).

    Note: when all observations across all groups are tied, returns `1.0` (R returns `NaN`).
    """
    cleaned = [c for g in groups if (c := clean(g))]
    k = len(cleaned)
    if k < 2:
        return None
    all_vals = [v for g in cleaned for v in g]
    n = len(all_vals)
    if n <= 1:
        return None
    ranks, ties = _average_ranks(all_vals)
    tie_sum = sum(t * t * t - t for t in ties)
    denom = 1.0 - tie_sum / (n * n * n - n)
    if denom <= 0.0:
        return 1.0
    offset = 0
    stat = 0.0
    for g in cleaned:
        ng = len(g)
        rg = math.fsum(ranks[offset:offset + ng])
        stat += (rg * rg) / ng
        offset += ng
    h = (12.0 / (n * (n + 1)) * stat - 3.0 * (n + 1)) / denom
    return chisq_sf(max(0.0, h), k - 1)


# --- survival analysis (Kaplan-Meier, Greenwood SE & log-rank, pure stdlib) ------------------------------------------

def kaplan_meier(times: list[float], events: list[bool]) -> list[tuple[float, float, int, int, float]]:
    """Kaplan-Meier survival curve: list of `(time, surv, at_risk, n_events, greenwood_se)` at each event time."""
    pairs = [(t, bool(e)) for t, e in zip(times, events) if t is not None and math.isfinite(t)]
    if not pairs:
        return []
    pairs.sort(key=lambda p: p[0])
    n = len(pairs)
    curve: list[tuple[float, float, int, int, float]] = []
    surv = 1.0
    gw_sum = 0.0
    i = 0
    while i < n:
        u = pairs[i][0]
        at_risk = n - i
        d = 0
        while i < n and pairs[i][0] == u:
            if pairs[i][1]:
                d += 1
            i += 1
        if d > 0:
            surv *= 1.0 - d / at_risk
            if at_risk > d:
                gw_sum += d / (at_risk * (at_risk - d))
            se = surv * math.sqrt(gw_sum) if surv > 0.0 else 0.0
            curve.append((u, surv, at_risk, d, se))
    return curve


def km_median(times: list[float], events: list[bool], *, interpolate_half: bool = True) -> float | None:
    """Kaplan-Meier median time to event (None when survival never drops to <= 0.5).

    With `interpolate_half=True` (R `survival::survfit` / `transition.R`'s `km_median`), if survival hits 0.5
    exactly, returns the midpoint to the next event time. With `interpolate_half=False` (`repro.R`'s
    `time_to_pregnancy`), returns the first time with `surv <= 0.5`.
    """
    curve = kaplan_meier(times, events)
    for i, (u, s, _, _, _) in enumerate(curve):
        if abs(s - 0.5) < 1e-10:
            if interpolate_half and i + 1 < len(curve):
                return (u + curve[i + 1][0]) / 2.0
            return u
        if s < 0.5:
            return u
    return None


def _solve_linear(a: list[list[float]], b: list[float]) -> list[float] | None:
    """Solve Ax = b via Gaussian elimination with partial pivoting."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-15:
            return None
        m[col], m[pivot] = m[pivot], m[col]
        piv = m[col][col]
        for j in range(col, n + 1):
            m[col][j] /= piv
        for r in range(n):
            if r != col and m[r][col] != 0.0:
                factor = m[r][col]
                for j in range(col, n + 1):
                    m[r][j] -= factor * m[col][j]
    return [m[i][n] for i in range(n)]


def logrank_test(times: list[float], events: list[bool], groups: list) -> float | None:
    """Mantel-Haenszel log-rank test p-value across >= 2 groups (matching R's `survival::survdiff`)."""
    triples = [(t, bool(e), str(g)) for t, e, g in zip(times, events, groups)
               if t is not None and math.isfinite(t) and g is not None]
    if not triples:
        return None
    levels = sorted({g for _, _, g in triples})
    k = len(levels)
    if k < 2:
        return None
    idx = {g: i for i, g in enumerate(levels)}
    at_risk = [0] * k
    by_time: dict[float, list[tuple[int, bool]]] = defaultdict(list)
    for t, e, g in triples:
        gi = idx[g]
        at_risk[gi] += 1
        by_time[t].append((gi, e))
    obs_minus_exp = [0.0] * k
    var = [[0.0] * k for _ in range(k)]
    for t in sorted(by_time):
        n_tot = sum(at_risk)
        if n_tot == 0:
            break
        ev_counts = [0] * k
        exit_counts = [0] * k
        for gi, e in by_time[t]:
            exit_counts[gi] += 1
            if e:
                ev_counts[gi] += 1
        d_tot = sum(ev_counts)
        if d_tot > 0:
            for g in range(k):
                obs_minus_exp[g] += ev_counts[g] - at_risk[g] * (d_tot / n_tot)
            if n_tot > 1:
                factor = d_tot * (n_tot - d_tot) / (n_tot - 1.0)
                for g in range(k):
                    pg = at_risk[g] / n_tot
                    for h in range(k):
                        ph = at_risk[h] / n_tot
                        delta = 1.0 if g == h else 0.0
                        var[g][h] += factor * pg * (delta - ph)
        for g in range(k):
            at_risk[g] -= exit_counts[g]
    m = k - 1
    u = obs_minus_exp[:m]
    v = [row[:m] for row in var[:m]]
    if m == 1:
        if v[0][0] <= 0.0:
            return 1.0
        chisq = (u[0] * u[0]) / v[0][0]
    else:
        sol = _solve_linear(v, u)
        if sol is None:
            return None
        chisq = sum(ui * si for ui, si in zip(u, sol))
    return chisq_sf(max(0.0, chisq), m)
