# Tenacious-Bench v0.1 — Master Implementation Todos
# Path: A (SFT of generation component — justified by SOC-01 failure in Week 10)
# Backbone: Qwen 3.5 2B via Unsloth on Colab T4 (fp16 LoRA)
# Budget: $10 total across all API and compute charges

---

## OVERVIEW — FINAL DIRECTORY STRUCTURE

```
Evaluation Bench/
├── README.md                              ← Project overview, status, setup, what's next
├── audit_memo.md                          ← ≤600 words, ≥9 probe IDs, ≥5 trace IDs, 6 gaps
├── schema.json                            ← Tenacious-Bench task schema + 3 example tasks
├── scoring_evaluator.py                   ← Rule-based scorer, deterministic, no LLM calls
├── methodology.md                         ← Path A declaration, partitioning, contamination, model rotation
├── methodology_rationale.md              ← One-page paper-cited justification (final submission deliverable)
├── datasheet.md                           ← All 7 Gebru sections + Pushkarna 3 scopes
├── inter_rater_agreement.md              ← 30-task hand-label, agreement matrix, revision notes
├── cost_log.csv                           ← Every API/compute charge: timestamp, bucket, model, cost
├── model_card.md                          ← Backbone, training data, hyperparams, limits, eval results
├── evidence_graph.json                    ← Every number in memo/blog traced to source
├── report_interim.md                      ← Interim PDF-ready report (Acts I–II)
├── requirements.txt                       ← Pinned versions of all Python dependencies
├── .gitignore                             ← Must include tenacious_bench_v0.1/held_out/
├── synthesis_memos/
│   ├── liu_2024_synthetic_data.md
│   ├── gebru_pushkarna_datasheets.md
│   ├── chen_2025_contamination.md
│   ├── gu_llm_as_judge.md
│   ├── lima_2023.md
│   ├── magpie_2024.md
│   └── tulu3_2024.md
├── tenacious_bench_v0.1/
│   ├── train/train.jsonl                  ← 50% of filtered tasks (~100–168 tasks)
│   ├── dev/dev.jsonl                      ← 30% of filtered tasks (~60–100 tasks)
│   ├── held_out/held_out.jsonl            ← 20% of filtered tasks (~40–67 tasks) — GITIGNORED
│   └── contamination_check.json          ← 3-check results, must show "summary": "PASS"
├── generation_scripts/
│   ├── README.md                          ← Pipeline diagram, model routes, costs per mode
│   ├── generate_trace_derived.py          ← Converts Week 10 traces to benchmark tasks
│   ├── generate_programmatic.py          ← Combinatorial parameter expansion generator
│   ├── generate_synthesis.py              ← OpenRouter-backed multi-LLM synthesis
│   ├── hand_authored_tasks.jsonl          ← 30 hand-written adversarial tasks
│   ├── judge_filter.py                    ← Quality filter + Jaccard dedup
│   ├── judge_filter_log.jsonl             ← Per-task filter decisions (auto-generated)
│   ├── filtered_dataset.jsonl             ← Post-filter pool (auto-generated)
│   └── partition_and_contamination.py    ← Splits dataset, runs 3 contamination checks
├── training_data/
│   ├── sft_pairs_raw.jsonl                ← Chat-template formatted train partition (auto-generated)
│   └── sft_pairs_filtered.jsonl          ← Score-filtered SFT pairs (auto-generated)
├── training/
│   └── training_run.log                   ← Unsloth hyperparams + loss curve (auto-generated)
└── ablations/
    ├── ablation_results.json              ← Delta A, B, C, Cost-Pareto (auto-generated)
    └── held_out_traces.jsonl              ← Scored traces per model variant (auto-generated)
```

---

## PHASE 0 — Build Complete Mental Model
**Time estimate: 60 minutes (conversation only — no files written)**

- [x] **P0-01**: Understand the Week 10 → Week 11 transition
  - Anchor on trace `bcef6c8e2dfad99cd3b64e8d4d9451a3` (task_id 1, 6 turns, FAILED)
  - τ²-Bench retail: binary reward 1.0/0.0 based on task completion, no output quality grading
  - Gap: trace failed because agent wrote assertive velocity claim against `weak_hiring_velocity_signal` input — τ²-Bench assigns 0.0 but cannot identify WHAT was wrong
  - Week 11 goal: build Tenacious-Bench, which grades the content of the email, not just whether one was sent
  - **Success**: Can explain the gap in 3 sentences without notes

- [x] **P0-02**: Walk through all six failure modes with trace anchors
  - SOC (Signal Over-Claiming): `bcef6c8e`, `9880a74a` — assertive velocity claim against weak/failed signal
  - BOC (Bench Over-Commitment): `14789f6e`, `4a7f4b2a` — offered headcount exceeds bench availability
  - TD (Tone Drift): `c572a4a3`, `8630d83f` — agent mirrors prospect's register instead of Tenacious voice
  - SR (Signal Reliability): `699348eb`, `9d39b3e9` — stale or explicitly unreliable signal asserted as current fact
  - MTL (Multi-Thread Leakage): `4f46e62b` — fabricated commitments from prior thread imported into new output
  - ICP (ICP Pre-Qualification Failure): `ded84918` — full email sent to out-of-ICP prospect; disqualification was correct action
  - **Success**: Can name all six gaps and one trace per gap from memory

- [x] **P0-03**: Walk through the Tenacious Style Guide v2
  - 5 tone markers (Direct, Grounded, Honest, Professional, Non-condescending): each scored 1–5, all must be ≥4; fail 2+ = brand violation
  - Formatting constraints: cold outreach ≤120 words, one ask per email, no emojis, no bulleted lists in outreach
  - Banned phrase list (16 phrases): "world-class", "top talent", "best-in-class", "rockstar", "ninja", "guru", "skyrocket", "game-changer", "quick chat", "pick your brain", "circle back", "touch base", "synergy", "leverage" (verb), "passionate about", "value-add"
  - Pre-flight checklist: 7 checks — ICP fit first, then active signal, bench availability, claim support, banned phrases, word count, one ask
  - Outreach Decision Flow: 6 steps — disqualify at step 1 if out-of-ICP; ded84918 shows step 1 was skipped
  - 12 GOOD / 12 BAD examples: BAD = banned phrase, tone copy, over-word-count, multiple asks, unsupported claim; GOOD = every factual claim traces to a brief field
  - **Success**: Can explain why any given BAD example fails by pointing to a specific style guide rule

- [x] **P0-04**: Understand what a single benchmark task looks like
  - Input fields: `hiring_signal_brief` (what we know about prospect), `bench_summary` (available engineers), `prior_thread_context` (prior conversation, if any)
  - `candidate_output`: the email string being graded
  - `scoring_rubric`: array of check objects, each with `check_type`, `target`, `weight`, `description`
  - Four check types: `regex_negative` (fails if pattern found), `regex_positive` (fails if pattern absent), `length_check` (fails if outside [min, max] chars), `field_presence` (fails if required field missing)
  - `weighted_score`: sum(check_weight * check_pass) / sum(all_weights) → float 0.0–1.0
  - PASS threshold: `weighted_score >= 0.70`
  - Ground truth: deterministic — same input always returns same score; no LLM involved
  - **Success**: Can trace a score calculation by hand given a rubric and a candidate output

- [x] **P0-05**: Understand Path A (LoRA fine-tuning)
  - Path A = fine-tune the generation component of the Tenacious agent, specifically `compose_outreach()`
  - Backbone: Qwen 3.5 2B (open-source, Apache 2.0, fits on T4 GPU with fp16 LoRA)
  - LoRA: adds small "correction" matrices (r=16, alpha=32) to q_proj and v_proj attention layers; total trainable params ≈ 2% of backbone; does not modify backbone weights
  - Output: `adapter_config.json` + `adapter_model.safetensors` — small files (~32MB), pushed to HuggingFace Hub separately from backbone
  - Training library: Unsloth (4× faster than raw HuggingFace Trainer on T4, built-in flash attention)
  - Why not Path B (RLHF): requires reward model, multi-step pipeline, ≥10× more compute — out of budget
  - Why not Path C (prompt engineering only): cannot modify model weights, cannot generalize across all SOC variants; tested in Delta B ablation
  - **Success**: Can describe what a LoRA adapter is and why it's the right choice for this budget

- [x] **P0-06**: Walk through `readings_reference.md` — paper-to-decision mapping
  - Liu et al. → rule-based verification + quality filter before training
  - Gebru + Pushkarna → write `datasheet.md` concurrently; document WHY for every threshold (Microscopic scope)
  - Chen et al. → 3-check contamination protocol (8-gram + Jaccard + time-shift); seal held-out
  - Gu et al. → rule-based judge in dev phase; model rotation policy (different models for generation vs. judgment)
  - LIMA → 1,000–3,000 pairs target; quality over quantity; SFT teaches format not knowledge
  - Magpie → structured system prompt anchored to hiring brief format for synthesis generation
  - Tülu 3 → 4-mode data mix (30/30/25/15); held-out = unseen skill test, not memorization test
  - **Success**: Can state which decision each paper justifies without looking at the reference file

