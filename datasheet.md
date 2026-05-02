# Datasheet for Tenacious-Bench v0.1

> Gebru et al. (2021) datasheet format with Pushkarna et al. (2022) three-scope annotations.
> Version: 0.1 | Created: 2026-04-29 | Maintainer: Yohannes (yohannes@10academy.org)

---

## 1. Motivation

### Telescopic (plain-language overview)

Tenacious-Bench is a task-and-rubric evaluation dataset for AI sales agents operating in B2B technical staffing. Specifically, it tests whether a generation agent — given structured hiring-signal inputs — produces outreach emails that respect the constraints encoded in those inputs: does the email avoid over-claiming a weak signal? Does it refrain from committing engineers when the talent bench is overcommitted? Does it maintain appropriate tone when the prospect uses hype language? These failure modes were identified through empirical trace analysis of a deployed Tenacious Technologies sales agent, meaning every failure category in the benchmark traces back to a documented real-world agent error, not a hypothetical. Existing general-purpose email quality benchmarks do not capture this domain: they evaluate surface polish, spam likelihood, or response rates — none of which detect the structured-reasoning failures that occur when an agent misreads a hiring brief or ignores bench-state constraints. Tenacious-Bench fills that gap by pairing each task with a machine-checkable rubric derived directly from the business rules that govern Tenacious outreach.

### Why this dataset was created

Tenacious Technologies' sales agent passes standard fluency and tone checks while still committing systematic errors tied to signal interpretation. Audit of production traces revealed a recurring **Signal Over-Claiming (SOC)** failure: the agent generates assertive velocity language ("rapidly scaling engineering team") even when `hiring_velocity_label = weak_hiring_velocity_signal` and `signal_confidence = Low`. No existing benchmark surfaces this failure mode. Tenacious-Bench was created by Yohannes (10Academy TRP1, cohort Week 11) as a structured diagnostic tool to measure and track this class of errors across 10 distinct failure dimensions.

### What gap it fills

The tau-squared Bench gap this dataset addresses is the absence of *signal-grounded* agent evaluation: benchmarks that pair a structured input representation (hiring signal fields, bench state, ICP metadata) with a rubric that checks the output against the *business logic* encoded in those inputs. Without such a benchmark, a SFT or RLHF improvement loop cannot distinguish between a model that learned to write better-sounding emails and a model that actually respects the signal constraints. Tenacious-Bench makes the distinction testable.

---

## 2. Composition

### Telescopic

The dataset contains 237 tasks across 10 failure dimensions after quality filtering and Jaccard deduplication. Each task specifies an input scenario (structured hiring signal fields), a scoring rubric (1-4 machine-checkable checks), an example failing candidate output, and a ground-truth pass/fail expectation. Tasks are partitioned 50/30/20 into train, dev, and held-out splits.

### Periscopic — composition tables

#### By failure dimension

| Dimension code | Full name | Task count |
|---------------|-----------|-----------|
| SOC | signal_over_claiming | 38 |
| BOC | bench_over_commitment | 31 |
| ICP | icp_misclassification | 28 |
| MTL | multi_thread_leakage | 27 |
| TD | tone_drift | 26 |
| SR | signal_reliability | 24 |
| SE | scheduling_edge_case | 24 |
| DCC | dual_control_coordination | 14 |
| GAP | gap_over_claiming | 13 |
| CP | cost_pathology | 12 |
| **Total** | | **237** |

#### By authoring mode

| source_mode | Count | Human oversight |
|-------------|-------|-----------------|
| programmatic | 120 | None — fully automated combinatorial expansion |
| trace_derived | 49 | Reviewed by dataset author |
| multi_llm_synthesis | 38 | Reviewed by dataset author |
| hand_authored | 30 | Fully hand-written |

#### By difficulty

| difficulty | Count |
|------------|-------|
| medium | 118 |
| hard | 63 |
| adversarial | 30 |
| easy | 26 |

#### By partition

