# Synthesis Memo: Benchmarks and Data Contamination in the Era of Large Language Models
**Paper:** Chen et al., EMNLP 2025
**Author:** Yohannes | **Date:** 2026-05-01

---

## What the Paper Argues

Chen et al. document how static benchmarks decay once published online because LLMs are subsequently trained on web scrapes that include the benchmark's test questions. Their central claim is that contamination detection requires **two complementary checks**: n-gram overlap (which catches verbatim memorization) and embedding cosine similarity (which catches paraphrased contamination that n-gram matching misses). N-gram overlap alone produces false negatives when a model has seen a semantically equivalent but lexically different version of a test question.

The paper's protection recommendations: (1) seal the held-out partition before any model training begins, (2) keep held-out labels private to prevent leakage through label-guessing, (3) use programmatic synthesis for benchmark tasks because combinatorial parameter sampling produces low n-gram collision rates by design, and (4) apply both n-gram and embedding similarity checks before finalizing any partition.

---

## Where I Disagree — and Why My Evidence Supports It

**Chen et al.'s recommendation for embedding cosine similarity at threshold < 0.85 is infeasible at our budget and unnecessary given our generation strategy.**

Chen et al. recommend running embedding cosine similarity checks across the full held-out × train cross-product. For a dataset of 335 tasks, this requires embedding all tasks (an API call per task) and computing ~22,000 pairwise similarities. At OpenRouter embedding model pricing (~$0.02 per 1,000 tokens), this adds approximately $0.50–1.00 per contamination check run — a meaningful fraction of our $10 total budget, and one we would need to repeat every time the dataset changes.

More importantly, our programmatic generation mode makes this check largely redundant. Each programmatic task is a unique combination of 7 parameters (company_size × hiring_velocity_label × signal_confidence × requested_headcount × bench_state × ai_maturity_score × seed_dimension). Two tasks that share the same parameter combination are deduplicated by `judge_filter.py` before partitioning. Two tasks with different parameter combinations produce structurally distinct `hiring_signal_brief` fields — the probability of high embedding similarity between them is near zero by construction.

My design decision: use **Jaccard similarity < 0.60** as the dev-phase proxy for embedding cosine similarity. Jaccard on tokenized input fields catches cases where the same hiring brief language appears in both train and held-out — the contamination scenario we actually care about. Full embedding cosine checking is planned for v1.0 when the dataset is larger and the budget is less constrained.

The 8-gram overlap check (zero tolerance) remains in place as the primary guard against verbatim contamination, per Chen et al.'s recommendation. The time-shift check (all signal references use the documented 2026-04 window) addresses the temporal contamination vector Chen et al. identify for benchmarks that rely on real-world events.

---

## What I Adopt From the Paper

- **3-check contamination protocol:** 8-gram overlap (zero tolerance), Jaccard similarity (< 0.60 threshold), and time-shift verification (2026-04 window) — directly from Chen et al.'s multi-check recommendation.
- **Held-out sealed before training:** `tenacious_bench_v0.1/held_out/` is gitignored and never committed in plain text, implementing Chen et al.'s label-protection recommendation.
- **Programmatic generation for low collision rate:** The combinatorial expansion in `generate_programmatic.py` implements Chen et al.'s finding that parameter-sampled synthesis has near-zero collision rates with existing training data.
- **Contamination results documented:** `contamination_check.json` records results for all 3 checks with flagged pairs listed, enabling audit of the contamination protocol.