- [x] **P0-07**: State the full project story in narrative form
  - Arc: "SOC-01 failure exists in Week 10" → "τ²-Bench cannot detect it" → "audit memo proves the gap" → "we build 335 tasks to grade it" → "we train a LoRA adapter to fix it" → "we measure the lift" → "we publish dataset, adapter, blog, and memo"
  - Key numbers: 9 probe IDs, 6 gap categories, 10 trace IDs, ≥200 tasks after filter, 1,000–3,000 SFT pairs, $10 total budget
  - Key outputs: `tenacious_bench_v0.1` dataset on HuggingFace, `tenacious-outreach-lora-qwen35-2b` adapter on HuggingFace, blog post, 2-page memo, 6-min demo video
  - **Success**: Can narrate the full story in under 90 seconds without stopping

---

## PHASE 1 — Environment Setup and Preflight Readiness
**Time estimate: 90 minutes**

- [x] **P1-01**: Create HuggingFace account and write-access token
  - Go to huggingface.co → create account under username matching `{hf_username}` (decide now, cannot change)
  - Settings → Access Tokens → New Token → role: **write** → copy token
  - Create `.env` file in project root; add line: `HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxx`
  - Confirm `.env` is in `.gitignore` (add it if not present)
  - **Success**: `.env` exists, contains `HF_TOKEN=`, `.gitignore` contains `.env`

- [x] **P1-02**: Create OpenRouter account and test API key
  - Go to openrouter.ai → create account → Keys → New Key → copy
  - Add to `.env`: `OPENROUTER_API_KEY=sk-or-xxxxxxxxxxxx`
  - Test call via Python:
    ```python
    import requests, os
    r = requests.post("https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}"},
        json={"model": "deepseek/deepseek-chat", "messages": [{"role": "user", "content": "ping"}]})
    print(r.json()["choices"][0]["message"]["content"])
    ```
  - Log the test call in `cost_log.csv`: `timestamp,preflight,deepseek/deepseek-chat,api key test,$0.00`
  - **Success**: Test call returns a response; cost_log.csv has first row

- [ ] **P1-03**: Verify Google Colab T4 GPU runtime
  - Open new Colab notebook → Runtime → Change runtime type → T4 GPU → Save
  - Run cell: `!nvidia-smi`
  - Confirm output shows "Tesla T4" and ~15GB free memory
  - **Success**: `nvidia-smi` output contains "T4"

- [ ] **P1-04**: (Optional) Create RunPod account as Colab fallback
  - Required only if Colab disconnects during training run on Day 5
  - Go to runpod.io → create account → apply free credits if available
  - Identify cheapest GPU pod with ≥16GB VRAM (RTX 3090 or A4000, ~$0.34/hr)
  - Do NOT spin up a pod now — just confirm account is ready and credits are available
  - **Success**: RunPod account exists and has payment method or credits

- [ ] **P1-05**: Set up local Python 3.11+ environment
  - Verify: `python --version` shows 3.11.x or 3.12.x
  - Install dependencies:
    ```bash
    pip install transformers peft trl datasets accelerate bitsandbytes jsonschema python-dotenv requests
    ```
  - Verify:
    ```bash
    python -c "import trl, peft, datasets, jsonschema; print(trl.__version__, peft.__version__, datasets.__version__)"
    ```
  - Write `requirements.txt` with pinned versions from `pip freeze` output for the above packages
  - **Success**: Verify command prints version numbers without ImportError

- [ ] **P1-06**: Run Unsloth starter notebook on Colab T4
  - Open Unsloth Qwen fine-tuning example notebook from Unsloth GitHub/docs
  - Swap in a 5-row dummy JSONL dataset (write one manually — 5 system/user/assistant triplets)
  - Run full notebook end-to-end: model load → LoRA config → train → save adapter
  - Push dummy adapter to HuggingFace Hub: `model.push_to_hub("{hf_username}/tenacious-bench-dummy-test")`
  - Confirm adapter appears in HuggingFace repo under your account
  - Note: first-run kernel compile takes 6–10 minutes — expected, do not interrupt
  - **Success**: Adapter appears at `huggingface.co/{hf_username}/tenacious-bench-dummy-test` with `adapter_config.json`

- [ ] **P1-07**: Inventory Week 10 artifacts
  - Confirm these files exist and are non-empty:
    - `week_10_artifacts/trace_log.jsonl` (must have ≥61 lines with non-empty trace_id)
    - `week_10_artifacts/probe_library.md`
    - `week_10_artifacts/failure_taxonomy.md`
  - Validate JSON parse:
    ```bash
    python -c "import json; lines = [json.loads(l) for l in open('week_10_artifacts/trace_log.jsonl')]; print(len(lines), 'traces loaded')"
    ```
  - Confirm these 10 trace IDs are present in trace_log.jsonl: `bcef6c8e`, `9880a74a`, `699348eb`, `14789f6e`, `4a7f4b2a`, `c572a4a3`, `8630d83f`, `9d39b3e9`, `4f46e62b`, `ded84918`
  - **Success**: Parse command prints "61 traces loaded" (or more); no JSONDecodeError

- [ ] **P1-08**: Review schema.json starter and validate a dummy task
  - Read `tenacious_bench_v0.1/schema.json` if it exists from a prior session; otherwise note it will be written in P3-02
  - Write a 3-field dummy task JSON by hand:
    ```json
    {"task_id": "TB-SOC-001", "source_mode": "trace_derived", "difficulty": "easy"}
    ```
  - Validate against schema using jsonschema:
    ```python
    import json, jsonschema
    schema = json.load(open("schema.json"))
    task = {"task_id": "TB-SOC-001", "source_mode": "trace_derived", "difficulty": "easy"}
    jsonschema.validate(task, schema)
    print("valid")
    ```
  - **Success**: Validation either passes OR raises a clear error explaining which required field is missing (both are acceptable — confirms the library works)

- [ ] **P1-09**: Initialize `cost_log.csv`
  - Create file with header: `timestamp,bucket,model,purpose,cost_usd`
  - Add one row for every action taken in this phase (even $0.00 rows):
    - Row for OpenRouter API key test
    - Row for Colab session (cost $0.00 — free tier)
    - Row for Unsloth dummy run (cost $0.00 — Colab free tier)
  - Going forward: every API call and compute session must be logged here before moving to next todo
  - **Success**: File exists, header present, ≥3 rows

---

## PHASE 2 — Literature Synthesis Memos
**Time estimate: 90 minutes**
**Note: Each memo is ~400–500 words. Graded on the DISAGREEMENT section, not the summary.**

- [ ] **P2-01**: Write `synthesis_memos/liu_2024_synthetic_data.md`
  - Section 1 — Key Claim: synthetic data works when ground truth is verifiable; fails when it contains hallucinations or covers only narrow scenarios
  - Section 2 — Project Connection: our programmatic mode produces machine-verifiable ground truth (rule-based scorer); `judge_filter.py` removes low-quality outputs; 10-dimension sweep avoids narrow coverage
  - Section 3 — Disagreement: Liu recommends multi-agent simulations for interactive generation tasks; we reject this for dev phase because our documented failure modes (SOC-01, SOC-02) are single-step generation failures, not multi-turn trajectory failures — adding multi-agent simulation would introduce noise without signal gain
  - Evidence for disagreement: cite trace `bcef6c8e` (6-turn task that failed at generation step 1, not at turn 6) and trace `ded84918` (4-turn task where ICP failure occurred at step 1)
  - **Success**: File exists, contains all 3 sections, disagreement cites at least one trace ID

- [ ] **P2-02**: Write `synthesis_memos/gebru_pushkarna_datasheets.md`
  - Section 1 — Key Claim: datasets must be documented concurrently with creation; Pushkarna adds Telescopic/Periscopic/Microscopic scope structure
  - Section 2 — Project Connection: `datasheet.md` is written alongside dataset generation; Microscopic scope documents WHY threshold values (e.g., Jaccard < 0.60) were chosen
  - Section 3 — Disagreement: Pushkarna's full 31-theme Data Card framework is designed for large industrial dataset releases; we scope to Gebru's 7 sections + Pushkarna's 3 scopes only, because our dataset is a small research artifact (≤335 tasks), not an industrial release; applying all 31 themes would add documentation overhead that exceeds the size of the dataset itself
  - Justify by dataset size: cite ≤335 tasks as the constraint that makes a reduced framework appropriate
  - **Success**: File exists, disagreement explicitly mentions the 31-theme scope reduction with size justification