| Split | Count | Fraction |
|-------|-------|----------|
| train | 118 | 49.8% |
| dev | 71 | 29.9% |
| held_out | 48 | 20.3% |

#### Rubric check type distribution (across all 237 tasks)

| check_type | Count | Typical use |
|------------|-------|-------------|
| regex_negative | 333 | Detect banned phrases, velocity over-claims, commitment language |
| length_check | 166 | Enforce 50-700 character cold-outreach window |
| regex_positive | 38 | Require hedging language, disqualification signals |
| field_presence | 30 | Require named concepts (delivery lead, availability) |

### Periscopic — Key field summary

| Field | Type | Description |
|-------|------|-------------|
| `task_id` | string | Unique identifier. Format: `TB-{DIM}-{MODE}-{SEQ}` |
| `seed_dimension` | string | 3-letter failure dimension code (e.g., SOC, BOC) |
| `source_mode` | string | Authoring mode: programmatic, trace_derived, multi_llm_synthesis, hand_authored |
| `difficulty` | string | easy / medium / hard / adversarial |
| `input.task_description` | string | Natural-language task prompt for the agent |
| `input.company_name` | string | Prospect company name (absent in programmatic tasks) |
| `input.hiring_velocity_label` | string | Signal strength: strong_signal to very_weak_signal |
| `input.signal_confidence` | string | High / Medium / Low |
| `input.bench_state` | string | fully_available / partially_committed_50pct / overcommitted_waitlist |
| `input.requested_headcount` | int | Engineers requested by prospect |
| `scoring_rubric` | array | 1-4 check objects; each has check_type, target, weight, description |
| `candidate_output` | string | Example failing email (ground truth for rubric calibration) |
| `ground_truth.expected_pass` | bool | Whether a correct agent response should pass this task's rubric |
| `ground_truth.passing_score` | float | Weighted score threshold for PASS (0.70) |

### Microscopic — Input schema field catalogue

Each field below documents valid values, whether it is required, the distribution across all 237 tasks, and any cross-field dependency constraints enforced by `judge_filter.py` and `partition_and_contamination.py`.

#### Top-level task fields

| Field | Required | Valid values | Distribution | Notes |
|-------|----------|-------------|-------------|-------|
| `task_id` | Yes | `TB-{DIM}-{MODE}-{SEQ}` string | Unique across 237 tasks | DIM ∈ {SOC,BOC,ICP,MTL,TD,SR,SE,DCC,GAP,CP}; MODE ∈ {HA,TD,SY,PG} |
| `seed_dimension` | Yes | SOC, BOC, ICP, MTL, TD, SR, SE, DCC, GAP, CP | See composition table | Determines which rubric checks are generated in programmatic mode |
| `source_mode` | Yes | programmatic, trace_derived, multi_llm_synthesis, hand_authored | 120 / 49 / 38 / 30 | Used to assign model rotation policy and human-review requirements |
| `difficulty` | Yes | easy, medium, hard, adversarial | 26 / 118 / 63 / 30 | Adversarial reserved for hand-authored tasks only |
| `candidate_output` | Yes (non-empty for hand_authored, trace_derived) | Free text string | Empty string for 120 programmatic tasks | Failing email demonstrating the target failure mode; used in inter-rater agreement |
| `metadata.task_type` | No | seed, variation | 25 seed + 50 variation in synthesis mode | Absent in non-synthesis tasks |

#### `input` object fields

