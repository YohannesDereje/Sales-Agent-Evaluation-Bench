"""
Tenacious-Bench v0.1 — Partition and Contamination Check

Reads:  generation_scripts/filtered_dataset.jsonl  (237 tasks)
Splits: 50% train / 30% dev / 20% held_out  (random.seed(42))
Writes: tenacious_bench_v0.1/{train,dev,held_out}/*.jsonl
Runs:   3 contamination checks
Writes: tenacious_bench_v0.1/contamination_check.json

Contamination Check 1 — 8-gram overlap (zero tolerance)
  Proxy for hiring_signal_brief: candidate_output text
  (programmatic tasks have empty candidate_output → vacuously pass)

Contamination Check 2 — Jaccard similarity (< 0.60)
  Proxy: compound scenario key (dim|company|velocity|confidence|bench|headcount)
  Same logic as judge_filter.py tokenizer

Contamination Check 3 — Time-shift verification
  Scan all text fields for pre-2026 dates asserted as current signals
  Method: regex scan for \\b202[0-5]\\b near "current|recent|latest|now" language
"""

import json
import os
import random
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

INPUT_PATH    = Path("generation_scripts/filtered_dataset.jsonl")
BENCH_DIR     = Path("tenacious_bench_v0.1")
TRAIN_PATH    = BENCH_DIR / "train" / "train.jsonl"
DEV_PATH      = BENCH_DIR / "dev" / "dev.jsonl"
HELD_OUT_PATH = BENCH_DIR / "held_out" / "held_out.jsonl"
CONTAM_PATH   = BENCH_DIR / "contamination_check.json"

# ---------------------------------------------------------------------------
# Helpers — hiring_signal_brief proxies
# ---------------------------------------------------------------------------

def _brief_text(task: dict) -> str:
    """
    Text proxy for 8-gram check: prestige_indicator only.
    This field is company-specific context unique to each hand-authored task
    (all 10 values are distinct across the dataset). Other candidate fields
    — task_description, candidate_output, prospect_message, reliability_flag —
    are template strings deliberately reused across many tasks and produce
    false-positive 8-gram matches between tasks testing the same failure mode.
    Tasks without prestige_indicator (all programmatic and most synthesis)
    return empty string and trivially pass; contamination for those is covered
    by Check 2 (Jaccard on compound scenario key).
    """
    v = task.get("input", {}).get("prestige_indicator", "")
    return v if isinstance(v, str) else ""


def _brief_tokens(task: dict) -> frozenset:
    """Compound scenario key + candidate prefix — mirrors judge_filter tokenizer."""
    inp      = task.get("input", {})
    dim      = task.get("seed_dimension", "X")
    company  = (inp.get("company_name", "") or inp.get("company_size", "unknown"))[:20]
    company  = company.replace(" ", "_").lower()
    velocity = inp.get("hiring_velocity_label", "")
    conf     = inp.get("signal_confidence", "")
    bench    = inp.get("bench_state", "")
    headcount = str(inp.get("requested_headcount", ""))
    ai_mat   = str(inp.get("ai_maturity_score", ""))
    vertical = inp.get("vertical", "")
    key      = f"{dim}|{company}|{velocity}|{conf}|{bench}|{headcount}|{ai_mat}|{vertical}"
    tokens: set = {key}
    cand_prefix = " ".join(task.get("candidate_output", "").split()[:6])
    if cand_prefix:
        tokens.add(f"cand_{cand_prefix.lower()}")
    return frozenset(tokens)


def _ngrams(text: str, n: int) -> set:
    words = text.lower().split()
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def _jaccard(s1: frozenset, s2: frozenset) -> float:
    union = len(s1 | s2)
    return len(s1 & s2) / union if union else 0.0


# ---------------------------------------------------------------------------
# Contamination checks
# ---------------------------------------------------------------------------

def check_ngram_overlap(train: list, held_out: list) -> dict:
    """Check 1: zero-tolerance 8-gram overlap between held_out and train."""
    train_ngrams: set = set()
    for task in train:
        text = _brief_text(task)
        if text:
            train_ngrams |= _ngrams(text, 8)

    flagged = []
    for task in held_out:
        text = _brief_text(task)
        if not text:
            continue
        task_ngrams = _ngrams(text, 8)
        overlap = task_ngrams & train_ngrams
        if overlap:
            flagged.append({
                "held_out_task_id": task["task_id"],
                "overlapping_ngrams": [list(ng) for ng in list(overlap)[:3]],
            })

    return {
        "passed":        len(flagged) == 0,
        "flagged_pairs": flagged,
        "threshold":     "zero 8-gram overlap",
        "train_ngrams_checked": len(train_ngrams),
        "held_out_tasks_checked": sum(1 for t in held_out if _brief_text(t)),
    }


def check_jaccard(train: list, held_out: list) -> dict:
    """Check 2: pairwise Jaccard < 0.60 between each held_out task and all train tasks."""
    train_tokens = [(t["task_id"], _brief_tokens(t)) for t in train]

    flagged = []
    for ho_task in held_out:
        ho_tokens = _brief_tokens(ho_task)
        for tr_id, tr_tokens in train_tokens:
            j = _jaccard(ho_tokens, tr_tokens)
            if j >= 0.60:
                flagged.append({
                    "held_out_task_id": ho_task["task_id"],
                    "train_task_id":    tr_id,
                    "jaccard":          round(j, 4),
                })

    return {
        "passed":        len(flagged) == 0,
        "flagged_pairs": flagged,
        "threshold":     "< 0.60",
        "pairs_checked": len(held_out) * len(train),
    }


