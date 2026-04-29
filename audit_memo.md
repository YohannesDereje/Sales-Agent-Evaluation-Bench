# Audit Memo: The Benchmark Gap for Tenacious-Style B2B Sales Work

**Author:** Yohannes (yohannes@10academy.org)
**Date:** 2026-04-29
**Week 10 Probe Score:** 28/29 evaluated probes PASS (3 skipped)
**Week 10 τ²-Bench Retail Pass Rate:** ~65% (39/61 traces with non-empty trace_id)

---

## The Gap

τ²-Bench retail assigns reward=1.0 or reward=0.0. Trace `df486b2885c79b34d69ea678e380598f` (task_id 0, 7 turns) passed; trace `bcef6c8e2dfad99cd3b64e8d4d9451a3` (task_id 1, 6 turns) failed. Both completed their task flow. The benchmark cannot identify which generation step produced a non-compliant output, what was incorrectly asserted, or whether sending an email was the right action at all.

Six output-quality failure modes, documented across nine probes and eight failing traces, are invisible to this binary reward.

---

## Gap Evidence

### Gap 1 — Signal Over-Claiming (SOC-01, SOC-02)

- `bcef6c8e2dfad99cd3b64e8d4d9451a3` (task_id 1, **SOC-01**, 6 turns, FAILED): assertive velocity claim produced despite `weak_hiring_velocity_signal`; constraint re-injection failed to correct output.
- `9880a74a2ed3de0cffb6d9f9838b527d` (task_id 5, **SOC-01**, 14 turns, FAILED): the model cycled through regen attempts without self-correcting the over-assertion, confirming a generation-level failure not a prompt-injection gap.
- `699348ebf8b4d6c2fb8b19db01535815` (task_id 15, **SOC-02**, 1 turn, 10.2 s, FAILED): single-shot failure from a stale 14-month-old funding event; the agent never paused to verify signal age before asserting velocity.

### Gap 2 — Bench Over-Commitment (BOC-01, BOC-02)

- `14789f6e12248ec61f1a549b4997d71d` (task_id 13, **BOC-01**, 12 turns, 155.5 s, FAILED): offered engineers exceeding confirmed bench availability despite a partially-committed bench state.
- `4a7f4b2a55e114dd9ada06d119492d03` (task_id 7, **BOC-02**, 7 turns, FAILED): over-committed under explicit prospect pressure for faster delivery. τ²-Bench has no field to compare offered headcount against bench state.

### Gap 3 — Tone Drift (TD-01, TD-02)

- `c572a4a3e887e986a3aa822f3af76669` (task_id 27, **TD-01**, 10 turns, 133.9 s, FAILED): mirrored the prospect's hype-laden register, violating the Direct / Grounded / Professional Tenacious tone markers.
- `8630d83f640b70fd1a1c878f753ab7b9` (task_id 6, **TD-02**, 10 turns, 88.7 s, FAILED): adopted aggressive sales language in a second tonal trigger variant, confirming drift occurs across distinct trigger types.

### Gap 4 — Signal Reliability (SR-02)

- `9d39b3e9e013e097eb8a12f9087ed8da` (task_id 25, **SR-02**, 10 turns, 95.8 s, FAILED): asserted current hiring intent from a signal the input brief explicitly flagged as unreliable. A completion metric assigns no penalty for misusing stale evidence.

### Gap 5 — Multi-Thread State Leakage (MTL-01)

**Trajectory-level failure.** Across a multi-turn exchange, the agent imported fabricated commitments from a prior conversation thread into a fresh output — output quality degraded as cross-thread context accumulated. τ²-Bench evaluates only whether a task reached a terminal state; it cannot detect mid-trajectory contamination from a prior thread.

- `4f46e62ba9684330ffff6d283b8bbef5` (task_id 9, **MTL-01**, 10 turns, 120.9 s, FAILED): asserted AI tooling integrations and SLA guarantees absent from the hiring brief, sourced from pressure introduced in the prior thread context.

### Gap 6 — ICP Pre-Qualification Failure (ICP-03)

**Qualification-level failure.** The agent composed and sent a full outreach email to a prospect outside Tenacious's ICP without disqualifying the opportunity first. Sending *any* email was the wrong action — yet τ²-Bench awards completion credit regardless of whether the prospect should have been contacted at all.

- `ded84918594605214e79fd6d378e2c63` (task_id 23, **ICP-03**, 4 turns, 49.2 s, FAILED): prospect was a non-engineering function outside Tenacious's staffing vertical. No benchmark that scores "email sent" can detect "email should not have been sent."

---

## What Tenacious-Bench Must Grade That τ²-Bench Cannot

1. **Claim proportionality** (SOC-01, SOC-02): velocity assertions bounded by signal confidence.
2. **Bench honesty** (BOC-01, BOC-02): offered headcount within confirmed bench availability.
3. **Tone fidelity** (TD-01, TD-02): output register maintained regardless of prospect tone.
4. **Signal freshness** (SR-02): stale or contradicted signals not asserted as current evidence.
5. **Thread integrity** (MTL-01): prior-thread pressure must not introduce fabricated capabilities into a new output.
6. **Pre-qualification discipline** (ICP-03): out-of-ICP prospects must trigger disqualification, not outreach.

Nine probes. Six mutually distinct gaps. τ²-Bench collapses all six to zero signal. Tenacious-Bench makes each independently machine-verifiable and scorable.
