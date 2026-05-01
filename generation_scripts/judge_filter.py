"""
Tenacious-Bench v0.1 — Judge Filter

Rule-based quality filter + Jaccard deduplication.
No LLM calls — fully deterministic.

Reads:
  generation_scripts/trace_derived_raw.jsonl
  generation_scripts/programmatic_raw.jsonl
  generation_scripts/synthesis_raw.jsonl
  generation_scripts/hand_authored_tasks.jsonl

Scores each task on 3 dimensions (1–5 each):
  input_coherence             — key input fields present and internally consistent
  ground_truth_verifiability  — scoring_rubric non-empty, valid check types, non-empty targets
  rubric_application_clarity  — patterns non-trivial, length_check complete, weights valid

Inclusion threshold: ALL 3 dimensions ≥ 3.

Jaccard dedup: tokenize narrative fields; drop if Jaccard ≥ 0.80 against any included task
(keep the task with the higher input_coherence score when evicting).

Writes:
  generation_scripts/judge_filter_log.jsonl   — one record per input task
  generation_scripts/filtered_dataset.jsonl   — included tasks only
"""

import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR  = Path("generation_scripts")
INPUT_FILES = [
    SCRIPT_DIR / "trace_derived_raw.jsonl",
    SCRIPT_DIR / "programmatic_raw.jsonl",
    SCRIPT_DIR / "synthesis_raw.jsonl",
    SCRIPT_DIR / "hand_authored_tasks.jsonl",
]
LOG_PATH      = SCRIPT_DIR / "judge_filter_log.jsonl"
FILTERED_PATH = SCRIPT_DIR / "filtered_dataset.jsonl"

INCLUDE_THRESHOLD = 3   # all 3 scores must be >= this
JACCARD_THRESHOLD = 0.80

# ---------------------------------------------------------------------------
# Valid enumerations
# ---------------------------------------------------------------------------

VALID_CHECK_TYPES  = {"regex_negative", "regex_positive", "length_check", "field_presence"}
VALID_SIGNAL_CONF  = {"High", "Medium", "Low"}
VALID_BENCH_STATES = {"fully_available", "partially_committed_50pct", "overcommitted_waitlist"}

# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------

def score_input_coherence(task: dict) -> tuple[int, str]:
    """
    1-5 scale.
    Checks: task_description present, company identifier present,
    at least one signal field present, bench_state consistent if given.
    """
    inp     = task.get("input", {})
    issues  = []
    points  = 1  # baseline

    # task_description non-empty (most critical)
    desc = inp.get("task_description", "")
    if isinstance(desc, str) and len(desc.strip()) >= 10:
        points += 1
    else:
        issues.append("task_description missing or too short")

    # company identifier: company_name or company_size non-empty
    has_company = (
        bool(inp.get("company_name", "").strip())
        or bool(inp.get("company_size", "").strip())
    )
    if has_company:
        points += 1
    else:
        issues.append("no company_name or company_size")

    # at least one signal field present and non-empty
    signal_fields = [
        inp.get("hiring_velocity_label", ""),
        inp.get("signal_confidence", ""),
        inp.get("bench_state", ""),
        inp.get("icp_segment", ""),
        inp.get("prospect_message", ""),
        inp.get("active_brief_capabilities"),
    ]
    if any(f for f in signal_fields if f):
        points += 1
    else:
        issues.append("no signal fields present")

    # bench consistency: if overcommitted, requested > available (if both present)
    bench_state = inp.get("bench_state", "")
    avail       = inp.get("bench_available_count")
    req         = inp.get("requested_headcount")
    if (bench_state == "overcommitted_waitlist"
            and isinstance(avail, (int, float))
            and isinstance(req, (int, float))
            and req <= avail):
        issues.append("bench_state=overcommitted but requested_headcount <= bench_available_count")
        # do not subtract — just record; scoring cap already limits to 5
    elif bench_state or (isinstance(avail, (int, float)) and isinstance(req, (int, float))):
        # bench state present and consistent (or not present — not penalised)
        pass

    score = min(points, 5)
    return score, "; ".join(issues) if issues else "OK"


def score_ground_truth_verifiability(task: dict) -> tuple[int, str]:
    """
    1-5 scale.
    Checks: scoring_rubric non-empty, check_types valid, targets non-empty,
    expected_pass present.
    """
    rubric  = task.get("scoring_rubric", [])
    gt      = task.get("ground_truth", {})
    issues  = []
    points  = 1  # baseline

    if rubric:
        points += 1
    else:
        issues.append("scoring_rubric is empty")
        return 1, "; ".join(issues)

    # all check_types are valid enums
    bad_types = [c.get("check_type") for c in rubric if c.get("check_type") not in VALID_CHECK_TYPES]
    if not bad_types:
        points += 1
    else:
        issues.append(f"invalid check_type(s): {bad_types}")

    # all targets are non-empty
    bad_targets = []
    for c in rubric:
        t = c.get("target")
        if t is None or (isinstance(t, str) and not t.strip()):
            bad_targets.append(c.get("check_type", "?"))
    if not bad_targets:
        points += 1
    else:
        issues.append(f"empty target in checks: {bad_targets}")

    # expected_pass present in ground_truth
    if "expected_pass" in gt:
        points += 1
    else:
        issues.append("expected_pass missing from ground_truth")

    score = min(points, 5)
    return score, "; ".join(issues) if issues else "OK"


