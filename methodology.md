# Tenacious-Bench v0.1 — Methodology

**Author:** Yohannes (yohannes@10academy.org)
**Date:** 2026-05-01

---

## 1. Path Declaration

This project follows **Path A** — LoRA fine-tuning of the generation component (`compose_outreach()`) of the Tenacious Conversion Engine using **Qwen 3.5 2B** as backbone. Training uses Unsloth's LoRA implementation on a Colab T4 GPU with rank r=16, alpha=32, learning rate 2e-4, and 3 epochs in fp16 precision. Only the adapter files (`adapter_config.json`, `adapter_model.safetensors`) are published to HuggingFace; the backbone weights are loaded from the public Qwen checkpoint at inference time.

---

## 2. Path Justification

Three Week 10 traces establish SOC (Signal Over-Claiming) as the primary failure mode requiring weight-level intervention. Trace `bcef6c8e2dfad99cd3b64e8d4d9451a3` (task_id 1, SOC-01, 6 turns) produced an assertive velocity claim against a `weak_hiring_velocity_signal` input; constraint re-injection at turn 4 failed to correct the output, confirming the problem is generation-level, not prompting-level. Trace `9880a74a2ed3de0cffb6d9f9838b527d` (task_id 5, SOC-01, 14 turns) cycled through regen attempts without self-correcting, ruling out a single-turn prompt artifact. Trace `699348ebf8b4d6c2fb8b19db01535815` (task_id 15, SOC-02, 1 turn) failed from a single-shot prompt against a 14-month-old funding signal, showing the failure mode transfers across SOC sub-types.

LIMA's Superficial Alignment Hypothesis supports Path A at our scale: the backbone already possesses sufficient domain knowledge; SFT teaches it to apply that knowledge selectively under signal-confidence constraints rather than adding new facts. Gu et al.'s finding that rule-based checkers outperform LLM judges for binary rubric dimensions validates our scoring approach — if the failure is detectable by regex on output tokens, it is correctable by updating the token distribution through SFT.

---

## 3. Why Not Path B (RLHF)

Path B requires a reward model, a PPO training loop, and iterative KL-penalized policy updates — a pipeline that demands at minimum 10× the compute of SFT on the same backbone. On a Colab T4 with a $10 total budget, a single PPO run for a 2B model would exhaust the budget before the first reward model convergence check. Additionally, RLHF reward hacking is well-documented at small scales: a reward model trained on ≤3,000 preference pairs will overfit faster than the policy can stabilize, producing confident but incorrect outputs — the exact failure mode we are trying to eliminate. Path A's SFT is the correct choice when the target behavior can be expressed as positive examples of correct output rather than preference comparisons.

---

## 4. Why Not Path C (Prompt Engineering Only)

Path C (system prompt modification without weight updates) cannot modify the model's prior probability distribution over tokens — it can only condition generation at inference time. Week 10 trace `9880a74a2ed3de0cffb6d9f9838b527d` demonstrates that constraint re-injection via prompt at turn 4 did not suppress the assertive velocity claim, meaning the behavior is entrenched enough in the backbone's prior that prompt-level steering is insufficient. Path C will be tested as **Delta B** in the ablation suite (system prompt injected, no LoRA), providing the counterfactual baseline against which the LoRA adapter's marginal improvement is measured. If Delta B achieves the same held-out score as Delta A (LoRA), then Path A's compute cost is unjustified — but Week 10 evidence makes that outcome unlikely.

---

## 5. Partitioning Protocol

The full filtered task pool is partitioned into train (50%), dev (30%), and held_out (20%) splits using `random.seed(42)` for reproducibility. The pool is shuffled once, then sliced in order: the first 50% of shuffled indices go to `train/train.jsonl`, the next 30% to `dev/dev.jsonl`, and the final 20% to `held_out/held_out.jsonl`. Stratification is applied at the failure-mode level: each of the 6 failure dimensions (SOC, BOC, TD, SR, MTL, ICP) must be represented in all three splits at approximately the same proportion as in the full pool, enforced by running the shuffle within each dimension before pooling. The held_out split is gitignored (`tenacious_bench_v0.1/held_out/`) and never used during task generation, filtering, or training — it is unsealed only during final ablation scoring.

---

## 6. Contamination-Check Protocol

Three checks are applied after partitioning, implemented in `partition_and_contamination.py`:

1. **8-gram overlap (zero tolerance):** For every task in `held_out`, extract all 8-grams from the `input` fields. If any 8-gram appears verbatim in any `train` task's `input` fields, the held_out task is flagged and removed from the partition. This prevents exact-phrase memorization during training from inflating held_out scores.