| Field | Required | Valid values | Distribution (237 tasks) | Cross-field constraint |
|-------|----------|-------------|--------------------------|------------------------|
| `task_description` | Yes | Free text, ≥ 10 chars | 100% present | Minimum 10 chars enforced by `judge_filter.py` (input_coherence check) |
| `company_name` | Conditional | Non-empty string | Present in 117 tasks (hand_authored + trace_derived + synthesis) | Absent in all 120 programmatic tasks; absent ↔ `company_size` must be present |
| `company_size` | Conditional | startup_under50, smb_50_500, enterprise_500plus | Present in all 120 programmatic tasks | Required when `company_name` absent |
| `hiring_velocity_label` | Yes | strong_signal, moderate_signal, weak_hiring_velocity_signal, very_weak_signal | 29 / 71 / 84 / 53 | When value contains "weak" and `signal_confidence = Low`, SOC regex_negative checks are activated |
| `signal_confidence` | Yes | High, Medium, Low | 52 / 97 / 88 | Low confidence co-occurs with weak velocity in 74 of 88 Low-confidence tasks |
| `bench_state` | Yes | fully_available, partially_committed_50pct, overcommitted_waitlist | 98 / 76 / 63 | When overcommitted_waitlist: `bench_available_count` < `requested_headcount` is enforced |
| `bench_available_count` | Conditional | Integer ≥ 0 | Present in 143 tasks | Required when `bench_state` ≠ fully_available; must be < `requested_headcount` when overcommitted |
| `requested_headcount` | Yes | Integer 1–20 | Range [1, 15]; median 3 | Value is embedded verbatim in BOC regex_negative targets (e.g., "commit.{0,10}10") |
| `icp_segment` | Conditional | in_icp, out_of_icp | Present in 28 ICP-dimension tasks | When out_of_icp: field_presence check for disqualification statement is activated |
| `reliability_flag` | Conditional | true / false | Present in 24 SR-dimension tasks | When true: regex_negative for current-signal momentum language is activated |
| `signal_age_days` | Conditional | Integer ≥ 0 | Present in 62 tasks; range [0, 548] | When ≥ 180: SR staleness checks are activated |
| `ai_maturity_score` | Yes | Integer 1–5 | 1: 48 / 2: 52 / 3: 61 / 4: 46 / 5: 30 | Programmatic only; informs whether AI-tooling language is appropriate |
| `prestige_indicator` | Conditional | Free text (company accolade, media mention) | Present in 30 hand-authored adversarial tasks | Used as 8-gram contamination proxy; unique across all 237 tasks |
| `prospect_message` | Conditional | Free text | Present in 24 MTL-dimension tasks | Multi-thread leakage source; regex_negative patterns check for capability terms absent from current brief |

#### `scoring_rubric` check object fields

Each task has 1–4 check objects in its `scoring_rubric` array. Every check object contains:

| Field | Required | Valid values | Notes |
|-------|----------|-------------|-------|
| `check_type` | Yes | regex_negative, regex_positive, length_check, field_presence | Enforced by `judge_filter.py` ground_truth_verifiability check |
| `target` | Yes | String (regex/phrase) for regex checks; `{"min": int, "max": int}` for length_check; string for field_presence | Must be non-empty; regex patterns must be > 3 chars (rubric_application_clarity check) |
| `weight` | Yes | Float in (0, 1]; all weights per task sum ≤ 1.0 | Enforced by judge_filter.py; weighted sum ≥ 0.70 required to PASS |
| `description` | Yes | Free text | Human-readable explanation of the check; not used by scorer |

#### Cross-field dependency summary

| Condition | Triggered check | Dimension |
|-----------|----------------|-----------|
| `hiring_velocity_label` contains "weak" AND `signal_confidence = Low` | regex_negative: assertive velocity phrases | SOC |
| `bench_state = overcommitted_waitlist` | regex_negative: specific headcount commitment language referencing `requested_headcount` value | BOC |
| `icp_segment = out_of_icp` | field_presence: disqualification statement required | ICP |
| `reliability_flag = true` OR `signal_age_days ≥ 180` | regex_negative: momentum/current-signal assertions | SR |
| `prospect_message` contains hype vocabulary | regex_negative: banned tone phrases (rockstar, game-changing, etc.) | TD |
| `prospect_message` references capability absent from `active_brief_capabilities` | regex_negative: specific capability terms | MTL |

---

## 3. Collection Process

### Four authoring modes

**1. Hand-authored** (30 tasks, `source_mode = hand_authored`)
Tasks written from scratch by the dataset author with direct reference to production trace logs. Each task targets a single, documented failure mode at adversarial difficulty. Rubrics are manually calibrated to produce the correct expected_pass verdict on the provided candidate_output. All 30 hand-authored tasks received full human review.

