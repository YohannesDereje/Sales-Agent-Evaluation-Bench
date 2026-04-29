# Synthesis Memo: A Survey on LLM-as-a-Judge
**Paper:** Gu et al., 2024–2025 (latest revision)
**Author:** Yohannes | **Date:** 2026-04-29

---

## What the Paper Argues

Gu et al. survey the use of LLMs as automated evaluators across tasks ranging from open-ended generation to structured reasoning. Their central claim is that frontier LLMs (GPT-4-class, Claude-class) are capable judges for most natural language evaluation tasks and that smaller or rule-based systems introduce systematic calibration errors. The paper recommends using high-capability models as judges, applying pointwise or pairwise scoring with explicit rubrics, and averaging across multiple judge passes to reduce variance.

Key operational recommendations: (1) use the strongest available model as the primary judge, (2) provide detailed rubrics with scoring anchors, (3) avoid positional bias in pairwise comparisons by randomizing order, and (4) treat LLM judge scores as proxies for human preference, not ground truth.

---

## Where I Disagree — and Why My Evidence Supports It

**For rubric dimensions that are structurally binary and checkable by pattern matching, a frontier LLM judge is strictly worse than a deterministic rule-based check.**

Gu et al. treat LLM judgment as uniformly superior to rule-based evaluation. This is true for open-ended dimensions like "tone quality" or "persuasiveness." It is false for dimensions like `contains_calendar_link`, `no_assertive_velocity_claim`, or `signal_referenced`.

The evidence from Week 10 makes this concrete. The SOC-01 failure is detectable by a regex scan: does the output contain phrases matching `rapidly scal|aggressive.*hir|significant.*growth` when `hiring_velocity_label == weak_hiring_velocity_signal`? The answer is deterministic. A frontier LLM judge asked the same question introduces three failure modes that the regex does not: (1) the judge may hallucinate a "pass" if the email sounds professional despite containing a banned phrase, (2) the judge adds latency and cost to every evaluation call, and (3) the judge's reasoning is not auditable in the way a regex match is.

In `scoring_evaluator.py`, I implement a hybrid design: `regex_negative` and `regex_positive` checks handle all structurally binary dimensions deterministically. LLM judge scoring is reserved for genuinely subjective dimensions (tone fidelity, grounding quality) where pattern matching cannot substitute for semantic judgment. This is a deliberate inversion of Gu et al.'s default recommendation.

Gu et al. do acknowledge rule-based evaluation in Section 3.1 as appropriate for "constrained generation tasks," but frame it as a special case. For domain-specific agent evaluation where most rubric dimensions are binary constraints (not open-ended quality), rule-based checks should be the default and LLM judges should be the fallback — not the reverse.

My inter-rater agreement result is the validating evidence: when I apply the deterministic evaluator to the 30-task labeled subset, agreement between round 1 and round 2 is high precisely because the rule-based dimensions produce the same answer every time. LLM judge variance on the same tasks would have been measurably higher and would have required the calibration procedure Gu et al. recommend — adding cost with no benefit on binary dimensions.

---

## What I Adopt From the Paper

- **Pointwise scoring with explicit rubrics:** Each dimension in `scoring_evaluator.py` has a documented description, check type, and weight — following the paper's rubric-anchoring recommendation.
- **Rotation to prevent preference leakage:** Per Gu et al.'s discussion of self-preference bias (and Li et al. 2025 directly), the model that generates a task never judges it. This is enforced in the rotation policy in `methodology.md`.
- **Spot-check calibration:** The eval-tier judge (Claude Sonnet 4.6) is used on a 50-task sample of the filtered dataset to verify that the rule-based judge thresholds are well-calibrated, following the paper's recommendation for calibration against a stronger reference.
