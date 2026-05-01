# Todo Descriptions — What We Are Doing and Why

This file is written for you (Yohannes) to understand what is happening at each step of the project. Read this before we start each phase so you know exactly what we are building and why.

---

## Phase 0 — Build Complete Mental Model

**What this phase is about:**
Before we write a single file, you need to understand the project deeply enough to guide the work and answer questions about it. This phase has no code and no files — it is purely about understanding.

---

**P0-01: Understand what changed from Week 10 to Week 11**

In Week 10, you built a sales AI agent for Tenacious. That agent finds companies that might need engineers, reads their hiring signals, and writes outreach emails. There was an existing benchmark called τ²-Bench that tested whether the agent completed its tasks. The problem: τ²-Bench only checks if a task finished (yes/no). It cannot check if the email was written correctly.

In Week 11, we build a better benchmark — one that actually grades the quality of the email, not just whether one got sent.

---

**P0-02: Understand the six ways the agent can fail**

The agent can make 6 types of mistakes that τ²-Bench cannot see:
1. **SOC (Signal Over-Claiming)** — says "they're hiring aggressively" when the data shows weak signals
2. **BOC (Bench Over-Commitment)** — promises more engineers than Tenacious actually has available
3. **TD (Tone Drift)** — copies the prospect's hype language instead of staying professional
4. **SR (Signal Reliability)** — uses old or unreliable data as if it were current fact
5. **MTL (Multi-Thread Leakage)** — "remembers" things from a previous conversation that were never real
6. **ICP (ICP Pre-Qualification Failure)** — writes a full email to a company that Tenacious should never contact

We have real examples of each failure from Week 10 (specific trace IDs as evidence).

---

**P0-03: Understand the Tenacious Style Guide**

The style guide is the rulebook for how Tenacious emails must sound. It defines:
- **5 tone markers**: Direct, Grounded, Honest, Professional, Non-condescending
- **Formatting rules**: max 120 words for cold outreach, one ask per email, no emojis
- **Banned phrases**: "world-class", "top talent", "skyrocket", "quick chat", etc.
- **12 good examples** and **12 bad examples** — each with an explanation of why it passes or fails

This style guide is what our benchmark is testing against. When the agent writes an email, we check it against these rules automatically.

---

**P0-04: Understand what a benchmark "task" looks like**

A single benchmark task is like a test question with an answer key. It has:
- **Input**: a hiring brief (what we know about the prospect), bench state (what engineers are available), and context
- **Candidate output**: the email the AI agent wrote
- **Scoring rubric**: a checklist of things to verify automatically (does the email contain banned phrases? is it under 120 words? does it reference the hiring signal?)
- **Score**: a number from 0.0 to 1.0. If ≥ 0.70, it passes.

Everything is checked by a script — no human reads the emails during grading.

---

**P0-05: Understand Path A (what we are training)**

Path A means: we fine-tune a small language model to fix the SOC-01 failure mode.

"Fine-tuning" means taking a model that already knows how to write (Qwen 3.5, a small open-source model) and teaching it one specific new skill: tie claim strength to signal strength.

We use a technique called LoRA, which is like adding a small "correction layer" to the model without rewriting the whole model. It is fast, cheap (free on Google Colab), and precise.

The result is a file called a "LoRA adapter" — when plugged into the base model, it makes the model write compliant emails instead of over-claiming ones.

---

**P0-06: Understand why we read each paper**

Each of the 7 papers we read justifies one specific decision in this project:
- **Liu et al.** → why we use 4 different methods to generate our test cases
- **Gebru + Pushkarna** → why we write a datasheet with specific sections
- **Chen et al.** → why we run 3 contamination checks before finalizing the dataset
- **Gu et al.** → why we never use the same AI model to write AND grade the same test case
- **LIMA** → why 1,000–3,000 training examples is enough (quality > quantity)
- **Magpie** → how we generate synthetic training examples using a structured prompt
- **Tülu 3** → why we mix 4 different types of training data

---

**P0-07: Understand the complete project story**

Here is the full story in one paragraph:

The Tenacious sales AI agent fails in specific ways that no existing benchmark can measure. We prove the gap exists using real traces from Week 10 (the audit). We build a dataset of 200–335 test cases that specifically test for those failure modes (the benchmark). We use that dataset to train a small LoRA adapter that fixes the most critical failure (SOC-01 — the model over-claims when signals are weak). We run experiments to measure whether the fix worked. Then we publish everything: the dataset, the trained adapter, a blog post, and a memo to the CEO.

