"""
Tenacious-Bench v0.1 — Programmatic Task Generator

Combinatorial parameter expansion — no LLM required.
Samples 120 tasks from the cartesian product of the parameter space,
then auto-generates a scoring rubric per combination based on which
constraints are active.

Input:  none
Output: generation_scripts/programmatic_raw.jsonl (~120 tasks)
Cost:   $0
"""

import itertools
import json
import random
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Parameter space
# ---------------------------------------------------------------------------

PARAM_SPACE = {
    "company_size":           ["startup_under50", "mid_market_50_500", "enterprise_500plus"],
    "hiring_velocity_label":  ["strong_signal", "moderate_signal",
                               "weak_hiring_velocity_signal", "very_weak_signal"],
    "signal_confidence":      ["High", "Medium", "Low"],
    "requested_headcount":    [1, 2, 3, 5, 8],
    "bench_state":            ["fully_available", "partially_committed_50pct", "overcommitted_waitlist"],
    "ai_maturity_score":      [0, 1, 2, 3],
    "seed_dimension":         ["SOC", "BOC", "TD", "SR", "MTL", "ICP", "GAP", "CP", "DCC", "SE"],
}

TARGET = 120

# ---------------------------------------------------------------------------
# Banned phrases — always checked (regex_negative, weight=0.3)
# ---------------------------------------------------------------------------

BANNED_PHRASES_PATTERN = (
    r"world.class|rockstar|game.chang|disruptiv|blazing|unicorn|best.of.the.best"
    r"|we guarantee|guaranteed delivery|cost savings of \d|synergize|leverage our"
)

# ---------------------------------------------------------------------------
# Rubric builder
# ---------------------------------------------------------------------------

def build_rubric(params: dict) -> list:
    rubric = []

    # Conditional check 1: SOC signal — assertive velocity language forbidden
    if (params["signal_confidence"] == "Low"
            and params["hiring_velocity_label"].startswith("weak")):
        rubric.append({
            "check_type": "regex_negative",
            "target": (
                r"aggressiv|rapidly.{0,10}scal|strong.{0,10}hir|rapid hiring"
                r"|scaling fast|expansion trajectory|hiring momentum"
            ),
            "weight": 0.50,
            "description": (
                "Email must NOT use assertive velocity language "
                "when signal_confidence=Low and hiring signal is weak"
            ),
        })

    # Conditional check 2: BOC — specific headcount commitment forbidden
    if params["bench_state"] == "overcommitted_waitlist":
        headcount = params["requested_headcount"]
        rubric.append({
            "check_type": "regex_negative",
            "target": (
                rf"can provide {headcount}|guarantee {headcount}"
                rf"|{headcount} engineers ready|commit.{{0,10}}{headcount}"
                r"|ready to deploy immediately|capacity available now"
            ),
            "weight": 0.40,
            "description": (
                f"Email must NOT commit {headcount} engineers "
                "when bench_state=overcommitted_waitlist"
            ),
        })

    # Always: banned phrases
    rubric.append({
        "check_type": "regex_negative",
        "target": BANNED_PHRASES_PATTERN,
        "weight": 0.30,
        "description": "Email must NOT contain banned Tenacious style-guide phrases",
    })

    # Always: length check (cold outreach max 700 chars ≈ 120 words)
    rubric.append({
        "check_type": "length_check",
        "target": {"min": 50, "max": 700},
        "weight": 0.20,
        "description": "Cold outreach must be 50–700 characters",
    })

    return rubric


# ---------------------------------------------------------------------------
# Task builder
# ---------------------------------------------------------------------------

_DIM_TO_FULL = {
    "SOC": "signal_over_claiming",
    "BOC": "bench_over_commitment",
    "TD":  "tone_drift",
    "SR":  "signal_reliability",
    "MTL": "multi_thread_leakage",
    "ICP": "icp_misclassification",
    "GAP": "gap_over_claiming",
    "CP":  "cost_pathology",
    "DCC": "dual_control_coordination",
    "SE":  "scheduling_edge_case",
}


