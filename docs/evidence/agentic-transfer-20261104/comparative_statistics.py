"""Pure, prospective H/ECC statistics; no I/O, provider, fixture or logger.

Inputs are paired verified-success counts from the frozen, single-shot worlds.
The caller retains all four arms and terminal categories and supplies ``complete``
only after checking their full grid. This calculator compares H/ECC only.

The exact directional decision is an intersection-union test: H must be better
in BOTH fixed strata. Its p-value is not a pooled test of the average difference.
The average effect has a separate simultaneous conservative CP interval.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from fractions import Fraction
import math

ALPHA = 0.05
MINIMUM_OBSERVED_EFFECT = 0.20
STRATA = 2
WORLDS_PER_STRATUM = 8
BISECTION_STEPS = 80
MAX_BINOMIAL_N = 16
_COUNT_KEYS = ("both_success", "h_only", "ecc_only", "both_failure")
_ROW_KEYS = frozenset(("stratum", "planned_worlds", *_COUNT_KEYS))


def _integer(value, name, low=0, high=MAX_BINOMIAL_N):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(name)
    return value


def _tail_fraction(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value < 0.5:
        raise ValueError("tail_probability")
    return Fraction(str(value))


def _binomial_sum(n, p, start, stop):
    # Dyadic bisection points and the polynomial are evaluated as exact rationals.
    # There is no floating probability tolerance or external special-function lib.
    return sum((Fraction(math.comb(n, j)) * p**j * (1-p)**(n-j)
                for j in range(start, stop)), Fraction(0))


def _cp_brackets(k, n, tail_probability):
    _integer(n, "binomial_n", 1)
    _integer(k, "binomial_k", 0, n)
    tail = _tail_fraction(tail_probability)
    if k == 0:
        lower = Fraction(0)
    else:
        lo, hi = Fraction(0), Fraction(1)
        for _ in range(BISECTION_STEPS):
            mid = (lo+hi)/2
            if _binomial_sum(n, mid, k, n+1) < tail:
                lo = mid
            else:
                hi = mid
        lower = lo
    if k == n:
        upper = Fraction(1)
    else:
        lo, hi = Fraction(0), Fraction(1)
        for _ in range(BISECTION_STEPS):
            mid = (lo+hi)/2
            if _binomial_sum(n, mid, 0, k+1) > tail:
                lo = mid
            else:
                hi = mid
        upper = hi
    return lower, upper


def _outward(value, upper, *, low=0.0, high=1.0):
    if value <= low:
        return low
    if value >= high:
        return high
    if value.denominator == 1:
        return float(value)
    direction = math.inf if upper else -math.inf
    return min(high, max(low, math.nextafter(float(value), direction)))


def clopper_pearson_bounds(k, n, *, tail_probability):
    """CP bounds with specified probability in EACH tail (n<=16).

    Rational outer brackets are retained for 80 bisections; the final binary64
    conversion is rounded outwards. k=0 has exact lower0; k=n exact upper1.
    """
    lo, hi = _cp_brackets(k, n, tail_probability)
    return [_outward(lo, False), _outward(hi, True)]


def exact_paired_p_greater(h_only, ecc_only):
    """One-sided exact binomial tail over paired discordants; no discordance=1."""
    _integer(h_only, "h_only")
    _integer(ecc_only, "ecc_only")
    m = h_only+ecc_only
    if m > MAX_BINOMIAL_N:
        raise ValueError("discordant_count")
    if m == 0:
        return 1.0
    return sum(math.comb(m, j) for j in range(h_only, m+1)) / (2**m)


def _rows(values, name):
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)) or len(values) != STRATA:
        raise ValueError(name+"_two_strata_required")
    result = []
    for row in values:
        if not isinstance(row, Mapping) or set(row) != _ROW_KEYS:
            raise ValueError(name+"_row_shape")
        label = row["stratum"]
        if not isinstance(label, str) or not label.strip():
            raise ValueError(name+"_stratum")
        n = _integer(row["planned_worlds"], name+"_planned", 1)
        if n != WORLDS_PER_STRATUM:
            raise ValueError(name+"_planned_eight_required")
        counts = {k:_integer(row[k], name+"_"+k, 0, n) for k in _COUNT_KEYS}
        observed = sum(counts.values())
        if observed > n:
            raise ValueError(name+"_count_exceeds_plan")
        result.append({"stratum":label, "planned_worlds":n, **counts,
                       "observed_worlds":observed, "missing_worlds":n-observed})
    if len({r["stratum"] for r in result}) != STRATA:
        raise ValueError(name+"_duplicate_stratum")
    return sorted(result, key=lambda r:r["stratum"])


def analyze_comparison(positive_counts, negative_counts, *, complete, critical_harm_count=0):
    """Return JSON-safe statistics for the predeclared16positive/16negative grid.

    Rows have stratum, planned_worlds=8 and the four paired outcome counts.
    Missing worlds may be supplied, but block p-values, CIs and progression.
    ``complete`` additionally attests that the caller checked all FOUR arms.
    Terminal nondeliveries are not successes, with their categories kept by the
    caller; they must not be confused with an unexecuted/incomplete cohort.
    """
    if type(complete) is not bool:
        raise ValueError("complete_boolean_required")
    if type(critical_harm_count) is not int or critical_harm_count < 0:
        raise ValueError("critical_harm_count")
    positive = _rows(positive_counts, "positive")
    negative = _rows(negative_counts, "negative")
    if [r["stratum"] for r in positive] != [r["stratum"] for r in negative]:
        raise ValueError("positive_negative_strata_mismatch")
    all_full = all(r["missing_worlds"] == 0 for r in positive+negative)
    eligible = complete and all_full
    known_delta = sum((Fraction(r["h_only"]-r["ecc_only"], r["planned_worlds"])
                       for r in positive), Fraction(0))/STRATA
    missing_width = sum((Fraction(r["missing_worlds"], r["planned_worlds"])
                         for r in positive), Fraction(0))/STRATA
    point = float(known_delta) if all(r["missing_worlds"] == 0 for r in positive) else None
    result = {
        "schema":"hermes.comparative.paired-statistics.v1",
        "method":"two_stratum_IUT_exact_direction_and_simultaneous_CP_effect",
        "target":"conditional_on_two_fixed_world_generators_not_general_domains",
        "analysis_complete":eligible,
        "caller_four_arm_grid_complete":complete,
        "planned_positive_worlds":sum(r["planned_worlds"] for r in positive),
        "planned_negative_worlds":sum(r["planned_worlds"] for r in negative),
        "positive":positive, "negative":negative,
        "observed_effect":point,
        "effect_identification_bounds":[
            _outward(known_delta-missing_width, False, low=-1.0),
            _outward(known_delta+missing_width, True, low=-1.0)],
        "primary_directional_p":None, "effect_interval_95":None,
        "negative_relative_harm_upper_95":None,
        "critical_harm_count":critical_harm_count,
        "progression_signal":False,
        "minimum_twenty_point_gain_confirmed":False,
        "equivalence_confirmed":False,
        "five_point_negative_margin_confirmed":False,
        "verdict":"inconclusive_incomplete_cohort",
        "numerics":{"binomial_polynomials":"exact_rational", "bisection_steps":BISECTION_STEPS,
                    "final_float_rounding":"outward"},
    }
    if not eligible:
        return result

    effect_lower, effect_upper = Fraction(0), Fraction(0)
    tail = ALPHA/(2*STRATA*2)  # Four marginal probabilities, two tails each.
    for row in positive:
        b, c, n = row["h_only"], row["ecc_only"], row["planned_worlds"]
        lb, ub = _cp_brackets(b, n, tail)
        lc, uc = _cp_brackets(c, n, tail)
        effect_lower += (lb-uc)/STRATA
        effect_upper += (ub-lc)/STRATA
        row["discordants"] = b+c
        row["directional_p"] = exact_paired_p_greater(b, c)
        row["h_only_probability_interval_98_75"] = [_outward(lb, False), _outward(ub, True)]
        row["ecc_only_probability_interval_98_75"] = [_outward(lc, False), _outward(uc, True)]
    result["primary_directional_p"] = max(r["directional_p"] for r in positive)
    result["effect_interval_95"] = [_outward(effect_lower, False, low=-1.0),
                                     _outward(effect_upper, True, low=-1.0)]

    negative_upper = Fraction(0)
    for row in negative:
        # An ECC-only success is relative harm from H. Absolute failures remain.
        _, upper = _cp_brackets(row["ecc_only"], row["planned_worlds"], ALPHA/STRATA)
        negative_upper += upper/STRATA
        row["relative_harm_count"] = row["ecc_only"]
        row["H_absolute_failure_count"] = row["ecc_only"]+row["both_failure"]
        row["ECC_absolute_failure_count"] = row["h_only"]+row["both_failure"]
        row["relative_harm_upper_97_5"] = _outward(upper, True)
    result["negative_relative_harm_upper_95"] = _outward(negative_upper, True)
    result["minimum_twenty_point_gain_confirmed"] = effect_lower >= Fraction("0.20")
    result["five_point_negative_margin_confirmed"] = negative_upper <= Fraction("0.05")
    directional = result["primary_directional_p"] <= ALPHA
    useful_point = known_delta >= Fraction("0.20")
    result["progression_signal"] = directional and useful_point and critical_harm_count == 0
    if critical_harm_count:
        result["verdict"] = "blocked_critical_harm"
    elif result["progression_signal"]:
        result["verdict"] = "favorable_progression_signal_only"
    else:
        result["verdict"] = "inconclusive_no_useful_consistent_signal"
    return result