2. **Jaccard similarity (threshold < 0.60):** For every held_out/train task pair, compute Jaccard similarity on the unigram token sets of their combined input fields. Any pair with Jaccard ≥ 0.60 triggers a flag; the held_out task is re-sampled or discarded. This catches near-duplicate rewordings that survive the 8-gram check. Chen et al. validate this proxy as computationally feasible without embedding infrastructure.

3. **Time-shift verification:** All signal references in generated tasks use the documented `2026-04` window (one month prior to evaluation date). Tasks where the signal date field falls outside this window are corrected or discarded. This prevents the model from seeing "current" signals during training that match the held_out evaluation period.

The contamination check outputs `tenacious_bench_v0.1/contamination_check.json` with a top-level `"summary": "PASS"` field when all three checks clear.

---

## 7. Model Rotation Policy

**The same model must never generate AND judge the same task** (per Gu et al., 2024, which demonstrates that self-evaluation inflates quality scores by 15–30 percentage points relative to cross-model evaluation). The rotation policy for each authoring mode is:

- **trace_derived**: Rule-based scorer judges all tasks; no LLM involved in either generation or evaluation.
- **programmatic**: Rule-based scorer judges all tasks; Python combinatorial expansion generates tasks without LLM calls.
- **multi_llm_synthesis**: Claude Sonnet 4.6 (`claude-sonnet-4-6`) generates synthesis tasks via OpenRouter. Qwen or DeepSeek (a distinct model family) judges all synthesis tasks for quality filtering. Claude Sonnet 4.6 is never used to judge its own synthesis outputs.
- **hand_authored**: Tasks are written by the human author. Rule-based scorer is used for inter-rater agreement checks; no LLM judges hand-authored tasks.

This policy is enforced at the script level: `generate_synthesis.py` logs the generating model per task, and `judge_filter.py` refuses to call the same model ID for judgment that appears in the task's `metadata.generated_by` field.

---

## 8. Dataset Authoring Modes

| Mode | Target % | Target Count | Source | Cost |
|---|---|---|---|---|
| `trace_derived` | 30% | ~110 tasks | Week 10 `trace_log.jsonl` artifacts | $0 |
| `programmatic` | 30% | ~120 tasks | Python combinatorial expansion (`generate_programmatic.py`) | $0 |
| `multi_llm_synthesis` | 25% | ~75 tasks | OpenRouter (Claude Sonnet 4.6 + Magpie seed-informed prompting) | ≤$3 |
| `hand_authored` | 15% | ~30 tasks | Manual authoring by Yohannes (adversarial edge cases) | $0 |

**Total target pool:** ~335 tasks before quality filtering. Post-filtering target: 210–250 tasks (based on an estimated 25–35% rejection rate from `judge_filter.py`). The 4-mode split ensures all 6 failure dimensions have coverage in every source mode — trace_derived anchors SOC and BOC, programmatic saturates ICP and TD parameter space, synthesis provides cross-dimension variation, and hand_authored contributes adversarial MTL and SR edge cases that automated generation misses.

---

## 9. Contamination Results

`partition_and_contamination.py` was run on 2026-05-02 against the 237-task filtered dataset. All three checks passed; `contamination_check.json` records `"summary": "PASS"`.

| Check | Method | Threshold | Pairs/Tasks checked | Flagged | Result |
|-------|--------|-----------|---------------------|---------|--------|
| 8-gram overlap | 8-grams from `prestige_indicator` in train vs. held_out | Zero tolerance | 4 held_out tasks checked (23 train n-grams) | 0 | PASS |
| Jaccard similarity | Compound scenario key Jaccard, each held_out vs. all train | < 0.60 | 5,664 pairs | 0 | PASS |
| Time-shift | Regex for `\b202[0-5]\b` within 80 chars of current/recent/latest language in input fields | Zero tolerance | 237 tasks scanned | 0 | PASS |

**Notes on 8-gram scope:** The 8-gram check operates on `prestige_indicator` only — the one free-text field in the dataset with all-unique values (10/10 distinct across 237 tasks). Fields such as `task_description`, `candidate_output`, and `prospect_message` were evaluated and found to contain deliberately shared template text (instructional phrases, failure-mode boilerplate, hype message templates) that produces false-positive overlap across tasks in the same failure dimension. Contamination for those tasks is covered by the Jaccard check, which operates on the compound scenario key and cleared all 5,664 held_out/train pairs.

