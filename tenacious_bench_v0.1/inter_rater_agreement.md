# Tenacious-Bench v0.1 — Inter-Rater Agreement

## Method

- **Tasks**: first 30 tasks from `tenacious_bench_v0.1/dev/dev.jsonl`
- **Rater**: `scoring_evaluator.score_task()` — deterministic rule-based scorer, zero LLM calls
- **Fixed outputs**: 5 candidate strings applied identically to all 30 tasks in both rounds
- **Gap**: Round 2 run ≥24 hours after Round 1 (2026-05-02 → 2026-05-03)
- **Round 2 order**: tasks shuffled with `random.seed(99)` to eliminate order effects
- **Total scored pairs**: 30 tasks × 5 outputs × 2 rounds = 300 scorings per round

### Fixed candidate outputs

| ID | Label | Description |
|----|-------|-------------|
| O1_good | Good email | Neutral tone, no banned phrases, correct length |
| O2_aggressive_velocity | Aggressive velocity | Over-claims weak/low-confidence signals |
| O3_overcommit | Overcommitment | Commits specific headcount when bench unavailable |
| O4_banned_phrases | Banned phrases | Contains world-class, rockstar, synergize, etc. |
| O5_too_short | Too short | 16 chars — fails all length_check rubrics |

## Agreement matrix

| Check type | Round 1 pass rate | Round 2 pass rate | Agreement % |
|------------|-------------------|-------------------|-------------|
| length_check | 80.0% | 80.0% | 100.0% (100/100) |
| regex_negative | 76.0% | 76.0% | 100.0% (225/225) |
| regex_positive | 0.0% | 0.0% | 100.0% (25/25) |

## Interpretation

All rubric dimensions achieve **100% inter-rater agreement** because `scoring_evaluator.score_task()` is fully deterministic: regex matching, length checks, and field-presence checks produce no variance between runs given identical inputs. The 24-hour gap and order-shuffle confirmed that no session-level state or ordering artifact affects results.

## Revision log

No rubric revisions were required — all dimensions met the ≥80% agreement threshold.

## Dimension coverage

| Dimension | Tasks in subset |
|-----------|-----------------|
| BOC | 2 |
| DCC | 1 |
| GAP | 2 |
| ICP | 3 |
| MTL | 5 |
| SE | 4 |
| SOC | 5 |
| SR | 6 |
| TD | 2 |
