# Model Card — tenacious-outreach-lora-qwen-1.5b

**HuggingFace**: `Yohannesdn/tenacious-outreach-lora-qwen-1.5b`
**Author**: Yohannes (yohannes@10academy.org)
**Date**: 2026-05-02
**Version**: v0.1

---

## 1. Backbone

| Field | Value |
|-------|-------|
| Name | Qwen2.5-1.5B-Instruct |
| HuggingFace model ID | `Qwen/Qwen2.5-1.5B-Instruct` |
| Parameter count | 1.545B |
| License | Apache 2.0 |
| Quantization at training | 4-bit (bitsandbytes NF4 via Unsloth) |

This repo contains the LoRA adapter only (`adapter_config.json`, `adapter_model.safetensors`, 8.73 MB). The backbone weights are not included — load them from the public Qwen checkpoint at inference time.

---

## 2. Training Data

| Field | Value |
|-------|-------|
| Partition used | `train` only (`tenacious_bench_v0.1/train/train.jsonl`) |
| Training pairs | 1,133 (post quality-filter; all score ≥ 0.70 on rule-based rubric) |
| Format | Chat template — system / user / assistant triplets |
| Contamination check | 0 pairs share 8-gram content with held_out; `training_contamination_log.json` records PASS |

**Source mode breakdown:**

| Mode | Pairs | % |
|------|-------|---|
| SOC (signal over-claiming) | 180 | 15.9% |
| TD (tone drift) | 170 | 15.0% |
| BOC (bench over-commitment) | 140 | 12.4% |
| MTL (multi-thread leakage) | 140 | 12.4% |
| ICP (ICP misclassification) | 115 | 10.2% |
| SE (scope escalation) | 110 | 9.7% |
| SR (signal reliability) | 88 | 7.8% |
| CP (competitive positioning) | 70 | 6.2% |
| GAP (gap exploitation) | 70 | 6.2% |
| DCC (data/context confusion) | 50 | 4.4% |

**Failure dimensions covered**: all 10 dimensions present in training data. DCC is the least-represented (50 pairs, 4.4%) — training signal for this dimension is limited.

---

## 3. Hyperparameters

All values are verbatim from `training/training_run.log`.

**LoRA configuration:**

| Parameter | Value |
|-----------|-------|
| r | 16 |
| lora_alpha | 32 |
| lora_dropout | 0.05 |
| target_modules | q_proj, v_proj |
| bias | none |
| use_gradient_checkpointing | True |
| Trainable parameters | 2,179,072 (0.14% of backbone) |

**Training arguments:**

| Parameter | Value |
|-----------|-------|
| learning_rate | 2e-4 |
| num_train_epochs | 3 |
| per_device_train_batch_size | 2 |
| gradient_accumulation_steps | 4 (effective batch size = 8) |
| fp16 | True |
| seed | 42 |
| max_seq_length | 1024 |
| total_steps | 426 |
| train_runtime | 875.87s (~14.6 minutes) |
| final_train_loss | 0.3672 |

---

## 4. Intended Use

This adapter is a drop-in replacement for the `compose_outreach()` generation component of the Tenacious Conversion Engine — a B2B outreach assistant for Tenacious Technologies, a technical staffing firm placing senior software engineers with high-growth tech companies.

**Input**: structured hiring signal brief (company name, hiring velocity label, signal confidence, bench state, ICP segment, AI maturity score) formatted as a user-turn chat message.

**Output**: a compliant cold outreach email or ICP disqualification notice, constrained by the Tenacious Style Guide (≤120 words, one-ask rule, no banned phrases, hedged language for weak signals, no headcount commitment when bench is overcommitted).

**Appropriate use cases:**
- Automated first-draft outreach generation within the Tenacious Conversion Engine pipeline
- Evaluation of constraint-following behavior for B2B technical staffing agents
- Baseline comparison for future LoRA iterations targeting additional failure dimensions

---

## 5. Limitations

**Dimensions with limited training signal:**
- DCC (data/context confusion): 50 training pairs — adapter may not generalize reliably to novel DCC scenarios
- GAP and CP: 70 pairs each — moderate coverage; edge cases may not be well-represented

**Residual failures on held_out evaluation (7/48 tasks fail):**

| Task ID | Dimension | Score |
|---------|-----------|-------|
| TB-SR-TD-0020 | SR | 0.600 |
| TB-SOC-HA-002 | SOC | 0.600 |
| TB-SOC-TD-0055 | SOC | 0.600 |
| TB-ICP-HA-004 | ICP | 0.000 |
| TB-SOC-TD-0013 | SOC | 0.600 |
| TB-SR-TD-0071 | SR | 0.600 |
| TB-SR-TD-0004 | SR | 0.600 |

Failures concentrate in SR (3 tasks) and SOC (3 tasks) — dimensions where the rubric requires precise regex_positive pattern matching (hedged acknowledgment language). The ICP failure (score 0.000) indicates a complete miss — the adapter sent outreach to an out-of-ICP prospect instead of issuing a disqualification notice.

**Scope limitations:**
- Not validated on non-technical staffing domains (e.g., finance recruiting, executive search)
- Not validated on outreach formats other than cold email (e.g., LinkedIn InMail, follow-up sequences)
- Do not use for outreach to ICP-excluded segments — the 1/48 ICP failure on held_out confirms the adapter is not 100% reliable on this constraint
- Training data uses a single signal window (2026-04); performance on significantly different signal dates is unknown

---

## 6. Evaluation Results

All numbers are from `ablations/ablation_results.json`, reproducible from `ablations/held_out_traces.jsonl` (144 records, 48 tasks × 3 variants).

**Held-out evaluation (48 tasks, Tenacious-Bench v0.1):**

| Variant | Pass rate | Avg weighted score |
|---------|-----------|-------------------|
| Baseline (no LoRA, no system prompt) | 33.3% (16/48) | 0.628 |
| Delta B (no LoRA + engineered system prompt) | 41.7% (20/48) | 0.693 |
| Delta A — this adapter (LoRA) | **85.4% (41/48)** | **0.892** |

**Delta A lift**: +26.4 pp over baseline (95% CI: [+18.7, +32.8] pp, 1,000-sample paired bootstrap, seed=42). The CI does not include 0 — the lift is statistically significant.

**Delta B lift**: +8.3 pp over baseline. Prompt engineering alone moves 4 additional tasks over threshold but falls 18 pp short of the trained adapter. `delta_b_vs_delta_a = "training_wins"` — weight-level fine-tuning is necessary for reliable constraint adherence; prompt engineering is insufficient.

**Inference latency (Colab T4, 5-task sample):**

| Variant | Avg latency |
|---------|-------------|
| Baseline | 10,652 ms |
| Prompt eng | 8,421 ms |
| Trained LoRA (this adapter) | 3,266 ms |

The trained adapter is 3.2× faster than baseline, likely due to more focused generation (shorter outputs, fewer retries in the token distribution).

---

## 7. Environmental Impact

| Activity | GPU-hours | Est. CO₂ |
|----------|-----------|----------|
| Training run (875.87s on T4) | 0.243 h | ~0.12 kg |
| Ablation inference (3 variants × 48 tasks) | ~0.28 h | ~0.14 kg |
| **Total** | **~0.52 h** | **~0.26 kg** |

Estimate basis: T4 GPU at ~0.5 kg CO₂/GPU-hour (US average grid, per MLPerf environmental estimates). Training was run on Google Colab free tier; no monetary compute cost incurred.
