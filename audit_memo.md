# Audit Memo: The Benchmark Gap for Tenacious-Style B2B Sales Work

**Author:** Yohannes (yohannes@10academy.org)
**Date:** 2026-04-29
**Week 10 Probe Score:** 28/29 evaluated probes PASS (3 skipped)
**Week 10 τ²-Bench Retail Pass Rate:** ~65% (39/61 traces with non-empty trace_id)

---

## The Gap

τ²-Bench retail grades one thing: whether a task reached a terminal success state. Reward is binary — 1.0 or 0.0. Trace `df486b2885c79b34d69ea678e380598f` (task_id 0, 7 turns) scored reward=1.0. Trace `bcef6c8e2dfad99cd3b64e8d4d9451a3` (task_id 1, 6 turns) scored reward=0.0. The benchmark tells us the task completed or it did not. It does not tell us whether the output that caused completion was safe to send to a $240K ACV prospect.

This is precisely the gap that Tenacious-specific B2B sales work exposes. The Conversion Engine's critical failure mode is not task-completion failure — it is **output-quality failure at a specific generation step**: the agent asserts hiring velocity claims that are not supported by the signal it was given.

## What Week 10 Evidence Proves

Probe SOC-01 is the clearest demonstration. When `hiring_velocity_label` was set to `weak_hiring_velocity_signal`, the agent generated language asserting rapid team growth despite the flag. After two explicit regen attempts with the constraint injected into the prompt, the model still produced assertive language. This was the only probe that remained a genuine FAIL across all 29 evaluated probes. Neither τ²-Bench's completion metric nor any existing public benchmark would have flagged this, because the email technically completed the outreach task — it just over-claimed.

Probe SOC-02 and SOC-03 extend this: the agent conflates weak signals with high-confidence assertions in different surface forms. Probe TD-01 and TD-02 document tone drift when the company description included self-promotional language; the agent mirrored the prospect's register rather than maintaining Tenacious's grounded, direct style. Probe BOC-01 and BOC-02 show that when bench capacity is partially committed, the agent nonetheless offers full headcount to the prospect — a commitment it cannot honor. Probe SR-01 documents the agent treating 18-month-old funding data as current market signal.

Each of these is a generation-quality failure. Each produces an output that, on a task-completion metric, passes. None are detectable by τ²-Bench.

## The Trace Evidence

Trace `9880a74a2ed3de0cffb6d9f9838b527d` (task_id 5, 14 turns, FAILED) ran for 14 turns before termination — the extended duration is consistent with the agent attempting multiple regen paths after a constraint conflict, which matches the SOC failure pattern. Trace `8630d83f640b70fd1a1c878f753ab7b9` (task_id 6, 10 turns, FAILED) and trace `4a7f4b2a55e114dd9ada06d119492d03` (task_id 7, 7 turns, FAILED) both failed without runner errors, indicating the failure was in output quality evaluation, not execution. Compare with trace `170178dbc2ea769ecec011dc349a0338` (task_id 8, 10 turns, PASSED) — same turn count as task 6, opposite outcome, consistent with signal-grounding being the differentiating variable.

## What Tenacious-Bench Must Grade That τ²-Bench Cannot

1. **Claim proportionality**: Is every assertion in the output supported by the signal that was provided?
2. **Tone fidelity**: Does the output match Tenacious's defined style markers, independent of whether the task completed?
3. **Bench honesty**: Does the output offer only capacity that the bench summary confirms is available?
4. **Signal freshness**: Does the output treat stale data as current?

Probes TD-03, SR-01, BOC-01, BOC-02, and MTL-01 each expose a dimension of this quality space that τ²-Bench's binary reward collapses to zero signal. Tenacious-Bench is built to make each dimension independently measurable, machine-verifiable, and independently scorable.
