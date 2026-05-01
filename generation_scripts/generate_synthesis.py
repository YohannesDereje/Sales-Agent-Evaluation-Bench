"""
Tenacious-Bench v0.1 — Multi-LLM Synthesis Task Generator

Two-stage pipeline:
  Stage 1 (seeds):      Claude Sonnet 4.6 via OpenRouter generates complex scenario seeds,
                        one per failure dimension (25 seeds across 10 dimensions).
  Stage 2 (variations): DeepSeek Chat generates 2 variations per seed by changing one
                        input parameter — total target ~75 tasks.

Model rotation rule: Claude generates; Claude NEVER judges its own outputs.
Scoring rubrics are built programmatically (rule-based), not by any LLM.

Input:  OPENROUTER_API_KEY in .env
Output: generation_scripts/synthesis_raw.jsonl (~75 tasks)
Cost:   ≤$3 total; script raises RuntimeError if synthesis bucket in cost_log.csv exceeds $3
"""

import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL     = "https://openrouter.ai/api/v1/chat/completions"
SEED_MODEL         = "anthropic/claude-sonnet-4-6"
VARIATION_MODEL    = "deepseek/deepseek-chat"

BUDGET_CAP    = 3.00
COST_LOG_PATH = Path("cost_log.csv")
OUTPUT_PATH   = Path("generation_scripts/synthesis_raw.jsonl")

# OpenRouter pricing (per million tokens, as of 2026-05)
_PRICING = {
    "anthropic/claude-sonnet-4-6": {"input": 3.00,  "output": 15.00},
    "deepseek/deepseek-chat":       {"input": 0.14,  "output": 0.28},
}

# ---------------------------------------------------------------------------
# Seed dimensions + seeds per dimension
# The 10 dimensions map to seeds; some get 3 seeds to reach ~25 total.
# ---------------------------------------------------------------------------

SEED_DIMENSIONS = [
    ("SOC", 3),   # Signal Over-Claiming        — 3 seeds
    ("BOC", 3),   # Bench Over-Commitment       — 3 seeds
    ("TD",  3),   # Tone Drift                  — 3 seeds
    ("SR",  2),   # Signal Reliability          — 2 seeds
    ("MTL", 2),   # Multi-Thread Leakage        — 2 seeds
    ("ICP", 3),   # ICP Pre-Qualification       — 3 seeds
    ("GAP", 2),   # Gap Over-Claiming           — 2 seeds
    ("CP",  2),   # Cost Pathology              — 2 seeds
    ("DCC", 2),   # Dual-Control Coordination   — 2 seeds
    ("SE",  3),   # Scheduling Edge Case        — 3 seeds
]  # Total: 25 seeds

SCHEMA_FIELDS = (
    "company_name (string), company_size (startup_under50|mid_market_50_500|enterprise_500plus), "
    "hiring_velocity_label (strong_signal|moderate_signal|weak_hiring_velocity_signal|very_weak_signal), "
    "signal_confidence (High|Medium|Low), requested_headcount (int 1-10), "
    "bench_state (fully_available|partially_committed_50pct|overcommitted_waitlist), "
    "ai_maturity_score (0-3), icp_segment (segment_1-4 or out_of_icp), "
    "failure_scenario (string — why the agent would fail this dimension), "
    "candidate_output (string — the specific failing email or response text, 100-300 chars)"
)

SEED_SYSTEM_PROMPT = (
    "You are writing test cases for a B2B sales AI benchmark. "
    "Each test case is a hiring brief + failure scenario for the Tenacious Conversion Engine, "
    "a B2B SaaS tool that places software engineers at tech companies. "
    "Dimension: {dimension}. "
    "Brief schema: {schema_fields}. "
    "Generate one realistic, domain-specific test case where the agent would fail "
    "dimension {dimension}. "
    "Respond with ONLY a valid JSON object matching the schema above — no markdown, no explanation."
)

VARIATION_SYSTEM_PROMPT = (
    "You are generating a variation of a benchmark test case for a B2B sales AI benchmark. "
    "Given the seed test case below, produce ONE variation by changing exactly ONE of these fields: "
    "company_size, signal_confidence, bench_state, or ai_maturity_score. "
    "Keep the same seed_dimension and failure_scenario type. "
    "Respond with ONLY a valid JSON object in the same format as the seed — no markdown, no explanation."
)