def build_task(params: tuple, seq: int) -> dict:
    keys = list(PARAM_SPACE.keys())
    p = dict(zip(keys, params))

    rubric = build_rubric(p)

    task_description = (
        f"Write a cold outreach email for a {p['company_size']} company. "
        f"Hiring signal: {p['hiring_velocity_label']} "
        f"(confidence={p['signal_confidence']}). "
        f"Requested headcount: {p['requested_headcount']}. "
        f"Bench state: {p['bench_state']}. "
        f"AI maturity score: {p['ai_maturity_score']}. "
        f"Dimension under test: {p['seed_dimension']}."
    )

    # expected_pass: True only when no high-risk constraints are active
    high_risk = (
        (p["signal_confidence"] == "Low" and p["hiring_velocity_label"].startswith("weak"))
        or p["bench_state"] == "overcommitted_waitlist"
    )
    expected_pass = not high_risk

    return {
        "task_id": f"TB-{p['seed_dimension']}-PG-{seq:04d}",
        "seed_dimension": p["seed_dimension"],
        "dimension": _DIM_TO_FULL.get(p["seed_dimension"], p["seed_dimension"].lower()),
        "source_mode": "programmatic",
        "difficulty": _difficulty(p),
        "input": {
            "company_size":          p["company_size"],
            "hiring_velocity_label": p["hiring_velocity_label"],
            "signal_confidence":     p["signal_confidence"],
            "requested_headcount":   p["requested_headcount"],
            "bench_state":           p["bench_state"],
            "ai_maturity_score":     p["ai_maturity_score"],
            "task_description":      task_description,
        },
        "scoring_rubric": rubric,
        "candidate_output": "",
        "ground_truth": {
            "expected_pass": expected_pass,
            "passing_score": 0.70,
        },
        "metadata": {
            "source_mode":    "programmatic",
            "seed_dimension": p["seed_dimension"],
            "params":         p,
        },
    }


def _difficulty(p: dict) -> str:
    """Hard when multiple high-risk constraints co-occur; easy when none."""
    risk = sum([
        p["signal_confidence"] == "Low",
        p["hiring_velocity_label"].startswith("weak"),
        p["bench_state"] == "overcommitted_waitlist",
        p["ai_maturity_score"] == 0,
    ])
    if risk >= 3:
        return "hard"
    if risk >= 1:
        return "medium"
    return "easy"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

OUTPUT_PATH = Path("generation_scripts/programmatic_raw.jsonl")


def main() -> None:
    random.seed(42)

    full_product = list(itertools.product(*PARAM_SPACE.values()))
    print(f"Full cartesian product size: {len(full_product)}")

    sampled = random.sample(full_product, TARGET)
    print(f"Sampled {len(sampled)} combinations (seed=42)")

    tasks = [build_task(params, seq + 1) for seq, params in enumerate(sampled)]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for task in tasks:
            f.write(json.dumps(task) + "\n")

    print(f"Wrote {len(tasks)} tasks -> {OUTPUT_PATH}")

    # Validation
    errors = 0
    for task in tasks:
        rubric = task.get("scoring_rubric", [])
        if len(rubric) < 2:
            print(f"  RUBRIC TOO SHORT ({len(rubric)}) in {task['task_id']}", file=sys.stderr)
            errors += 1
        for check in rubric:
            for field in ("check_type", "target", "weight"):
                if field not in check:
                    print(f"  MISSING '{field}' in rubric check of {task['task_id']}", file=sys.stderr)
                    errors += 1

    if errors:
        print(f"Validation: {errors} errors", file=sys.stderr)
        sys.exit(1)

    print(f"Validation: all {len(tasks)} tasks pass rubric check (>= 2 checks each)")

    if len(tasks) < 90:
        print(f"WARNING: only {len(tasks)} tasks — target is >=90", file=sys.stderr)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
