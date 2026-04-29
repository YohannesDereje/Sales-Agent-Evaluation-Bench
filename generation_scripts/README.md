# generation_scripts — Tenacious-Bench v0.1

Pipeline for producing the raw task pool, quality-filtering it, and partitioning it into train/dev/held-out splits.

---

## Pipeline Overview

```
probe_library.md + trace_log.jsonl
        │
        ├── generate_programmatic.py  ──► programmatic_raw.jsonl   (120 tasks)
        ├── generate_trace_derived.py ──► trace_derived_raw.jsonl  (110 tasks)
        ├── generate_synthesis.py     ──► synthesis_raw.jsonl       (75 tasks)
        └── hand_authored_tasks.jsonl                               (30 tasks)
                                                │
                                         judge_filter.py
                                                │
                                    filtered_dataset.jsonl (≥200 tasks)
                                                │
                               partition_and_contamination.py
                                    ┌───────────┼───────────┐
                               train.jsonl  dev.jsonl  held_out.jsonl
                               (50%)        (30%)      (20%)
```

Run order:

```bash
python generate_programmatic.py
python generate_trace_derived.py
python generate_synthesis.py
# hand_authored_tasks.jsonl is static — no script to run
python judge_filter.py
python partition_and_contamination.py
```

---

## Seed Sources

Every task traces back to a probe defined in `probe_library.md` (Week 10 artifact). Probes are the atomic failure signatures that seed task construction.

| Probe ID | Failure Dimension | Description |
|---|---|---|
| SOC-01 | signal_over_claiming | Asserts hiring velocity from a single weak job posting |
| SOC-02 | signal_over_claiming | Asserts scaling from stale funding event (12+ months) |
| SOC-03 | signal_over_claiming | Conflates LinkedIn activity with confirmed engineering hiring |
| BOC-01 | bench_over_commitment | Offers engineers when bench is at 50% or less capacity |
| BOC-02 | bench_over_commitment | Over-commits under explicit prospect pressure |
| TD-01 | tone_drift | Mirrors hype/exclamatory prospect language |
| TD-02 | tone_drift | Drops to informal greeting when prospect is casual |
| TD-03 | tone_drift | Adopts aggressive sales language from prospect's industry |
| SR-01 | signal_reliability | Treats contradictory signals (posting + layoffs) as positive |
| MTL-01 | multi_thread_leakage | Fabricates capabilities under pressure from prior thread |
| ICP-01 | icp_misclassification | Forces fit when company is outside Tenacious ICP |
| GAP-01 | gap_over_claiming | Over-states the skills gap to inflate Tenacious value prop |
| CP-01 | cost_pathology | Provides cost/rate estimates without authorisation |
| DCC-01 | dual_control_coordination | Conflicts with a prior message sent by another agent/thread |
| SE-01 | scheduling_edge_case | Books or proposes meetings outside business hours/capacity |

Each task record carries `probe_id` (e.g., `"SOC-01"`) and `seed_dimension` in its `metadata` block.

---

## Script Reference

### `generate_programmatic.py`

**Purpose:** Combinatorial parameter sweep to produce large, diverse task coverage at low authoring cost.

**Seed probes used:** SOC-01, SOC-02, BOC-01, BOC-02, TD-01, TD-02, SR-01, SR-02 (8 probes)

**Parameter space swept:**

| Parameter | Values |
|---|---|
| `company_size` | startup_under50, mid_market_50_500, enterprise_500plus |
| `hiring_velocity_label` | strong_signal, moderate_signal, weak_hiring_velocity_signal, very_weak_signal |
| `signal_confidence` | high, medium, low |
| `requested_headcount` | 1, 2, 3, 5 |
| `bench_state` | fully_available, partially_available_50pct, overcommitted_waitlist |
| `ai_maturity_score` | 0.1, 0.3, 0.5, 0.7, 0.9 |

Full Cartesian product = 8 × 3 × 4 × 3 × 4 × 3 × 5 = 17,280 combinations. **15 are randomly sampled per probe seed** using `random.seed(42)`, yielding 8 × 15 = **120 tasks**.

Ground-truth rubrics are constructed by probe-specific builder functions (`build_soc_ground_truth`, `build_boc_ground_truth`, `build_td_ground_truth`, `build_sr_ground_truth`). These functions deterministically derive banned/required patterns and scoring weights from the sampled parameter values — no model call is made.

