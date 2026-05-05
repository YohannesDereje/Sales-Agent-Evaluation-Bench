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

**Path A (chosen):** Supervised Fine-Tuning of the generation component using LoRA on a Qwen2.5-1.5B-Instruct backbone via Unsloth on Colab T4. Training data is the Tenacious-Bench train partition. Rationale and training stack documented in `methodology.md`.

---

## Dataset

**Schema:** [`schema.json`](schema.json) — JSON Schema draft-07 defining all task fields.

**Post-filter partition counts:**

| Partition | File | Count | Use |
|---|---|---|---|
| Train | `tenacious_bench_v0.1/train/train.jsonl` | 118 | SFT training (1,133 pairs after augmentation) |
| Dev | `tenacious_bench_v0.1/dev/dev.jsonl` | 71 | Hyperparameter tuning, rubric iteration |
| Held-out | `tenacious_bench_v0.1/held_out/held_out.jsonl` | 48 | Sealed — final evaluation only |

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
# 0. Clone the repo
git clone https://github.com/YohannesDereje/Sales-Agent-Evaluation-Bench.git
cd tenacious-bench

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

## Results (Week 11 Final — 2026-05-02)

| Deliverable | Status |
|---|---|
| Task schema (`schema.json`) | Done |
| Scoring evaluator (`scoring_evaluator.py`) | Done — self-test passes |
| Audit memo (`audit_memo.md`) | Done |
| Methodology (`methodology.md`) | Done |
| Generation scripts (all 4 modes) | Done |
| Quality filter (`judge_filter.py`) | Done |
| Partition + contamination check | Done — 0 pairs flagged across 5,664 comparisons |
| Inter-rater agreement report | Done — 100% IRA |
| Datasheet (Gebru + Pushkarna) | Done |
| SFT training (Unsloth / Colab T4) | Done — 875s, final loss 0.3672 |
| Held-out evaluation (48 tasks) | Done — 85.4% pass rate (41/48) |
| Dataset published to HuggingFace | Done — CC-BY-4.0 |
| LoRA adapter published to HuggingFace | Done |

### Delta A — Training vs Baseline

| Metric | Value |
|---|---|
| Baseline pass rate (no LoRA, no system prompt) | 33.3% (16/48) |
| Prompt engineering only (Delta B) | 41.7% (20/48) |
| Trained LoRA adapter (Delta A) | **85.4% (41/48)** |
| Delta A lift over baseline | **+26.4 pp** |
| 95% CI (1,000 bootstrap resamples) | [+18.7, +32.8] pp |
| Verdict | **training_wins** — prompt engineering insufficient |

The trained adapter is also **3.2× faster** than baseline at inference (3,266 ms vs 10,652 ms average, Colab T4). The speedup is a decode-phase effect: autoregressive inference splits into a fixed-cost prefill phase (input tokens processed in parallel, compute-bound) and a linear-cost decode phase (one token generated per step, memory-bound, scales directly with output length). The baseline model generates verbose, unconstrained outputs; the LoRA adapter learned through SFT to produce concise, task-specific outputs — reducing the number of decode iterations proportionally. LoRA weights are merged into the base model at inference (`W' = W + BA`, per Hu et al. 2021), adding zero architectural overhead. Prompt engineering reduces latency slightly (8,421 ms) by partially constraining output length via in-context steering, but is less reliable than weight-level training for controlling the output distribution — the adapter internalised when to emit EOS, the prompt only suggests it.

Seven tasks still fail with the trained adapter: SR×3, SOC×3, ICP×1. Full scored traces in `ablations/held_out_traces.jsonl`. All numeric claims are cross-referenced in `evidence_graph.json`.

---

## Community Engagement

