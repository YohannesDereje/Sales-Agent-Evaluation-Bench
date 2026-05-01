# Tenacious-Bench v0.1 — Generation Pipeline

A new reader can understand the full pipeline from this file without reading the scripts.

---

## Pipeline overview

```
Week 10 traces                    No input (parameter space)
  (trace_log.jsonl)                      |
       |                                 |
       v                                 v
generate_trace_derived.py      generate_programmatic.py
       |                                 |
       v                                 v
trace_derived_raw.jsonl        programmatic_raw.jsonl       hand_authored_tasks.jsonl
(110 raw tasks)                (120 raw tasks)              (30 tasks, hand-written)
                                                                      |
                 generate_synthesis.py                                |
              (Claude Sonnet 4.6 seeds +                              |
               DeepSeek Chat variations)                              |
                       |                                              |
                       v                                              |
               synthesis_raw.jsonl                                    |
               (75 raw tasks)                                         |
                       |                                              |
                       +------------------+---------------------------+
                                          |
                                          v
                                  judge_filter.py
                           (quality score + Jaccard dedup)
                                          |
                                          v
                              filtered_dataset.jsonl
                              (237 tasks, all modes)
                                          |
                                          v
                           partition_and_contamination.py
                           (50/30/20 split, 3 contamination checks)
                                          |
                    +---------------------+---------------------+
                    v                     v                     v
           train/train.jsonl      dev/dev.jsonl       held_out/held_out.jsonl
           (118 tasks)            (71 tasks)          (48 tasks, gitignored)
                                          |
                                          v
                             run_inter_rater_agreement.py
                             (30 dev tasks x 5 fixed outputs x 2 rounds)
                                          |
                                          v
                              inter_rater_agreement.md
```

---

## Per-script reference

### `generate_trace_derived.py`

| | |
|-|-|
| **Input** | `week_10_artifacts/trace_log.jsonl` (211 production agent traces) |
| **Output** | `generation_scripts/trace_derived_raw.jsonl` (110 raw tasks) |
| **Model** | None — rule-based extraction from trace metadata |
| **Cost** | $0 |
| **What it does** | Reads failed traces (traces where the agent produced an over-claim or constraint violation), extracts structured input fields, and constructs a scoring rubric that formalizes the violated constraint. Each output task maps directly to one observed failure event. |

### `generate_programmatic.py`

| | |
|-|-|
| **Input** | None — parameter space is hard-coded |
| **Output** | `generation_scripts/programmatic_raw.jsonl` (120 raw tasks) |
| **Model** | None — pure Python combinatorial expansion |
| **Cost** | $0 |
| **What it does** | Samples 120 tasks from the Cartesian product of 7 parameter axes (company_size x hiring_velocity_label x signal_confidence x requested_headcount x bench_state x ai_maturity_score x seed_dimension) using `random.seed(42)`. Rubrics are generated deterministically: active high-risk constraints (weak signal + low confidence, overcommitted bench) trigger corresponding regex-negative checks. |

### `generate_synthesis.py`

| | |
|-|-|
| **Input** | `OPENROUTER_API_KEY` in `.env` |
| **Output** | `generation_scripts/synthesis_raw.jsonl` (~75 raw tasks) |
| **Model (Stage 1 — seeds)** | `anthropic/claude-sonnet-4-6` via OpenRouter |
| **Model (Stage 2 — variations)** | `deepseek/deepseek-chat` via OpenRouter |
| **Cost** | <= $3 total (hard cap enforced via `cost_log.csv`; script raises RuntimeError if exceeded) |
| **What it does** | Two-stage pipeline. Stage 1: Claude Sonnet 4.6 generates one complex scenario seed per slot (25 seeds across 10 dimensions). Stage 2: DeepSeek Chat generates 2 variations per seed by changing exactly one parameter (company_size, signal_confidence, bench_state, or ai_maturity_score), targeting ~75 tasks total. Rubrics are built programmatically, never by an LLM. |

### `_build_hand_authored.py`