- [ ] **P2-03**: Write `synthesis_memos/chen_2025_contamination.md`
  - Section 1 — Key Claim: n-gram overlap alone misses paraphrased contamination; embedding similarity (cosine) is required for complete detection; protection strategies include sealing held-out and keeping labels private
  - Section 2 — Project Connection: 3-check protocol (8-gram zero tolerance, Jaccard <0.60, time-shift 2026-04); held-out gitignored; programmatic mode has near-zero collision rate by design
  - Section 3 — Disagreement: Chen recommends embedding cosine similarity at threshold < 0.85; we use Jaccard < 0.60 as the dev-phase proxy (no embedding model required); full cosine check is planned for v1.0 but excluded from dev phase to stay within the $10 budget and avoid a model dependency in the contamination pipeline
  - Cite cost constraint explicitly: embedding calls at scale add ~$0.50–1.00 per run against our $10 total
  - **Success**: File exists, disagreement explains the Jaccard-for-cosine substitution with budget justification

- [ ] **P2-04**: Write `synthesis_memos/gu_llm_as_judge.md`
  - Section 1 — Key Claim: LLM judges suffer from self-preference bias; the same model must never generate AND judge the same task; rule-based evaluation is preferred when tasks have a single verifiable correct answer
  - Section 2 — Project Connection: scoring system uses 4 rule-based check types, no LLM; model rotation policy ensures Claude generates synthesis tasks but never judges them; Qwen/DeepSeek used as judge model family
  - Section 3 — No core disagreement; instead: nuance on scope — Gu recommends LLM-as-Judge for open-ended tasks where rubrics are subjective; our failure modes have machine-verifiable correct answers (banned phrase present/absent, word count ≤120, signal reference present/absent); Gu's own paper endorses rule-based over LLM-based exactly in this condition
  - Cite specific check types: `regex_negative` for banned phrases, `length_check` for word count, `regex_positive` for signal reference
  - **Success**: File exists, explains why rule-based is appropriate for our specific check types (not just that we chose it)

- [ ] **P2-05**: Write `synthesis_memos/lima_2023.md`
  - Section 1 — Key Claim (Superficial Alignment Hypothesis): a pretrained model already contains its knowledge; SFT teaches format and style, not new knowledge; 1,000 high-quality examples outperform 52,000 mediocre ones
  - Section 2 — Project Connection: Qwen 3.5 already knows what a professional email looks like; SOC-01 is a calibration gap (model fails to constrain claim strength to match signal confidence), not a knowledge gap; 1,000–3,000 pairs is enough to recalibrate this behavior
  - Section 3 — Disagreement / Scale Nuance: LIMA was validated on a 65B model; our backbone is 2B; at smaller scale the pretrained knowledge base is narrower, so the model may need closer to 3,000 pairs (not 1,000) to achieve equivalent calibration; we set our target at 1,000–3,000 (not 1,000) to account for backbone scale difference
  - Cite backbone choice documentation: Qwen 3.5 2B selected for T4 fit, not for raw capability
  - **Success**: File exists, scale nuance explicitly addresses the 65B vs. 2B difference

- [ ] **P2-06**: Write `synthesis_memos/magpie_2024.md`
  - Section 1 — Key Claim: aligned LLMs can self-generate training data from a structured pre-query template with no human seeds; domain-specific system prompts steer generation to narrow domains; produces more diverse data than Self-Instruct
  - Section 2 — Project Connection: synthesis mode uses Claude Sonnet 4.6 with Tenacious hiring brief format as structured anchor prompt; this is Magpie applied to a B2B sales domain
  - Section 3 — Disagreement: Magpie uses zero-seed generation (only a system prompt, no example inputs); we use seed-informed generation (structured hiring brief template + signal parameters as anchors) because our domain is too narrow for zero-seed generation to stay on-distribution; without a brief template, the model generates plausible-sounding but off-distribution tasks (wrong industry, wrong signal type)
  - Cite Magpie's own finding: system prompt specificity directly controls domain focus; our brief template is a maximally specific system prompt
  - **Success**: File exists, disagreement explains zero-seed vs. seed-informed distinction with domain-narrowness justification

- [ ] **P2-07**: Write `synthesis_memos/tulu3_2024.md`
  - Section 1 — Key Claim: effective SFT mixing is iterative and benchmark-driven; small amounts of domain-specific data produce large targeted skill gains; diverse conversational data prevents general capability degradation; domain-specific and general data are additive
  - Section 2 — Project Connection: 4-mode mix (30% trace / 30% programmatic / 25% synthesis / 15% hand-authored) mirrors Tülu 3's mixing philosophy; sealed held-out tests skill transfer, not memorization
  - Section 3 — Disagreement: Tülu 3 iteratively ablates data mixes across full training runs (939k prompts); our budget and scope do not permit iterative ablation; we use a fixed 30/30/25/15 split informed by failure-dimension coverage targets, not by benchmark-driven feedback loops; iterative mixing only matters at scale — LIMA shows saturation at 3,000 pairs, which is below the threshold where mixing ratios have measurable impact
  - Cite scale constraint: $10 budget + T4 GPU allows at most 2–3 training runs, not 10+ ablation runs
  - **Success**: File exists, disagreement explicitly argues that iterative mixing is a scale-dependent technique not applicable at our dataset size

- [ ] **P2-08**: Create `synthesis_memos/` directory and commit all 7 memos
  - Verify directory contains exactly these 7 files:
    - `liu_2024_synthetic_data.md`
    - `gebru_pushkarna_datasheets.md`
    - `chen_2025_contamination.md`
    - `gu_llm_as_judge.md`
    - `lima_2023.md`
    - `magpie_2024.md`
    - `tulu3_2024.md`
  - Run `git add synthesis_memos/ && git commit -m "Add 7 literature synthesis memos"`
  - Interim submission requires at least 2 common memos committed; all 7 required for final
  - **Success**: `ls synthesis_memos/` lists all 7 files; git log shows commit

---

## PHASE 3 — Act I: Audit and Schema Design
**Time estimate: 80 minutes**

- [ ] **P3-01**: Write `audit_memo.md`
  - Maximum 600 words — verify with `python -c "print(len(open('audit_memo.md').read().split()))"` before commit
  - Required structure:
    - Section 1 — The Gap: one paragraph stating what τ²-Bench retail cannot grade about Tenacious-specific behavior and why
    - Section 2 — Gap Evidence: subsections for each of the 6 gaps, each citing a trace ID with turn count, duration, and failure description
    - Section 3 — What Tenacious-Bench Must Grade: 6-item list mapping each gap to its machine-verifiable check type
  - Must reference ≥9 probe IDs: SOC-01, SOC-02, BOC-01, BOC-02, TD-01, TD-02, SR-02, MTL-01, ICP-03
  - Must reference ≥5 trace IDs with turn count and duration:
    - `bcef6c8e2dfad99cd3b64e8d4d9451a3` (task_id 1, 6 turns, FAILED)
    - `9880a74a2ed3de0cffb6d9f9838b527d` (task_id 5, 14 turns, FAILED)
    - `699348eb` (task_id 15, 1 turn, 10.2s, FAILED — stale signal)
    - `14789f6e12248ec61f1a549b4997d71d` (task_id 13, 12 turns, 155.5s, FAILED)
    - `c572a4a3e887e986a3aa822f3af76669` (task_id 27, 10 turns, 133.9s, FAILED)
    - `4f46e62ba9684330ffff6d283b8bbef5` (task_id 9, 10 turns, 120.9s, FAILED)
    - `ded84918594605214e79fd6d378e2c63` (task_id 23, 4 turns, 49.2s, FAILED)
  - 6 gap categories must be mutually distinct (SOC, BOC, TD, SR, MTL, ICP)
  - Verify word count before commit: must be ≤600 words
  - **Success**: Word count ≤600; all 9 probe IDs present; ≥5 trace IDs with metadata; 6 distinct gap categories named

- [ ] **P3-02**: Design `schema.json`
  - JSON Schema draft-07 format
  - Required fields per task:
    - `task_id` (string, pattern: `TB-[A-Z]{2,3}-[0-9]{3}`)
    - `seed_dimension` (enum: SOC, BOC, TD, SR, MTL, ICP, GAP, CP, DCC, SE)
    - `source_mode` (enum: trace_derived, programmatic, multi_llm_synthesis, hand_authored)
    - `difficulty` (enum: easy, medium, hard, adversarial)
    - `input` (object with required sub-fields: `hiring_signal_brief` string, `bench_summary` string, `prior_thread_context` string)
    - `candidate_output` (string — empty string when used as a task template before scoring)
    - `scoring_rubric` (array of check objects; each check requires: `check_type` enum, `target` string/object, `weight` number, `description` string)
    - `ground_truth` (object with `expected_pass` boolean and `passing_score` number ≥0.70)
    - `metadata` (object with: `source_trace_id` string, `signal_confidence` enum High/Medium/Low, `icp_segment` string)
  - Check type enum: `regex_negative`, `regex_positive`, `length_check`, `field_presence`
  - Pass threshold: weighted score ≥ 0.70
  - **Success**: `python -c "import json; s = json.load(open('schema.json')); print('valid JSON')"` exits 0

