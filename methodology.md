# Methodology: Tenacious-Bench v0.1

**Author:** Yohannes (yohannes@10academy.org)
**Date:** 2026-04-29
**Version:** 0.1

---

## Path Declaration

**Selected Path: Path A — Supervised Fine-Tuning of a Generation Component**

The trained artifact is a LoRA adapter on Qwen 3.5 (0.8B or 2B backbone) that replaces the `compose_outreach()` function in the Tenacious Conversion Engine. The adapter is trained to natively tie claim strength to the signal confidence level provided in the hiring brief, eliminating the generation-quality failure documented in SOC-01.

---

## Path Justification

### The Failure Mode Points to Path A

The definitive evidence is SOC-01. When `hiring_velocity_label` was set to `weak_hiring_velocity_signal`, the agent produced assertive hiring velocity language despite the explicit flag. After two prompt-level regen attempts with the constraint injected, the model still produced assertive language — this is recorded as `assertive_claim_regen_failed` in the probe notes.

Three traces from `trace_log.jsonl` confirm the pattern:

- **`bcef6c8e2dfad99cd3b64e8d4d9451a3`** (task_id 1, FAILED, 6 turns): failed at output evaluation despite completing the task flow, consistent with a generation-quality violation being caught post-hoc.
- **`9880a74a2ed3de0cffb6d9f9838b527d`** (task_id 5, FAILED, 14 turns): 14-turn run indicates the agent cycled through multiple regen attempts after a constraint conflict — the extended trace length is the behavioral signature of the SOC failure attempting to self-correct via prompt re-injection without success.
- **`8630d83f640b70fd1a1c878f753ab7b9`** (task_id 6, FAILED, 10 turns): no runner error, output-level failure, consistent with a tone/claim evaluation catching an over-assertion.

### Why Not Path B

Path B addresses inconsistency — the agent gets it right most of the time but cannot detect when it is wrong. Our agent's problem is the opposite: it reliably generates the wrong thing in a specific input condition. The Python-based tone probe already acts as the judge layer. Training a second judge on top of existing detection would duplicate infrastructure without fixing the root cause.

### Why Not Path C

Path C addresses trajectory failures — locally reasonable steps that compound into bad endings across a multi-turn conversation. Our documented failures are concentrated at a single generation step: `compose_outreach()`. There is no trajectory compounding in the Week 10 evidence.

### Paper Alignment

- **LIMA (Zhou et al., NeurIPS 2023):** Quality dominates quantity at the 1,000–3,000 pair scale. Our training data strategy focuses on high-quality (input, compliant_output) pairs derived from probe-triggered traces rather than bulk generation, directly applying this finding.
- **Magpie (Xu et al., 2024):** Self-instruction from aligned LLMs with structured prompts. We adapt this technique for Tenacious-style outreach drafts — using the hiring brief template as the structured prompt anchor and generating compliant output variants across the 8 probe dimensions.

---

## Partitioning Protocol

- **Random seed:** 42 (fixed for reproducibility)
- **Split:** 50% training / 30% public dev / 20% sealed held-out
- **Sealing rule:** Held-out partition is gitignored and never committed unencrypted
- **Contamination:** Held-out sealing runs three checks (documented below) before any task enters the held-out file

---

## Contamination-Check Protocol

Three checks are run by `generation_scripts/partition_and_contamination.py` before any task enters the held-out partition:

1. **N-gram overlap:** No 8-gram sequence from a held-out task's `input.hiring_signal_brief.signal_text` or `input.task_instruction` may appear verbatim in any training task's corresponding fields. Threshold: zero overlap.
2. **Lexical similarity (Jaccard proxy):** Tokenized input fields of held-out vs. training tasks must have Jaccard similarity < 0.6. This is the dev-phase proxy for cosine similarity < 0.85 (no embedding model required for interim submission; full embedding check runs in final submission).
3. **Time-shift verification:** All tasks that reference public company signals use the window `2026-04` as the documented signal date. No task uses a generic placeholder date; every signal reference is traceable to the April 2026 authoring session.

---

## Contamination Check Results

`partition_and_contamination.py` writes results to `tenacious_bench_v0.1/contamination_check.json`. All three checks passed with zero flagged pairs.

| Check | Pairs flagged | Action taken |
|-------|--------------|--------------|
| 8-gram overlap (threshold: any match → flag) | 0 | None required |
| Jaccard similarity (threshold: ≥ 0.60 → flag) | 0 | None required |
| Time-shift verification (window: 2026-04) | PASS | Documented in `contamination_check.json` |

**Final dataset status:** `contamination_check.json` records `"summary": "PASS"`. The post-filter, post-dedup pool of ≥ 200 tasks is cleared for the 50/30/20 partition with no cross-partition contamination. No tasks were dropped or modified as a result of the contamination checks.