# ---------------------------------------------------------------------------
# Cost helpers
# ---------------------------------------------------------------------------

def _current_synthesis_spend() -> float:
    if not COST_LOG_PATH.exists():
        return 0.0
    total = 0.0
    with open(COST_LOG_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("bucket") == "synthesis":
                try:
                    total += float(row["cost_usd"])
                except (ValueError, KeyError):
                    pass
    return total


def _compute_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    rates = _PRICING.get(model, {"input": 3.00, "output": 15.00})
    return (prompt_tokens * rates["input"] + completion_tokens * rates["output"]) / 1_000_000


def _log_cost(model: str, purpose: str, cost_usd: float) -> None:
    write_header = not COST_LOG_PATH.exists()
    with open(COST_LOG_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["timestamp", "bucket", "model", "purpose", "cost_usd"])
        writer.writerow([
            datetime.now(timezone.utc).isoformat(),
            "synthesis",
            model,
            purpose,
            f"{cost_usd:.8f}",
        ])


def _check_budget() -> None:
    spent = _current_synthesis_spend()
    if spent >= BUDGET_CAP:
        raise RuntimeError(
            f"Synthesis budget cap reached: ${spent:.4f} >= ${BUDGET_CAP:.2f}. "
            "Halting to prevent overspend."
        )


# ---------------------------------------------------------------------------
# OpenRouter call
# ---------------------------------------------------------------------------

def _call_openrouter(model: str, system_prompt: str, user_content: str,
                     max_tokens: int = 600, retries: int = 2) -> tuple[str, int, int]:
    """Returns (text, prompt_tokens, completion_tokens)."""
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY not set in .env")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/Yohannesdn/tenacious-bench",
        "X-Title": "Tenacious-Bench v0.1 synthesis generator",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_content},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.8,
    }

    for attempt in range(retries + 1):
        try:
            resp = requests.post(OPENROUTER_URL, headers=headers,
                                 json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"].strip()
            usage = data.get("usage", {})
            pt = usage.get("prompt_tokens", 0)
            ct = usage.get("completion_tokens", 0)
            return text, pt, ct
        except (requests.RequestException, KeyError, IndexError) as e:
            if attempt < retries:
                print(f"  Retry {attempt + 1}/{retries} after error: {e}")
                time.sleep(2 ** attempt)
            else:
                raise RuntimeError(f"OpenRouter call failed after {retries + 1} attempts: {e}") from e


# ---------------------------------------------------------------------------
# JSON extraction from LLM output
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict:
    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text.strip(), flags=re.MULTILINE)
    return json.loads(text.strip())


# ---------------------------------------------------------------------------
# Rubric builder (programmatic — no LLM involved in scoring)
# ---------------------------------------------------------------------------

_BANNED = (
    r"world.class|rockstar|game.chang|disruptiv|blazing|unicorn|best.of.the.best"
    r"|we guarantee|guaranteed delivery|cost savings of \d|synergize"
)