- [ ] **P3-03**: Write 3 example tasks conforming to `schema.json`
  - Example 1 (BOC dimension, programmatic, medium difficulty):
    - Input: bench_summary shows 2 engineers available, hiring_signal_brief shows moderate signal, prior_thread_context empty
    - Candidate output: email promising 4 engineers within 2 weeks
    - Scoring rubric: `regex_negative` checking for "4 engineers" or "guaranteed within", weight=0.5; `field_presence` checking that email references bench state, weight=0.3; `length_check` ≤120 words, weight=0.2
    - Ground truth: `expected_pass: false`, `passing_score: 0.70`
  - Example 2 (SOC dimension, trace_derived, hard difficulty):
    - Input: hiring_signal_brief with `signal_confidence: Low`, `weak_hiring_velocity_signal`
    - Candidate output: email with "scaling aggressively" or similar assertive velocity claim
    - Scoring rubric: `regex_negative` for assertive velocity phrases, weight=0.6; `regex_positive` for signal-hedged language, weight=0.4
    - Ground truth: `expected_pass: false`
    - Metadata: `source_trace_id: "bcef6c8e2dfad99cd3b64e8d4d9451a3"`
  - Example 3 (ICP dimension, hand_authored, adversarial difficulty):
    - Input: prospect is a non-engineering function (marketing ops, legal), but brief has surface-level hiring signals
    - Candidate output: full outreach email sent anyway
    - Scoring rubric: `regex_negative` for presence of full email body when ICP check should have fired, weight=0.7; `field_presence` for ICP disqualification statement, weight=0.3
    - Ground truth: `expected_pass: false`
  - **Success**: All 3 tasks parse as valid JSON; `scoring_evaluator.py` (P3-04) can score all 3 without KeyError

- [ ] **P3-04**: Write `scoring_evaluator.py`
  - CLI: `python scoring_evaluator.py --task <task_json_path> --output "<email_string>"`
  - Also supports: `python scoring_evaluator.py --schema schema.json --example N` (runs against example task N in schema)
  - Core logic:
    ```python
    def score_task(task: dict, candidate_output: str) -> dict:
        results = []
        for check in task["scoring_rubric"]:
            if check["check_type"] == "regex_negative":
                passed = not bool(re.search(check["target"], candidate_output, re.IGNORECASE))
            elif check["check_type"] == "regex_positive":
                passed = bool(re.search(check["target"], candidate_output, re.IGNORECASE))
            elif check["check_type"] == "length_check":
                passed = check["target"]["min"] <= len(candidate_output) <= check["target"]["max"]
            elif check["check_type"] == "field_presence":
                passed = check["target"].lower() in candidate_output.lower()
            results.append({"check_type": check["check_type"], "passed": passed, "weight": check["weight"]})
        weighted_score = sum(r["weight"] for r in results if r["passed"]) / sum(c["weight"] for c in task["scoring_rubric"])
        return {"task_id": task["task_id"], "weighted_score": round(weighted_score, 4), "pass": weighted_score >= 0.70, "check_results": results}
    ```
  - Output format: `{"task_id": str, "weighted_score": float, "pass": bool, "check_results": [{"check_type": str, "passed": bool, "weight": float}]}`
  - Must be fully rule-based — zero LLM calls
  - Must be deterministic: same input → same output across consecutive runs
  - Run against all 3 example tasks from P3-03 and print scores to stdout
  - **Success**: `python scoring_evaluator.py` exits code 0; prints 3 score dicts; running twice produces identical output

- [ ] **P3-05**: Write `methodology.md` (first draft)
  - Required sections:
    1. **Path Declaration**: "This project follows Path A — LoRA fine-tuning of the generation component (`compose_outreach()`) of the Tenacious Conversion Engine using Qwen 3.5 2B as backbone."
    2. **Path Justification**: cite ≥3 trace IDs showing SOC failure mode as the primary gap; cite LIMA (format gap, not knowledge gap) and Gu et al. (rule-based scoring validates detection)
    3. **Why Not Path B (RLHF)**: requires reward model + PPO pipeline; ≥10× compute cost; $10 budget makes this infeasible
    4. **Why Not Path C (Prompt Engineering Only)**: cannot modify weights; Delta B ablation will test whether a system prompt alone achieves the same result
    5. **Partitioning Protocol**: `random.seed(42)`, shuffle full pool, split 50%/30%/20% → `train/`, `dev/`, `held_out/`
    6. **Contamination-Check Protocol**: 3 checks — (1) 8-gram overlap: zero tolerance between held_out and train input fields; (2) Jaccard similarity: flag if ≥0.60 between held_out and train tasks; (3) time-shift: all signal references use documented `2026-04` window
    7. **Model Rotation Policy**: "The same model must never generate AND judge the same task (per Gu et al.). Claude Sonnet 4.6 generates synthesis tasks; Qwen/DeepSeek judges all synthesis tasks. Rule-based scorer judges programmatic and trace-derived tasks (no LLM involved)."
    8. **Dataset Authoring Modes**: table with columns: Mode, Target %, Target Count, Source, Cost — rows for trace_derived (30%, ~110, week_10_artifacts, $0), programmatic (30%, ~120, Python script, $0), multi_llm_synthesis (25%, ~75, OpenRouter, ≤$3), hand_authored (15%, ~30, manual, $0)
  - **Success**: All 8 sections present with non-stub content (≥3 sentences per section)

---

## PHASE 4 — Act II: Dataset Authoring
**Time estimate: 150 minutes**

- [ ] **P4-01**: Write `generation_scripts/generate_trace_derived.py`
  - Input: `week_10_artifacts/trace_log.jsonl`
  - Logic:
    - Parse all lines; filter to records with non-empty `trace_id`
    - TASK_ID_TO_PROBE mapping (hardcoded dict): `{1: "SOC-01", 5: "SOC-01", 15: "SOC-02", 13: "BOC-01", 7: "BOC-02", 27: "TD-01", 6: "TD-02", 25: "SR-02", 9: "MTL-01", 23: "ICP-03"}`
    - For each trace in the mapping: extract `input` fields from trace, extract `candidate_output` from agent's final email turn, assign `ground_truth.expected_pass` based on trace's `reward` field (1.0 → pass, 0.0 → fail), set `difficulty` based on `duration_s` (<30s: easy, 30–90s: medium, >90s: hard)
    - Set `source_mode: "trace_derived"`, `metadata.source_trace_id: <trace_id>`
  - Target output: ≈110 tasks to `generation_scripts/trace_derived_raw.jsonl`
  - Cost: $0 — no LLM calls
  - **Success**: Script exits 0; `wc -l generation_scripts/trace_derived_raw.jsonl` shows ≥90; each line is valid JSON with `task_id`, `source_mode`, `scoring_rubric`

- [ ] **P4-02**: Write `generation_scripts/generate_programmatic.py`
  - Combinatorial parameter expansion — no LLM required
  - Parameter space:
    - `company_size`: ["startup_under50", "mid_market_50_500", "enterprise_500plus"]
    - `hiring_velocity_label`: ["strong_signal", "moderate_signal", "weak_hiring_velocity_signal", "very_weak_signal"]
    - `signal_confidence`: ["High", "Medium", "Low"]
    - `requested_headcount`: [1, 2, 3, 5, 8]
    - `bench_state`: ["fully_available", "partially_committed_50pct", "overcommitted_waitlist"]
    - `ai_maturity_score`: [0, 1, 2, 3]
    - `seed_dimension`: ["SOC", "BOC", "TD", "SR", "MTL", "ICP", "GAP", "CP", "DCC", "SE"]
  - Use `random.seed(42)` + `random.sample(list(itertools.product(...)), 120)` — do NOT use full cartesian product
  - For each parameter combination, auto-generate a scoring rubric:
    - If `signal_confidence == "Low"` AND `hiring_velocity_label` starts with "weak": add `regex_negative` for assertive velocity phrases (weight=0.5)
    - If `bench_state == "overcommitted_waitlist"`: add `regex_negative` for specific headcount promises (weight=0.4)
    - Always add `length_check` (max 700 chars for cold outreach ≈ 120 words), weight=0.2
    - Always add `regex_negative` for banned phrases list, weight=0.3
  - Include metadata: `{"source_mode": "programmatic", "seed_dimension": "SOC", "params": {...}}`
  - Output: `generation_scripts/programmatic_raw.jsonl`, target ≈120 tasks
  - Cost: $0
  - **Success**: Script exits 0; `wc -l` ≥90; each task has `scoring_rubric` array with ≥2 checks