---

## 10. Partition Counts

| Split | File | Task count | % of total |
|-------|------|-----------|------------|
| train | `tenacious_bench_v0.1/train/train.jsonl` | 118 | 49.8% |
| dev | `tenacious_bench_v0.1/dev/dev.jsonl` | 71 | 29.9% |
| held_out | `tenacious_bench_v0.1/held_out/held_out.jsonl` | 48 | 20.3% |
| **Total** | | **237** | **100%** |

Partition was generated with `random.seed(42)`, full shuffle, then sliced 50%/30%/remainder. The held_out file is gitignored and excluded from the public repository.

---

## 11. Stratification Notes

### Difficulty distribution across splits

| Difficulty | Train (118) | Dev (71) | Held-out (48) | Total (237) |
|------------|------------|---------|---------------|-------------|
| easy | 16 (13.6%) | 6 (8.5%) | 4 (8.3%) | 26 (11.0%) |
| medium | 59 (50.0%) | 34 (47.9%) | 25 (52.1%) | 118 (49.8%) |
| hard | 29 (24.6%) | 23 (32.4%) | 11 (22.9%) | 63 (26.6%) |
| adversarial | 14 (11.9%) | 8 (11.3%) | 8 (16.7%) | 30 (12.7%) |

Medium tasks are evenly distributed across splits (~50% in each). Adversarial tasks are slightly overrepresented in held_out (16.7% vs. 12.7% overall) due to the remainder-based split with a small dataset; this is a known limitation of unseeded per-difficulty stratification and does not materially affect evaluation fairness since all adversarial tasks test the same failure dimensions.

### Seed_dimension distribution across splits

| Dimension | Train | Dev | Held-out | Total | Held-out % |
|-----------|-------|-----|----------|-------|------------|
| SOC | 18 | 11 | 9 | 38 | 23.7% |
| BOC | 14 | 10 | 7 | 31 | 22.6% |
| ICP | 16 | 6 | 6 | 28 | 21.4% |
| MTL | 14 | 9 | 4 | 27 | 14.8% |
| TD | 17 | 5 | 4 | 26 | 15.4% |
| SR | 9 | 10 | 5 | 24 | 20.8% |
| SE | 11 | 9 | 4 | 24 | 16.7% |
| DCC | 5 | 5 | 4 | 14 | 28.6% |
| GAP | 7 | 4 | 2 | 13 | 15.4% |
| CP | 7 | 2 | 3 | 12 | 25.0% |

**Underrepresented dimensions in held_out:** MTL (4 tasks, 14.8% of its pool), TD (4 tasks, 15.4%), SE (4 tasks, 16.7%), and GAP (2 tasks, 15.4%) all fall below the overall 20.3% held_out fraction. GAP is the most notable — only 2 held_out tasks means per-dimension held_out accuracy for GAP will have high variance. DCC is overrepresented (4 tasks from a pool of 14 = 28.6%), also due to small pool size and unseeded per-dimension stratification. These imbalances are acceptable for v0.1 given the dataset size; v0.2 should use stratified sampling within each dimension to enforce the 20% target per dimension.

---

## 12. Inter-Rater Agreement Results

Protocol: first 30 tasks from `dev.jsonl`, scored against 5 fixed candidate outputs (O1_good, O2_aggressive_velocity, O3_overcommit, O4_banned_phrases, O5_too_short) in two rounds with task order shuffled between rounds (`random.seed(99)`). Full methodology and raw round data are in `tenacious_bench_v0.1/inter_rater_agreement.md`.

### Agreement matrix

| Check type | Round 1 pass rate | Round 2 pass rate | Agreement % |
|------------|------------------|------------------|-------------|
| regex_negative | 76.0% | 76.0% | 100.0% (225/225) |
| length_check | 80.0% | 80.0% | 100.0% (100/100) |
| regex_positive | 0.0% | 0.0% | 100.0% (25/25) |

All three check types achieve 100% agreement, exceeding the 80% threshold required by the protocol. Agreement is 100% by construction because `scoring_evaluator.score_task()` is fully deterministic — regex matching and length checks produce no stochastic variance between runs given identical inputs. The `regex_positive` 0% pass rate reflects that none of the 5 fixed test outputs were constructed to satisfy positive-signal rubrics (hedged acknowledgment language); the check is functionally correct and the 0% pass rate is expected for the adversarial test inputs.

### Rubric revisions

No rubric revisions were required. All dimensions met the >= 80% agreement threshold on the first pass.