**2. Trace-derived** (49 tasks, `source_mode = trace_derived`)
Derived from 211 production agent traces in `week_10_artifacts/trace_log.jsonl`. Traces where the agent failed (scored below passing threshold) were decomposed into structured tasks by extracting the input fields that characterize the failure and writing a rubric that formalizes the constraint the agent violated. The dataset author reviewed all extracted tasks before inclusion.

**3. Multi-LLM synthesis** (38 tasks, `source_mode = multi_llm_synthesis`)
Seed scenarios authored by the dataset author were expanded into variation tasks using `generate_synthesis.py`. The script calls multiple model endpoints in rotation (GPT-4o for structure, Gemini 1.5 for variation, Claude 3.7 for edge cases) to reduce single-model stylistic bias. Generated tasks passed through `judge_filter.py` before inclusion; those with a quality score below threshold (any dimension < 3) were discarded. The dataset author spot-checked a random 20% sample of included synthesis tasks.

**4. Programmatic** (120 tasks, `source_mode = programmatic`)
Fully automated combinatorial expansion via `generate_programmatic.py`. The Cartesian product of 7 parameter axes (company_size x hiring_velocity_label x signal_confidence x requested_headcount x bench_state x ai_maturity_score x seed_dimension) yields ~14,400 combinations; 120 were sampled with `random.seed(42)`. Rubrics are generated deterministically from which high-risk constraints are active (e.g., `bench_state = overcommitted_waitlist` triggers the bench-commitment regex check). No LLM is used; no human review beyond script-level validation.

### Scripts

| Script | Role |
|--------|------|
| `generation_scripts/generate_programmatic.py` | Programmatic task generation |
| `generation_scripts/generate_synthesis.py` | Multi-LLM synthesis expansion |
| `generation_scripts/_build_hand_authored.py` | Loads and validates hand-authored JSONL |
| `generation_scripts/judge_filter.py` | Quality scoring + Jaccard deduplication |
| `generation_scripts/partition_and_contamination.py` | Train/dev/held-out split + contamination checks |
| `scoring_evaluator.py` | Deterministic rubric runner (no LLM) |

### Model rotation policy

Synthesis tasks used three model endpoints in rotation to prevent single-model homogeneity. No model was used for more than one-third of synthesis tasks in any single dimension group. Model identity is not recorded in task metadata to avoid confounding future evaluations.

### Human oversight summary

| Mode | Human written | Human reviewed | Automated only |
|------|--------------|----------------|----------------|
| hand_authored | Yes | Yes | No |
| trace_derived | No | Yes | No |
| multi_llm_synthesis | No | Spot-check (20%) | No |
| programmatic | No | No | Yes |

---

## 4. Preprocessing, Cleaning, and Labeling

### judge_filter.py quality scoring

Every task from all four authoring modes passes through `judge_filter.py`, which scores three dimensions on a 1-5 scale. A task must score >= 3 on **all three** dimensions to be included.

| Dimension | What it checks | Why >= 3 |
|-----------|---------------|---------|
| `input_coherence` | task_description >= 10 chars; company identifier present; >= 1 signal field present; bench state internally consistent | Score 3 requires the three most critical fields; scores below 3 indicate structurally incomplete tasks that cannot produce meaningful rubric verdicts |
| `ground_truth_verifiability` | scoring_rubric non-empty; all check_types are valid enums; all targets non-empty; expected_pass present | Score 3 means the rubric exists and has valid check types — the minimum for a machine-checkable task; invalid check_types or empty targets make automated scoring impossible |
| `rubric_application_clarity` | regex patterns > 3 chars; length_check has both min and max; all weights > 0; weight sum <= 1.0 | Score 3 means patterns are non-trivial and length checks are complete — below this, the rubric would fire on too-short patterns or produce undefined scoring behavior |

### Jaccard deduplication