---

## Phase 1 — Environment Setup and Preflight Readiness

**What this phase is about:**
Before we can build or train anything, we need accounts and tools set up. The project uses specific platforms. This phase makes sure everything works before the deadline pressure starts.

---

**P1-01: HuggingFace account and token**

HuggingFace is where we will publish our dataset and trained model at the end of the project. Think of it like GitHub but specifically for AI datasets and models. We need a "write token" so our scripts can upload files to HuggingFace automatically.

---

**P1-02: OpenRouter account and key**

OpenRouter is a service that lets you call many different AI models through one API. We use it to generate synthetic test cases (using cheap models like DeepSeek) and to judge quality. We need an API key to make these calls, and we need to track every dollar we spend — the total budget is $10.

---

**P1-03: Google Colab + T4 GPU test**

Google Colab is a free cloud computing platform. The T4 GPU is the free tier — it has enough memory (16GB) to run our LoRA training. We need to confirm it works before Day 5 when we actually train. "Kernel compile takes 6-10 minutes on the first run" — this is normal, don't panic.

---

**P1-04: RunPod (optional backup)**

If Colab disconnects us during training (it sometimes does after a few hours), RunPod is a paid fallback (~$0.34/hour). Only needed if Colab fails. Setting it up early means we don't waste time on Day 5 figuring it out in a crisis.

---

**P1-05: Local Python environment**

We need Python and several libraries installed on your local machine for running scripts locally (dataset generation, contamination checks, etc.). This is a one-time setup.

---

**P1-06: Unsloth starter notebook**

Unsloth is the library we use for fast LoRA training. Before we train for real, we need to confirm it works end-to-end with a tiny dummy run. This catches any environment problems early. The test pushes a dummy adapter to HuggingFace — so this also confirms P1-01 worked.

---

**P1-07: Inventory Week 10 artifacts**

The Week 10 outputs (trace logs, probe library, failure taxonomy) are the seed for everything we build. If they're missing or corrupted, we need to know now — not on Day 2.

---

**P1-08: Schema starter review**

The project provides a starting schema (a template for what a benchmark task looks like). We need to confirm we can read it and validate a sample task against it. This is like checking that the blueprint makes sense before we start building.

---

**P1-09: Cost tracking**

The project document says every API and compute charge must be logged. This is itself graded. Start logging from Day 0.

---

## Phase 2 — Literature Synthesis Memos

**What this phase is about:**
Each of the 7 papers we read requires a one-page memo committed to the repository. The memo is NOT a summary. It must include one thing where you DISAGREE with the paper and explain why using your own Week 10 evidence. This is what gets graded.

---

**P2-01 to P2-07: One memo per paper**

For each paper, the memo does three things:
1. States the paper's main claim in one sentence
2. Connects it to a specific decision in this project
3. Names one place where the paper's recommendation doesn't fit our situation — and explains why using our evidence

For example: LIMA says 1,000 training pairs is enough on a 65B model. Our model is 2B. We argue we need 3,000 pairs to compensate. That disagreement, backed by our reasoning, is what gets us credit.

These memos are committed to the `synthesis_memos/` folder in the repo.

---

**P2-08: Commit all memos**

After writing all 7 memos, commit them to GitHub. The interim submission deadline requires at least 2 of the common memos to be committed. All 7 are required for the final submission.

---

## Phase 3 — Act I: Audit and Schema Design

**What this phase is about:**
This is Day 1 work. We write the audit memo (proving the benchmark gap exists) and design the benchmark schema (what each test case looks like). The key constraint: everything must be machine-gradable — a script must be able to score any email without a human reading it.

---

**P3-01: The audit memo**

A 600-word document that answers: "What does τ²-Bench fail to measure, and here is the proof from Week 10." It must cite at least 8 probe IDs and 5 real trace IDs. We already have this written from the interim submission, but we are rewriting it with full understanding this time.

---

**P3-02: The schema**

The schema is the blueprint for every test case in our benchmark. It defines exactly what fields a task has. The most important part is the `scoring_rubric` — the list of checks that a script runs on any email to score it. Everything in the rubric must be something a computer can check automatically (pattern matching, word counting, field presence).

