# Readings Reference — Tenacious-Bench v0.1

For each paper: the one key claim that matters for this project, why, and what decision it drives.

---

## Common Readings (All Paths)

### 1. Liu et al. (COLM 2024) — Synthetic Data Best Practices

**Key claim:** Synthetic data works when ground truth can be verified and quality control is applied. It fails when it contains hallucinations or covers only narrow scenarios.

**Connection to our project:** Our programmatic generation mode produces tasks with machine-verifiable ground truth (rule-based scorer, not LLM judge). Our `judge_filter.py` filters out low-quality outputs before they enter training. The diversity warning is why we generate across 10 failure dimensions rather than just producing more SOC examples.

**Decision it drives:** Use rule-based verification wherever possible. Filter synthetic data before use. Vary probe dimensions to avoid covering only one failure mode.

---

### 2. Gebru et al. (2021) + Pushkarna et al. (FAccT 2022) — Dataset Documentation

**Key claim:** Datasets must be documented *while being built*, not after. Documentation must cover motivation, provenance, transformations, and intended/unsuitable use cases. Pushkarna adds three documentation scopes: Telescopic (overview), Periscopic (technical detail), Microscopic (the human rationale behind decisions).

**Connection to our project:** This is why `datasheet.md` exists and why it follows Gebru's 7 sections plus Pushkarna's three scopes. The "concurrent creation" rule means the datasheet is written as we build, capturing decisions we would otherwise forget. The Microscopic scope is where we document *why* we chose specific threshold values (e.g., Jaccard < 0.60) rather than just *what* they are.

**Decision it drives:** Write `datasheet.md` alongside dataset generation. Document every threshold decision with a rationale, not just the value.

---

### 3. Chen et al. (EMNLP 2025) — Benchmarks and Data Contamination

**Key claim:** Static benchmarks decay when published on the internet because LLMs are trained on web scrapes. Detection requires n-gram overlap AND embedding similarity (n-gram alone misses paraphrased contamination). Protection strategies: seal the held-out partition, keep labels private, use rule-based synthesis for low collision rates.

**Connection to our project:** This justifies our 3-check contamination protocol: 8-gram overlap (zero tolerance), Jaccard similarity (< 0.60 threshold), and time-shift verification. Our programmatic generation mode has near-zero collision rate by design — each task is a unique combinatorial parameter sample. The gitignore rule sealing `tenacious_bench_v0.1/held_out/` comes directly from this paper's label-protection recommendation.

**Decision it drives:** Run all 3 contamination checks before finalizing the partition. Seal held-out labels. Never publish held-out tasks in plain text.

---

### 4. Gu et al. (2024–2025) — LLM-as-a-Judge Survey

**Key claim:** LLM judges suffer from self-preference bias — a model consistently rates its own outputs higher. The same model must never generate AND judge the same task. Rule-based evaluation is preferred when tasks have a single verifiable correct answer.

**Connection to our project:** Our scoring system uses 4 rule-based check types (regex_negative, regex_positive, length_check, field_presence) — not an LLM — because our tasks have machine-verifiable correct answers (e.g., "this output must NOT contain the phrase X"). The model rotation policy in `methodology.md` (different models for generation vs. evaluation) is a direct application of this finding.

**Decision it drives:** Keep the dev-phase judge rule-based. For the final spot-check, use a different model family from the one that generated the synthesis tasks (Claude generated → Qwen/DeepSeek judges, not Claude again).

---

## Path A Readings (SFT)

### 5. LIMA — Zhou et al. (NeurIPS 2023)

**Key claim (Superficial Alignment Hypothesis):** A large pretrained model already contains the knowledge it needs. SFT does not teach new knowledge — it teaches the model the *style and format* of compliant outputs. 1,000 high-quality examples outperform 52,000 mediocre ones. Doubling data from 2,000 to 32,000 examples produced almost no quality gain without adding diversity.

**Connection to our project:** Qwen 3.5 already knows what a professional outreach email looks like. The SOC-01 failure is not a knowledge gap — the model knows what "weak hiring signal" means. It is a format/calibration gap: the model has not learned to *constrain claim strength* to match signal confidence. 1,000–3,000 high-quality (hiring brief → compliant email) pairs is enough to recalibrate this behavior. This is why our training target is 1,000–3,000 pairs, not 50,000.

**Decision it drives:** Prioritize quality filtering over raw volume. Target 1,000–3,000 pairs. Each pair must represent a distinct probe dimension, not just more SOC examples.

---

### 6. Magpie — Xu et al. (2024)

**Key claim:** Aligned LLMs can generate their own training data by completing a structured pre-query template with no human seeds. A domain-specific system prompt steers generation to a narrow domain. This produces more diverse data than Self-Instruct because it samples from the model's full learned distribution, not from a small set of seed examples.

**Connection to our project:** Our synthesis mode (≈25% of the dataset) uses Claude Sonnet 4.6 with the Tenacious hiring brief format as the structured anchor prompt. This is the MAGPIE technique applied to a sales domain — we define the role and context in a system prompt, and the model generates realistic scenario variations. The quality filtering recommendations (embedding distance for dedup, reward-model-style scoring for clarity) directly inform our `judge_filter.py` design.

**Decision it drives:** Use a structured system prompt anchored to the hiring brief schema when generating synthesis tasks. Apply embedding-based dedup (Jaccard proxy in dev phase, cosine in v1.0) to remove near-duplicates after generation.

---

### 7. Tülu 3 — Ivison et al. (2024)

**Key claim:** Effective SFT mixing is iterative and benchmark-driven. Small amounts of domain-specific data (30k–35k examples in their scale) produce large, targeted skill gains. Diverse conversational data prevents degradation of general capabilities. Domain-specific and general data are largely additive — improving one does not hurt the other.

**Connection to our project:** Our 4-mode data mix (30% programmatic / 30% trace-derived / 25% synthesis / 15% hand-authored) mirrors Tülu 3's mixing philosophy. At our scale (1,000–3,000 pairs), the programmatic and trace-derived modes anchor the model to real failure patterns, while synthesis and hand-authored modes add coverage and adversarial hardness. Tülu 3's "unseen evaluation suite" strategy validates our sealed held-out partition — we evaluate on tasks the model has never seen, testing whether the *skill* transferred, not whether the model memorized specific examples.

**Decision it drives:** Maintain all 4 source modes in the training mix — do not collapse to a single source. Evaluate on the sealed held-out partition to measure true skill transfer, not memorization.

---

## Summary Table

| Paper | The one thing it justifies in our project |
|---|---|
| Liu et al. | Rule-based verification + quality filter before training |
| Gebru + Pushkarna | Write `datasheet.md` concurrently; document *why* for every threshold |
| Chen et al. | 3-check contamination protocol; seal + gitignore held-out |
| Gu et al. | Rule-based judge in dev phase; model rotation policy |
| LIMA | 1,000–3,000 pairs target; quality > quantity |
| Magpie | Structured system prompt anchor for synthesis mode; embedding dedup |
| Tülu 3 | 4-mode data mix; held-out = unseen skill test, not memorization test |
