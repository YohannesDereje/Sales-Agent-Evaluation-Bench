"""
Tenacious-Bench Judge Filter v0.1
Rule-based quality filter for raw generated tasks.

Reads: programmatic_raw.jsonl, trace_derived_raw.jsonl,
       synthesis_raw.jsonl, hand_authored_tasks.jsonl

Scores each task on 3 dimensions (1-5):
  input_coherence         - internal consistency of input fields
  ground_truth_verifiability - rubric can be applied by scoring_evaluator.py
  rubric_clarity          - patterns are specific enough to be unambiguous

Threshold: ALL dimensions >= 3 to pass (see THRESHOLD below)

Deduplication: Jaccard similarity of signal_text tokens; skip if >= 0.8
  (deliberately higher than the final 0.6 target to retain more tasks at dev phase)

Outputs:
  judge_filter_log.jsonl  - all records with scores + pass/fail
  filtered_dataset.jsonl  - only passing tasks (all 3 dims >= THRESHOLD)
"""

import json
import re
from pathlib import Path

THRESHOLD = 3        # ALL dimensions must be >= this to pass
DEDUP_JACCARD = 0.8  # Jaccard similarity threshold for dedup (dev phase)

RAW_FILES = [
    "programmatic_raw.jsonl",
    "trace_derived_raw.jsonl",
    "synthesis_raw.jsonl",
    "hand_authored_tasks.jsonl",
]

HERE = Path(__file__).parent


# ─────────────────────────────────────────────────────────────────────────────
# Scoring functions
# ─────────────────────────────────────────────────────────────────────────────

def score_input_coherence(task: dict) -> tuple[int, str]:
    """
    Rule-based coherence checks (1-5):
      5 — all checks pass
      4 — 1 minor issue
      3 — 2 issues or 1 structural issue
      2 — critical field missing or type mismatch
      1 — task is unparseable / empty input
    """
    inp = task.get("input", {})
    hsb = inp.get("hiring_signal_brief", {})
    bench = inp.get("bench_summary", {})
    issues = []

    # Required input fields
    for field in ["hiring_signal_brief", "bench_summary", "task_instruction"]:
        if not inp.get(field):
            issues.append(f"missing input.{field}")

    # hiring_signal_brief required keys
    for key in ["company_name", "signal_type", "signal_confidence",
                "hiring_velocity_label", "headcount_requested", "stack"]:
        if key not in hsb:
            issues.append(f"missing hsb.{key}")

    # bench_summary required keys
    for key in ["available_engineers", "available_headcount", "earliest_start_weeks"]:
        if key not in bench:
            issues.append(f"missing bench.{key}")

    # Coherence: available_headcount <= available_engineers
    ae = bench.get("available_engineers", 0)
    ah = bench.get("available_headcount", 0)
    if isinstance(ae, int) and isinstance(ah, int) and ah > ae:
        issues.append("available_headcount > available_engineers")

    # signal_confidence must be valid
    valid_conf = {"high", "medium", "low"}
    if hsb.get("signal_confidence") not in valid_conf:
        issues.append(f"invalid signal_confidence: {hsb.get('signal_confidence')}")

    # hiring_velocity_label must be valid
    valid_vel = {"strong_signal", "moderate_signal", "weak_hiring_velocity_signal", "very_weak_signal"}
    if hsb.get("hiring_velocity_label") not in valid_vel:
        issues.append(f"invalid hiring_velocity_label: {hsb.get('hiring_velocity_label')}")

    n = len(issues)
    if n == 0:
        score = 5
    elif n == 1:
        score = 4
    elif n <= 2:
        score = 3
    elif n <= 4:
        score = 2
    else:
        score = 1

    reason = "OK" if not issues else "; ".join(issues)
    return score, reason