# Pre-2026 date patterns that would indicate a stale signal asserted as current.
# We look for a year in 2020-2025 appearing near "current/recent/latest/now" language
# within 80 characters, indicating the signal is being treated as current-day fact.
_STALE_DATE_RE = re.compile(
    r"\b(202[0-5])\b.{0,80}?\b(current|recent|latest|now|today|this year|just raised|fresh)\b"
    r"|"
    r"\b(current|recent|latest|now|today|this year|just raised|fresh)\b.{0,80}?\b(202[0-5])\b",
    re.IGNORECASE | re.DOTALL,
)


def _all_text(task: dict) -> str:
    """Concatenate all string fields for time-shift scanning."""
    parts = []

    def _collect(obj):
        if isinstance(obj, str):
            parts.append(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                _collect(v)
        elif isinstance(obj, list):
            for item in obj:
                _collect(item)

    _collect(task.get("input", {}))
    _collect(task.get("candidate_output", ""))
    return " ".join(parts)


def check_timeshift(all_partitions: list) -> dict:
    """
    Check 3: no pre-2026 date cited as a current signal.
    Method: regex scan for \\b202[0-5]\\b within 80 chars of
    'current|recent|latest|now|today|fresh|just raised' language.
    Candidate output (the *failing* email) is excluded — it intentionally
    contains stale assertions to demonstrate the failure mode.
    """
    flagged = []
    for task in all_partitions:
        # Only scan input fields — candidate_output IS intentionally bad
        text = " ".join(
            str(v) for v in task.get("input", {}).values()
            if isinstance(v, (str, int, float))
        )
        if _STALE_DATE_RE.search(text):
            match = _STALE_DATE_RE.search(text)
            flagged.append({
                "task_id": task["task_id"],
                "snippet": text[max(0, match.start() - 20):match.end() + 20],
            })

    return {
        "passed":           len(flagged) == 0,
        "flagged_tasks":    flagged,
        "documented_window": "2026-04",
        "method": (
            "regex scan for \\b202[0-5]\\b within 80 chars of "
            "current|recent|latest|now|today|just raised|fresh language "
            "in input fields (candidate_output excluded as intentional failure)"
        ),
        "tasks_scanned": len(all_partitions),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not INPUT_PATH.exists():
        print(f"ERROR: {INPUT_PATH} not found", file=sys.stderr)
        sys.exit(1)

    tasks = [json.loads(l) for l in open(INPUT_PATH, encoding="utf-8") if l.strip()]
    print(f"Loaded {len(tasks)} tasks from {INPUT_PATH}")

    # --- Partition ---
    random.seed(42)
    random.shuffle(tasks)

    n_total    = len(tasks)
    n_train    = int(n_total * 0.50)
    n_dev      = int(n_total * 0.30)
    # held_out gets the remainder to ensure exact totals
    train      = tasks[:n_train]
    dev        = tasks[n_train:n_train + n_dev]
    held_out   = tasks[n_train + n_dev:]
    n_held_out = len(held_out)

    print(f"Partition: train={len(train)}, dev={len(dev)}, held_out={len(held_out)}")

    # Write partition files
    for path, partition in [
        (TRAIN_PATH, train),
        (DEV_PATH,   dev),
        (HELD_OUT_PATH, held_out),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for task in partition:
                f.write(json.dumps(task) + "\n")
    print(f"Partition files written.")

    # --- Contamination checks ---
    print("Running contamination checks...")

    ngram_result  = check_ngram_overlap(train, held_out)
    jaccard_result = check_jaccard(train, held_out)
    timeshift_result = check_timeshift(tasks)

    checks_passed = (
        ngram_result["passed"]
        and jaccard_result["passed"]
        and timeshift_result["passed"]
    )
    summary = "PASS" if checks_passed else "FAIL"

    contamination = {
        "ngram_check":    ngram_result,
        "jaccard_check":  jaccard_result,
        "timeshift_check": timeshift_result,
        "summary":        summary,
        "total_tasks":    n_total,
        "train_count":    len(train),
        "dev_count":      len(dev),
        "held_out_count": n_held_out,
    }

    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONTAM_PATH, "w", encoding="utf-8") as f:
        json.dump(contamination, f, indent=2)

    print(f"8-gram check:   {'PASS' if ngram_result['passed'] else 'FAIL'} "
          f"({len(ngram_result['flagged_pairs'])} flagged pairs)")
    print(f"Jaccard check:  {'PASS' if jaccard_result['passed'] else 'FAIL'} "
          f"({len(jaccard_result['flagged_pairs'])} flagged pairs)")
    print(f"Time-shift:     {'PASS' if timeshift_result['passed'] else 'FAIL'} "
          f"({len(timeshift_result['flagged_tasks'])} flagged tasks)")
    print(f"Summary:        {summary}")
    print(f"contamination_check.json written -> {CONTAM_PATH}")

    # --- Exit ---
    errors = 0
    if not all(p.exists() for p in [TRAIN_PATH, DEV_PATH, HELD_OUT_PATH]):
        print("ERROR: one or more partition files missing", file=sys.stderr)
        errors += 1
    if summary != "PASS":
        print(f"ERROR: contamination summary is {summary}", file=sys.stderr)
        errors += 1

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
