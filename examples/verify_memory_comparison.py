#!/usr/bin/env python3
"""Verify the published synthetic comparison without network or a model.

This is a data-integrity and arithmetic check, not a new semantic judgment or
an execution of the private Hermes integration. The reconciliation and paired
calculation reuse the frozen experiment aggregation. Requires Python 3.11+.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path

SCHEMA = "persistent-memory.memory-on-off.v1"
EXPECTED_SHA256 = "c780e229b7aaa5bc5bf6c5343778a44307359a11f909ba2eccd142a1d5715e36"
ARMS = ("presence", "absence")
OUTCOMES = ("gain", "loss", "tie_success", "tie_failure", "unknown")
DEFAULT = Path(__file__).resolve().parents[1] / "docs/evidence/memory-on-off-20261020/comparison.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def aggregate(data: dict) -> dict:
    """Reconcile original annotations; retain unknowns, including interrupted arms."""
    require(data["schema"] == SCHEMA, "Unexpected schema")
    cases = data["cases"]
    require(len(cases) == 8, "Expected eight tasks")
    require({c["id"] for c in cases} == {f"MC20N{i:02d}" for i in range(1, 9)}, "Unexpected or duplicate task IDs")
    counts = {arm: {"success": 0, "failure": 0, "unknown": 0, "denominator": 8} for arm in ARMS}
    paired = dict.fromkeys(OUTCOMES, 0)
    complete = requests = low = high = 0
    for case in cases:
        require(set(case["arms"]) == set(ARMS), "Each task needs both arms")
        scores = {}
        for name in ARMS:
            arm = case["arms"][name]
            answer = arm["answer"]
            require(type(arm["completed"]) is bool, "Invalid completed flag")
            require((isinstance(answer, str) and bool(answer)) if arm["completed"] else answer is None, "Answer/completion mismatch")
            digest = hashlib.sha256(answer.encode("utf-8")).hexdigest() if answer is not None else None
            require(digest == arm["answer_sha256"], "Original answer digest mismatch")
            require(type(arm["provider_requests"]) is int and arm["provider_requests"] in (1, 2), "Unexpected request count")
            requests += arm["provider_requests"]
            complete += int(arm["completed"])
            require(set(arm["judgments"]) == {"A", "B"}, "Two original annotations required")
            a, b = (arm["judgments"][j]["strict_success"] for j in ("A", "B"))
            require(a is None or type(a) is bool, "Invalid primary verdict")
            require(a is b, "Primary annotation disagreement")
            require(arm["completed"] or a is None, "Incomplete answer must remain unknown")
            scores[name] = a
            counts[name]["unknown" if a is None else "success" if a else "failure"] += 1
        presence, absence = (scores[arm] for arm in ARMS)
        outcome = "unknown" if presence is None or absence is None else "gain" if presence and not absence else "loss" if absence and not presence else "tie_success" if presence else "tie_failure"
        require(outcome == case["outcome"], "Paired outcome differs from annotations")
        paired[outcome] += 1
        possibilities = [int(p) - int(a) for p, a in itertools.product([False, True] if presence is None else [presence], [False, True] if absence is None else [absence])]
        low += min(possibilities)
        high += max(possibilities)
    summary = {"counts": counts, "paired": paired, "exact_net_gain": low if low == high else None,
               "possible_net_gain_task_bounds": {"lower": low, "upper": high}, "not_confidence_interval": True}
    require(summary == data["summary"], "Published summary does not match original verdicts")
    accounting = data["accounting"]
    require(requests == accounting["provider_requests"] == 17, "Request total mismatch")
    require(complete == accounting["completed_answers"] == 15, "Completed answer total mismatch")
    require(accounting["attempted_arms"] == 16 and accounting["incomplete_answers"] == 1 and accounting["retries"] == 0, "Attempt accounting mismatch")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT)
    args = parser.parse_args()
    raw = args.path.read_bytes()
    require(len(raw) <= 100_000, "Dataset exceeds expected bound")
    require(hashlib.sha256(raw).hexdigest() == EXPECTED_SHA256, "Dataset differs from the published pinned export")
    data = json.loads(raw)
    result = aggregate(data)
    print(json.dumps({"verified": True, "schema": SCHEMA, "sha256": EXPECTED_SHA256, **result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