- **HuggingFace dataset (CC-BY-4.0):** [Yohannesdn/tenacious_bench_v0.1](https://huggingface.co/datasets/Yohannesdn/tenacious_bench_v0.1)
- **HuggingFace LoRA adapter:** [Yohannesdn/tenacious-outreach-lora-qwen-1.5b](https://huggingface.co/Yohannesdn/tenacious-outreach-lora-qwen-1.5b)
- **Blog post (Substack):** [We Built a Benchmark Because Our AI Kept Lying About Hiring Signals](https://open.substack.com/pub/yohannesdereje/p/we-built-a-benchmark-because-our?r=8btd9e&utm_campaign=post&utm_medium=web&showWelcomeOnShare=true)
- **Blog post (Medium):** [We Built a Benchmark Because Our AI Kept Lying About Hiring Signals](https://medium.com/@yohannesdereje1221/we-built-a-benchmark-because-our-ai-kept-lying-about-hiring-signals-a08adc217cdc)
- **τ²-Bench community issue #294:** [6 output-quality failure modes τ²-Bench retail cannot detect](https://github.com/sierra-research/tau2-bench/issues/294#issue-4369585785)

---

## What's Next — v0.2 Roadmap

Four failure modes were observed informally but not formalized in v0.1:

1. **Multi-turn constraint decay** — correct on turn 1, drifts toward over-claiming by turn 6+
2. **Numeric hallucination** — fabricating placement rates, time-to-hire figures absent from the brief
3. **Competitor misrepresentation** — implicit comparisons to named competitors without basis
4. **Temporal signal confusion** — citing an 18-month-old event as "you just raised a Series B"

v0.2 will add these four dimensions, expand the held-out set to 100+ tasks, increase SR training pairs to ≥150, and replace the Jaccard contamination proxy with embedding cosine similarity (< 0.85 threshold).

---

## References

- Gebru et al. (2021). *Datasheets for Datasets.* Communications of the ACM.
- Pushkarna & Zaldivar (2022). *Data Cards: Purposeful and Transparent Dataset Documentation.* FAccT.
- Zhou et al. (2023). *LIMA: Less Is More for Alignment.* NeurIPS.
- Xu et al. (2024). *Magpie: Alignment Data Synthesis from Scratch.* arXiv.
- Li et al. (2025). *Preference Leakage: A Contamination Problem in LLM-as-a-judge.* arXiv.
- Liu et al. (2024). *What Makes Good Data for Alignment?* COLM 2024.
- Gu et al. (2024). *A Survey on LLM-as-a-Judge.* arXiv.
- Chen et al. (2025). *Benchmark Contamination and Evaluation Integrity.* arXiv.
- Ivison et al. (2023). *Camels in a Changing Climate: Enhancing LM Adaptation with Tülu 3 (Tulu 3).* arXiv.
- τ²-Bench (tau2-Bench): Task and Tool-Use Benchmark for Conversational AI Agents (retail split used for Week 10 baseline).
- Hu, E. J., et al. (2021). *LoRA: Low-Rank Adaptation of Large Language Models.* arXiv:2106.09685. (Describes the low-rank adaptation mechanism and zero-overhead inference via weight merging.)
- Agrawal, A., et al. (2023). *SARATHI: Efficient LLM Inference by Piggybacking Decodes with Chunked Prefills.* arXiv:2308.16369. (Explains the prefill/decode split and why the decode phase dominates production latency.)
- OpenRouter (2024). Multi-provider LLM inference API. openrouter.ai.
- **License:** CC-BY-4.0 — see [`LICENSE`](LICENSE) for the full text.

---

## License and Attribution

This repository is released under the **Creative Commons Attribution 4.0 International License** — see [`LICENSE`](LICENSE).

**Attribution:** If you use Tenacious-Bench in your work, please cite:

```
Yohannes (2026). Tenacious-Bench v0.1: A Domain-Specific Evaluation Benchmark
for B2B Sales AI Agents. 10Academy TRP1 Week 11.
Dataset: https://huggingface.co/datasets/Yohannesdn/tenacious_bench_v0.1
```

**Credits:**
- Backbone model: [Qwen2.5-1.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct) (Alibaba Cloud, Apache-2.0)
- Training framework: [Unsloth](https://github.com/unslothai/unsloth) + [TRL](https://github.com/huggingface/trl)
- Evaluation framework: [τ²-Bench](https://github.com/sierra-research/tau2-bench) (Week 10 baseline)
- Literature: Gebru et al. (2021), Zhou et al. (2023), Chen et al. (2025) — full references above