def score_ground_truth_verifiability(task: dict) -> tuple[int, str]:
    """
    Checks that ground_truth is structured so scoring_evaluator.py can run (1-5):
      5 — all criteria verifiable, weights sum to 1.0
      4 — weights off by <0.05 or 1 minor issue
      3 — weights sum issue or 1 criterion missing check_type
      2 — multiple criteria unparseable
      1 — ground_truth missing entirely
    """
    gt = task.get("ground_truth", {})
    if not gt:
        return 1, "ground_truth missing"

    pc = gt.get("passing_criteria", {})
    sc = gt.get("scoring", {})
    issues = []

    if not pc:
        issues.append("passing_criteria empty")
    if not sc:
        issues.append("scoring empty")

    # Keys must match
    pc_keys = set(pc.keys())
    sc_keys = set(sc.keys())
    if pc_keys != sc_keys:
        extra_sc = sc_keys - pc_keys
        extra_pc = pc_keys - sc_keys
        if extra_sc:
            issues.append(f"scoring has extra keys: {extra_sc}")
        if extra_pc:
            issues.append(f"passing_criteria has extra keys: {extra_pc}")

    # Each criterion must have check_type
    valid_check_types = {"regex_negative", "regex_positive", "length_check", "field_presence"}
    for dim_name, criterion in pc.items():
        ct = criterion.get("check_type")
        if ct not in valid_check_types:
            issues.append(f"criterion '{dim_name}' has invalid check_type: {ct}")
        # regex_negative needs banned_patterns
        if ct == "regex_negative" and not criterion.get("banned_patterns"):
            issues.append(f"'{dim_name}' regex_negative missing banned_patterns")
        # regex_positive needs required_patterns
        if ct == "regex_positive" and not criterion.get("required_patterns"):
            issues.append(f"'{dim_name}' regex_positive missing required_patterns")

    # Weights must sum to ~1.0
    weight_sum = sum(sc.values()) if sc else 0.0
    if abs(weight_sum - 1.0) > 0.05:
        issues.append(f"scoring weights sum to {weight_sum:.3f}, expected 1.0")
    elif abs(weight_sum - 1.0) > 0.001:
        issues.append(f"scoring weights slightly off: {weight_sum:.3f}")

    n = len(issues)
    if n == 0:
        score = 5
    elif n == 1 and "slightly off" in issues[0]:
        score = 4
    elif n == 1:
        score = 4
    elif n == 2:
        score = 3
    elif n <= 4:
        score = 2
    else:
        score = 1

    reason = "OK" if not issues else "; ".join(issues)
    return score, reason


def score_rubric_clarity(task: dict) -> tuple[int, str]:
    """
    Checks that patterns are specific and non-trivially short (1-5):
      5 — all patterns ≥ 4 chars, no single-character wildcards, ≥ 2 criteria
      4 — 1 vague pattern
      3 — 2-3 vague patterns or only 1 criterion
      2 — patterns mostly trivial or too broad
      1 — no patterns at all
    """
    gt = task.get("ground_truth", {})
    pc = gt.get("passing_criteria", {})
    issues = []

    if not pc:
        return 1, "no passing_criteria"

    if len(pc) < 2:
        issues.append("only 1 rubric dimension (≥2 recommended)")

    all_patterns = []
    for dim_name, criterion in pc.items():
        ct = criterion.get("check_type")
        if ct == "regex_negative":
            pats = criterion.get("banned_patterns", [])
        elif ct == "regex_positive":
            pats = criterion.get("required_patterns", [])
        else:
            pats = []

        if ct in ("regex_negative", "regex_positive") and not pats:
            issues.append(f"'{dim_name}' has no patterns")

        for p in pats:
            all_patterns.append((dim_name, p))
            # Flag patterns that are very short (< 4 chars stripped of regex meta)
            stripped = re.sub(r'[\\.*+?()\[\]{}^$|]', '', p)
            if len(stripped) < 4:
                issues.append(f"'{dim_name}' pattern too vague: '{p}'")

    if not all_patterns:
        return 1, "no patterns found in any criterion"

    n = len(issues)
    if n == 0:
        score = 5
    elif n == 1:
        score = 4
    elif n <= 3:
        score = 3
    elif n <= 5:
        score = 2
    else:
        score = 1

    reason = "OK" if not issues else "; ".join(issues)
    return score, reason


# ─────────────────────────────────────────────────────────────────────────────
# Deduplication
# ─────────────────────────────────────────────────────────────────────────────