- [ ] **P4-03**: Write `generation_scripts/generate_synthesis.py`
  - Uses OpenRouter API (requires `OPENROUTER_API_KEY` from `.env`)
  - Model routing:
    - Hard seed generation: `anthropic/claude-sonnet-4-6` — generates 30–50 unique, complex scenario seeds (one per seed dimension), each as a full hiring brief + failure scenario description
    - Bulk variation: `deepseek/deepseek-chat` (or `qwen/qwen3-latest`) — takes each hard seed and generates 2–3 variations by changing one parameter
  - Model rotation rule: Claude generates seeds; Claude must NOT judge any Claude-generated task; judgment delegated to rule-based scorer
  - System prompt for Claude seed generation:
    ```
    You are writing test cases for a B2B sales AI benchmark. Each test case is a hiring brief + failure scenario for the Tenacious Conversion Engine.
    Dimension: {dimension}. Brief schema: {schema_fields}. Generate one realistic, domain-specific test case where the agent would fail dimension {dimension}.
    ```
  - Log every API call to `cost_log.csv` with model, tokens used, cost
  - Budget cap: ≤$3 for this script; add a cost guard: if `cost_log.csv` total for `synthesis` bucket exceeds $3, raise RuntimeError
  - Output: `generation_scripts/synthesis_raw.jsonl`, target ≈75 tasks
  - Include metadata: `{"source_mode": "multi_llm_synthesis", "synthesis_seed_model": "claude-sonnet-4-6", "variation_model": "deepseek/deepseek-chat"}`
  - **Success**: Script exits 0; `wc -l` ≥60; cost_log.csv synthesis bucket total ≤$3

- [ ] **P4-04**: Write `generation_scripts/hand_authored_tasks.jsonl`
  - 30 tasks written manually as JSONL — not generated by script
  - Each task must be `"difficulty": "adversarial"` and `"source_mode": "hand_authored"`
  - Required edge case categories:
    - 10 tasks: prestigious company name + weak hiring signal (tempts over-claiming; SOC)
    - 5 tasks: stale funding (>12 months old) + recent layoffs in the brief (SR)
    - 5 tasks: prior thread contained prospect's pressure to assert AI capabilities (MTL)
    - 5 tasks: out-of-ICP prospect with plausible surface signals (ICP — like ded84918)
    - 5 tasks: bench partially committed + explicit prospect pressure for fast delivery (BOC — like 4a7f4b2a)
  - Each task must have a complete `scoring_rubric` with ≥2 checks that a human could apply by hand
  - These are the highest-value tasks in the dataset — invest the most authoring time here
  - **Success**: `wc -l generation_scripts/hand_authored_tasks.jsonl` shows 30; each line is valid JSON; `"difficulty": "adversarial"` present in all lines

- [ ] **P4-05**: Write `generation_scripts/judge_filter.py`
  - Reads: `trace_derived_raw.jsonl`, `programmatic_raw.jsonl`, `synthesis_raw.jsonl`, `hand_authored_tasks.jsonl` from `generation_scripts/`
  - Pointwise scoring on 3 dimensions (rule-based, NOT LLM, for dev phase):
    - `input_coherence` (1–5): check that `hiring_signal_brief`, `bench_summary` fields are non-empty and internally consistent (e.g., bench_state matches headcount range)
    - `ground_truth_verifiability` (1–5): check that `scoring_rubric` is non-empty, all checks have non-empty `target` fields, and check types are valid enum values
    - `rubric_application_clarity` (1–5): check that `regex_negative` patterns are non-trivial (length >3 chars), `length_check` has both min and max, weights sum to ≤1.0
  - Inclusion threshold: ALL 3 dimensions must score ≥3
  - Jaccard dedup: tokenize `hiring_signal_brief` field; compute Jaccard similarity between all pairs; drop task if Jaccard ≥0.80 against any already-included task (keep the one with higher coherence score)
  - Output files:
    - `generation_scripts/judge_filter_log.jsonl`: one record per input task with all 3 scores + include/exclude decision + reason if excluded
    - `generation_scripts/filtered_dataset.jsonl`: only included tasks
  - **Success**: `filtered_dataset.jsonl` has ≥200 tasks; `judge_filter_log.jsonl` has same count as all 4 input files combined; no task in filtered output has Jaccard ≥0.80 with any other

- [ ] **P4-06**: Run full generation pipeline in sequence
  - Run in order:
    ```bash
    python generation_scripts/generate_trace_derived.py
    python generation_scripts/generate_programmatic.py
    python generation_scripts/generate_synthesis.py
    python generation_scripts/judge_filter.py
    ```
  - After each script: verify output file exists and has non-zero line count
  - After `judge_filter.py`: verify `filtered_dataset.jsonl` has ≥200 tasks
  - Record final source-mode counts in a summary:
    - trace_derived: N tasks
    - programmatic: N tasks
    - multi_llm_synthesis: N tasks
    - hand_authored: N tasks
    - Total after filter: N tasks
  - Record seed-dimension distribution (how many tasks per dimension: SOC, BOC, TD, SR, MTL, ICP, etc.)
  - **Success**: All 4 scripts exit 0; `filtered_dataset.jsonl` has ≥200 lines; every line is valid JSON

- [ ] **P4-07**: Write `generation_scripts/partition_and_contamination.py`
  - Input: `generation_scripts/filtered_dataset.jsonl`
  - Partitioning: `random.seed(42)`, shuffle all tasks, split 50%/30%/20%
  - Write:
    - `tenacious_bench_v0.1/train/train.jsonl`
    - `tenacious_bench_v0.1/dev/dev.jsonl`
    - `tenacious_bench_v0.1/held_out/held_out.jsonl`
  - Contamination Check 1 — 8-gram overlap:
    - Extract 8-grams from all `hiring_signal_brief` fields in train
    - For each held_out task: check if any 8-gram appears in train set
    - Zero-tolerance: any match → flag pair
  - Contamination Check 2 — Jaccard similarity:
    - Tokenize `hiring_signal_brief` for all train and held_out tasks
    - Compute pairwise Jaccard between each held_out task and all train tasks
    - Flag any pair with Jaccard ≥ 0.60
  - Contamination Check 3 — Time-shift verification:
    - Verify all signal references in all partitions use the `2026-04` window (no pre-2026 dates asserted as current)
    - Document the verification method in the check output
  - Write `tenacious_bench_v0.1/contamination_check.json`:
    ```json
    {
      "ngram_check": {"passed": true, "flagged_pairs": [], "threshold": "zero 8-gram overlap"},
      "jaccard_check": {"passed": true, "flagged_pairs": [], "threshold": "< 0.60"},
      "timeshift_check": {"passed": true, "documented_window": "2026-04", "method": "regex scan for pre-2026 dates"},
      "summary": "PASS",
      "total_tasks": N,
      "train_count": N1,
      "dev_count": N2,
      "held_out_count": N3
    }
    ```
  - **Success**: Script exits 0; all 3 partition files exist with correct approximate counts; `contamination_check.json` shows `"summary": "PASS"`

- [ ] **P4-08**: Run `partition_and_contamination.py` and verify outputs
  - Run: `python generation_scripts/partition_and_contamination.py`
  - Verify partition files exist:
    ```bash
    wc -l tenacious_bench_v0.1/train/train.jsonl
    wc -l tenacious_bench_v0.1/dev/dev.jsonl
    wc -l tenacious_bench_v0.1/held_out/held_out.jsonl
    ```
  - Verify `contamination_check.json` shows `"summary": "PASS"`
  - Verify held_out is gitignored: `git check-ignore -v tenacious_bench_v0.1/held_out/held_out.jsonl` should return a match
  - If contamination check FAILS: inspect `flagged_pairs` list, remove the flagged tasks from `filtered_dataset.jsonl`, re-run partition script
  - **Success**: All 3 partition files exist; `"summary": "PASS"` confirmed; held_out is gitignored

- [ ] **P4-09**: Inter-rater agreement (hand-label 30-task subset)
  - Select first 30 tasks from `dev.jsonl`
  - Round 1: run `scoring_evaluator.py` on each of the 30 tasks using 5 fixed candidate_output strings (same 5 strings applied to all 30 tasks); record PASS/FAIL per check per task in a spreadsheet or JSON file
  - Wait ≥24 hours
  - Round 2: re-run the same 30 tasks with shuffled order, without looking at Round 1 results; record again
  - Compute per-rubric-dimension agreement: `count(round1_pass == round2_pass) / 30`
  - If any dimension < 80% agreement: revise the rubric description for that check type; re-run both rounds; document the revision
  - Write `inter_rater_agreement.md`:
    - Method description (30 tasks, 5 fixed outputs, 24h gap)
    - Agreement matrix (markdown table: dimension | round1 pass rate | round2 pass rate | agreement %)
    - Revision log if any dimension required rubric changes
  - **Success**: All rubric dimensions show ≥80% agreement; `inter_rater_agreement.md` exists with table

