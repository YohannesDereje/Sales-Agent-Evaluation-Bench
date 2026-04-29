# Tenacious-Bench v0.1

A domain-specific evaluation benchmark for B2B sales AI agents in the technical staffing vertical. Tenacious-Bench tests whether an AI outreach agent is **honest, proportionate, and professionally grounded** — not just whether it completes a task.

---

## Overview

The **Tenacious Conversion Engine** is an AI agent that generates cold outreach emails for Tenacious, a contract engineering staffing firm. The agent receives a hiring-signal brief (job posting, funding event, LinkedIn growth), a bench availability summary, and an optional prior email thread, then drafts an outreach email to the prospect's engineering hiring manager.

Existing benchmarks (τ²-Bench, WebArena) score binary task completion: did the agent send an email? Tenacious-Bench scores **output quality**: did the agent make claims supported by the available evidence? Did it promise engineers it doesn't have? Did it mirror inappropriate prospect tone?

**10 failure dimensions are tracked:**

| Code | Dimension | Example Failure |
|---|---|---|
| SOC | signal_over_claiming | "Your team is rapidly scaling!" — from a 6-week-old stale posting |
| BOC | bench_over_commitment | "We have 3 engineers ready" — when bench has 1 available |
| TD | tone_drift | Mirroring a prospect's hype language ("CRUSH it", "rockstar engineers") |
| SR | signal_reliability | Ignoring recent layoffs while asserting a hiring push |
| MTL | multi_thread_leakage | Fabricating AI tooling capabilities under prospect pressure |
| ICP | icp_misclassification | Pitching software engineers for a sysadmin role at a law firm |
| GAP | gap_over_claiming | Inflating the skills gap to raise urgency |
| CP | cost_pathology | Quoting rates without authorisation |
| DCC | dual_control_coordination | Contradicting a message sent by a parallel agent thread |
| SE | scheduling_edge_case | Proposing meetings outside prospect business hours |

---

## Week 10 Baseline

The Week 10 τ²-Bench retail evaluation of the Tenacious Conversion Engine produced **42 valid execution traces** across 30 task types. Key finding:

> The agent passed binary task-completion checks but repeatedly asserted strong hiring-velocity claims from signals labelled `weak_hiring_velocity_signal` — probe **SOC-01** (Signal Over-Claiming). This failure is invisible to τ²-Bench, which only checks whether an email was sent.

Trace IDs anchoring the SOC-01 failure evidence: `bcef6c8e`, `9880a74a`, `8630d83f`. Full analysis in `audit_memo.md`.

**Path A (chosen):** Supervised Fine-Tuning of the generation component using LoRA on a Qwen 3.5 backbone. Training data is the Tenacious-Bench train partition. Rationale and training stack documented in `methodology.md`.

---

## Dataset

**Schema:** [`schema.json`](schema.json) — JSON Schema draft-07 defining all task fields.

**Post-filter partition counts (approximate):**

| Partition | File | Count | Use |
|---|---|---|---|
| Train | `tenacious_bench_v0.1/train/train.jsonl` | ~150 | SFT training |
| Dev | `tenacious_bench_v0.1/dev/dev.jsonl` | ~90 | Hyperparameter tuning, rubric iteration |
| Held-out | `tenacious_bench_v0.1/held_out/held_out.jsonl` | ~60 | Sealed — final evaluation only |

**Raw generation (pre-filter):**

| Source Mode | Script | Raw Tasks |
|---|---|---|
| Programmatic | `generation_scripts/generate_programmatic.py` | 120 |
| Trace-derived | `generation_scripts/generate_trace_derived.py` | 110 |
| Multi-LLM synthesis | `generation_scripts/generate_synthesis.py` | 75 |
| Hand-authored adversarial | `generation_scripts/hand_authored_tasks.jsonl` | 30 |
| **Total raw** | | **335** |

Quality-filtered and deduplicated to ≥ 200 tasks by `generation_scripts/judge_filter.py`.

Contamination check results: `tenacious_bench_v0.1/contamination_check.json` (no 8-gram overlap, Jaccard < 0.6 between held-out and train).

---

## How to Evaluate

### Score a single output

```bash
# Score against example 1 from schema.json
python scoring_evaluator.py --task schema.json --example 1 --output "your email text here"

# Score a task by task_id from the dev set
python scoring_evaluator.py --task tenacious_bench_v0.1/dev/dev.jsonl --task-id TB-SOC-201 --output "your email text here"

# Get JSON output (for pipeline integration)
python scoring_evaluator.py --task schema.json --example 1 --output "..." --json
```

### Run the self-test (no arguments needed)

```bash
python scoring_evaluator.py
```

Runs passing and failing candidate outputs against all 3 schema examples. Expected output: all 6 test cases score correctly (3 pass, 3 fail).

### Evaluate a model over the full dev set

```python
import json
from scoring_evaluator import score_task

with open("tenacious_bench_v0.1/dev/dev.jsonl") as f:
    tasks = [json.loads(line) for line in f]

results = [score_task(task, your_model_generate(task)) for task in tasks]
pass_rate = sum(r["passed"] for r in results) / len(results)
print(f"Dev pass rate: {pass_rate:.1%}")
```

### Scoring rubric

Each task has a `ground_truth` block with 2–4 rubric criteria. Supported check types:

