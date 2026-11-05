"""Join verified, normalized B receipts to the frozen confirmation roster."""

from collections import Counter
import re

from comparative_statistics import analyze_comparison


ARMS = ("H", "E", "T", "N")
COHORTS = ("positive", "negative")
PAIR_KEYS = {
    (1, 1): "both_success", (1, 0): "h_only",
    (0, 1): "ecc_only", (0, 0): "both_failure",
}
SHA256 = re.compile(r"[0-9a-f]{64}")


def _score(row, request_sha256):
    if row["request_sha256"] != request_sha256:
        raise ValueError("B request differs from frozen roster")
    gate, terminal, pipeline = row["gate"], row["terminal"], row["pipeline"]
    if gate not in ("VALID", "VIOLATION", "UNKNOWN"):
        raise ValueError("invalid rights/integrity status")
    if terminal not in ("GRADED", "NONDELIVERY", "UNRESOLVED"):
        raise ValueError("invalid B terminal status")
    if pipeline not in ("COMPLETE", "INCOMPLETE", "UNKNOWN"):
        raise ValueError("invalid pipeline status")
    if not isinstance(row["reason"], str) or not row["reason"].strip():
        raise ValueError("missing evidence reason")
    business = row["business_passed"]
    if (terminal == "GRADED" and type(business) is not bool) or (
            terminal != "GRADED" and business is not None):
        raise ValueError("business verdict conflicts with terminal status")
    if pipeline == "COMPLETE" and terminal != "GRADED":
        raise ValueError("complete pipeline requires a graded B")
    y = int(gate == "VALID" and business is True)
    return {
        **row,
        "Y_business_ITT": y,
        "Z_pipeline_complete": int(gate == "VALID" and pipeline == "COMPLETE"),
        "terminal_for_analysis": gate != "UNKNOWN" and terminal != "UNRESOLVED",
        "Y_sensitivity_upper": int(gate != "VIOLATION" and business is not False),
    }


def reduce_conf_grades(roster, receipts):
    """Reduce 32 frozen worlds, using only verified receipts supplied by the caller.

    The caller authenticates source receipts and validates the frozen plan. This
    function checks join identity and design shape before reducing the outcomes.
    """
    strata = {entry["stratum"] for entry in roster.values()}
    sizes = Counter((entry["cohort"], entry["stratum"]) for entry in roster.values())
    if len(strata) != 2 or sizes != {(c, s): 8 for c in COHORTS for s in strata}:
        raise ValueError("expected eight worlds in each of four frozen cells")
    if any(not isinstance(world, str) or not world or
           not isinstance(entry["stratum"], str) or not entry["stratum"].strip() or
           not SHA256.fullmatch(entry["request_sha256"])
           for world, entry in roster.items()):
        raise ValueError("invalid frozen roster identity")

    scores = {}
    for row in receipts:
        world, arm = row["world"], row["arm"]
        key = (world, arm)
        if world not in roster or arm not in ARMS or key in scores:
            raise ValueError("unknown or duplicate B receipt identity")
        scores[key] = _score(row, roster[world]["request_sha256"])

    counts = {(c, s): Counter() for c in COHORTS for s in strata}
    totals = Counter()
    lower = upper = harm_lower = harm_upper = 0
    missing = []
    for world, entry in sorted(roster.items()):
        for arm in ARMS:
            score = scores.get((world, arm))
            if score is None or not score["terminal_for_analysis"]:
                missing.append([world, arm])
            if score is not None:
                totals[entry["cohort"], arm] += score["Y_business_ITT"]
        h, e = (scores.get((world, arm)) for arm in ("H", "E"))
        if h and e and h["terminal_for_analysis"] and e["terminal_for_analysis"]:
            pair = (h["Y_business_ITT"], e["Y_business_ITT"])
            counts[entry["cohort"], entry["stratum"]][PAIR_KEYS[pair]] += 1
        h_low, h_high = (h["Y_business_ITT"], h["Y_sensitivity_upper"]) if h else (0, 1)
        e_low, e_high = (e["Y_business_ITT"], e["Y_sensitivity_upper"]) if e else (0, 1)
        if entry["cohort"] == "positive":
            lower += h_low - e_high
            upper += h_high - e_low
        else:
            harm_lower += e_low * (1 - h_high)
            harm_upper += e_high * (1 - h_low)

    def rows(cohort):
        return [
            {"stratum": stratum, "planned_worlds": 8,
             **{key: counts[cohort, stratum][key] for key in PAIR_KEYS.values()}}
            for stratum in sorted(strata)
        ]

    critical = sum(score["gate"] == "VIOLATION" for score in scores.values())
    statistics = analyze_comparison(
        rows("positive"), rows("negative"), complete=not missing,
        critical_harm_count=critical,
    )
    return {
        "statistics": statistics,
        "stop_for_rights_or_integrity": critical > 0,
        "unresolved_world_arms": missing,
        "positive_unknown_sensitivity_bounds": [lower / 16, upper / 16],
        "negative_relative_harm_unknown_sensitivity_bounds": [harm_lower / 16, harm_upper / 16],
        "descriptive_ITT_successes_per_16": {
            c: {arm: totals[c, arm] for arm in ARMS} for c in COHORTS
        },
        "scores": [scores[key] for key in sorted(scores)],
    }
