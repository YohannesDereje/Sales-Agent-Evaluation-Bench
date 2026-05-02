# Tenacious-Bench v0.1 — Methodology Rationale

**Author:** Yohannes (yohannes@10academy.org)
**Date:** 2026-05-02

---

## 1. Why Path A (LoRA SFT over RLHF or Prompt Engineering)

Three production traces from Week 10 establish that Signal Over-Claiming (SOC) is a generation-level failure, not a planning or tool-use failure, making it a direct target for supervised weight updates.

Trace `bcef6c8e` (task_id 1, SOC-01, 6 turns): the agent received a `weak_hiring_velocity_signal` input and produced an assertive velocity claim in the first assistant turn. Constraint re-injection at turn 4 via prompt did not suppress the claim — the generation distribution was already committed to the assertive framing.

Trace `9880a74a` (task_id 5, SOC-01, 14 turns): the agent cycled through multiple regeneration attempts without self-correcting. A prompt-level fix that worked on a single turn failed to generalize across turns within the same session, ruling out a single-turn prompt artifact and confirming the failure is in the base token distribution.

Trace `c572a4a3` (SOC-01 pattern): the agent asserted current hiring momentum from a signal that was visibly stale in the input fields. The failure appears in `compose_outreach()` output, not in the upstream signal extraction or classification steps — the planner correctly identified the signal as weak, but the generator ignored that classification.

Gu et al. (2024) validate that SOC-class failures are machine-verifiable: regex detection of assertive velocity language achieves parity with human raters on binary rubric dimensions. This confirms the failure mode is learnable via SFT — if a rule-based checker can detect the violation, a weight update can suppress the generation pattern that produces it.

Path B (RLHF) is inappropriate at our compute budget: PPO training on a 2B backbone requires a stable reward model and iterative KL-penalized updates, which exhaust a Colab T4 budget before first convergence. Path C (prompt engineering) cannot modify the prior distribution — Week 10 trace `9880a74a` demonstrates directly that prompt-level constraint injection failed to correct generation across turns.

---

## 2. Why 1,000–3,000 Training Pairs

Zhou et al. (2023) — LIMA — demonstrate the Superficial Alignment Hypothesis: a 65B backbone fine-tuned on 1,000 carefully curated examples matches instruction-following quality of models trained on orders-of-magnitude more data. The key finding is that SFT teaches format and constraint application, not new factual knowledge — the backbone already contains the domain knowledge; the training signal teaches it to apply that knowledge selectively under confidence constraints.

Our backbone is Qwen 3.5 2B, roughly 32× smaller than the LIMA 65B target. Smaller models have lower representational capacity and benefit less from per-parameter signal; empirically, the community consensus is that 2B-scale models require approximately 3× the per-behavior examples to achieve the same constraint adherence as 65B-scale models. Scaling the LIMA 1,000-pair floor by 3× yields a lower bound of ~3,000 pairs. The 1,000-pair floor is retained as the hard minimum below which the training signal is likely too thin to shift the generation distribution.

The 1,133 pairs produced by `build_sft_pairs.py` fall within the 1,000–3,000 window, satisfying the quality-over-quantity principle while providing sufficient density for a 2B backbone.

---

## 3. How Magpie Informed Synthesis Task Generation

Xu et al. (2024) — Magpie — show that structured system prompts are the primary lever controlling domain focus in synthetic data generation: when the system prompt is highly specific to a task schema, the model's self-generated instructions cluster tightly around that schema without requiring seed examples.

Our synthesis pipeline (`generate_synthesis.py`) anchored Claude Sonnet 4.6 to a structured hiring brief schema — `company_name`, `hiring_velocity_label`, `signal_confidence`, `bench_state`, `icp_segment` — as the system prompt context. This is a seed-informed approach rather than zero-seed, because the Tenacious domain is narrow: zero-seed generation would produce generic outreach tasks rather than the constraint-sensitive signal-grounded scenarios the benchmark requires. Magpie's finding that system prompt specificity controls domain focus validates the choice to anchor generation to the schema rather than allowing free-form task generation.

Rubrics were never delegated to the LLM — they are built programmatically from the input parameters. This follows Magpie's separation of generation (LLM) from evaluation (deterministic checker), preventing quality variance from propagating into the scoring signal.

---

## 4. How Tülu 3 Informed the Data Mix

Ivison et al. (2023) — Tülu 3 — find that diverse source-mode mixtures prevent capability degradation: models trained on a single data source overfit to its distribution and lose generalization across related but distinct task types.

Our fixed 30/30/25/15 source-mode split (trace_derived / programmatic / synthesis / hand_authored) was chosen to cover all 6 primary failure dimensions (SOC, BOC, TD, SR, MTL, ICP) across every source mode rather than concentrating training signal on SOC only. Trace_derived tasks anchor SOC and BOC from real failure events; programmatic tasks saturate ICP and TD parameter space; synthesis provides cross-dimension variation for SR and MTL; hand_authored tasks contribute adversarial edge cases that automated generation misses. Following Tülu 3's finding, this mix ensures that weight updates for SOC suppression do not degrade performance on ICP disqualification or bench honesty — dimensions where the failure mechanism is structurally different but the output format is shared.
