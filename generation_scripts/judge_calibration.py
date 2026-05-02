"""
Tenacious-Bench v0.1 — LLM Calibration Stage

Two-tier LLM spot-check that runs AFTER rule-based judge_filter.py.

Tier architecture
-----------------
Dev-tier  (DEV_TIER_MODEL):
    Runs on ALL tasks that survived rule-based filtering.
    Checks semantic validity — does the rubric actually test the failure
    mode it claims to test?  Uses a cheap, fast model for high-volume coverage.

Eval-tier (EVAL_TIER_MODEL):
    Runs on a random CALIBRATION_SAMPLE_SIZE (~50) subset of dev-tier-passed tasks.
    Cross-validates dev-tier judgments at higher capability.
    Disagreement rate > 20% triggers a recalibration warning — human review needed.

Reads:
    generation_scripts/filtered_dataset.jsonl   (output of judge_filter.py)

Writes:
    generation_scripts/judge_calibration_log.jsonl

Requires:
    OPENROUTER_API_KEY in environment or in openrouter_key.txt at repo root.
    Run judge_filter.py first.
"""

import json
import os
import random
import sys
import urllib.request
import urllib.error
from pathlib import Path

# ---------------------------------------------------------------------------
# Model configuration — tier separation
# ---------------------------------------------------------------------------

DEV_TIER_MODEL  = "openai/gpt-4o-mini"          # high-volume filter pass (all tasks)
EVAL_TIER_MODEL = "anthropic/claude-haiku-4-5-20251001"  # spot-check only (~50 tasks)

CALIBRATION_SAMPLE_SIZE = 50   # number of tasks for eval-tier spot-check
RANDOM_SEED = 42
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# ---------------------------------------------------------------------------
# Committed judge prompts — both prompts are version-controlled here
# ---------------------------------------------------------------------------

DEV_TIER_SYSTEM_PROMPT = (
    "You are a benchmark quality evaluator for Tenacious-Bench, a domain-specific "
    "evaluation benchmark for B2B sales AI agents in the technical staffing vertical.\n\n"
    "Your job is to verify that a benchmark task's scoring rubric correctly targets "
    "its declared failure dimension. Evaluate three criteria:\n\n"
    "1. rubric_alignment (1-5): Are the rubric checks (regex patterns, field presence "
    "requirements) semantically aligned with the declared failure dimension? "
    "SOC tasks should ban assertive velocity phrases from weak signals. "
    "ICP tasks should require a disqualification notice. "
    "BOC tasks should ban specific headcount commitments when bench is overcommitted.\n\n"
    "2. rubric_difficulty_balance (1-5): Is the rubric calibrated correctly? "
    "Score 1 if trivially easy (any email passes) or trivially hard (no reasonable "
    "email could pass). Score 5 if a well-calibrated output clearly passes and a "
    "constraint-violating output clearly fails.\n\n"
    "3. input_consistency (1-5): Are the input fields internally consistent? "
    "A signal_confidence=Low task should not also have hiring_velocity_label=strong. "
    "An overcommitted bench should have bench_available_count < requested_headcount.\n\n"
    "Return ONLY a JSON object with exactly these keys:\n"
    '{"rubric_alignment": <int>, "rubric_difficulty_balance": <int>, '
    '"input_consistency": <int>, "passes_calibration": <bool>, '
    '"reason": "<one sentence>"}\n\n'
    "passes_calibration is true iff ALL three scores >= 3."
)

DEV_TIER_USER_TEMPLATE = (
    "Task ID: {task_id}\n"
    "Declared failure dimension: {seed_dimension}\n\n"
    "Input fields (key subset):\n{input_summary}\n\n"
    "Scoring rubric:\n{rubric_summary}\n\n"
    "Evaluate and return the JSON object."
)

EVAL_TIER_SYSTEM_PROMPT = (
    "You are a senior benchmark auditor for Tenacious-Bench, a domain-specific "
    "evaluation benchmark for B2B sales AI agents in technical staffing.\n\n"
    "A dev-tier model (gpt-4o-mini) has already scored this task. "
    "Your role is to independently re-evaluate and confirm or override that judgment.\n\n"
    "Evaluation criteria are identical to the dev-tier:\n"
    "1. rubric_alignment (1-5)\n"
    "2. rubric_difficulty_balance (1-5)\n"
    "3. input_consistency (1-5)\n\n"
    "Pay special attention to dimension-specific calibration issues:\n"
    "- SOC: regex_negative patterns must catch velocity over-claims without blocking "
    "appropriate professional enthusiasm (e.g., banning 'scaling' is too broad; "
    "banning 'rapidly scaling' from a Low-confidence signal is correct).\n"
    "- ICP: the disqualification condition (icp_segment=out_of_icp) must be unambiguous "
    "from the input fields alone — no inference required.\n"
    "- SR: staleness-acknowledgment patterns (regex_positive) must be specific enough "
    "to be trainable — 'noticed...earlier' is specific; 'mentioned' is too vague.\n"
    "- BOC: headcount commitment bans must reference the actual requested_headcount "
    "value, not a generic phrase.\n\n"
    "Return ONLY a JSON object with exactly these keys:\n"
    '{"rubric_alignment": <int>, "rubric_difficulty_balance": <int>, '
    '"input_consistency": <int>, "passes_calibration": <bool>, '
    '"dev_tier_agreement": <bool>, "reason": "<one sentence; note disagreements>"}\n\n'
    "dev_tier_agreement is true iff your passes_calibration matches the dev-tier value."
)

