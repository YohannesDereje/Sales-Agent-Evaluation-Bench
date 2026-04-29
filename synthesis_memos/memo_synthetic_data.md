# Synthesis Memo: Best Practices and Lessons Learned on Synthetic Data for Language Models
**Paper:** Liu et al., COLM 2024
**Author:** Yohannes | **Date:** 2026-04-29

---

## What the Paper Argues

Liu et al. survey the landscape of synthetic data generation for LLM training and evaluation. Their central claim is that synthetic data quality depends on three pillars: **source diversity** (seeding from varied real-world sources to prevent distributional collapse), **verification** (filtering generated data through automated or model-based quality checks), and **task alignment** (ensuring synthetic tasks match the target deployment distribution). The paper recommends broad seed diversity as a safeguard against the model learning spurious surface patterns from a narrow corpus.

The operational recommendations most relevant to Tenacious-Bench are: (1) use multiple LLM families for generation to prevent single-model bias, (2) apply quality filters before any synthetic data enters training or evaluation, and (3) document provenance for every generated example.

---

## Where I Disagree — and Why My Evidence Supports It

**The paper's recommendation for broad source diversity is over-specified for narrow-domain benchmarks.**

Liu et al. argue that seeding from diverse sources is a general principle that prevents distributional collapse. This is sound advice for general-purpose alignment datasets. However, for Tenacious-Bench — a benchmark designed to measure one agent's behavior on one workflow — broad diversity is actively counterproductive.

The evidence from Week 10 is direct: the agent's failure mode (SOC-01) is triggered by a specific combination of inputs: `weak_hiring_velocity_signal` + a task instruction to write outreach. This failure does not appear in diverse general-domain seeds. It only appears when the seed corpus is drawn from Tenacious's actual hiring-signal brief format. A broad-diversity approach would drown this signal in irrelevant variation and produce a benchmark that measures general outreach quality rather than the specific claim-proportionality failure we need to measure.

My programmatic generation strategy inverts Liu et al.'s recommendation deliberately: I use a **narrow, domain-specific seed corpus** (8 probes from the Tenacious probe library) and achieve coverage through **combinatorial parameter expansion** (velocity label × company size × bench state × signal confidence). This produces 90+ tasks that all stress the same failure dimension at different input configurations — which is what a targeted evaluation benchmark requires.

Liu et al. acknowledge this tension in Section 4.2 when discussing "task-specific synthetic data," but treat it as a special case rather than the dominant regime for domain-specific agents. For production FDE work where the target workflow is known and narrow, focused seeding outperforms diverse seeding. The Week 10 probe library is the evidence: 28 of 29 probes were authored with narrow, failure-mode-specific seeds and successfully exposed the agent's behavior. A diverse random seed corpus would not have produced SOC-01.

---

## What I Adopt From the Paper

- **Multi-LLM generation routing:** I follow the paper's recommendation to use different model families for generation and judgment, documented in the model rotation policy in `methodology.md`.
- **Provenance tracking:** Every task records `source_mode`, `seed_probe`, and `created_by` in its metadata field, satisfying the paper's documentation standard.
- **Quality filtering before inclusion:** The `judge_filter.py` pipeline applies pointwise scoring on three dimensions before any task enters the dataset.
