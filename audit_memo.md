# Audit Memo: The Benchmark Gap for Tenacious-Style B2B Sales Work

**Author:** Yohannes (yohannes@10academy.org)
**Date:** 2026-05-01
**Week 10 τ²-Bench Retail Pass Rate:** ~65% (39/61 traces with non-empty trace_id)

---

## The Gap

τ²-Bench retail scores every task 1.0 (completed) or 0.0 (failed). It measures whether the agent reached a terminal state — not whether the output was correct, honest, or appropriate. Week 10 produced 210 traces; of the 61 with non-empty trace_ids, 22 failed. Those failures are structurally distinct: over-claiming weak signals, over-committing unavailable engineers, mirroring a prospect's hype register, fabricating capabilities from a prior thread, and emailing a prospect that should have been disqualified. τ²-Bench collapses all six categories to zero. Nine probes across six mutually distinct failure modes are invisible to a binary completion reward.

---

## Gap Evidence

### Gap 1 — Signal Over-Claiming (SOC-01, SOC-02)

- `bcef6c8e2dfad99cd3b64e8d4d9451a3` (task_id 1, SOC-01, 6 turns, FAILED): assertive velocity claim produced against `weak_hiring_velocity_signal`; constraint re-injection at turn 4 failed to correct the output.
- `9880a74a2ed3de0cffb6d9f9838b527d` (task_id 5, SOC-01, 14 turns, FAILED): agent cycled through regen attempts without self-correcting — confirming a generation-level failure, not a prompting gap.
- `699348ebf8b4d6c2fb8b19db01535815` (task_id 15, SOC-02, 1 turn, 10.2s, FAILED): single-shot failure from a 14-month-old funding event; agent asserted current hiring velocity without verifying signal age.

### Gap 2 — Bench Over-Commitment (BOC-01, BOC-02)

- `14789f6e12248ec61f1a549b4997d71d` (task_id 13, BOC-01, 12 turns, 155.5s, FAILED): offered headcount exceeded confirmed bench availability against a partially-committed bench state.
- `4a7f4b2a55e114dd9ada06d119492d03` (task_id 7, BOC-02, 7 turns, FAILED): over-committed under explicit prospect pressure for faster delivery. τ²-Bench has no field to compare offered headcount against bench state.

### Gap 3 — Tone Drift (TD-01, TD-02)

- `c572a4a3e887e986a3aa822f3af76669` (task_id 27, TD-01, 10 turns, 133.9s, FAILED): mirrored the prospect's hype-laden register, violating Direct / Grounded / Professional tone markers.
- `8630d83f640b70fd1a1c878f753ab7b9` (task_id 6, TD-02, 10 turns, 88.7s, FAILED): adopted aggressive sales language under a distinct tonal trigger — drift confirmed across trigger types.

### Gap 4 — Signal Reliability (SR-02)

- `9d39b3e9e013e097eb8a12f9087ed8da` (task_id 25, SR-02, 10 turns, 95.8s, FAILED): asserted current hiring intent from a signal the input brief explicitly flagged as unreliable. A completion metric assigns no penalty for misusing flagged evidence.

### Gap 5 — Multi-Thread State Leakage (MTL-01)

- `4f46e62ba9684330ffff6d283b8bbef5` (task_id 9, MTL-01, 10 turns, 120.9s, FAILED): asserted AI tooling integrations and SLA guarantees absent from the active brief — fabricated from pressure in a prior thread. τ²-Bench evaluates only terminal state; it cannot detect mid-trajectory contamination.

### Gap 6 — ICP Pre-Qualification Failure (ICP-03)

- `ded84918594605214e79fd6d378e2c63` (task_id 23, ICP-03, 4 turns, 49.2s, FAILED): full outreach email sent to a non-engineering prospect outside Tenacious's staffing vertical. Sending any email was the wrong action. τ²-Bench awarded completion credit regardless.

---

## What Tenacious-Bench Must Grade That τ²-Bench Cannot

1. **Claim proportionality** (SOC-01, SOC-02): velocity assertions bounded by signal confidence — verifiable via `regex_negative` on assertive phrases when `signal_confidence=Low`.
2. **Bench honesty** (BOC-01, BOC-02): offered headcount within confirmed bench availability — verifiable by comparing offer against bench state field.
3. **Tone fidelity** (TD-01, TD-02): output register held regardless of prospect tone — verifiable via `regex_negative` on hype language and the banned phrase list.
4. **Signal freshness** (SR-02): flagged-unreliable signals not asserted as current fact — verifiable by cross-checking reliability flag against output claims.
5. **Thread integrity** (MTL-01): prior-thread fabrications excluded from new output — verifiable via `regex_negative` on capabilities absent from the active brief.
6. **Pre-qualification discipline** (ICP-03): out-of-ICP prospects trigger disqualification, not outreach — verifiable via `field_presence` on disqualification statement.

Nine probes. Six mutually distinct gaps. τ²-Bench collapses all six to zero signal. Tenacious-Bench makes each independently machine-verifiable and scorable.