**Why zero flags are structurally expected:**

- *Programmatic tasks* share parameter templates but differ in the specific combination of sampled values. An 8-gram overlap between two tasks would require identical parameter values across all fields simultaneously — the `random.seed(42)` combinatorial sweep avoids this by design.
- *Trace-derived tasks* are each anchored to a distinct `source_trace_id`. No two tasks share the same trace as a generation seed, so their `signal_text` fields are structurally distinct.
- *Synthesis tasks* carry an explicit `confounding_factor` field that varies across tasks within the same dimension, reducing lexical similarity below the 0.60 Jaccard threshold.
- *Hand-authored tasks* were written with distinct company archetypes and adversarial scenarios per category, with no templated repetition.

**Action protocol for any future flagged pairs** (applicable if the dedup threshold is tightened to 0.60 for v1.0 release):

| Similarity | Action |
|-----------|--------|
| N-gram overlap (any) | Drop the held-out task; retain train duplicate as training record |
| Jaccard ≥ 0.70 | Modify one non-evaluation field in the held-out task (e.g., company name, signal date) to reduce similarity, then re-run check |
| Jaccard 0.60–0.70 | Retain with documented justification if similarity is in boilerplate fields (company description, greeting) and not in `signal_text` or `task_instruction` |

---

## Partitioning and Stratification Notes

The `random.seed(42)` shuffle partitions the filtered pool as a single random sequence rather than a stratified sample. Per-dimension representation across splits is therefore not guaranteed for dimensions with low raw task counts (DCC: 12 raw tasks; SE: 12 raw tasks).

**Approximate difficulty mix** across the raw pool (post-filter proportions will be similar):

| Difficulty | Approx. share | Source |
|------------|--------------|--------|
| `easy` | ~15% | Trace-derived tasks with duration < 70 s |
| `medium` | ~55% | All programmatic tasks; trace-derived 70–120 s |
| `hard` | ~18% | Trace-derived > 120 s; synthesis tasks |
| `adversarial` | ~12% | All 30 hand-authored tasks |

Because the random shuffle does not preferentially separate by difficulty or dimension, each partition receives approximately the same difficulty mix. This is acceptable for the dev-phase evaluation where overall pass rate is the primary metric. For v1.0 (Day 7), stratified sampling by `seed_dimension` and `difficulty` is planned to guarantee minimum per-stratum representation in the held-out partition and to ensure that every failure dimension — including low-count ones like DCC and SE — has at least one task in held-out evaluation.

---

## Model Rotation Policy (Preference Leakage Prevention)

Per Li et al. (2025) *Preference Leakage*: never use the same model to both generate and judge the same task.

- **Generation (programmatic/trace-derived):** Python template logic — no LLM.
- **Generation (synthesis tasks):** Claude Sonnet 4.6 (claude-sonnet-4-6).
- **Quality judge (dev phase):** Rule-based evaluator (`judge_filter.py`) — no LLM.
- **Quality judge (final submission spot-check):** Different model family (OpenRouter cheap tier: Qwen3-Next or DeepSeek V3.2).
- **Held-out evaluation:** Claude Sonnet 4.6 (eval-tier) — used only on the sealed slice, maximum 4 passes.

This rotation ensures no model grades its own outputs at any stage.

---

## Dataset Authoring Modes

| Mode | Target share | Source |
|------|-------------|--------|
| Trace-derived | ≈30% | `week_10_artifacts/trace_log.jsonl` records 151–211 |
| Programmatic (parameter sweeps) | ≈30% | Templates × combinatorial expansion from 8 probe seeds |
| Multi-LLM synthesis | ≈25% | Claude Sonnet 4.6 authoring hard seeds anchored to failure taxonomy |
| Hand-authored adversarial | ≈15% | Written directly to defeat SOC failure mode on edge cases |

---

## Backbone and Training Stack

- **Backbone:** Qwen 3.5 0.8B or 2B (pinned version in `requirements.txt`)
- **Adapter:** LoRA only (PEFT library) — no full fine-tune
- **Framework:** Unsloth on Google Colab T4 (free tier)
- **Precision:** fp16 mixed precision on T4
- **Training data format:** Chat-template format (instruction/response pairs)
- **Target training pairs:** 1,000–3,000 high-quality pairs after quality filtering

---

## Cost Discipline

| Bucket | Budget | Actual (interim) |
|--------|--------|-----------------|
| Dataset authoring (dev-tier LLM) | $3–5 | $0.00 (template generation) |
| Training | $0–5 | $0.00 (not yet run) |
| Held-out evaluation | $2–3 | $0.00 (not yet run) |
| Reserve | $1–2 | $0.00 |
| **Total** | **$10** | **$0.00** |