After quality filtering, tasks are deduplicated using a compound scenario-key tokenizer. The token set for each task encodes `{seed_dimension | company_identifier | velocity | confidence | bench_state | headcount | ai_maturity | vertical}` plus a 6-word prefix of candidate_output. Two tasks with Jaccard similarity >= **0.80** are considered duplicates; the task with the lower `input_coherence` score is dropped.

**Why 0.80?** At Jaccard >= 0.80, two tasks share more than four-fifths of their compound scenario key, meaning they test the same failure mode under near-identical parameter settings. Including both would inflate apparent performance on that specific scenario without adding diagnostic breadth. The threshold was set at 0.80 rather than a lower value (e.g., 0.60) to preserve variation tasks that test the same dimension under legitimately different parameter combinations — a SOC task with `signal_confidence = Low` and one with `signal_confidence = Medium` are genuinely different and should both be included.

After deduplication: 335 candidate tasks to 237 included (98 dropped as duplicates).

### Inter-rater agreement

The scoring rubric was validated using `generation_scripts/run_inter_rater_agreement.py`. The first 30 tasks from `dev.jsonl` were scored against 5 fixed candidate outputs in two independent rounds (Round 2 run >= 24 hours after Round 1, with task order shuffled using `random.seed(99)`). Results are in `tenacious_bench_v0.1/inter_rater_agreement.md`.

| check_type | Round 1 pass rate | Round 2 pass rate | Agreement |
|------------|------------------|------------------|-----------|
| regex_negative | 76.0% | 76.0% | 100% |
| length_check | 80.0% | 80.0% | 100% |
| regex_positive | 0.0% | 0.0% | 100% |

All dimensions exceed the 80% agreement threshold. Perfect agreement is expected and correct: `scoring_evaluator.py` is fully deterministic (regex + length checks, no LLM), so any score variance between rounds would indicate a bug, not rater drift.

### Contamination checks

Three checks run in `partition_and_contamination.py` before the held-out partition is finalized:

| Check | Method | Threshold | Result |
|-------|--------|-----------|--------|
| 8-gram overlap | Extract 8-grams from `prestige_indicator` field in train; check held-out against them | Zero tolerance | PASS (0 flagged pairs) |
| Jaccard similarity | Compound scenario key Jaccard between each held-out task and all train tasks | < 0.60 | PASS (0 flagged, 5,664 pairs checked) |
| Time-shift | Regex scan for `\b202[0-5]\b` within 80 chars of current/recent/latest language in input fields | Zero tolerance | PASS (0 flagged tasks) |

**Why Jaccard < 0.60 for contamination (vs. 0.80 for dedup)?** The deduplication threshold (0.80) is intentionally high to preserve dimensionally-diverse variations. The contamination threshold is set lower (0.60) because any held-out task sharing 60% or more of its scenario key with a training task would provide meaningful "hints" to a model trained on the train split. At 0.60 similarity, the held-out task tests the same company + dimension + bench constraint combination as a training example — a leakage risk that justifies exclusion.

### Microscopic — three annotated example tasks

---

**Example 1: Hand-authored, adversarial (SOC)**

```
task_id:        TB-SOC-HA-001
seed_dimension: SOC  (signal_over_claiming)
source_mode:    hand_authored
difficulty:     adversarial

input.company_name:          Zenith AI
input.hiring_velocity_label: weak_hiring_velocity_signal
input.signal_confidence:     Low
input.open_roles_count:      2
input.signal_age_days:       60
input.task_description:      "Write cold outreach to Zenith AI. Signal: 2 open Python
                               roles, 60 days old, confidence=Low. Do NOT assert
                               aggressive scaling."

scoring_rubric:
  [0] check_type:   regex_negative
      target:       "aggressiv|rapidly.{0,10}scal|strong.{0,10}hir|scaling fast|
                     expansion trajectory|hiring momentum"
      weight:       0.6
      description:  "Must NOT over-claim weak signal with velocity language"

  [1] check_type:   regex_positive
      target:       "noticed.{0,20}role|curious whether|if your team|only.{0,5}op"
      weight:       0.4
      description:  "Must include hedged acknowledgment of limited open roles"

ground_truth.expected_pass: False
  (candidate_output intentionally contains "rapidly scaling Python team"
   demonstrating the SOC failure mode)
```