| | |
|-|-|
| **Input** | `generation_scripts/hand_authored_tasks.jsonl` (30 tasks, written by dataset author) |
| **Output** | Validates and normalises `hand_authored_tasks.jsonl` in-place |
| **Model** | None |
| **Cost** | $0 |
| **What it does** | Loads hand-authored tasks, checks required fields, verifies rubric weights sum to <= 1.0, and writes a clean validated version back. All 30 tasks were written from scratch by the dataset author targeting adversarial edge cases in SOC, BOC, SR, MTL, and ICP. |

### `judge_filter.py`

| | |
|-|-|
| **Input** | All four raw files: `trace_derived_raw.jsonl`, `programmatic_raw.jsonl`, `synthesis_raw.jsonl`, `hand_authored_tasks.jsonl` |
| **Output** | `judge_filter_log.jsonl` (335 records), `filtered_dataset.jsonl` (237 tasks) |
| **Model** | None — fully rule-based |
| **Cost** | $0 |
| **What it does** | Scores every task on 3 quality dimensions (1-5 each), drops tasks below threshold, then deduplicates on compound scenario key using Jaccard similarity. See [Judge Filter Thresholds](#judge-filter-thresholds) section below. |

### `partition_and_contamination.py`

| | |
|-|-|
| **Input** | `generation_scripts/filtered_dataset.jsonl` (237 tasks) |
| **Output** | `tenacious_bench_v0.1/train/train.jsonl` (118), `dev/dev.jsonl` (71), `held_out/held_out.jsonl` (48), `contamination_check.json` |
| **Model** | None |
| **Cost** | $0 |
| **What it does** | Shuffles tasks with `random.seed(42)`, slices 50/30/20, then runs 3 contamination checks. Exits 0 only if all 3 checks pass. See [Contamination Checks](#contamination-checks) section below. |

### `run_inter_rater_agreement.py`

| | |
|-|-|
| **Input** | `tenacious_bench_v0.1/dev/dev.jsonl` (first 30 tasks) |
| **Output** | `inter_rater_round1.json`, `inter_rater_round2.json`, `inter_rater_agreement.md` |
| **Model** | None — uses `scoring_evaluator.score_task()` |
| **Cost** | $0 |
| **What it does** | Scores 30 dev tasks against 5 fixed candidate outputs in 2 rounds (Round 2 with shuffled order). Computes per-check-type agreement; exits 1 if any dimension falls below 80%. |

---

## 15-probe seed table

The seed probes define the scenario archetypes used across hand-authored and synthesis authoring modes. Each probe targets a specific failure mechanism within its dimension.

| Probe ID | Dimension | Description | Source Mode | Target Count |
|----------|-----------|-------------|-------------|-------------|
| SOC-01 | signal_over_claiming | Weak signal + Low confidence; media coverage tempts velocity over-claim | hand_authored + synthesis | 5 |
| SOC-02 | signal_over_claiming | Signal > 90 days old asserted as current hiring momentum | hand_authored + synthesis | 5 |
| SOC-03 | signal_over_claiming | Funding event without open roles cited as strong hiring signal | hand_authored + synthesis | 5 |
| BOC-01 | bench_over_commitment | Overcommitted bench; agent commits exact requested headcount | hand_authored + synthesis | 5 |
| BOC-02 | bench_over_commitment | Partially committed bench; agent promises unrealistic deployment timeline | hand_authored + synthesis | 4 |
| BOC-03 | bench_over_commitment | Zero bench availability; agent claims immediate capacity | synthesis | 3 |
| TD-01 | tone_drift | Prospect uses hype language; agent mirrors "rockstar/game-changing" vocabulary | hand_authored + synthesis | 5 |
| TD-02 | tone_drift | Prospect writes informally; agent escalates energy and uses banned phrases | synthesis | 4 |
| TD-03 | tone_drift | Prospect expresses urgency; agent overclaims delivery speed | synthesis | 3 |
| SR-01 | signal_reliability | Funding signal > 180 days old cited as current hiring intelligence | hand_authored + synthesis | 5 |
| SR-02 | signal_reliability | Layoff event within last 90 days misread as expansion signal | hand_authored + synthesis | 5 |
| MTL-01 | multi_thread_leakage | Prior thread references capability never offered to this prospect | hand_authored + synthesis | 5 |
| MTL-02 | multi_thread_leakage | Cross-thread client detail leaked into unrelated prospect outreach | hand_authored + synthesis | 5 |
| ICP-01 | icp_misclassification | Enterprise company with frozen headcount treated as ICP-qualified | hand_authored + synthesis | 5 |
| ICP-02 | icp_misclassification | Prospect in excluded vertical; agent proceeds without disqualification | hand_authored + synthesis | 5 |

*Remaining 10 dimensions (GAP, CP, DCC, SE) are covered by programmatic and synthesis tasks without named probe IDs.*

---

## Judge filter thresholds

`judge_filter.py` scores each task on three 1-5 dimensions. **All three must score >= 3** for the task to be included.

| Dimension | Key checks | Minimum passing behavior |
|-----------|-----------|--------------------------|
| `input_coherence` (1-5) | task_description >= 10 chars; company identifier present; >= 1 signal field present; bench state internally consistent | Score 3 requires description + company + at least one signal field |
| `ground_truth_verifiability` (1-5) | scoring_rubric non-empty; all check_types are valid enums (regex_negative, regex_positive, length_check, field_presence); all targets non-empty; expected_pass present in ground_truth | Score 3 means rubric exists with valid check types — minimum for machine-checkable scoring |
| `rubric_application_clarity` (1-5) | regex patterns > 3 chars (non-trivial); length_check has both min and max; all weights > 0; sum of weights <= 1.0 | Score 3 means no trivial patterns and complete length checks |

**Jaccard deduplication:** after quality filtering, tasks with compound scenario key Jaccard >= **0.80** are considered duplicates. The lower-quality task (by input_coherence score) is dropped. This preserves same-dimension tasks with different parameters while removing near-identical scenario restatements.

Result: 335 raw tasks in → 237 included (98 dropped: 0 from quality filter, 98 from Jaccard dedup).

---

## Contamination checks

Three checks in `partition_and_contamination.py`; all must pass for the script to exit 0.

| Check | Proxy field | Threshold | Rationale |
|-------|-------------|-----------|-----------|
| 8-gram overlap | `prestige_indicator` (unique free-text per task) | Zero tolerance | Verbatim company-context phrases in held_out must not appear in train |
| Jaccard similarity | Compound scenario key (dim\|company\|velocity\|confidence\|bench\|headcount\|ai_maturity\|vertical) | < 0.60 | Held_out tasks must not share > 60% of their scenario key with any train task |
| Time-shift | All input string fields | Zero pre-2026 dates near current-signal language | All signals must use the 2026-04 documented window |

v0.1 result: all 3 checks PASS (0 flagged pairs, 5,664 Jaccard pairs checked).

---

## Model rotation policy

**Rule: the model that generates a task never judges it.**

| Mode | Generating model | Judging model | Rationale |
|------|-----------------|---------------|-----------|
| trace_derived | None (rule-based extraction) | Rule-based scorer | No LLM involved |
| programmatic | None (Python combinatorics) | Rule-based scorer | No LLM involved |
| multi_llm_synthesis (seeds) | Claude Sonnet 4.6 (`anthropic/claude-sonnet-4-6`) | Rule-based scorer only | Claude never scores its own outputs |
| multi_llm_synthesis (variations) | DeepSeek Chat (`deepseek/deepseek-chat`) | Rule-based scorer only | DeepSeek never scores its own outputs |
| hand_authored | Human (dataset author) | Rule-based scorer | Human authoring + automated rubric verification |

Rubrics are **always built programmatically** — no LLM constructs scoring targets or weights. This ensures that LLM quality variance cannot corrupt the evaluation signal.

---

## Total cost breakdown

| Mode | Tasks generated | Cost |
|------|----------------|------|
| trace_derived | 110 raw (49 post-filter) | $0 |
| programmatic | 120 raw (120 post-filter) | $0 |
| multi_llm_synthesis | 75 raw (38 post-filter) | <= $3 |
| hand_authored | 30 raw (30 post-filter) | $0 |
| judge_filter.py | — | $0 |
| partition_and_contamination.py | — | $0 |
| **Total** | 335 raw → 237 final | **<= $3** |

The synthesis budget cap is enforced at runtime: `generate_synthesis.py` reads `cost_log.csv` before each API call and raises `RuntimeError` if the running synthesis total exceeds $3.00.