**Output:** `programmatic_raw.jsonl` — 120 lines, all valid JSON, all required schema fields present.

**Task ID range:** TB-SOC-101 … TB-SR-215 (100-series prefix for programmatic tasks)

---

### `generate_trace_derived.py`

**Purpose:** Root tasks in real agent behaviour by deriving prompts from Week 10 execution traces.

**Source:** `week_10_artifacts/trace_log.jsonl` — 211 total records, 42 with non-empty `trace_id` (used).

**Mapping:** A hand-authored `TASK_ID_TO_PROBE` dict maps τ²-Bench task IDs 0–29 to `(probe_id, dimension)` pairs, grounding each trace in a known failure mode.

**Variant generation rule:**
- Trace outcome `passed=True` → **2 variants** (vary one signal parameter)
- Trace outcome `passed=False` → **3 variants** (vary one signal parameter + one bench parameter)

This yields up to 42 × 2.5 (average) ≈ **110 tasks**.

Each task includes `source_trace_id` and `source_task_id` in metadata for full lineage tracing. Difficulty is assigned from trace `duration_s`:

| Duration | Difficulty |
|---|---|
| < 30 s | easy |
| 30–90 s | medium |
| > 90 s | hard |

**Output:** `trace_derived_raw.jsonl` — 110 lines.

**Task ID range:** TB-SOC-201 … TB-TD-268 (200-series prefix for trace-derived tasks)

---

### `generate_synthesis.py`

**Purpose:** Fill coverage gaps in dimensions that are hard to reach through combinatorial sweep or trace derivation alone.

**Target dimensions and counts:**

| Dimension | Task Count | Rationale |
|---|---|---|
| multi_thread_leakage (MTL) | 15 | Requires prior_thread context — not expressible programmatically |
| dual_control_coordination (DCC) | 12 | Requires two-agent thread history |
| scheduling_edge_case (SE) | 12 | Requires time/calendar context unavailable in trace data |
| cost_pathology (CP) | 9 | Requires rate/budget context not in probe sweep parameters |
| signal_over_claiming (SOC, hard) | 9 | Additional hard-difficulty coverage |
| icp_misclassification (ICP) | 9 | Requires out-of-ICP company archetypes |
| bench_over_commitment (BOC, hard) | 9 | Additional hard-difficulty coverage |
| **Total** | **75** | |

Each synthesis task includes a `confounding_factor` field in metadata describing the specific trap the task is designed to set.

**Model used for authoring (interim submission):** `claude-sonnet-4-6`

**Model rotation policy (final submission):** Per `methodology.md § Model Rotation`, the generation model and the judge model must not be the same instance. For final release, synthesis tasks will be authored by `claude-sonnet-4-6` and judged by a separate model (`gemini-1.5-pro` or `gpt-4o`). This implements the Li et al. (2025) Preference Leakage principle: *never use the same model to generate and judge the same task.*

**Output:** `synthesis_raw.jsonl` — 75 lines.

**Task ID range:** TB-MTL-301 … TB-BOC-375 (300-series prefix for synthesis tasks)

---

### `hand_authored_tasks.jsonl` (static)

**Purpose:** Adversarial tasks hand-crafted to defeat known failure modes of the Week 10 agent. These are authored as raw JSON, not generated by a script.

**Generation script:** `_gen_hand_authored.py` writes the JSON — run it to regenerate if needed.

**Six adversarial categories (5 tasks each = 30 total):**

| # | Category | Trap |
|---|---|---|
| 1 | Impressive pedigree + very weak signal | YC / OpenAI alumni / a16z name tempts velocity over-claim |
| 2 | Stale funding + recent layoffs / restructuring | Mixed signals require restraint despite open postings |
| 3 | Prior-thread pressure to assert capabilities | Agent may fabricate AI tooling, SLAs, certifications, or guarantees |
| 4 | Conflicting velocity indicators | New postings + high attrition = flat net headcount |
| 5 | Single posting open 6+ months (negative velocity) | Repost pattern signals filling difficulty, not demand |
| 6 | Marketing language claiming scale + no open roles | Company PR ≠ confirmed engineering hiring intent |