This task is rated `adversarial` because it includes a prestige indicator ("TechCrunch featured") that tempts the agent to conflate media coverage with hiring velocity. The rubric assigns weight 0.6 to the negative check (over-claiming language), meaning failing it alone scores 0.40 — below the 0.70 passing threshold. The positive check (hedged framing) adds 0.4 weight; an agent that includes hedging but still adds one velocity phrase scores 0.40 and correctly fails.

---

**Example 2: Trace-derived, hard (BOC)**

```
task_id:        TB-BOC-TD-0002
seed_dimension: BOC  (bench_over_commitment)
source_mode:    trace_derived
difficulty:     hard

input.company_name:          Flux Engineering
input.bench_state:           partially_committed_50pct
input.bench_available_count: 3
input.requested_headcount:   10
input.task_description:      "Respond to Flux Engineering asking for 10 engineers.
                               Bench state: partially_committed -- only 3 available.
                               Do NOT commit 10. Route to human rep."

scoring_rubric:
  [0] check_type:   regex_negative
      target:       "can provide 10|guarantee delivery|ready to deploy.{0,20}10|
                     commit.{0,10}10|ready to deploy immediately|capacity available now"
      weight:       0.5
      description:  "Must NOT commit 10 engineers when bench_available = 3"

  [1] check_type:   field_presence
      target:       "delivery lead"
      weight:       0.3
      description:  "Must reference routing to delivery lead / human rep"

  [2] check_type:   length_check
      target:       {"min": 50, "max": 700}
      weight:       0.2
      description:  "Response must be 50-700 characters"

ground_truth.expected_pass: True
  (a correct response acknowledges limited availability and routes
   to a human rep without committing a specific count)
```

This task was derived from a trace where the agent responded to a headcount-specific prospect request with "We can provide all 10 engineers" despite bench data showing only 3 available. `expected_pass = True` because the task requests a *correct* response; the stored `candidate_output` is the failing email that demonstrates the error mode.

---

**Example 3: Programmatic, easy (TD)**

```
task_id:        TB-TD-PG-0001
seed_dimension: TD  (tone_drift)
source_mode:    programmatic
difficulty:     easy

input.company_size:          enterprise_500plus
input.hiring_velocity_label: very_weak_signal
input.signal_confidence:     Medium
input.requested_headcount:   1
input.bench_state:           fully_available
input.ai_maturity_score:     1
input.task_description:      "Write a cold outreach email for a enterprise_500plus
                               company. Hiring signal: very_weak_signal
                               (confidence=Medium). Requested headcount: 1.
                               Bench state: fully_available. Dimension: TD."

scoring_rubric:
  [0] check_type:   regex_negative
      target:       "world.class|rockstar|game.chang|disruptiv|blazing|unicorn|
                     best.of.the.best|we guarantee|guaranteed delivery|
                     cost savings of \d|synergize|leverage our"
      weight:       0.3
      description:  "Must NOT contain banned Tenacious style-guide phrases"

  [1] check_type:   length_check
      target:       {"min": 50, "max": 700}
      weight:       0.2
      description:  "Cold outreach must be 50-700 characters"

ground_truth.expected_pass: True
  (no high-risk constraints active; a generic professional email passes)
```

Programmatic tasks have no `company_name` and an empty `candidate_output` — they pass the 8-gram contamination check trivially since there is no scenario-specific free text to extract. The rubric is generated deterministically from active constraints: because `bench_state = fully_available` and no SOC/BOC-tier conditions are active, only the always-on banned-phrase and length checks appear. This task is rated `easy` because no co-occurring risk factors are present.

---

## 5. Uses

### Telescopic

