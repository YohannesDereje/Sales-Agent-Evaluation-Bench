"""
Tenacious-Bench v0.1 — Ablation Harness

Runs Delta A, Delta B, Delta C, and Cost-Pareto comparisons from a single
parameterized interface against the sealed held-out partition.

Usage:
    python ablations/run_ablations.py --variant all          # run everything
    python ablations/run_ablations.py --variant delta_a
    python ablations/run_ablations.py --variant delta_b
    python ablations/run_ablations.py --variant delta_c
    python ablations/run_ablations.py --variant cost_pareto

Outputs:
    ablations/held_out_traces.jsonl     -- per-task scored traces (all variants)
    ablations/ablation_results.json     -- summary stats: pass rates, CIs, p-values

Requires:
    - tenacious_bench_v0.1/held_out/held_out.jsonl  (sealed partition)
    - training/checkpoints/  OR  HF adapter pull for trained_lora variant
    - unsloth, transformers, trl installed
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

HELD_OUT_FILE  = Path("tenacious_bench_v0.1/held_out/held_out.jsonl")
TRACES_FILE    = Path("ablations/held_out_traces.jsonl")
RESULTS_FILE   = Path("ablations/ablation_results.json")
WEEK10_TAU2_FILE = Path("week_10_artifacts/tau2_results.json")  # Week 10 τ²-Bench scores

# ---------------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------------

BACKBONE         = "unsloth/Qwen2.5-1.5B-Instruct"
ADAPTER_REPO     = "Yohannesdn/tenacious-outreach-lora-qwen-1.5b"
MAX_NEW_TOKENS   = 300
BOOTSTRAP_N      = 1000
BOOTSTRAP_SEED   = 42

# Engineered system prompt for Delta B (prompt-engineering-only baseline)
DELTA_B_SYSTEM_PROMPT = (
    "You are a B2B outreach specialist for Tenacious Technologies, a contract "
    "engineering staffing firm. When drafting outreach emails, follow these rules "
    "strictly:\n"
    "1. SIGNAL HONESTY: If hiring_velocity_label contains 'weak' or signal_confidence "
    "is Low, do NOT use assertive velocity language such as 'rapidly scaling', "
    "'strong hiring momentum', or 'aggressive growth'. Use hedged framing instead.\n"
    "2. BENCH HONESTY: Never commit to a specific headcount that exceeds "
    "bench_available_count. Route to a human delivery lead if overcommitted.\n"
    "3. TONE: Maintain professional Tenacious voice. Do not mirror hype language "
    "from the prospect. Avoid: rockstar, game-changing, crushing it, world-class.\n"
    "4. ICP COMPLIANCE: If icp_segment is out_of_icp, issue a disqualification "
    "notice and do not send outreach.\n"
    "5. SIGNAL RELIABILITY: If reliability_flag is set or signal is older than "
    "180 days, acknowledge staleness explicitly before referencing the signal.\n"
    "Keep the email to 50-700 characters. Be specific, professional, and honest."
)

# ---------------------------------------------------------------------------
# Scoring — reuse scoring_evaluator logic inline
# ---------------------------------------------------------------------------

import re

def run_check(check: dict, output: str) -> float:
    ct     = check.get("check_type", "")
    target = check.get("target")
    weight = float(check.get("weight", 0))

    if ct == "regex_negative":
        pattern = target if isinstance(target, str) else ""
        passed  = not bool(re.search(pattern, output, re.IGNORECASE)) if pattern else True
    elif ct == "regex_positive":
        pattern = target if isinstance(target, str) else ""
        passed  = bool(re.search(pattern, output, re.IGNORECASE)) if pattern else False
    elif ct == "length_check":
        mn = target.get("min", 0) if isinstance(target, dict) else 0
        mx = target.get("max", 9999) if isinstance(target, dict) else 9999
        passed = mn <= len(output) <= mx
    elif ct == "field_presence":
        phrase = target if isinstance(target, str) else ""
        passed = phrase.lower() in output.lower() if phrase else False
    else:
        passed = False

    return weight if passed else 0.0


def score_task(task: dict, output: str) -> dict:
    rubric  = task.get("scoring_rubric", [])
    details = []
    total   = 0.0
    for check in rubric:
        earned = run_check(check, output)
        total += earned
        details.append({
            "check_type": check.get("check_type"),
            "weight":     check.get("weight"),
            "earned":     earned,
            "passed":     earned > 0,
        })
    threshold = task.get("ground_truth", {}).get("passing_score", 0.70)
    return {
        "weighted_score": round(total, 4),
        "passed":         total >= threshold,
        "threshold":      threshold,
        "checks":         details,
    }

# ---------------------------------------------------------------------------
# Model loading helpers
# ---------------------------------------------------------------------------

def load_baseline_model():
    """Load Qwen2.5-1.5B-Instruct with no LoRA adapter."""
    from unsloth import FastLanguageModel
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name    = BACKBONE,
        max_seq_length = 1024,
        dtype         = None,
        load_in_4bit  = True,
    )
    FastLanguageModel.for_inference(model)
    return model, tokenizer


def load_prompt_eng_model():
    """Same backbone as baseline — system prompt injected at inference time."""
    return load_baseline_model()  # model identical; prompt differs at call site


def load_trained_lora_model():
    """Load base model then merge the trained LoRA adapter."""
    from unsloth import FastLanguageModel
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name    = ADAPTER_REPO,   # HF adapter repo (already merged or PEFT)
        max_seq_length = 1024,
        dtype         = None,
        load_in_4bit  = True,
    )
    FastLanguageModel.for_inference(model)
    return model, tokenizer


MODEL_LOADERS = {
    "baseline":   load_baseline_model,
    "prompt_eng": load_prompt_eng_model,
    "trained_lora": load_trained_lora_model,
}

# ---------------------------------------------------------------------------
# Per-task inference with timing and token counting
# ---------------------------------------------------------------------------

def build_prompt(task: dict, system_prompt: str | None, tokenizer) -> list[dict]:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": task["input"]["task_description"]})
    return messages


def generate_output(model, tokenizer, messages: list[dict]) -> tuple[str, int, int, float]:
    """
    Returns (output_text, input_tokens, output_tokens, latency_ms).
    Counts tokens for Cost-Pareto instrumentation.
    """
    inputs = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_tensors="pt",
    ).to(model.device)

    input_tokens = inputs.shape[-1]

    t0 = time.perf_counter()
    with __import__("torch").no_grad():
        out_ids = model.generate(
            inputs,
            max_new_tokens = MAX_NEW_TOKENS,
            do_sample      = False,
            temperature    = 1.0,
            use_cache      = True,
        )
    latency_ms = (time.perf_counter() - t0) * 1000

    new_ids      = out_ids[0][input_tokens:]
    output_text  = tokenizer.decode(new_ids, skip_special_tokens=True).strip()
    output_tokens = len(new_ids)

    return output_text, input_tokens, output_tokens, latency_ms


def cost_usd(input_tokens: int, output_tokens: int, variant: str) -> float:
    """
    Per-task cost in USD.  Local T4 inference = $0.00.
    Formula retained so the harness is portable to cloud inference:
      GPT-4o-mini pricing: $0.15/1M input, $0.60/1M output
    """
    if variant in ("baseline", "prompt_eng", "trained_lora"):
        return 0.0   # local Colab T4 — no API cost
    # Cloud fallback pricing (not used in v0.1):
    return (input_tokens * 0.15 + output_tokens * 0.60) / 1_000_000

# ---------------------------------------------------------------------------
# Evaluate one variant over the full held-out set
# ---------------------------------------------------------------------------

def evaluate_variant(
    variant: str,
    tasks: list[dict],
    model,
    tokenizer,
    system_prompt: str | None = None,
) -> list[dict]:
    """
    Score every task in `tasks` with the given model + optional system prompt.
    Returns a list of trace records ready for held_out_traces.jsonl.
    """
    traces = []
    for task in tasks:
        task_id  = task.get("task_id", "?")
        messages = build_prompt(task, system_prompt, tokenizer)

        try:
            output, n_in, n_out, latency = generate_output(model, tokenizer, messages)
            score   = score_task(task, output)
            err     = None
        except Exception as e:
            output, n_in, n_out, latency = "", 0, 0, 0.0
            score   = {"weighted_score": 0.0, "passed": False, "threshold": 0.70, "checks": []}
            err     = str(e)
            print(f"  ERROR on {task_id} ({variant}): {e}", file=sys.stderr)

        traces.append({
            "task_id":        task_id,
            "seed_dimension": task.get("seed_dimension", ""),
            "model_variant":  variant,
            "output":         output,
            "weighted_score": score["weighted_score"],
            "pass":           score["passed"],
            "checks":         score["checks"],
            "input_tokens":   n_in,
            "output_tokens":  n_out,
            "latency_ms":     round(latency, 1),
            "cost_usd":       cost_usd(n_in, n_out, variant),
            "error":          err,
        })

    n_pass = sum(1 for t in traces if t["pass"])
    print(f"  {variant}: {n_pass}/{len(traces)} passed ({n_pass/len(traces):.1%})")
    return traces

# ---------------------------------------------------------------------------
# Bootstrap statistics — paired bootstrap CI and p-value
# ---------------------------------------------------------------------------

def paired_bootstrap(
    scores_a: list[float],
    scores_b: list[float],
    n_resamples: int = BOOTSTRAP_N,
    seed: int = BOOTSTRAP_SEED,
) -> dict:
    """
    Paired bootstrap confidence interval and p-value for the lift (A - B).

    Returns:
        lift:     observed mean(A) - mean(B)
        ci_lower: 2.5th percentile of bootstrap distribution
        ci_upper: 97.5th percentile of bootstrap distribution
        p_value:  fraction of bootstrap samples where lift <= 0 (one-sided H0: lift <= 0)
    """
    rng   = np.random.default_rng(seed)
    a     = np.array(scores_a)
    b     = np.array(scores_b)
    n     = len(a)
    assert len(a) == len(b), "score lists must be same length (paired)"

    obs_lift = a.mean() - b.mean()
    boot_lifts = np.empty(n_resamples)

    for i in range(n_resamples):
        idx = rng.integers(0, n, size=n)
        boot_lifts[i] = a[idx].mean() - b[idx].mean()

    ci_lower = float(np.percentile(boot_lifts, 2.5))
    ci_upper = float(np.percentile(boot_lifts, 97.5))
    p_value  = float((boot_lifts <= 0).mean())   # one-sided: P(lift <= 0)

    return {
        "lift":     round(float(obs_lift), 6),
        "ci_lower": round(ci_lower, 6),
        "ci_upper": round(ci_upper, 6),
        "p_value":  round(p_value, 4),
        "n_resamples": n_resamples,
        "seed":     seed,
    }

# ---------------------------------------------------------------------------
# Delta C — τ²-Bench reference (informational, no re-run)
# ---------------------------------------------------------------------------

def delta_c_informational() -> dict:
    """
    Loads Week 10 τ²-Bench results from week_10_artifacts/tau2_results.json
    and reports the comparison informally.

    τ²-Bench measures binary task completion (email sent = PASS), not output
    quality.  Delta C records the gap between τ²-Bench pass rate (typically
    near 1.0 for a functional agent) and Tenacious-Bench held-out pass rate
    to quantify how much quality signal τ²-Bench is missing.

    No re-run of τ²-Bench retail is performed — the Week 10 result is treated
    as a fixed reference point.
    """
    tau2_pass_rate = None
    tau2_task_count = None

    if WEEK10_TAU2_FILE.exists():
        with open(WEEK10_TAU2_FILE, encoding="utf-8") as f:
            tau2 = json.load(f)
        tau2_pass_rate  = tau2.get("pass_rate")
        tau2_task_count = tau2.get("task_count")
    else:
        # Hardcoded from Week 10 evaluation report (no re-run needed)
        tau2_pass_rate  = 1.0   # τ²-Bench: agent sent email → PASS on all 42 tasks
        tau2_task_count = 42

    return {
        "tau2_pass_rate":            tau2_pass_rate,
        "tau2_task_count":           tau2_task_count,
        "tenacious_bench_note":      (
            "τ²-Bench awards binary task-completion credit (email sent = PASS). "
            "Tenacious-Bench measures output-quality compliance (signal honesty, "
            "bench commitment, ICP disqualification). The gap between τ²-Bench "
            "pass rate (~1.0) and Tenacious-Bench baseline pass rate (0.333) "
            "quantifies failure modes that τ²-Bench cannot detect."
        ),
        "tau2_gap_vs_baseline":      round(tau2_pass_rate - 0.3333, 4) if tau2_pass_rate else None,
        "rerun_required":            False,
    }

# ---------------------------------------------------------------------------
# Cost-Pareto summary
# ---------------------------------------------------------------------------

def cost_pareto_summary(all_traces: dict[str, list[dict]]) -> dict:
    """
    Aggregates timing, token, and cost metrics across variants.
    `all_traces` is a dict mapping variant name -> list of trace records.
    """
    summary = {}
    for variant, traces in all_traces.items():
        latencies  = [t["latency_ms"] for t in traces if t["latency_ms"] > 0]
        in_toks    = [t["input_tokens"] for t in traces]
        out_toks   = [t["output_tokens"] for t in traces]
        costs      = [t["cost_usd"] for t in traces]
        n_pass     = sum(1 for t in traces if t["pass"])

        summary[variant] = {
            "pass_rate":           round(n_pass / len(traces), 4) if traces else 0,
            "avg_latency_ms":      round(float(np.mean(latencies)), 1) if latencies else 0,
            "p50_latency_ms":      round(float(np.percentile(latencies, 50)), 1) if latencies else 0,
            "p95_latency_ms":      round(float(np.percentile(latencies, 95)), 1) if latencies else 0,
            "avg_input_tokens":    round(float(np.mean(in_toks)), 1) if in_toks else 0,
            "avg_output_tokens":   round(float(np.mean(out_toks)), 1) if out_toks else 0,
            "cost_per_task_usd":   round(float(np.mean(costs)), 6) if costs else 0,
            "cost_per_1k_tasks_usd": round(float(np.mean(costs)) * 1000, 4) if costs else 0,
        }
    return summary

# ---------------------------------------------------------------------------
# Main harness
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Tenacious-Bench v0.1 Ablation Harness")
    parser.add_argument(
        "--variant",
        choices=["delta_a", "delta_b", "delta_c", "cost_pareto", "all"],
        default="all",
        help="Which ablation to run (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load tasks and print counts without running inference",
    )
    args = parser.parse_args()

    run_delta_a    = args.variant in ("delta_a",    "all")
    run_delta_b    = args.variant in ("delta_b",    "all")
    run_delta_c    = args.variant in ("delta_c",    "all")
    run_cost_pareto = args.variant in ("cost_pareto", "all")

    # ── Load held-out tasks ───────────────────────────────────────────────
    if not HELD_OUT_FILE.exists():
        print(f"ERROR: {HELD_OUT_FILE} not found. Unseal the held-out partition first.",
              file=sys.stderr)
        sys.exit(1)

    tasks = []
    with open(HELD_OUT_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                tasks.append(json.loads(line))

    print(f"Held-out tasks loaded: {len(tasks)}")

    if args.dry_run:
        print("Dry run — exiting before inference.")
        sys.exit(0)

    all_traces: dict[str, list[dict]] = {}
    results: dict = {}

    # ── Delta C — τ²-Bench reference (no inference needed) ────────────────
    if run_delta_c:
        print("\n── Delta C: τ²-Bench informational reference ──")
        results["delta_c"] = delta_c_informational()
        print(f"  τ²-Bench pass rate (Week 10): {results['delta_c']['tau2_pass_rate']:.1%}")
        print(f"  τ²-Bench gap vs baseline: {results['delta_c']['tau2_gap_vs_baseline']:.3f}")

    # ── Run inference variants ─────────────────────────────────────────────
    variants_to_run: list[tuple[str, str | None]] = []

    if run_delta_a or run_cost_pareto:
        variants_to_run.append(("baseline",     None))
        variants_to_run.append(("trained_lora", None))
    if run_delta_b or run_cost_pareto:
        if "baseline" not in [v for v, _ in variants_to_run]:
            variants_to_run.append(("baseline", None))
        variants_to_run.append(("prompt_eng", DELTA_B_SYSTEM_PROMPT))

    # Deduplicate (baseline may appear twice)
    seen: set = set()
    unique_variants = []
    for v, sp in variants_to_run:
        if v not in seen:
            unique_variants.append((v, sp))
            seen.add(v)

    for variant, system_prompt in unique_variants:
        print(f"\n── Running variant: {variant} ──")
        loader = MODEL_LOADERS.get(variant)
        if loader is None:
            print(f"  ERROR: no loader for variant '{variant}'", file=sys.stderr)
            continue

        try:
            model, tokenizer = loader()
        except Exception as e:
            print(f"  ERROR loading model for {variant}: {e}", file=sys.stderr)
            continue

        traces = evaluate_variant(variant, tasks, model, tokenizer, system_prompt)
        all_traces[variant] = traces

        # Free GPU memory between variants
        try:
            del model
            import torch, gc
            gc.collect()
            torch.cuda.empty_cache()
        except Exception:
            pass

    # ── Delta A statistics ────────────────────────────────────────────────
    if run_delta_a and "baseline" in all_traces and "trained_lora" in all_traces:
        print("\n── Delta A: trained_lora vs baseline ──")
        base_scores  = [float(t["pass"]) for t in all_traces["baseline"]]
        lora_scores  = [float(t["pass"]) for t in all_traces["trained_lora"]]

        stats = paired_bootstrap(lora_scores, base_scores)
        results["delta_a"] = {
            "baseline_pass_rate":  round(float(np.mean(base_scores)), 4),
            "trained_pass_rate":   round(float(np.mean(lora_scores)), 4),
            "delta_a_lift":        stats["lift"],
            "delta_a_ci_lower":    stats["ci_lower"],
            "delta_a_ci_upper":    stats["ci_upper"],
            "delta_a_p_value":     stats["p_value"],
            "n_resamples":         stats["n_resamples"],
            "bootstrap_seed":      stats["seed"],
            "significant":         stats["ci_lower"] > 0,
        }
        print(f"  Baseline:     {results['delta_a']['baseline_pass_rate']:.1%}")
        print(f"  Trained LoRA: {results['delta_a']['trained_pass_rate']:.1%}")
        print(f"  Lift:         +{stats['lift']:.4f}  "
              f"95% CI [{stats['ci_lower']:.4f}, {stats['ci_upper']:.4f}]  "
              f"p={stats['p_value']:.4f}")

    # ── Delta B statistics ────────────────────────────────────────────────
    if run_delta_b and "baseline" in all_traces and "prompt_eng" in all_traces:
        print("\n── Delta B: prompt_eng vs baseline ──")
        base_scores   = [float(t["pass"]) for t in all_traces["baseline"]]
        prompt_scores = [float(t["pass"]) for t in all_traces["prompt_eng"]]

        stats = paired_bootstrap(prompt_scores, base_scores)
        results["delta_b"] = {
            "baseline_pass_rate":    round(float(np.mean(base_scores)), 4),
            "prompt_eng_pass_rate":  round(float(np.mean(prompt_scores)), 4),
            "delta_b_lift":          stats["lift"],
            "delta_b_ci_lower":      stats["ci_lower"],
            "delta_b_ci_upper":      stats["ci_upper"],
            "delta_b_p_value":       stats["p_value"],
            "n_resamples":           stats["n_resamples"],
            "bootstrap_seed":        stats["seed"],
        }
        print(f"  Baseline:    {results['delta_b']['baseline_pass_rate']:.1%}")
        print(f"  Prompt eng:  {results['delta_b']['prompt_eng_pass_rate']:.1%}")
        print(f"  Lift:        +{stats['lift']:.4f}  "
              f"95% CI [{stats['ci_lower']:.4f}, {stats['ci_upper']:.4f}]  "
              f"p={stats['p_value']:.4f}")

        # Head-to-head: training vs prompt engineering
        if "delta_a" in results:
            a_lift = results["delta_a"]["delta_a_lift"]
            b_lift = results["delta_b"]["delta_b_lift"]
            results["delta_b"]["delta_b_vs_delta_a"] = (
                "training_wins" if a_lift > b_lift else "prompt_eng_wins"
            )
            print(f"  Delta A lift {a_lift:.4f} vs Delta B lift {b_lift:.4f} → "
                  f"{results['delta_b']['delta_b_vs_delta_a']}")

    # ── Cost-Pareto ───────────────────────────────────────────────────────
    if run_cost_pareto and all_traces:
        print("\n── Cost-Pareto summary ──")
        pareto = cost_pareto_summary(all_traces)
        results["cost_pareto"] = pareto
        for variant, m in pareto.items():
            print(f"  {variant:15s}  pass={m['pass_rate']:.1%}  "
                  f"p50={m['p50_latency_ms']:.0f}ms  "
                  f"out_tok={m['avg_output_tokens']:.0f}  "
                  f"cost/1k=${m['cost_per_1k_tasks_usd']:.4f}")

    # ── Write outputs ──────────────────────────────────────────────────────
    TRACES_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Flatten all traces to a single JSONL file
    if all_traces:
        with open(TRACES_FILE, "w", encoding="utf-8") as f:
            for traces in all_traces.values():
                for rec in traces:
                    f.write(json.dumps(rec) + "\n")
        n_traces = sum(len(v) for v in all_traces.values())
        print(f"\nTraces written -> {TRACES_FILE} ({n_traces} records)")

    # Write summary results
    if results:
        # Flatten delta_a and delta_b keys to top level for backward compatibility
        flat: dict = {}
        if "delta_a" in results:
            flat.update({
                "delta_a_lift":          results["delta_a"]["delta_a_lift"],
                "delta_a_ci_lower":      results["delta_a"]["delta_a_ci_lower"],
                "delta_a_ci_upper":      results["delta_a"]["delta_a_ci_upper"],
                "delta_a_p_value":       results["delta_a"].get("delta_a_p_value"),
                "trained_pass_rate":     results["delta_a"]["trained_pass_rate"],
                "baseline_pass_rate":    results["delta_a"]["baseline_pass_rate"],
            })
        if "delta_b" in results:
            flat.update({
                "delta_b_lift":          results["delta_b"]["delta_b_lift"],
                "delta_b_ci_lower":      results["delta_b"]["delta_b_ci_lower"],
                "delta_b_ci_upper":      results["delta_b"]["delta_b_ci_upper"],
                "delta_b_p_value":       results["delta_b"].get("delta_b_p_value"),
                "prompt_eng_pass_rate":  results["delta_b"]["prompt_eng_pass_rate"],
                "delta_b_vs_delta_a":    results["delta_b"].get("delta_b_vs_delta_a"),
            })
        if "cost_pareto" in results:
            flat["cost_pareto"] = results["cost_pareto"]
        if "delta_c" in results:
            flat["delta_c"] = results["delta_c"]

        with open(RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(flat, f, indent=2)
        print(f"Results written -> {RESULTS_FILE}")

    print("\nAblation harness complete.")


if __name__ == "__main__":
    main()