---

**P3-03: Three example tasks**

We write three concrete example tasks to prove the schema works. One for each difficulty level. These are not generated — we write them by hand to validate the schema makes sense.

---

**P3-04: The scoring evaluator script**

A Python script that takes any task + any email output and returns a score from 0.0 to 1.0. This script is one of the most important deliverables of the whole project — every benchmark score in the final submission comes from running this script. It must be deterministic: same input always gives same output.

---

**P3-05: Methodology document (first draft)**

A document that explains our choices: why Path A, why this partitioning strategy, why these contamination thresholds. This document grows throughout the project — we start it here and keep adding to it.

---

## Phase 4 — Act II: Dataset Authoring

**What this phase is about:**
This is Days 2-3 work. We generate 200-335 test cases using 4 different methods, filter them for quality, check for contamination, split them into 3 partitions (train/dev/held-out), and document everything.

---

**P4-01: Trace-derived tasks**

We take the real outputs from Week 10 (stored in `trace_log.jsonl`) and restructure them into benchmark tasks. These are the highest-quality tasks because they reflect how the real agent actually behaves. No AI needed — we just reformat what already exists.

---

**P4-02: Programmatic tasks**

We write a script that generates test cases by filling in templates with different parameter combinations. For example: company_size=50, signal_confidence=Low, requested_headcount=10, bench_state=partial. The script automatically creates a scoring rubric based on the parameters. One template becomes 20 different test cases.

---

**P4-03: Synthesis tasks**

We use AI models (through OpenRouter) to generate harder test cases. Claude writes the difficult seeds (unusual scenarios). A cheaper model generates variations. We keep all spending under $3 for this entire step.

---

**P4-04: Hand-authored adversarial tasks**

The 30 hardest tasks, written by us manually. These are specifically designed to defeat the agent on tricky edge cases that the automatic generation would miss. These carry the most grading weight for "originality."

---

**P4-05: Quality filter script**

Every generated task goes through a filter before entering the dataset. The filter checks 3 things: Does the task make sense as an input? Can the ground truth be verified automatically? Is the scoring rubric clear? Tasks that score below 3/5 on any dimension are removed.

---

**P4-06: Run the pipeline**

Run all the generation scripts, combine the outputs, run the quality filter. Confirm at least 200 tasks remain after filtering.

---

**P4-07: Partition and contamination script**

This script splits the dataset into three groups: 50% for training the LoRA adapter, 30% as a public development set, 20% as a sealed held-out set (used only for final evaluation). It also runs 3 contamination checks to make sure no test cases leaked into training.

---

**P4-08: Run the partition script**

Run it, verify it passes all 3 contamination checks, and confirm the held-out folder is sealed (gitignored — it never goes to GitHub in plain text).

---

**P4-09: Inter-rater agreement**

We manually grade 30 tasks, wait a day, then grade the same 30 tasks again without looking at our first answers. If we agree with ourselves ≥ 80% of the time on every dimension, the rubric is clear enough. If not, we revise the rubric until it is.

This step proves the benchmark is reliable — that it gives the same answer every time for the same email.

---

**P4-10: The datasheet**

A 3-5 page document that formally describes our dataset following two academic frameworks (Gebru's 7 sections + Pushkarna's three-scope structure). This is what makes a JSON file into a legitimate benchmark that the research community can trust and cite.

---

**P4-11: Update methodology document**

Add the real results from the contamination checks and the inter-rater agreement test to the methodology document.

---

**P4-12: Generation scripts README**

A document inside the `generation_scripts/` folder explaining what each script does, how to run the pipeline, and which AI models were used for which steps.

---

**[INTERIM SUBMISSION CHECKPOINT]**

At this point, the Wednesday submission is due. Everything up to Phase 4 must be committed to GitHub, plus a PDF report. After submitting, we continue to Phase 5.

---

## Phase 5 — Act III: Method Selection and Training Data Preparation

**What this phase is about:**
Day 4 work. We take the training partition of our benchmark and reformat it specifically for teaching the LoRA adapter. The training data must be in a specific format, and only the highest-quality pairs get used.

---

**P5-01: Convert to chat-template format**