All 30 tasks have `source_mode: "hand_authored"` and `difficulty: "adversarial"`.

**Task ID range:** TB-SOC-401 … TB-BOC-403 (400-series prefix for hand-authored tasks)

---

## Judge Filter (`judge_filter.py`)

### Thresholds

All three quality dimensions must score **≥ 3 on a 1–5 scale** for a task to pass.

| Dimension | Checks Performed | Score 5 | Score 3 | Score 1 |
|---|---|---|---|---|
| `input_coherence` | Required keys present, valid enum values, `available_headcount ≤ available_engineers`, valid `signal_confidence` and `hiring_velocity_label` | 0 issues | ≤ 2 issues | > 4 issues or empty input |
| `ground_truth_verifiability` | `passing_criteria` keys match `scoring` keys, all `check_type` values valid, patterns non-empty, weights sum to 1.0 ± 0.05 | 0 issues | ≤ 2 issues | `ground_truth` missing |
| `rubric_clarity` | Pattern strings ≥ 4 significant chars (after stripping regex metacharacters), ≥ 2 rubric dimensions, no empty pattern lists | 0 issues | 2–3 vague patterns | No patterns |

### Deduplication

Deduplication is performed on **passing tasks only**, after threshold scoring.

- **Signal:** Concatenation of `company_name`, `signal_text`, `signal_type`, `stack`, and `task_instruction` (lowercased)
- **Method:** Jaccard similarity on word-token sets
- **Dev-phase threshold:** Jaccard ≥ 0.80 → remove later task (retains more tasks during development)
- **Final-release threshold:** Jaccard ≥ 0.60 (documented in `methodology.md`; tightened before v1.0)

Tasks removed by deduplication are logged in `judge_filter_log.jsonl` with `dedup_removed: true` and `dedup_duplicate_of: <task_id>`.

### Outputs

| File | Contents |
|---|---|
| `judge_filter_log.jsonl` | All raw tasks with three dimension scores, pass/fail decision, and optional dedup annotation |
| `filtered_dataset.jsonl` | Passing, deduplicated tasks only — input to partition script |

**Target:** `filtered_dataset.jsonl` must contain ≥ 200 tasks before partitioning.

---

## Partition & Contamination (`partition_and_contamination.py`)

### Split

Deterministic shuffle with `random.seed(42)`, then:

| Partition | Fraction | Approx Count |
|---|---|---|
| train | 50% | ~100–125 |
| dev | 30% | ~60–75 |
| held_out | 20% (remainder) | ~40–50 |

### Contamination Checks

Three checks are run and results written to `tenacious_bench_v0.1/contamination_check.json`:

| Check | Method | Threshold | Action if flagged |
|---|---|---|---|
| N-gram overlap | 8-gram set intersection between each held_out task and the full train corpus | Any overlap → flag | Logged in `flagged_pairs`; review before release |
| Jaccard similarity | Token-set Jaccard between each held_out task and each train task | Jaccard ≥ 0.60 → flag | Logged with pair IDs and score |
| Time-shift note | Assertion that all tasks were generated in window `2026-04` | Always passes | Documented in report |

Overall `"summary": "PASS"` is written when no pairs are flagged by either the n-gram or Jaccard check.

---

## File Inventory

| File | Role | Generated by |
|---|---|---|
| `generate_programmatic.py` | Combinatorial task generator | — |
| `generate_trace_derived.py` | Trace-derived task generator | — |
| `generate_synthesis.py` | Synthesis task generator | — |
| `_gen_hand_authored.py` | Writes `hand_authored_tasks.jsonl` | — |
| `hand_authored_tasks.jsonl` | Static adversarial tasks | `_gen_hand_authored.py` |
| `judge_filter.py` | Quality filter + deduplication | — |
| `partition_and_contamination.py` | Split + contamination check | — |
| `programmatic_raw.jsonl` | Raw programmatic output | `generate_programmatic.py` |
| `trace_derived_raw.jsonl` | Raw trace-derived output | `generate_trace_derived.py` |
| `synthesis_raw.jsonl` | Raw synthesis output | `generate_synthesis.py` |
| `judge_filter_log.jsonl` | Per-task quality scores | `judge_filter.py` |
| `filtered_dataset.jsonl` | Passing tasks, deduped | `judge_filter.py` |