| Check Type | Passes When |
|---|---|
| `regex_negative` | NONE of the `banned_patterns` match the output |
| `regex_positive` | ANY of the `required_patterns` match the output |
| `length_check` | `len(output)` is within `[min_chars, max_chars]` |
| `field_presence` | All `required_fields` strings appear in the output |

A task **passes** when `total_score ≥ 0.70`. Weights per criterion are defined in `ground_truth.scoring` and sum to 1.0.

---

## Setup & Reproduce

**Requirements:** Python 3.9+, no external dependencies for the scorer or generation scripts.

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Verify the scorer works
python scoring_evaluator.py

# 3. Regenerate the full dataset from scratch
python generation_scripts/generate_programmatic.py
python generation_scripts/generate_trace_derived.py
python generation_scripts/generate_synthesis.py
python generation_scripts/judge_filter.py
python generation_scripts/partition_and_contamination.py
```

All generation scripts are deterministic (`random.seed(42)` throughout). Running them twice produces identical output.

**Note on held-out partition:** `tenacious_bench_v0.1/held_out/` is gitignored. Do not use it for training or prompt development. See `.gitignore`.

---

## Repository Structure

```
Evaluation Bench/
├── schema.json                          # Task schema + 3 annotated examples
├── scoring_evaluator.py                 # Deterministic scorer (no external deps)
├── audit_memo.md                        # τ²-Bench gap analysis — why this benchmark exists
├── methodology.md                       # Path A (SFT) rationale, training stack, data protocol
├── inter_rater_agreement.md             # Rubric reliability report (100% IRA on all dimensions)
├── datasheet.md                         # Gebru + Pushkarna Data Card
├── requirements.txt                     # Python dependencies
├── generation_scripts/
│   ├── README.md                        # Generation pipeline documentation
│   ├── generate_programmatic.py
│   ├── generate_trace_derived.py
│   ├── generate_synthesis.py
│   ├── hand_authored_tasks.jsonl        # 30 adversarial tasks (static)
│   ├── _gen_hand_authored.py            # Script that wrote hand_authored_tasks.jsonl
│   ├── judge_filter.py
│   ├── partition_and_contamination.py
│   ├── programmatic_raw.jsonl           # Generated outputs (git-tracked)
│   ├── trace_derived_raw.jsonl
│   ├── synthesis_raw.jsonl
│   ├── judge_filter_log.jsonl
│   └── filtered_dataset.jsonl
├── tenacious_bench_v0.1/
│   ├── train/train.jsonl
│   ├── dev/dev.jsonl
│   ├── held_out/                        # gitignored — sealed partition
│   └── contamination_check.json
├── synthesis_memos/
│   ├── memo_synthetic_data.md           # Liu et al. COLM 2024 — narrow seeding argument
│   └── memo_llm_as_a_judge.md          # Gu et al. 2024 — regex vs LLM judge argument
└── week_10_artifacts/
    └── trace_log.jsonl                  # Source traces for trace_derived tasks
```

---

## Current Status (Week 11 Interim — 2026-04-29)

| Deliverable | Status |
|---|---|
| Task schema (`schema.json`) | Done |
| Scoring evaluator (`scoring_evaluator.py`) | Done — self-test passes |
| Audit memo (`audit_memo.md`) | Done |
| Methodology (`methodology.md`) | Done |
| Generation scripts (all 4 modes) | Done |
| Quality filter (`judge_filter.py`) | Done |
| Partition + contamination check | Done |
| Inter-rater agreement report | Done — 100% IRA |
| Datasheet (Gebru + Pushkarna) | Done |
| SFT training (Unsloth / Colab T4) | Not started — Week 11 Days 4–7 |
| Held-out evaluation of fine-tuned model | Not started — Week 11 Days 6–7 |

---

## What's Next — Days 4–7 Plan

**Day 4 — SFT data preparation**
- Populate `candidate_output` fields in train.jsonl by prompting `claude-sonnet-4-6` with each task input
- Generate preference pairs (passing output, failing output) for DPO format
- Verify all training records score ≥ 0.70 on the rubric before inclusion

**Day 5 — Fine-tuning**
- Run LoRA fine-tuning on Qwen 3.5 via Unsloth on Google Colab T4 (free tier)
- Monitor train loss and dev pass rate per epoch
- Save checkpoint at best dev pass rate

**Day 6 — Held-out evaluation**
- Unseal `tenacious_bench_v0.1/held_out/` for the first and only time
- Score the fine-tuned model against the held-out partition
- Record per-dimension pass rates; compare against Week 10 baseline

**Day 7 — Final submission**
- Refresh held-out patterns to prevent v0.1 leakage in future releases
- Write `report_final.md` with evaluation results and failure analysis
- Publish dataset to HuggingFace Hub (train + dev partitions only)
- Tag release as `v1.0`

---

## References

- Gebru et al. (2021). *Datasheets for Datasets.* Communications of the ACM.
- Pushkarna & Zaldivar (2022). *Data Cards: Purposeful and Transparent Dataset Documentation.* FAccT.
- Zhou et al. (2023). *LIMA: Less Is More for Alignment.* NeurIPS.
- Xu et al. (2024). *Magpie: Alignment Data Synthesis from Scratch.* arXiv.
- Li et al. (2025). *Preference Leakage: A Contamination Problem in LLM-as-a-judge.* arXiv.
- Liu et al. (2024). *What Makes Good Data for Alignment?* COLM 2024.
- Gu et al. (2024). *A Survey on LLM-as-a-Judge.* arXiv.