def tokenize(text: str) -> set:
    return set(re.findall(r'\b\w+\b', text.lower()))


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def get_signal_text(task: dict) -> str:
    hsb = task.get("input", {}).get("hiring_signal_brief", {})
    parts = [
        hsb.get("company_name", ""),
        hsb.get("signal_text", ""),
        hsb.get("signal_type", ""),
        " ".join(hsb.get("stack", [])),
    ]
    return " ".join(p for p in parts if p)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    # Load all tasks
    all_tasks = []
    for fname in RAW_FILES:
        fpath = HERE / fname
        if not fpath.exists():
            print(f"[SKIP] {fname} not found")
            continue
        count = 0
        with open(fpath, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    task = json.loads(line)
                    all_tasks.append(task)
                    count += 1
                except json.JSONDecodeError as e:
                    print(f"[ERROR] {fname}:{lineno} JSON parse error: {e}")
        print(f"Loaded {count} tasks from {fname}")

    print(f"\nTotal raw tasks loaded: {len(all_tasks)}")

    # Score each task
    scored = []
    for task in all_tasks:
        coh_score, coh_reason = score_input_coherence(task)
        ver_score, ver_reason = score_ground_truth_verifiability(task)
        cla_score, cla_reason = score_rubric_clarity(task)

        all_pass = (
            coh_score >= THRESHOLD
            and ver_score >= THRESHOLD
            and cla_score >= THRESHOLD
        )

        record = {
            "task_id": task.get("task_id", "unknown"),
            "dimension": task.get("dimension", "unknown"),
            "source_mode": task.get("source_mode", "unknown"),
            "difficulty": task.get("difficulty", "unknown"),
            "scores": {
                "input_coherence": coh_score,
                "ground_truth_verifiability": ver_score,
                "rubric_clarity": cla_score,
            },
            "reasons": {
                "input_coherence": coh_reason,
                "ground_truth_verifiability": ver_reason,
                "rubric_clarity": cla_reason,
            },
            "passed_threshold": all_pass,
            "threshold": THRESHOLD,
        }
        scored.append((task, record))

    # Deduplication on passing tasks
    passing_before_dedup = [(t, r) for t, r in scored if r["passed_threshold"]]
    print(f"Passed threshold before dedup: {len(passing_before_dedup)}")

    seen_tokens = []  # list of (task_id, token_set) for seen passing tasks
    deduped_passing = []
    dedup_removed = []

    for task, record in passing_before_dedup:
        sig_text = get_signal_text(task)
        tok = tokenize(sig_text)
        is_dup = False
        for seen_id, seen_tok in seen_tokens:
            j = jaccard(tok, seen_tok)
            if j >= DEDUP_JACCARD:
                dedup_removed.append({
                    "task_id": record["task_id"],
                    "duplicate_of": seen_id,
                    "jaccard": round(j, 4),
                })
                record["passed_threshold"] = False
                record["dedup_removed"] = True
                record["dedup_duplicate_of"] = seen_id
                is_dup = True
                break
        if not is_dup:
            seen_tokens.append((record["task_id"], tok))
            deduped_passing.append((task, record))

    print(f"Removed {len(dedup_removed)} duplicates (Jaccard >= {DEDUP_JACCARD})")
    print(f"Final passing tasks: {len(deduped_passing)}")

    # Write judge_filter_log.jsonl (all records)
    log_path = HERE / "judge_filter_log.jsonl"
    with open(log_path, "w", encoding="utf-8") as f:
        for _, record in scored:
            f.write(json.dumps(record) + "\n")
    print(f"\nWrote judge_filter_log.jsonl ({len(scored)} records)")

    # Write filtered_dataset.jsonl (passing tasks only)
    filtered_path = HERE / "filtered_dataset.jsonl"
    with open(filtered_path, "w", encoding="utf-8") as f:
        for task, _ in deduped_passing:
            f.write(json.dumps(task) + "\n")
    print(f"Wrote filtered_dataset.jsonl ({len(deduped_passing)} tasks)")

    # Summary statistics
    total = len(scored)
    passed = len(deduped_passing)
    failed = total - passed
    pass_rate = passed / total * 100 if total > 0 else 0

    print(f"\n{'='*60}")
    print(f"JUDGE FILTER SUMMARY")
    print(f"{'='*60}")
    print(f"  Total raw tasks:      {total}")
    print(f"  Passed threshold:     {passed}  ({pass_rate:.1f}%)")
    print(f"  Failed threshold:     {failed}")
    print(f"  Dedup removed:        {len(dedup_removed)}")
    print(f"  Threshold applied:    all dimensions >= {THRESHOLD}")
    print(f"  Dedup Jaccard cutoff: {DEDUP_JACCARD}")

    # Score distribution
    for dim in ["input_coherence", "ground_truth_verifiability", "rubric_clarity"]:
        scores_list = [r["scores"][dim] for _, r in scored]
        avg = sum(scores_list) / len(scores_list) if scores_list else 0
        below = sum(1 for s in scores_list if s < THRESHOLD)
        print(f"  {dim:<35}: avg={avg:.2f}, below_threshold={below}")

    if passed < 200:
        print(f"\n[WARNING] filtered_dataset has {passed} tasks — target is >=200")
    else:
        print(f"\n[OK] filtered_dataset has {passed} tasks (target >=200 met)")

    # Dimension breakdown
    print(f"\nDimension breakdown (filtered):")
    dim_counts: dict = {}
    for task, _ in deduped_passing:
        d = task.get("dimension", "unknown")
        dim_counts[d] = dim_counts.get(d, 0) + 1
    for d, c in sorted(dim_counts.items()):
        print(f"  {d:<40}: {c}")


if __name__ == "__main__":
    main()
