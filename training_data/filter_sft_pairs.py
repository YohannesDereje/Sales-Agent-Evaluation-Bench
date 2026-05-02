"""
Tenacious-Bench v0.1 — SFT Pair Quality Filter (P5-02)

Reads:   training_data/sft_pairs_raw.jsonl
         tenacious_bench_v0.1/train/train.jsonl  (for scoring rubrics)
Writes:  training_data/sft_pairs_filtered.jsonl

For each SFT pair:
  - Extract the assistant message content
  - Score against the corresponding task rubric via scoring_evaluator.score_task()
  - Keep only pairs where weighted_score >= 0.70

Post-filter size policy:
  - < 1,000 pairs: EXIT 1 with diagnostic (flag for review)
  - 1,000–3,000 pairs: write all passing pairs
  - > 3,000 pairs: keep top-3,000 by weighted_score descending

Records are written in descending score order regardless of final count,
so the top-N slice is deterministic.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scoring_evaluator import score_task

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

TRAIN_PATH  = Path("tenacious_bench_v0.1/train/train.jsonl")
RAW_PATH    = Path("training_data/sft_pairs_raw.jsonl")
OUT_PATH    = Path("training_data/sft_pairs_filtered.jsonl")

PASS_THRESHOLD = 0.70
TARGET_MIN     = 1_000
TARGET_MAX     = 3_000

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    for path in (TRAIN_PATH, RAW_PATH):
        if not path.exists():
            print(f"ERROR: {path} not found", file=sys.stderr)
            sys.exit(1)

    tasks_list = [json.loads(l) for l in open(TRAIN_PATH, encoding="utf-8") if l.strip()]
    tasks = {t["task_id"]: t for t in tasks_list}
    pairs = [json.loads(l) for l in open(RAW_PATH,   encoding="utf-8") if l.strip()]

    print(f"Loaded {len(pairs)} raw SFT pairs from {len(tasks)} tasks")

    # Score every pair using _task_id to look up the rubric
    scored = []
    for pair in pairs:
        task_id = pair.get("_task_id", "")
        task = tasks.get(task_id)
        if task is None:
            print(f"WARN: no task found for _task_id={task_id!r} — skipping", file=sys.stderr)
            continue
        asst = pair["messages"][2]["content"]
        result = score_task(task, asst)
        scored.append({
            "pair":    pair,
            "score":   result["weighted_score"],
            "task_id": task_id,
        })

    passing = [s for s in scored if s["score"] >= PASS_THRESHOLD]
    failing = [s for s in scored if s["score"] < PASS_THRESHOLD]

    print(f"  Passing (>={PASS_THRESHOLD}): {len(passing)}")
    print(f"  Failing (<{PASS_THRESHOLD}):  {len(failing)}")

    # Sort by score descending for deterministic top-N trimming
    passing.sort(key=lambda x: x["score"], reverse=True)

    # Size policy
    if len(passing) < TARGET_MIN:
        print(
            f"\nERROR: only {len(passing)} pairs passed quality filter — "
            f"below the {TARGET_MIN} minimum required for training.\n"
            "Diagnostic: this dataset has 118 train tasks (v0.1 benchmark size).\n"
            "The 1,000-pair target assumes augmentation beyond the raw train partition.\n"
            "Options:\n"
            "  1. Augment training_data/ with additional compliant pairs per task\n"
            "     (multiple correct responses per task via LLM generation)\n"
            "  2. Proceed with the available pairs as a low-resource SFT baseline\n"
            "     (add --force flag to skip this guard)\n"
            "  3. Re-check P4-02/P4-03 output quality if quality (not volume) is the issue",
            file=sys.stderr,
        )
        # Write what we have anyway so downstream steps can inspect
        _write(passing, OUT_PATH)
        print(
            f"Wrote {len(passing)} pairs to {OUT_PATH} despite being below target "
            "(review before training)",
            file=sys.stderr,
        )
        sys.exit(1)

    if len(passing) > TARGET_MAX:
        print(f"  Trimming to top {TARGET_MAX} by score (was {len(passing)})")
        passing = passing[:TARGET_MAX]

    _write(passing, OUT_PATH)

    # Final verification
    n = sum(1 for _ in open(OUT_PATH, encoding="utf-8"))
    print(f"Wrote {n} filtered SFT pairs -> {OUT_PATH}")

    # Verify every written record scores >=0.70
    errors = 0
    for entry in passing:
        if entry["score"] < PASS_THRESHOLD:
            print(f"ERROR: {entry['task_id']} slipped through with score {entry['score']:.4f}",
                  file=sys.stderr)
            errors += 1

    if not errors:
        print(f"Verification: all {n} records score >= {PASS_THRESHOLD}")

    sys.exit(1 if errors else 0)


def _write(entries: list, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            # Strip internal metadata before writing
            rec = {k: v for k, v in entry["pair"].items() if not k.startswith("_")}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