The training data needs to be in a format the LoRA training library understands. Each example becomes a "conversation" with three turns: (1) a system prompt defining the Tenacious voice, (2) a user turn with the hiring brief as an instruction, (3) an assistant turn with a compliant email as the response. This is the input-output pair the model learns from.

---

**P5-02: Filter by quality score**

We only train on examples where the "correct" email actually passes our scoring rubric (score ≥ 0.70). If the training example itself is flawed, the model learns the wrong behavior. Target: 1,000–3,000 high-quality pairs after filtering.

---

**P5-03: Second contamination check**

Before training, we verify again that no training example overlaps with the held-out test set. This is important because we want to measure real improvement, not memorization.

---

**P5-04: Methodology rationale document**

A one-page document that explains our training approach using the papers we read. This is a final-submission graded deliverable — it must cite LIMA, Magpie, Tülu 3, and 3 Week 10 trace IDs.

---

**P5-05 and P5-06: Verification and composition check**

Load the training data with the HuggingFace library to confirm it's formatted correctly. Count how many examples we have per failure dimension — we want coverage across multiple failure types, not just SOC.

---

## Phase 6 — Act IV: Train, Ablate, Measure

**What this phase is about:**
Days 5-6 work. The actual training run, followed by rigorous experiments to measure whether training helped.

---

**P6-01: Configure the training**

Set the specific hyperparameters (learning rate, number of training epochs, LoRA settings). We use settings recommended by the Unsloth documentation for Qwen 3.5 on T4.

---

**P6-02: Run the training**

One training run, 30-90 minutes. If it's not improving after 30 minutes, the data is the problem — stop and fix the data, don't add more compute.

---

**P6-03: Push the adapter to HuggingFace**

After training, push the LoRA adapter (not the full model — just the small correction file) to HuggingFace under your account.

---

**P6-04: Delta A — did training help?**

Run the trained model on the held-out test set. Compare its score to the Week 10 baseline. Compute a confidence interval. If the trained model scores higher with p < 0.05, training worked.

---

**P6-05: Delta B — did we actually need training?**

Run the same test with the base model (no LoRA) but with a carefully written system prompt that explains the SOC rule. If the prompt alone achieves the same result as training, our training run was unnecessary — and we report that honestly. Many projects fail Delta B. That is a legitimate, publishable finding.

---

**P6-06: Cost-Pareto**

Measure how much each approach costs per email (time + money). A 3% improvement that doubles cost is worse than a 2% improvement at the same cost.

---

**P6-07 and P6-08: Save all evidence**

Every scored trace, every number, every log — saved to files. This is the evidence behind every claim in the memo and the blog post.

---

## Phase 7 — Act V: Publish and Engage

**What this phase is about:**
Day 7 work. Everything ships publicly. Your name goes on it permanently.

---

**P7-01: Pre-publication checklist**

Before anything goes public, we run through 8 required checks: datasheet complete, license correct, README runnable, seeds fixed, held-out sealed, contamination report committed, model card complete, attribution clean. All 8 must pass.

---

**P7-02: Publish the dataset to HuggingFace**

The benchmark dataset (train + dev partitions only — NOT the held-out) is published publicly. Anyone in the world can download it and test their own sales AI agent against it.

---

**P7-03: Write the blog post**

A 1,200–2,000 word technical blog post published under your name. It tells the story of the project: what was wrong with existing benchmarks, how you found the gaps, how you built the dataset, what the training experiment showed, and what the honest results were.

---

**P7-04: Community engagement**

Post a GitHub issue on the τ²-Bench repository explaining the gap you found and linking your dataset. This is how you contribute your findings back to the AI evaluation community.

---

**P7-05: The CEO memo**

A 2-page PDF written to the Tenacious CEO and CFO. Page 1: what we built, did it work, should they deploy it. Page 2: what we still don't know, what could go wrong, and when to turn it off.

---

**P7-06: Evidence graph**

A JSON file that maps every number in the memo to its source. If the memo says "lift of 8.3 percentage points," the evidence graph shows exactly which file and which rows produced that number. This makes the work reproducible and prevents anyone from challenging claims without a counter-argument.

---

**P7-07: Demo video**

A 6-minute screen recording showing the dataset live on HuggingFace, one email being scored by the evaluator, one ablation result traced back to its source, the blog post, and the community issue.

---

**P7-08: Final submission**

All URLs gathered into one place and submitted. Everything must be publicly accessible with no login required.