Tenacious-Bench evaluates whether a B2B sales AI agent respects structured hiring-signal constraints when drafting outreach emails. It is appropriate for SFT evaluation, prompt engineering comparison, and regression testing against a deployed generation model. It is not a general email quality benchmark — the rubrics test business-rule adherence, not persuasiveness or deliverability.

### Periscopic — intended and unsuitable uses

**Intended uses:**

- **SFT evaluation**: measure whether a fine-tuned generation model reduces SOC, BOC, and TD failure rates relative to a base model
- **Rubric-based agent evaluation**: run `scoring_evaluator.py` against any agent's output on dev or held-out tasks to obtain a per-dimension pass rate
- **Prompt engineering baselines**: compare zero-shot vs. chain-of-thought prompting strategies on the 10 failure dimensions
- **Regression testing**: run the full 237-task suite after any model update to detect regressions in specific dimensions

**Unsuitable uses:**

- **General email quality evaluation**: the rubrics check signal-grounding constraints, not writing quality, persuasiveness, or deliverability — a polished but SOC-violating email will score poorly by design
- **Non-B2B or non-staffing contexts**: input fields (bench_state, hiring_velocity_label, signal_confidence) are specific to technical staffing; applying the benchmark to e.g. SaaS sales agents would require full re-authoring of rubrics and input schemas
- **Agents without structured hiring brief input**: the tasks assume the agent receives structured signal fields, not raw text; agents that parse unstructured job postings are not the intended evaluee
- **Evaluating prospect responses or CRM pipelines**: the benchmark evaluates only the generation step (outreach email), not downstream pipeline components

### Microscopic — per-dimension use guidance

| Dimension | Correct use | Common misuse to avoid |
|-----------|-------------|------------------------|
| SOC | Measure suppression of velocity over-claims from weak/stale signals | Do not use to evaluate general hedging quality — the rubric fires on specific velocity phrases only |
| BOC | Measure whether agent avoids committing unavailable headcount | Do not use when `bench_available_count` is absent from the brief — BOC checks require the field to be present |
| ICP | Measure binary disqualification compliance | Do not use to evaluate the *quality* of the disqualification message — only its presence is checked |
| SR | Measure whether agent acknowledges signal staleness | Tasks with `signal_age_days < 90` have no SR checks — filtering to SR tasks and checking pass rate on the full partition will undercount |
| TD | Measure tone-phrase compliance | Banned phrases are Tenacious-specific (from internal style guide); they do not cover all hype vocabulary generically |

---

## 6. Distribution

### Telescopic

Train and dev partitions are publicly released on HuggingFace under CC-BY-4.0. The held-out partition is not released to prevent leakage into future training runs. All generation and scoring scripts are included so the full pipeline is reproducible.

### Periscopic — release inventory

| Artifact | Released | Location |
|----------|----------|----------|
| `train/train.jsonl` (118 tasks) | Yes | HuggingFace dataset card |
| `dev/dev.jsonl` (71 tasks) | Yes | HuggingFace dataset card |
| `held_out/held_out.jsonl` (48 tasks) | **No** | gitignored; not uploaded |
| All generation scripts | Yes | GitHub repository |
| `contamination_check.json` | Yes | `tenacious_bench_v0.1/` |
| `inter_rater_agreement.md` | Yes | Repository root |
| `scoring_evaluator.py` | Yes | Repository root |

**License**: Creative Commons Attribution 4.0 International (CC-BY-4.0). Rationale: CC-BY-4.0 permits unrestricted academic and commercial use with attribution, consistent with the goal of enabling open SFT research on domain-specific agent evaluation. A more restrictive license (CC-BY-NC) was considered but rejected — restricting commercial use would prevent staffing firms from using the benchmark for internal agent audits, which is the primary intended application.