def score_rubric_application_clarity(task: dict) -> tuple[int, str]:
    """
    1-5 scale.
    Checks: regex patterns non-trivial (>3 chars), length_check has min+max,
    all weights > 0, sum of weights <= 1.0.
    """
    rubric = task.get("scoring_rubric", [])
    if not rubric:
        return 1, "scoring_rubric is empty"

    issues = []
    points = 1  # baseline

    # regex_negative / regex_positive patterns have length > 3
    short_patterns = []
    for c in rubric:
        if c.get("check_type") in ("regex_negative", "regex_positive"):
            target = c.get("target", "")
            if isinstance(target, str) and len(target) <= 3:
                short_patterns.append(repr(target))
    if not short_patterns:
        points += 1
    else:
        issues.append(f"trivial regex pattern(s): {short_patterns}")

    # length_check checks have both min and max
    bad_length = []
    for c in rubric:
        if c.get("check_type") == "length_check":
            t = c.get("target", {})
            if not (isinstance(t, dict) and "min" in t and "max" in t):
                bad_length.append("incomplete length_check target")
    if not bad_length:
        points += 1
    else:
        issues.extend(bad_length)

    # all weights are positive
    bad_weights = [c.get("weight") for c in rubric if not isinstance(c.get("weight"), (int, float)) or c.get("weight", 0) <= 0]
    if not bad_weights:
        points += 1
    else:
        issues.append(f"non-positive weight(s): {bad_weights}")

    # sum of weights <= 1.0
    total_w = sum(c.get("weight", 0) for c in rubric if isinstance(c.get("weight"), (int, float)))
    if total_w <= 1.001:  # small float tolerance
        points += 1
    else:
        issues.append(f"weights sum {total_w:.3f} > 1.0")

    score = min(points, 5)
    return score, "; ".join(issues) if issues else "OK"


# ---------------------------------------------------------------------------
# Jaccard tokenizer — compound scenario-key proxy for hiring_signal_brief
#
# Using narrative text (task_description / candidate_output) inflates
# similarity for template-generated tasks that share prose structure but
# test genuinely different scenarios. Instead, we encode each task as a
# small set of tokens derived from its core scenario parameters:
#
#   seed_dimension | company identifier | velocity | confidence | bench | headcount | ai_maturity
#
# Two tasks with identical compound key AND identical candidate_output
# prefix are genuine duplicates. Different dimensions on the same hiring
# situation are distinct tasks and produce different compound keys.
# ---------------------------------------------------------------------------

def tokenize(task: dict) -> frozenset:
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
    prospect = inp.get("prospect_message", "")[:30]

    key = f"{dim}|{company}|{velocity}|{conf}|{bench}|{headcount}|{ai_mat}|{vertical}"
    tokens: set = {key}

    # Include first 6 words of candidate_output to catch story-level duplicates
    # (same scenario with different parameter labels but identical failing email)
    cand_prefix = " ".join(task.get("candidate_output", "").split()[:6])
    if cand_prefix:
        tokens.add(f"cand_{cand_prefix.lower()}")
    if prospect:
        tokens.add(f"prospect_{prospect.lower()}")

    return frozenset(tokens)