- [ ] **P4-10**: Write `datasheet.md`
  - Length: 3–5 pages
  - Must include ALL 7 Gebru sections:
    1. **Motivation**: why Tenacious-Bench was created; what τ²-Bench gap it fills; who created it and for what purpose
    2. **Composition**: task counts by dimension (table), source_mode distribution (table), partition sizes (table), what each field represents
    3. **Collection Process**: 4 authoring modes described; scripts used; models used (with model rotation policy); which tasks have human oversight vs. automated generation
    4. **Preprocessing/Cleaning/Labeling**: judge_filter.py thresholds (all 3 dimensions, ≥3 threshold); Jaccard dedup threshold (0.80); inter-rater protocol; contamination check thresholds
    5. **Uses**: intended (evaluating B2B sales AI agents for Tenacious-style SOC/BOC/TD/SR/MTL/ICP failure modes); unsuitable (general-purpose email evaluation; non-B2B technical staffing contexts; evaluating agents without a structured hiring brief input)
    6. **Distribution**: license CC-BY-4.0; HuggingFace URL (to be filled); held-out partition release policy (not released in v0.1; may be released after v0.2 benchmark supersedes it)
    7. **Maintenance**: maintainer (Yohannes, yohannes@10academy.org); update cadence (on major version increments); deprecation plan
  - Must include Pushkarna 3 scopes in each section:
    - **Telescopic**: plain-language one-paragraph overview in Motivation section
    - **Periscopic**: composition table with numeric counts in Composition section
    - **Microscopic**: 3 example tasks with full rubric annotated in Collection Process or Preprocessing section; include WHY threshold values were chosen (e.g., "Jaccard < 0.60 chosen because...")
  - **Success**: All 7 sections present with non-stub content (≥3 sentences each); all 3 Pushkarna scopes present; threshold rationales documented in Microscopic scope

- [ ] **P4-11**: Update `methodology.md` with actual results
  - Add section: **Contamination Results** — paste table from `contamination_check.json` (0 flagged pairs per check)
  - Add section: **Partition Counts** — actual counts from train/dev/held_out splits
  - Add section: **Stratification Notes** — difficulty distribution across partitions (table: easy/medium/hard/adversarial counts per split); seed_dimension distribution per split; note if any dimension is underrepresented in held_out
  - Add section: **Inter-Rater Agreement Results** — copy agreement matrix from `inter_rater_agreement.md`; note any rubric revisions made
  - **Success**: All 4 new sections present with actual numbers (not placeholder text)

- [ ] **P4-12**: Write `generation_scripts/README.md`
  - Include:
    - Pipeline diagram (text-based, shows script execution order with → arrows)
    - 15-probe seed table: columns = Probe ID, Dimension, Description, Source Mode, Target Count
    - Per-script description: input, output, cost, model used (if any)
    - Judge filter thresholds: all 3 dimensions, inclusion criteria, Jaccard dedup threshold
    - Model rotation policy: which model generates what, which model judges what
    - Total cost breakdown: per mode (trace: $0, programmatic: $0, synthesis: ≤$3, hand_authored: $0)
  - **Success**: File exists; a new reader can understand the full pipeline without reading the scripts

**[INTERIM SUBMISSION CHECKPOINT]** — Verify before committing to GitHub:
- [ ] `audit_memo.md` — word count ≤600, ≥9 probe IDs, ≥5 trace IDs
- [ ] `schema.json` — valid JSON, ≥3 example tasks
- [ ] `scoring_evaluator.py` — exits code 0, scores all 3 examples
- [ ] `tenacious_bench_v0.1/train/train.jsonl` — exists, ≥100 lines
- [ ] `tenacious_bench_v0.1/dev/dev.jsonl` — exists, ≥60 lines
- [ ] `tenacious_bench_v0.1/held_out/` — gitignored, NOT committed
- [ ] `tenacious_bench_v0.1/contamination_check.json` — `"summary": "PASS"`
- [ ] `datasheet.md` — all 7 Gebru sections + 3 Pushkarna scopes
- [ ] `methodology.md` — all 8 sections including actual contamination results
- [ ] `inter_rater_agreement.md` — all dimensions ≥80%
- [ ] `generation_scripts/` — all 4 scripts + `hand_authored_tasks.jsonl` + `README.md`
- [ ] `synthesis_memos/` — at least 2 common memos committed (4 common + 3 path-A for final)
- [ ] `cost_log.csv` — all charges logged
- [ ] `README.md` at root — overview, status, setup instructions, Days 4–7 plan
- [ ] PDF report: bench composition table, IRA results, 3 annotated example tasks, Days 4–7 plan

---

## PHASE 5 — Act III: Training Data Preparation
**Time estimate: 60 minutes**

- [ ] **P5-01**: Convert train partition to SFT chat-template format
  - Input: `tenacious_bench_v0.1/train/train.jsonl`
  - Each record → chat format:
    ```json
    {"messages": [
      {"role": "system", "content": "You are the Tenacious Conversion Engine...{TENACIOUS_SYSTEM_PROMPT}"},
      {"role": "user", "content": "{hiring_signal_brief}\nBench state: {bench_summary}\nContext: {prior_thread_context}"},
      {"role": "assistant", "content": "{ground_truth compliant output}"}
    ]}
    ```
  - TENACIOUS_SYSTEM_PROMPT must include: tone markers (Direct, Grounded, Honest, Professional, Non-condescending), banned phrase list, word limit (120 words cold), one-ask rule, ICP pre-qualification requirement
  - Output: `training_data/sft_pairs_raw.jsonl`
  - **Success**: File exists; `from datasets import load_dataset; ds = load_dataset("json", data_files="training_data/sft_pairs_raw.jsonl")` succeeds; all records have `messages` key with 3-item list

- [ ] **P5-02**: Filter SFT pairs by quality score
  - Input: `training_data/sft_pairs_raw.jsonl`
  - For each record: extract `candidate_output` from the `assistant` message turn; run through `scoring_evaluator.py`; keep only records where `weighted_score >= 0.70`
  - Output: `training_data/sft_pairs_filtered.jsonl`
  - Target: 1,000–3,000 pairs after filtering
  - If result < 1,000 pairs: STOP — flag for review before training; likely cause is ground truth outputs in train partition being low quality → re-check P4-02/P4-03 output quality
  - If result > 3,000 pairs: filter to top 3,000 by score (highest `weighted_score` first)
  - **Success**: `wc -l training_data/sft_pairs_filtered.jsonl` between 1000 and 3000; every record scores ≥0.70

- [ ] **P5-03**: Run second contamination check on training data
  - Extract all `hiring_signal_brief` fields from `sft_pairs_filtered.jsonl`
  - Run 8-gram overlap check against all `hiring_signal_brief` fields in `tenacious_bench_v0.1/held_out/held_out.jsonl`
  - Zero tolerance: any overlap → remove the training pair and log it
  - Document results: "Second contamination pass: N pairs removed; 0 8-gram overlaps with held_out found."
  - **Success**: No 8-gram overlap between training data and held_out; result logged in `methodology.md`

- [ ] **P5-04**: Write `methodology_rationale.md`
  - One page (~500–700 words)
  - Required sections:
    1. **Why Path A**: cite ≥3 trace IDs (SOC-01 pattern in `bcef6c8e`, `9880a74a`, `c572a4a3`) showing the failure is in `compose_outreach()` generation, not in planning or tool use; cite Gu et al. (rule-based detection confirms SOC is machine-verifiable)
    2. **Why 1,000–3,000 pairs**: cite LIMA (Superficial Alignment Hypothesis, format not knowledge, 1k pairs on 65B); explain backbone scale adjustment (2B model → need ~3,000 pairs to compensate)
    3. **How Magpie informed synthesis**: structured system prompt anchored to hiring brief schema; seed-informed (not zero-seed) because domain is narrow; cite Magpie's finding that system prompt specificity controls domain focus
    4. **How Tülu 3 informed data mix**: fixed 30/30/25/15 source-mode split chosen to cover all 6 failure dimensions rather than concentrating on SOC only; cite Tülu 3's finding that diverse data prevents capability degradation
  - **Success**: All 4 sections present; ≥3 trace IDs cited; LIMA, Magpie, Tülu 3 all cited by name with year

- [ ] **P5-05**: Verify training data loads with HuggingFace datasets library
  - Run:
    ```python
    from datasets import load_dataset
    ds = load_dataset("json", data_files="training_data/sft_pairs_filtered.jsonl")
    print(f"Total pairs: {len(ds['train'])}")
    sample = ds['train'][0]
    assert 'messages' in sample
    assert len(sample['messages']) == 3
    assert sample['messages'][0]['role'] == 'system'
    print("Format verified")
    ```
  - **Success**: Script exits 0; prints "Format verified"; no KeyError or AssertionError

- [ ] **P5-06**: Document training data composition in `methodology.md`
  - Add table: columns = seed_dimension, count_in_training_data, % of total
  - Flag any dimension with < 20 pairs (will have limited training signal — note this honestly)
  - Note if any dimension has 0 pairs (not represented in training data — model receives no signal for that failure mode)
  - **Success**: Composition table added to methodology.md; all dimensions listed (even zeros)

---

## PHASE 6 — Act IV: Train, Ablate, Measure
**Time estimate: 3–5 hours (dominated by training run)**

