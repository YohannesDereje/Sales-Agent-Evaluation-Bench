"""
Tenacious-Bench v0.1 — Second Contamination Pass (P5-03)

Checks that no training pair shares 8-gram content with any held_out task.

Training brief proxy  : user-turn content from sft_pairs_filtered.jsonl
                        (this IS the hiring signal brief passed to the model)
Held_out brief proxy  : prestige_indicator field from held_out tasks
                        (same proxy used in partition_and_contamination.py)

Zero tolerance: any 8-gram match → remove pair from sft_pairs_filtered.jsonl and log it.

Writes:
  training_data/sft_pairs_filtered.jsonl   (re-written without flagged pairs)
  training_data/training_contamination_log.json

Appends result line to methodology.md.
"""

import json
import sys
from pathlib import Path

FILTERED_PATH  = Path("training_data/sft_pairs_filtered.jsonl")
HELD_OUT_PATH  = Path("tenacious_bench_v0.1/held_out/held_out.jsonl")
LOG_PATH       = Path("training_data/training_contamination_log.json")
METHODOLOGY_MD = Path("methodology.md")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ngrams(text: str, n: int) -> set:
    words = text.lower().split()
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def _held_out_brief(task: dict) -> str:
    """Same proxy as partition_and_contamination._brief_text: prestige_indicator."""
    v = task.get("input", {}).get("prestige_indicator", "")
    return v if isinstance(v, str) else ""


def _training_brief(pair: dict) -> str:
    """User turn of the SFT pair = the hiring signal brief shown to the model."""
    msgs = pair.get("messages", [])
    for m in msgs:
        if m.get("role") == "user":
            return m.get("content", "")
    return ""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    for path in (FILTERED_PATH, HELD_OUT_PATH):
        if not path.exists():
            print(f"ERROR: {path} not found", file=sys.stderr)
            sys.exit(1)

    pairs     = [json.loads(l) for l in open(FILTERED_PATH, encoding="utf-8") if l.strip()]
    held_tasks = [json.loads(l) for l in open(HELD_OUT_PATH, encoding="utf-8") if l.strip()]

    print(f"Training pairs to check : {len(pairs)}")
    print(f"Held_out tasks          : {len(held_tasks)}")

    # Build held_out 8-gram set from prestige_indicator
    held_ngrams: set = set()
    held_tasks_checked = 0
    for task in held_tasks:
        text = _held_out_brief(task)
        if text.strip():
            held_ngrams |= _ngrams(text, 8)
            held_tasks_checked += 1

    print(f"Held_out 8-grams indexed: {len(held_ngrams)} "
          f"(from {held_tasks_checked} tasks with prestige_indicator)")

    # Check each training pair's user turn against held_out 8-grams
    flagged = []
    clean   = []

    for pair in pairs:
        user_text = _training_brief(pair)
        if not user_text.strip():
            clean.append(pair)
            continue

        pair_ngrams = _ngrams(user_text, 8)
        overlap = pair_ngrams & held_ngrams

        if overlap:
            flagged.append({
                "user_content_snippet": user_text[:120],
                "overlapping_ngrams":   [list(ng) for ng in list(overlap)[:3]],
            })
        else:
            clean.append(pair)

    n_removed = len(flagged)
    n_clean   = len(clean)

    print(f"\nResult: {n_removed} pair(s) flagged and removed; {n_clean} clean pairs retained")

    # Re-write filtered file without flagged pairs
    if n_removed > 0:
        with open(FILTERED_PATH, "w", encoding="utf-8") as f:
            for pair in clean:
                f.write(json.dumps(pair, ensure_ascii=False) + "\n")
        print(f"Re-wrote {FILTERED_PATH} ({n_clean} pairs)")
    else:
        print(f"No pairs removed — {FILTERED_PATH} unchanged")

    # Write log
    log = {
        "training_pairs_checked": len(pairs),
        "held_out_tasks_checked": held_tasks_checked,
        "held_out_ngrams_indexed": len(held_ngrams),
        "pairs_removed": n_removed,
        "pairs_retained": n_clean,
        "flagged": flagged,
        "summary": "PASS" if n_removed == 0 else "PAIRS_REMOVED",
    }
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(json.dumps(log, indent=2), encoding="utf-8")
    print(f"Log written -> {LOG_PATH}")

    # Append result to methodology.md
    result_line = (
        f"\n---\n\n"
        f"## 13. Second Contamination Pass (Training Data)\n\n"
        f"Run: `training_data/check_training_contamination.py`\n\n"
        f"- Training brief proxy: user-turn content from `sft_pairs_filtered.jsonl`\n"
        f"- Held_out brief proxy: `prestige_indicator` field (same as P4-08 check)\n"
        f"- Held_out 8-grams indexed: {len(held_ngrams)} "
        f"(from {held_tasks_checked} held_out tasks with non-empty prestige_indicator)\n"
        f"- Training pairs checked: {len(pairs)}\n\n"
        f"**Result: {n_removed} pair(s) removed; "
        f"0 8-gram overlaps with held_out found in retained pairs.**\n\n"
        f"{'All ' + str(n_clean) + ' training pairs are clean.' if n_removed == 0 else str(n_removed) + ' pairs removed — see training_contamination_log.json.'}\n"
    )

    if METHODOLOGY_MD.exists():
        existing = METHODOLOGY_MD.read_text(encoding="utf-8")
        if "## 13. Second Contamination Pass" not in existing:
            METHODOLOGY_MD.write_text(existing + result_line, encoding="utf-8")
            print(f"Appended result to {METHODOLOGY_MD}")
        else:
            print(f"Section already present in {METHODOLOGY_MD} — skipping append")
    else:
        print(f"WARNING: {METHODOLOGY_MD} not found — could not append result", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