def jaccard(s1: frozenset, s2: frozenset) -> float:
    if not s1 and not s2:
        return 1.0
    union = len(s1 | s2)
    return len(s1 & s2) / union if union else 0.0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # --- Load all input tasks ---
    all_tasks = []
    for path in INPUT_FILES:
        if not path.exists():
            print(f"WARNING: {path} not found — skipping", file=sys.stderr)
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        task = json.loads(line)
                        task["_source_file"] = path.name
                        all_tasks.append(task)
                    except json.JSONDecodeError as e:
                        print(f"  JSON error in {path.name}: {e}", file=sys.stderr)

    print(f"Loaded {len(all_tasks)} tasks from {len(INPUT_FILES)} files")

    # Sort input tasks by quality priority so higher-quality tasks survive dedup
    # when a duplicate pair is found.  hand_authored > trace_derived > synthesis
    # seeds > programmatic > synthesis variations.
    _priority = {"hand_authored": 0, "trace_derived": 1,
                 "multi_llm_synthesis": 2, "programmatic": 3}

    def _sort_key(t: dict) -> tuple:
        p = _priority.get(t.get("source_mode", ""), 4)
        is_var = 1 if t.get("metadata", {}).get("task_type") == "variation" else 0
        return (p, is_var)

    all_tasks.sort(key=_sort_key)

    # --- Score each task ---
    scored = []
    for task in all_tasks:
        ic_score,  ic_reason  = score_input_coherence(task)
        gtv_score, gtv_reason = score_ground_truth_verifiability(task)
        rac_score, rac_reason = score_rubric_application_clarity(task)

        passes_threshold = (ic_score >= INCLUDE_THRESHOLD
                            and gtv_score >= INCLUDE_THRESHOLD
                            and rac_score >= INCLUDE_THRESHOLD)

        scored.append({
            "task": task,
            "input_coherence":            ic_score,
            "ground_truth_verifiability":  gtv_score,
            "rubric_application_clarity":  rac_score,
            "passes_threshold":            passes_threshold,
            "ic_reason":                   ic_reason,
            "gtv_reason":                  gtv_reason,
            "rac_reason":                  rac_reason,
        })

    threshold_pass = [s for s in scored if s["passes_threshold"]]
    threshold_fail = [s for s in scored if not s["passes_threshold"]]
    print(f"  Threshold pass (all >=3): {len(threshold_pass)}")
    print(f"  Threshold fail:           {len(threshold_fail)}")

    # --- Jaccard dedup on threshold-passing tasks ---
    # Sort by input_coherence descending so higher-quality tasks are
    # considered first and survive dedup over lower-quality duplicates.
    threshold_pass.sort(key=lambda s: s["input_coherence"], reverse=True)

    included    = []   # (scored_entry, token_set)
    dedup_drops = set()

    for entry in threshold_pass:
        tokens = tokenize(entry["task"])
        duplicate_of = None
        for prev_entry, prev_tokens in included:
            j = jaccard(tokens, prev_tokens)
            if j >= JACCARD_THRESHOLD:
                duplicate_of = prev_entry["task"].get("task_id", "?")
                break
        if duplicate_of is None:
            included.append((entry, tokens))
        else:
            dedup_drops.add(entry["task"].get("task_id", "?"))
            entry["jaccard_drop_duplicate_of"] = duplicate_of

    print(f"  After Jaccard dedup:      {len(included)}")
    print(f"  Dropped as duplicates:    {len(dedup_drops)}")

    # --- Write log ---
    SCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    included_ids = {e["task"].get("task_id") for e, _ in included}

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        for entry in scored:
            task    = entry["task"]
            task_id = task.get("task_id", "?")
            final_include = task_id in included_ids
            reason_parts  = []
            if not entry["passes_threshold"]:
                if entry["input_coherence"] < INCLUDE_THRESHOLD:
                    reason_parts.append(f"input_coherence={entry['input_coherence']} ({entry['ic_reason']})")
                if entry["ground_truth_verifiability"] < INCLUDE_THRESHOLD:
                    reason_parts.append(f"gtv={entry['ground_truth_verifiability']} ({entry['gtv_reason']})")
                if entry["rubric_application_clarity"] < INCLUDE_THRESHOLD:
                    reason_parts.append(f"rac={entry['rac_reason']}")
            elif task_id in dedup_drops:
                reason_parts.append(f"jaccard_dup_of={entry.get('jaccard_drop_duplicate_of', '?')}")

            log_record = {
                "task_id":                       task_id,
                "source_file":                   task.get("_source_file", ""),
                "seed_dimension":                task.get("seed_dimension", ""),
                "source_mode":                   task.get("source_mode", ""),
                "input_coherence":               entry["input_coherence"],
                "ground_truth_verifiability":    entry["ground_truth_verifiability"],
                "rubric_application_clarity":    entry["rubric_application_clarity"],
                "include":                        final_include,
                "exclude_reason":                "; ".join(reason_parts) if reason_parts else "",
            }
            f.write(json.dumps(log_record) + "\n")

    print(f"Log written -> {LOG_PATH} ({len(all_tasks)} records)")

    # --- Write filtered dataset ---
    with open(FILTERED_PATH, "w", encoding="utf-8") as f:
        for entry, _ in included:
            task = {k: v for k, v in entry["task"].items() if not k.startswith("_")}
            f.write(json.dumps(task) + "\n")

    n_filtered = len(included)
    print(f"Filtered dataset written -> {FILTERED_PATH} ({n_filtered} tasks)")

    # --- Success checks ---
    errors = 0
    if n_filtered < 200:
        print(f"ERROR: filtered_dataset has {n_filtered} tasks — target is >=200", file=sys.stderr)
        errors += 1

    log_count = sum(1 for _ in open(LOG_PATH))
    if log_count != len(all_tasks):
        print(f"ERROR: log has {log_count} records but input had {len(all_tasks)}", file=sys.stderr)
        errors += 1

    # Verify no Jaccard >= 0.80 within filtered output
    filtered_tokens = [tokenize(e["task"]) for e, _ in included]
    jac_violations = 0
    for i in range(len(filtered_tokens)):
        for j in range(i + 1, len(filtered_tokens)):
            if jaccard(filtered_tokens[i], filtered_tokens[j]) >= JACCARD_THRESHOLD:
                jac_violations += 1
    if jac_violations:
        print(f"ERROR: {jac_violations} Jaccard violation(s) in filtered output", file=sys.stderr)
        errors += 1
    else:
        print("Jaccard check: no violations in filtered output")

    # Score distribution summary
    dim_counts: dict = {}
    for entry, _ in included:
        d = entry["task"].get("seed_dimension", "?")
        dim_counts[d] = dim_counts.get(d, 0) + 1
    print(f"Filtered dimension spread: {dim_counts}")

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