- [ ] **P6-01**: Configure Unsloth training notebook on Colab T4
  - Open Colab, connect to T4 GPU (confirm `!nvidia-smi` shows T4)
  - Install: `!pip install unsloth`
  - Load backbone: `from unsloth import FastLanguageModel; model, tokenizer = FastLanguageModel.from_pretrained("Qwen/Qwen2.5-0.5B-Instruct")` — use Qwen 3.5 2B if memory allows, 0.8B as fallback
  - LoRA config:
    ```python
    model = FastLanguageModel.get_peft_model(model,
        r=16, lora_alpha=32, lora_dropout=0.05,
        target_modules=["q_proj", "v_proj"],
        bias="none", use_gradient_checkpointing=True)
    ```
  - Training args:
    ```python
    TrainingArguments(learning_rate=2e-4, num_train_epochs=3,
        per_device_train_batch_size=2, gradient_accumulation_steps=4,
        fp16=True, seed=42, output_dir="./training")
    ```
  - Pin backbone version in `requirements.txt` (e.g., `transformers==4.47.0`)
  - **Success**: Model loads without OOM error; `model.print_trainable_parameters()` shows LoRA params active

- [ ] **P6-02**: Run training
  - Expected wall time: 30–90 minutes on T4 depending on dataset size
  - Monitor training loss: if loss is NOT decreasing by end of epoch 1 → kill run immediately; diagnose data format issue before adding more compute
  - Log all output to `training/training_run.log`:
    - Exact backbone version
    - All hyperparameters
    - Per-step loss (copy from Colab output)
    - Total training time
    - Final training loss
  - Budget: $0 (Colab T4 free tier)
  - **Success**: Training completes without OOM; final training loss lower than initial; `training_run.log` exists with loss curve

- [ ] **P6-03**: Push LoRA adapter to HuggingFace Hub
  - Push adapter files only — do NOT merge adapter into backbone:
    ```python
    model.push_to_hub("{hf_username}/tenacious-outreach-lora-qwen35-{backbone_size}", token=HF_TOKEN)
    ```
  - Verify HuggingFace repo contains: `adapter_config.json`, `adapter_model.safetensors`
  - Confirm backbone is NOT included in the repo (adapter only)
  - Confirm repo is public and accessible without login
  - **Success**: HuggingFace repo page is accessible; contains `adapter_config.json`; repo size is <100MB (adapter only)

- [ ] **P6-04**: Run Delta A ablation — trained vs. baseline
  - Load LoRA adapter + backbone; run inference on all tasks in `held_out/held_out.jsonl`; score with `scoring_evaluator.py`
  - Also run baseline (backbone only, no LoRA, no system prompt) on same held_out tasks
  - Compute pass rate for both: `(count of tasks where weighted_score >= 0.70) / total_held_out_tasks`
  - Delta A lift: `trained_pass_rate - baseline_pass_rate`
  - 95% CI using paired bootstrap:
    ```python
    import numpy as np
    scores_trained = [...]  # list of weighted_scores
    scores_baseline = [...]
    diffs = np.array(scores_trained) - np.array(scores_baseline)
    bootstraps = [np.mean(np.random.choice(diffs, len(diffs), replace=True)) for _ in range(1000)]
    ci_lower, ci_upper = np.percentile(bootstraps, [2.5, 97.5])
    ```
  - Write to `ablations/ablation_results.json`:
    ```json
    {"delta_a_lift": float, "delta_a_ci_lower": float, "delta_a_ci_upper": float,
     "trained_pass_rate": float, "baseline_pass_rate": float}
    ```
  - If Delta A is negative or CI includes 0: report honestly; do not deploy trained adapter
  - **Success**: `ablation_results.json` exists with all 5 keys; CI computed from 1,000 bootstrap resamples

- [ ] **P6-05**: Run Delta B ablation — base model + prompt engineering vs. trained
  - Take baseline backbone (no LoRA); add a carefully engineered system prompt that explicitly states the SOC constraint: "Do NOT write assertive velocity claims when signal_confidence is Low or hiring_velocity_label contains 'weak'. Use hedged language: 'it appears', 'it looks like', 'potentially'."
  - Run on same held_out tasks; score with same evaluator
  - Compute Delta B lift: `prompt_eng_pass_rate - baseline_pass_rate`
  - Compare to Delta A: if Delta B ≥ Delta A → training did NOT beat prompt engineering → report this finding honestly in blog and memo (it is a legitimate publishable result)
  - Append to `ablation_results.json`:
    ```json
    {"delta_b_lift": float, "prompt_eng_pass_rate": float,
     "delta_b_vs_delta_a": "training_wins | prompt_wins | tie"}
    ```
  - **Success**: Delta B computed; honest comparison to Delta A documented; `ablation_results.json` updated

- [ ] **P6-06**: Run Cost-Pareto analysis
  - Measure for each variant (baseline / base + prompt / trained):
    - Per-task inference latency: `time.time()` before and after each inference call; average over held_out set
    - Per-task cost: compute from `(input_tokens + output_tokens) * price_per_1k_tokens` (use OpenRouter pricing if inference is via API; $0 if local)
  - Append to `ablation_results.json`:
    ```json
    {"cost_pareto": {
      "baseline": {"avg_latency_ms": float, "cost_per_1k_tasks_usd": float},
      "prompt_eng": {"avg_latency_ms": float, "cost_per_1k_tasks_usd": float},
      "trained_lora": {"avg_latency_ms": float, "cost_per_1k_tasks_usd": float}
    }}
    ```
  - **Success**: All 3 variants have latency and cost entries; no variant is missing

- [ ] **P6-07**: Write raw scored traces to `ablations/held_out_traces.jsonl`
  - One JSONL record per (task × model_variant) combination:
    ```json
    {"task_id": str, "model_variant": "baseline|prompt_eng|trained_lora",
     "candidate_output": str, "weighted_score": float, "pass": bool, "check_results": [...]}
    ```
  - These are the evidence backing every numeric claim in the memo
  - Every number in `ablation_results.json` must be reproducible from this file
  - **Success**: `wc -l ablations/held_out_traces.jsonl` = (held_out_count × 3); every task_id appears 3 times

- [ ] **P6-08**: Write `model_card.md`
  - Required sections:
    - **Backbone**: name, version, source (HuggingFace model ID), license
    - **Training Data**: partition used (train only), size, source modes breakdown, failure dimensions covered
    - **Hyperparameters**: all LoRA settings + training args from P6-01 (verbatim)
    - **Intended Use**: drop-in replacement for `compose_outreach()` in Tenacious Conversion Engine; input = hiring brief + bench state; output = compliant outreach email
    - **Limitations**: trained primarily on SOC failure mode; limited training signal for BOC/TD/MTL; not validated on non-technical staffing domains; do not use for cold outreach to ICP-excluded segments
    - **Evaluation Results**: Delta A lift with 95% CI; Delta B result; honest statement if prompt engineering was competitive
    - **Environmental Impact**: Colab T4 GPU-hours used; equivalent CO2 estimate (use codecarbon or estimate manually at ~0.5kg CO2/GPU-hour for T4)
  - **Success**: All 7 sections present; evaluation results section contains actual numbers from `ablation_results.json`

---

## PHASE 7 — Act V: Publish and Engage
**Time estimate: 3–4 hours**

- [ ] **P7-01**: Run pre-publication checklist — all 8 must pass before anything goes public
  - [ ] `datasheet.md` has non-stub content in all 7 Gebru sections (≥3 sentences each)
  - [ ] License is CC-BY-4.0 and documented in both `methodology.md` and `datasheet.md` Distribution section
  - [ ] Root `README.md` is runnable: a stranger can `git clone`, `pip install -r requirements.txt`, and `python scoring_evaluator.py` in < 10 minutes
  - [ ] All scripts use `random.seed(42)` — verify by grep: `grep -r "random.seed" generation_scripts/`
  - [ ] `held_out/` is in `.gitignore` and NOT present in `git ls-files`
  - [ ] `contamination_check.json` is committed and shows `"summary": "PASS"`
  - [ ] `model_card.md` is complete (all 7 sections)
  - [ ] All papers, datasets, tools cited in `README.md` and `methodology.md` (check for: Liu et al., Gebru et al., Pushkarna et al., Chen et al., Gu et al., LIMA, Magpie, Tülu 3, Unsloth, HuggingFace, OpenRouter, τ²-Bench)
  - **Success**: All 8 boxes checked before P7-02 begins

- [ ] **P7-02**: Publish `tenacious_bench_v0.1` dataset to HuggingFace Hub
  - Upload `train/train.jsonl` and `dev/dev.jsonl` ONLY — do NOT upload `held_out/`
  - Include in the HuggingFace dataset repo:
    - `README.md` with quickstart: "Run `python scoring_evaluator.py --schema schema.json --example 1` to score an example task in < 2 minutes"
    - `datasheet.md`
    - `schema.json`
    - `scoring_evaluator.py`
    - Baseline scores: Week 10 agent pass rate on dev partition (run baseline inference against dev tasks)
  - Set license to CC-BY-4.0 in the dataset card YAML frontmatter
  - **Success**: Dataset page is public; `train` and `dev` splits are downloadable; `held_out` is absent; license is visible on dataset card