def _build_rubric(dim: str, params: dict) -> list:
    rubric = []

    if dim == "SOC":
        rubric.append({
            "check_type": "regex_negative",
            "target": r"aggressiv|rapidly.{0,10}scal|strong.{0,10}hir|rapid hiring|scaling fast",
            "weight": 0.60,
            "description": "Email must NOT use assertive velocity language on weak signal",
        })
        rubric.append({
            "check_type": "regex_positive",
            "target": r"noticed.{0,20}role|curious whether|if your team|haven.t seen",
            "weight": 0.40,
            "description": "Email must use hedged ask language",
        })

    elif dim == "BOC":
        hc = params.get("requested_headcount", 5)
        rubric.append({
            "check_type": "regex_negative",
            "target": rf"can provide {hc}|guarantee {hc}|{hc} engineers ready|commit.{{0,10}}{hc}",
            "weight": 0.50,
            "description": f"Email must NOT commit {hc} engineers when bench is constrained",
        })
        rubric.append({
            "check_type": "field_presence",
            "target": "delivery lead",
            "weight": 0.30,
            "description": "Email must route to human delivery lead",
        })
        rubric.append({
            "check_type": "length_check",
            "target": {"min": 50, "max": 700},
            "weight": 0.20,
            "description": "Cold outreach must be 50-700 characters",
        })

    elif dim == "TD":
        rubric.append({
            "check_type": "regex_negative",
            "target": _BANNED,
            "weight": 0.50,
            "description": "Email must NOT use hype or banned phrases",
        })
        rubric.append({
            "check_type": "regex_negative",
            "target": r"I understand.*but|actually.*many companies|let me be (frank|clear)",
            "weight": 0.30,
            "description": "Email must NOT be condescending",
        })
        rubric.append({
            "check_type": "length_check",
            "target": {"min": 50, "max": 700},
            "weight": 0.20,
            "description": "Response must be 50-700 characters",
        })

    elif dim == "SR":
        rubric.append({
            "check_type": "regex_negative",
            "target": r"current(ly)?.{0,10}hir|recent.{0,10}expan|right now|actively seek",
            "weight": 0.60,
            "description": "Email must NOT assert stale signal as current fact",
        })
        rubric.append({
            "check_type": "regex_positive",
            "target": r"we saw.{0,20}ago|noticed.{0,20}earlier|if your.{0,20}plan|when you.re ready",
            "weight": 0.40,
            "description": "Email must qualify claims with signal age",
        })

    elif dim == "MTL":
        rubric.append({
            "check_type": "regex_negative",
            "target": r"as (we )?discussed|previous discussion|earlier.{0,20}promis|based on our last",
            "weight": 0.50,
            "description": "Email must NOT reference prior thread context",
        })
        rubric.append({
            "check_type": "regex_negative",
            "target": r"SLA guarantee|AI tooling integration|custom deployment|as promised",
            "weight": 0.50,
            "description": "Email must NOT include capabilities from prior thread",
        })

    elif dim == "ICP":
        rubric.append({
            "check_type": "regex_negative",
            "target": r"I noticed.{0,30}team|love to explore|support your hir|hiring goals",
            "weight": 0.70,
            "description": "Output must NOT contain outreach email to disqualified prospect",
        })
        rubric.append({
            "check_type": "field_presence",
            "target": "not a fit",
            "weight": 0.30,
            "description": "Output must contain ICP disqualification statement",
        })

    else:
        # GAP, CP, DCC, SE — generic rubric
        rubric.append({
            "check_type": "regex_negative",
            "target": _BANNED,
            "weight": 0.50,
            "description": "Email must NOT contain banned phrases",
        })
        rubric.append({
            "check_type": "length_check",
            "target": {"min": 50, "max": 700},
            "weight": 0.50,
            "description": "Response must be 50-700 characters",
        })

    return rubric


# ---------------------------------------------------------------------------
# Task assembler
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


