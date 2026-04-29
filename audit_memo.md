# Audit Memo: The Benchmark Gap for Tenacious-Style B2B Sales Work

**Author:** Yohannes (yohannes@10academy.org)
**Date:** 2026-04-29
**Week 10 Probe Score:** 28/29 evaluated probes PASS (3 skipped)
**Week 10 τ²-Bench Retail Pass Rate:** ~65% (39/61 traces with non-empty trace_id)

---

## The Gap

τ²-Bench retail grades one thing: whether a task reached a terminal success state. Reward is binary — 1.0 or 0.0. Trace `df486b2885c79b34d69ea678e380598f` (task_id 0, 7 turns) scored reward=1.0. Trace `bcef6c8e2dfad99cd3b64e8d4d9451a3` (task_id 1, 6 turns) scored reward=0.0. The benchmark tells us the task completed or it did not. It does not tell us whether the output was safe to send to a $240K ACV prospect.

The Conversion Engine's critical failure mode is not task-completion failure — it is **output-quality failure at a specific generation step**. Four distinct failure dimensions are evidenced in Week 10 traces below; none are detectable by τ²-Bench's binary reward.

---

## Gap Evidence — Annotated Traces

Each gap is anchored to a distinct trace and probe reference from `week_10_artifacts/trace_log.jsonl`.

### Gap 1 — Signal Over-Claiming (SOC-01)

When `hiring_velocity_label` was `weak_hiring_velocity_signal`, the agent produced assertive hiring-velocity language after two prompt-level regen attempts with the constraint injected. This was the only probe that remained a genuine FAIL across all 29 evaluated probes.

- **`bcef6c8e2dfad99cd3b64e8d4d9451a3`** (task_id 1, probe SOC-01, 6 turns, FAILED): output-quality violation caught post-hoc; task flow completed, but output contained an unsupported velocity claim. τ²-Bench assigned reward=0.0 without identifying which generation step failed.
- **`9880a74a2ed3de0cffb6d9f9838b527d`** (task_id 5, probe SOC-01, 14 turns, FAILED): 14-turn run is the behavioral signature of the model cycling through regen attempts after a constraint conflict and failing to self-correct via prompt re-injection.

### Gap 2 — Bench Over-Commitment (BOC-02)

When bench capacity was partially committed, the agent offered full headcount to the prospect — a commitment it cannot honour.

- **`4a7f4b2a55e114dd9ada06d119492d03`** (task_id 7, probe BOC-02, 7 turns, FAILED): USER_STOP termination, no runner error. The failure is in output content: the agent offered headcount inconsistent with the bench summary in the input. τ²-Bench has no mechanism to compare offered headcount against bench availability; it scored this trace on completion state only.

### Gap 3 — Tone Drift (TD-02)

When the prospect description contained self-promotional language, the agent mirrored the prospect's register instead of maintaining Tenacious's grounded, direct style.

- **`8630d83f640b70fd1a1c878f753ab7b9`** (task_id 6, probe TD-02, 10 turns, FAILED): USER_STOP termination, 88.7 s. The trace captures adoption of hype-mirroring language that violates the Direct, Grounded, and Professional Tenacious tone markers. A binary completion metric cannot distinguish a tone-compliant email from a hype-mirrored one.

### Gap 4 — Signal Reliability (SR-02)

When contradictory signals were present, the agent treated the older positive signal as current market evidence and omitted the contradicting indicator from its output.

- **`9d39b3e9e013e097eb8a12f9087ed8da`** (task_id 25, probe SR-02, 10 turns, FAILED): USER_STOP termination, 95.8 s. Output asserted current hiring intent from a signal the input brief explicitly flagged as unreliable. Turn count and duration are directly comparable to the TD-02 trace above (10 turns / 88.7 s), confirming this is a generation-quality failure rather than an infrastructure or turn-limit issue.

---

## What Tenacious-Bench Must Grade That τ²-Bench Cannot

1. **Claim proportionality**: Is every velocity assertion supported by the provided signal?
2. **Tone fidelity**: Does the output match Tenacious's defined style markers regardless of task completion?
3. **Bench honesty**: Does the output offer only capacity the bench summary confirms is available?
4. **Signal freshness**: Does the output treat stale or contradicted data as current?

Probes SOC-01 (trace `bcef6c8e`), BOC-02 (trace `4a7f4b2a`), TD-02 (trace `8630d83f`), and SR-02 (trace `9d39b3e9`) — each anchored to a distinct failing trace above — expose four independent dimensions of output quality that τ²-Bench's binary reward collapses to zero signal. Tenacious-Bench is built to make each dimension independently measurable, machine-verifiable, and independently scorable.