EVAL_TIER_USER_TEMPLATE = (
    "Task ID: {task_id}\n"
    "Declared failure dimension: {seed_dimension}\n\n"
    "Input fields (key subset):\n{input_summary}\n\n"
    "Scoring rubric:\n{rubric_summary}\n\n"
    "Dev-tier judgment: passes_calibration={dev_passes}, reason=\"{dev_reason}\"\n\n"
    "Independently evaluate and return the JSON object."
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        key_file = Path("openrouter_key.txt")
        if key_file.exists():
            key = key_file.read_text(encoding="utf-8").strip()
    if not key:
        raise RuntimeError(
            "OPENROUTER_API_KEY not set. Export it or put it in openrouter_key.txt."
        )
    return key


def _summarize_input(task: dict) -> str:
    inp = task.get("input", {})
    fields = [
        "task_description", "company_name", "company_size",
        "hiring_velocity_label", "signal_confidence", "bench_state",
        "bench_available_count", "requested_headcount", "icp_segment",
        "reliability_flag", "ai_maturity_score",
    ]
    lines = []
    for f in fields:
        v = inp.get(f)
        if v is not None:
            lines.append(f"  {f}: {v}")
    return "\n".join(lines) if lines else "  (no input fields)"


def _summarize_rubric(task: dict) -> str:
    rubric = task.get("scoring_rubric", [])
    lines = []
    for c in rubric:
        ct = c.get("check_type", "?")
        tgt = c.get("target", "")
        w = c.get("weight", "?")
        if isinstance(tgt, dict):
            tgt_str = json.dumps(tgt)
        else:
            tgt_str = str(tgt)[:120]
        lines.append(f"  [{ct}] weight={w}  target={tgt_str}")
    return "\n".join(lines) if lines else "  (empty rubric)"


def call_openrouter(model: str, system: str, user: str, api_key: str) -> dict:
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        "temperature": 0,
        "max_tokens": 300,
    }).encode("utf-8")

    req = urllib.request.Request(
        OPENROUTER_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
            "HTTP-Referer":  "https://github.com/YohannesDereje/Sales-Agent-Evaluation-Bench",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"OpenRouter HTTP {e.code}: {e.read().decode()[:300]}") from e

    content = body["choices"][0]["message"]["content"].strip()
    # Extract JSON — model may wrap in ```json ... ```
    if "```" in content:
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
    return json.loads(content)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    filtered_path = Path("generation_scripts/filtered_dataset.jsonl")
    log_path      = Path("generation_scripts/judge_calibration_log.jsonl")

    if not filtered_path.exists():
        print(f"ERROR: {filtered_path} not found. Run judge_filter.py first.", file=sys.stderr)
        sys.exit(1)

    api_key = load_api_key()

    tasks = []
    with open(filtered_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                tasks.append(json.loads(line))

    print(f"Loaded {len(tasks)} tasks from {filtered_path}")

    # ── Dev-tier pass — all tasks ──────────────────────────────────────────
    print(f"\nDev-tier pass ({DEV_TIER_MODEL}) — {len(tasks)} tasks …")
    dev_results: dict[str, dict] = {}

    for i, task in enumerate(tasks, 1):
        task_id = task.get("task_id", f"UNKNOWN_{i}")
        user_msg = DEV_TIER_USER_TEMPLATE.format(
            task_id=task_id,
            seed_dimension=task.get("seed_dimension", "?"),
            input_summary=_summarize_input(task),
            rubric_summary=_summarize_rubric(task),
        )
        try:
            result = call_openrouter(DEV_TIER_MODEL, DEV_TIER_SYSTEM_PROMPT, user_msg, api_key)
            dev_results[task_id] = {
                "rubric_alignment":         result.get("rubric_alignment", 0),
                "rubric_difficulty_balance": result.get("rubric_difficulty_balance", 0),
                "input_consistency":         result.get("input_consistency", 0),
                "passes_calibration":        result.get("passes_calibration", False),
                "reason":                    result.get("reason", ""),
                "error":                     None,
            }
        except Exception as e:
            dev_results[task_id] = {
                "rubric_alignment": 0, "rubric_difficulty_balance": 0,
                "input_consistency": 0, "passes_calibration": False,
                "reason": "", "error": str(e),
            }
            print(f"  WARNING: dev-tier error on {task_id}: {e}", file=sys.stderr)

        if i % 25 == 0:
            print(f"  {i}/{len(tasks)} done …")

    dev_pass_count = sum(1 for r in dev_results.values() if r["passes_calibration"])
    print(f"Dev-tier: {dev_pass_count}/{len(tasks)} passed calibration")

    # ── Eval-tier pass — sampled ~50 tasks ────────────────────────────────
    rng = random.Random(RANDOM_SEED)
    eval_sample = rng.sample(tasks, min(CALIBRATION_SAMPLE_SIZE, len(tasks)))
    print(f"\nEval-tier pass ({EVAL_TIER_MODEL}) — {len(eval_sample)} sampled tasks …")

    eval_results: dict[str, dict] = {}
    agreements = 0

    for i, task in enumerate(eval_sample, 1):
        task_id   = task.get("task_id", f"UNKNOWN_{i}")
        dev_r     = dev_results.get(task_id, {})
        dev_pass  = dev_r.get("passes_calibration", False)
        dev_reason = dev_r.get("reason", "")

        user_msg = EVAL_TIER_USER_TEMPLATE.format(
            task_id=task_id,
            seed_dimension=task.get("seed_dimension", "?"),
            input_summary=_summarize_input(task),
            rubric_summary=_summarize_rubric(task),
            dev_passes=dev_pass,
            dev_reason=dev_reason,
        )
        try:
            result = call_openrouter(EVAL_TIER_MODEL, EVAL_TIER_SYSTEM_PROMPT, user_msg, api_key)
            agrees = result.get("dev_tier_agreement", result.get("passes_calibration") == dev_pass)
            if agrees:
                agreements += 1
            eval_results[task_id] = {
                "rubric_alignment":         result.get("rubric_alignment", 0),
                "rubric_difficulty_balance": result.get("rubric_difficulty_balance", 0),
                "input_consistency":         result.get("input_consistency", 0),
                "passes_calibration":        result.get("passes_calibration", False),
                "dev_tier_agreement":        agrees,
                "reason":                    result.get("reason", ""),
                "error":                     None,
            }
        except Exception as e:
            eval_results[task_id] = {
                "rubric_alignment": 0, "rubric_difficulty_balance": 0,
                "input_consistency": 0, "passes_calibration": False,
                "dev_tier_agreement": False, "reason": "", "error": str(e),
            }
            print(f"  WARNING: eval-tier error on {task_id}: {e}", file=sys.stderr)

    agreement_rate = agreements / len(eval_sample) if eval_sample else 1.0
    print(f"Eval-tier agreement with dev-tier: {agreements}/{len(eval_sample)} ({agreement_rate:.0%})")
    if agreement_rate < 0.80:
        print(
            "WARNING: agreement rate < 80% — dev-tier calibration is unreliable. "
            "Review judge_calibration_log.jsonl for disagreements and consider "
            "re-running with updated DEV_TIER_SYSTEM_PROMPT.",
            file=sys.stderr,
        )

    # ── Write log ──────────────────────────────────────────────────────────
    with open(log_path, "w", encoding="utf-8") as f:
        for task in tasks:
            task_id = task.get("task_id", "?")
            dev_r   = dev_results.get(task_id, {})
            eval_r  = eval_results.get(task_id)   # None if not in eval sample

            record = {
                "task_id":        task_id,
                "seed_dimension": task.get("seed_dimension", ""),
                "source_mode":    task.get("source_mode", ""),
                "dev_tier": {
                    "model":                     DEV_TIER_MODEL,
                    "rubric_alignment":          dev_r.get("rubric_alignment"),
                    "rubric_difficulty_balance": dev_r.get("rubric_difficulty_balance"),
                    "input_consistency":         dev_r.get("input_consistency"),
                    "passes_calibration":        dev_r.get("passes_calibration"),
                    "reason":                    dev_r.get("reason"),
                    "error":                     dev_r.get("error"),
                },
                "eval_tier": None if eval_r is None else {
                    "model":                     EVAL_TIER_MODEL,
                    "rubric_alignment":          eval_r.get("rubric_alignment"),
                    "rubric_difficulty_balance": eval_r.get("rubric_difficulty_balance"),
                    "input_consistency":         eval_r.get("input_consistency"),
                    "passes_calibration":        eval_r.get("passes_calibration"),
                    "dev_tier_agreement":        eval_r.get("dev_tier_agreement"),
                    "reason":                    eval_r.get("reason"),
                    "error":                     eval_r.get("error"),
                },
                "in_eval_sample": task_id in eval_results,
            }
            f.write(json.dumps(record) + "\n")

    print(f"\nCalibration log written -> {log_path} ({len(tasks)} records)")
    print(f"Summary: dev_pass={dev_pass_count}/{len(tasks)}, "
          f"eval_agreement={agreement_rate:.0%} over {len(eval_sample)}-task sample")

    sys.exit(0)


if __name__ == "__main__":
    main()