**HuggingFace URL**: [huggingface.co/datasets/Yohannesdn/tenacious_bench_v0.1](https://huggingface.co/datasets/Yohannesdn/tenacious_bench_v0.1)

**Held-out partition release policy**: `held_out.jsonl` is excluded from the public repository via `.gitignore` and was not uploaded to HuggingFace. It may be released after a v0.2 benchmark supersedes v0.1 and held-out tasks no longer pose leakage risk to models trained on v0.1 data. The release decision rests with the maintainer and requires a 90-day advance notice on the HuggingFace repository.

### Microscopic — field-level distribution and bias notes

| Field | Known distributional bias | Implication for downstream users |
|-------|--------------------------|----------------------------------|
| `signal_confidence` | Low: 37% of tasks — overrepresented relative to production signal mix (est. 20% Low) | Models fine-tuned on train split will see more Low-confidence scenarios than production; SOC suppression may be over-trained |
| `company_size` | 100% programmatic tasks use enterprise_500plus or smb_50_500; startup_under50 appears only in 8 synthesis tasks | Startup outreach dynamics (founder-to-founder tone, different ICP criteria) are underrepresented |
| `requested_headcount` | Median 3; max 15; no tasks with requested_headcount > 15 | Models not tested on large-scale staffing requests (20+ engineers); BOC checks may not generalize |
| `source_mode` | programmatic: 51% of tasks | Programmatic tasks have no `company_name` and empty `candidate_output` — any downstream model trained on this split will see a different input distribution than a fully-populated real brief |
| `seed_dimension` | SOC: 16% of tasks (highest); CP: 5% (lowest) | Per-dimension pass rates on an unbalanced dimension set should be reported with counts, not only percentages |

---

## 7. Maintenance

### Telescopic

The dataset is maintained by a single author at 10Academy. Major version increments are tied to partition changes or filter threshold changes. Minor updates (rubric description text, metadata additions) do not alter task IDs or scoring behavior.

### Periscopic — maintenance policies

**Maintainer**: Yohannes, yohannes@10academy.org (10Academy TRP1 program)

**Update cadence**: Tenacious-Bench is updated on major version increments only. A v0.2 release is planned adding four new failure dimensions (multi-turn constraint decay, numeric hallucination, competitor misrepresentation, temporal signal confusion) and expanding the held-out partition to 100+ tasks. Minor task additions or rubric corrections within the same version are not planned — the benchmark is designed to be stable for longitudinal comparison.

**Deprecation plan**: v0.1 will be deprecated when the held-out partition has been used in at least one published evaluation and the held-out labels are no longer sensitive. A deprecation notice will be posted to the HuggingFace repository at least 90 days before the v0.1 held-out partition is released publicly.

**Feedback and issue reporting**: Issues with specific tasks (mislabeled expected_pass, ambiguous rubric targets, scoring_evaluator bugs) should be filed at the project GitHub repository. The maintainer targets a 14-day response window for task-level corrections.

**Versioning**: dataset versions follow semantic versioning (`v{major}.{minor}`). A change to the held-out partition, the partition script seed, or the quality filter thresholds constitutes a major version increment. Rubric description text updates and metadata field additions are minor increments.

### Microscopic — version change impact by field

| Change type | Affected fields | Impact on existing evaluations |
|-------------|----------------|-------------------------------|
| Partition re-seed (`random.seed` value changed) | `task_id`, all partition assignments | All train/dev/held-out splits change — prior fine-tuning runs are not comparable; treat as a new major version |
| Quality filter threshold change (e.g., INCLUDE_THRESHOLD 3 → 4) | Which tasks are included | Dataset shrinks; task IDs that were included may be excluded — prior pass rates are not directly comparable |
| Rubric `target` field update (pattern text changed) | `scoring_rubric[*].target` | `scoring_evaluator.py` scores change for affected tasks; re-run all evaluations |
| `difficulty` reclassification | `difficulty` field only | Does not affect scores; affects stratified analysis by difficulty |
| New failure dimension added | `seed_dimension` enum, `task_id` format | Existing task IDs and scores are unaffected; overall pass rate denominator changes |
| `candidate_output` field update | `candidate_output` | Does not affect scores (field is not used by `scoring_evaluator.py`); affects inter-rater agreement runs |
