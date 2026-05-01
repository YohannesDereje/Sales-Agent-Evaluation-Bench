# Synthesis Memo: Magpie — Alignment Data Synthesis from Scratch by Prompting Aligned LLMs
**Paper:** Xu et al., 2024
**Author:** Yohannes | **Date:** 2026-05-01

---

## What the Paper Argues

Xu et al. introduce Magpie: a technique where an aligned LLM generates its own instruction-following training data by completing a structured pre-query template with no human-authored seed examples. The model is prompted with only a system prompt and an empty user-turn template; it generates both the instruction and the response. A domain-specific system prompt steers generation toward a target domain. The key finding: Magpie produces more diverse data than Self-Instruct because it samples from the model's full learned distribution rather than from a small set of seed examples, which Self-Instruct tends to overfit.

The operational recommendation: use a structured system prompt anchored to the target domain, generate a large pool of (instruction, response) pairs, apply quality filtering, and use the result as SFT training data.

---

## Where I Disagree — and Why My Evidence Supports It

**Zero-seed generation is insufficient for our domain. We use seed-informed generation because Tenacious's failure modes require a specific input structure that zero-seed generation cannot reliably produce.**

Magpie's zero-seed approach works because the tasks it targets (general instruction following, reasoning, coding) are well-represented in the model's pretraining distribution. The model can generate diverse, on-distribution instructions for these domains because it has seen thousands of examples of them.

Tenacious's hiring brief format is not well-represented in any model's pretraining distribution. The specific combination of fields — `hiring_signal_brief`, `bench_summary`, `signal_confidence`, `hiring_velocity_label`, `prior_thread_context` — does not appear in web-scraped text. When I tested zero-seed generation in early prototyping (asking Claude to generate "a B2B sales outreach task"), the outputs were plausible-sounding but off-distribution: they omitted the `signal_confidence` field (the key variable for SOC), used vague prospect descriptions, and produced scoring rubrics that were not machine-verifiable.

My synthesis generation uses **seed-informed generation**: a structured system prompt that includes the Tenacious brief schema, an example of a well-formed input, and the specific failure dimension being targeted. This is still Magpie's core technique — an aligned LLM generating its own training data from a template — but with a richer template that includes the domain schema as a seed. The tradeoff is slightly less diversity (bounded by the schema) in exchange for on-distribution tasks that actually test the failure modes we need to measure.

Magpie's own finding supports this: system prompt specificity directly controls domain focus. Our structured brief template is a maximally specific system prompt. The diversity Magpie achieves through zero-seed generation we achieve through the combinatorial programmatic mode — the two modes are complementary, not redundant.

---

## What I Adopt From the Paper

- **Aligned LLM as data generator:** Claude Sonnet 4.6 generates synthesis task seeds — applying Magpie's finding that aligned models produce higher-quality instruction data than unaligned models.
- **Quality filtering after generation:** `judge_filter.py` applies the same quality-filtering logic Magpie recommends before any generated task enters the dataset.
- **Embedding-based deduplication:** Magpie recommends cosine dedup to remove near-duplicate generated examples; we implement Jaccard dedup as the dev-phase proxy for the same purpose.
- **Model rotation:** Magpie's multi-model pipeline (different models for different generation stages) is reflected in our routing: Claude generates seeds, a cheap tier generates variations, the rule-based scorer judges all of them.