- [ ] **P7-03**: Write technical blog post
  - Length: 1,200–2,000 words
  - Required sections in order:
    1. **The Gap** (~300 words): what τ²-Bench misses; cite 2 concrete failure traces with task_id and failure description
    2. **The Audit** (~250 words): how 6 gaps were found; probe IDs and trace IDs as evidence; methodology of audit
    3. **The Dataset** (~350 words): 4 authoring modes; model routing decisions; hard design choices named (Jaccard threshold, why Jaccard not cosine, 30/30/25/15 split, why 9 probe dimensions not 1)
    4. **The Training** (~300 words): Path A choice; LIMA justification; what the LoRA adapter does; what it does not do (does not fix BOC or ICP)
    5. **The Honest Result** (~200 words): Delta A lift with 95% CI; Delta B result (positive or negative); honest statement about limitations
    6. **What's Next** (~100 words): v0.2 plans; 4 failure modes Tenacious-Bench v0.1 does not capture
  - Publish to HuggingFace community blog (preferred) or Substack
  - **Success**: Post is publicly accessible; all 6 sections present; Delta A and Delta B numbers match `ablation_results.json`

- [ ] **P7-04**: Write community engagement artifact
  - Open a GitHub issue on the τ²-Bench repository
  - Title: "Tenacious-Bench: 6 output-quality failure modes τ²-Bench retail cannot detect in B2B sales agents"
  - Body must include:
    - One concrete example: trace `ded84918` — task_id 23, 4 turns, 49.2s — τ²-Bench gave completion credit; Tenacious-Bench scores it FAIL (ICP-03, full email sent to out-of-ICP prospect)
    - Link to HuggingFace dataset
    - Description of all 6 failure mode categories
    - Brief statement of how Tenacious-Bench makes each independently machine-verifiable
  - Save the GitHub issue URL
  - **Success**: Issue is posted publicly; contains trace ID example; HuggingFace link is live

- [ ] **P7-05**: Write `memo.pdf` (2 pages exactly)
  - Page 1 — The Decision:
    - 3-sentence executive summary: what was built, what it measures, what it found
    - Headline result: Delta A lift on held_out with 95% CI (e.g., "+8.3 pp [3.1, 13.5], p=0.003")
    - Delta B comparison: honest statement (e.g., "System prompt engineering achieved +4.1 pp — training outperformed prompting by 4.2 pp")
    - Per-task cost delta: cost with trained component vs. without
    - Production recommendation: one of three — "Deploy", "Deploy with caveat: [specific condition]", "Do not deploy: [what must change first]"
  - Page 2 — Skeptic's Appendix:
    - 4 failure modes Tenacious-Bench v0.1 still does not capture (name them specifically)
    - One honest unresolved training failure (e.g., "MTL dimension: adapter showed no lift — training signal was insufficient (N=8 pairs)")
    - Kill-switch trigger: "If production pass rate on SOC dimension drops below [X]% over a rolling 100-email window, disable LoRA adapter and revert to baseline."
  - Export as PDF; ensure it is exactly 2 pages when printed at A4 or Letter
  - **Success**: PDF exists; is exactly 2 pages; all numeric claims are present in `evidence_graph.json` (P7-06)

- [ ] **P7-06**: Write `evidence_graph.json`
  - One entry per numeric claim in `memo.pdf` and the blog post
  - Format:
    ```json
    [
      {"claim": "Delta A lift of +8.3 pp",
       "value": 0.083,
       "source_type": "ablation_result",
       "source_id": "ablations/ablation_results.json:delta_a_lift"},
      {"claim": "95% CI [3.1, 13.5]",
       "value": [0.031, 0.135],
       "source_type": "ablation_result",
       "source_id": "ablations/ablation_results.json:delta_a_ci_lower,delta_a_ci_upper"}
    ]
    ```
  - Every number in the memo must have an entry — check memo sentence by sentence
  - **Success**: Every numeric claim in `memo.pdf` has a corresponding entry; all `source_id` fields point to existing files

- [ ] **P7-07**: Record demo video (max 6 minutes, no login required to view)
  - Must show (in order):
    1. HuggingFace dataset page — scroll to show datasheet, partition splits, CC-BY-4.0 license
    2. Run `scoring_evaluator.py` on one task end-to-end — show input, output, score breakdown in terminal
    3. Open `ablations/held_out_traces.jsonl` — find one trace, show its score; open `evidence_graph.json` and find the matching claim — demonstrate the evidence chain
    4. Show blog post page (scrolled to Delta A and Delta B results section)
    5. Show GitHub issue on τ²-Bench repo
  - Record at 720p minimum; upload to YouTube (unlisted OK) or Loom (no login required to view)
  - **Success**: Video is accessible without login; all 5 items visible; total duration ≤6 minutes

- [ ] **P7-08**: Final submission package
  - Gather all URLs into one document:
    - GitHub repo URL (public)
    - `memo.pdf` download link (from GitHub or direct)
    - Demo video URL (no login required)
    - HuggingFace dataset URL (`{hf_username}/tenacious_bench_v0.1`)
    - HuggingFace model URL (`{hf_username}/tenacious-outreach-lora-qwen35-{size}`)
    - Blog post URL
    - Community engagement URL (GitHub issue)
  - Verify every URL is publicly accessible before submitting
  - **Success**: All 7 URLs confirmed public; submission package complete

---

## KEY REFERENCE: TRACE IDs

| Trace ID (first 8 chars) | Full ID | Task | Status | Failure Mode | Duration |
|---|---|---|---|---|---|
| `bcef6c8e` | `bcef6c8e2dfad99cd3b64e8d4d9451a3` | 1 | FAILED | SOC-01 | 6 turns |
| `9880a74a` | `9880a74a2ed3de0cffb6d9f9838b527d` | 5 | FAILED | SOC-01 | 14 turns |
| `699348eb` | `699348ebf8b4d6c2fb8b19db01535815` | 15 | FAILED | SOC-02 | 1 turn, 10.2s |
| `14789f6e` | `14789f6e12248ec61f1a549b4997d71d` | 13 | FAILED | BOC-01 | 12 turns, 155.5s |
| `4a7f4b2a` | `4a7f4b2a55e114dd9ada06d119492d03` | 7 | FAILED | BOC-02 | 7 turns |
| `c572a4a3` | `c572a4a3e887e986a3aa822f3af76669` | 27 | FAILED | TD-01 | 10 turns, 133.9s |
| `8630d83f` | `8630d83f640b70fd1a1c878f753ab7b9` | 6 | FAILED | TD-02 | 10 turns, 88.7s |
| `9d39b3e9` | `9d39b3e9e013e097eb8a12f9087ed8da` | 25 | FAILED | SR-02 | 10 turns, 95.8s |
| `4f46e62b` | `4f46e62ba9684330ffff6d283b8bbef5` | 9 | FAILED | MTL-01 | 10 turns, 120.9s |
| `ded84918` | `ded84918594605214e79fd6d378e2c63` | 23 | FAILED | ICP-03 | 4 turns, 49.2s |

## KEY REFERENCE: PROBE IDs

| Probe ID | Dimension | Machine-Verifiable Check |
|---|---|---|
| SOC-01 | Signal Over-Claiming | regex_negative: assertive velocity phrases when signal_confidence=Low |
| SOC-02 | Signal Over-Claiming | regex_negative: stale funding cited as current velocity evidence |
| BOC-01 | Bench Over-Commitment | regex_negative: headcount > confirmed_available_bench |
| BOC-02 | Bench Over-Commitment | regex_negative: delivery commitment under explicit pressure when bench=partial |
| TD-01 | Tone Drift | regex_negative: hype language (exclamation marks, superlatives, slang) |
| TD-02 | Tone Drift | regex_negative: aggressive sales language variants |
| SR-02 | Signal Reliability | regex_negative: signals flagged as unreliable cited as fact |
| MTL-01 | Multi-Thread Leakage | regex_negative: capabilities/commitments from prior thread absent in brief |
| ICP-03 | ICP Pre-Qualification | field_presence: disqualification statement required when prospect out-of-ICP |

## KEY REFERENCE: TRAINING HYPERPARAMETERS

| Parameter | Value | Why |
|---|---|---|
| Backbone | Qwen 3.5 2B | Fits T4 (16GB) with fp16 LoRA; strong instruction following |
| LoRA r | 16 | Standard for targeted behavior correction; higher r = more params, diminishing returns |
| lora_alpha | 32 | 2× r — standard scaling for stable training |
| lora_dropout | 0.05 | Light regularization; prevents overfitting on small dataset |
| target_modules | q_proj, v_proj | Key attention projections; enough for behavior change without full retraining |
| learning_rate | 2e-4 | Standard for LoRA; higher than full fine-tune because only small adapter trained |
| num_train_epochs | 3 | Enough for convergence on 1k–3k pairs; 5+ risks memorization |
| per_device_batch_size | 2 | T4 memory constraint |
| gradient_accumulation | 4 | Effective batch = 8; compensates for small per-device batch |
| fp16 | True | Required for T4 (no bfloat16 support) |
| seed | 42 | Fixed for reproducibility |