def _assemble_task(dim: str, parsed: dict, seq: int,
                   task_type: str, seed_seq: int | None = None) -> dict:
    rubric = _build_rubric(dim, parsed)
    label  = "SEED" if task_type == "seed" else f"VAR{seed_seq}"
    return {
        "task_id": f"TB-{dim}-SY-{seq:04d}-{label}",
        "seed_dimension": dim,
        "dimension": _DIM_TO_FULL.get(dim, dim.lower()),
        "source_mode": "multi_llm_synthesis",
        "difficulty": "hard" if task_type == "seed" else "medium",
        "input": {
            "company_name":          parsed.get("company_name", ""),
            "company_size":          parsed.get("company_size", ""),
            "hiring_velocity_label": parsed.get("hiring_velocity_label", ""),
            "signal_confidence":     parsed.get("signal_confidence", ""),
            "requested_headcount":   parsed.get("requested_headcount", 3),
            "bench_state":           parsed.get("bench_state", ""),
            "ai_maturity_score":     parsed.get("ai_maturity_score", 0),
            "icp_segment":           parsed.get("icp_segment", ""),
            "task_description":      parsed.get("failure_scenario", ""),
        },
        "scoring_rubric": rubric,
        "candidate_output": parsed.get("candidate_output", ""),
        "ground_truth": {
            "expected_pass": False,  # all synthesis tasks demonstrate failure scenarios
            "passing_score": 0.70,
        },
        "metadata": {
            "source_mode":           "multi_llm_synthesis",
            "synthesis_seed_model":  SEED_MODEL,
            "variation_model":       VARIATION_MODEL if task_type == "variation" else None,
            "generated_by":          SEED_MODEL if task_type == "seed" else VARIATION_MODEL,
            "task_type":             task_type,
        },
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not OPENROUTER_API_KEY:
        print("ERROR: OPENROUTER_API_KEY not set in .env", file=sys.stderr)
        sys.exit(1)

    _check_budget()

    tasks  = []
    global_seq = 1

    for dim, n_seeds in SEED_DIMENSIONS:
        print(f"\n[{dim}] Generating {n_seeds} seed(s) with {SEED_MODEL}")
        seeds_for_dim = []

        for seed_idx in range(n_seeds):
            _check_budget()

            system_prompt = SEED_SYSTEM_PROMPT.format(
                dimension=dim,
                schema_fields=SCHEMA_FIELDS,
            )
            user_msg = (
                f"Generate seed #{seed_idx + 1} of {n_seeds} for dimension {dim}. "
                f"Make it distinct from prior seeds for this dimension."
            )

            try:
                text, pt, ct = _call_openrouter(SEED_MODEL, system_prompt, user_msg,
                                                max_tokens=600)
            except RuntimeError as e:
                print(f"  SKIP seed {seed_idx + 1}: {e}", file=sys.stderr)
                continue

            cost = _compute_cost(SEED_MODEL, pt, ct)
            _log_cost(SEED_MODEL, f"seed dim={dim} idx={seed_idx}", cost)
            print(f"  Seed {seed_idx + 1}: {pt}pt + {ct}ct = ${cost:.5f}")

            try:
                parsed = _extract_json(text)
            except (json.JSONDecodeError, ValueError) as e:
                print(f"  SKIP seed {seed_idx + 1}: JSON parse error: {e}", file=sys.stderr)
                continue

            task = _assemble_task(dim, parsed, global_seq, "seed")
            tasks.append(task)
            seeds_for_dim.append(parsed)
            global_seq += 1

        # Stage 2: variations for each seed (DeepSeek)
        for s_idx, seed_parsed in enumerate(seeds_for_dim):
            for var_idx in range(2):
                _check_budget()

                system_prompt = VARIATION_SYSTEM_PROMPT
                user_msg = (
                    f"Seed test case:\n{json.dumps(seed_parsed, indent=2)}\n\n"
                    f"Generate variation #{var_idx + 1} — change exactly ONE field."
                )

                try:
                    text, pt, ct = _call_openrouter(VARIATION_MODEL, system_prompt, user_msg,
                                                    max_tokens=500)
                except RuntimeError as e:
                    print(f"  SKIP var {var_idx + 1}: {e}", file=sys.stderr)
                    continue

                cost = _compute_cost(VARIATION_MODEL, pt, ct)
                _log_cost(VARIATION_MODEL, f"variation dim={dim} seed={s_idx} var={var_idx}", cost)
                print(f"  Variation {s_idx + 1}.{var_idx + 1}: {pt}pt + {ct}ct = ${cost:.6f}")

                try:
                    parsed = _extract_json(text)
                except (json.JSONDecodeError, ValueError) as e:
                    print(f"  SKIP var {var_idx + 1}: JSON parse error: {e}", file=sys.stderr)
                    continue

                task = _assemble_task(dim, parsed, global_seq, "variation", seed_seq=s_idx + 1)
                tasks.append(task)
                global_seq += 1

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for task in tasks:
            f.write(json.dumps(task) + "\n")

    total_spend = _current_synthesis_spend()
    print(f"\nWrote {len(tasks)} tasks -> {OUTPUT_PATH}")
    print(f"Total synthesis spend: ${total_spend:.4f} (cap: ${BUDGET_CAP:.2f})")

    # Success checks
    errors = 0
    if len(tasks) < 60:
        print(f"WARNING: only {len(tasks)} tasks — target is >=60", file=sys.stderr)
        errors += 1
    if total_spend > BUDGET_CAP:
        print(f"ERROR: synthesis spend ${total_spend:.4f} exceeds cap ${BUDGET_CAP:.2f}",
              file=sys.stderr)
        errors += 1

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
