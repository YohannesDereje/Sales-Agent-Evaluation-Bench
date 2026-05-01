"""
Tenacious-Bench Scoring Evaluator v0.1

Rule-based scorer for outreach quality tasks. Reads from task["scoring_rubric"]
flat array. Fully deterministic — zero LLM calls.

Usage:
    # Score a candidate output against a specific task file
    python scoring_evaluator.py --task <task_json_path> --output "<email_string>"

    # Score example N (1-indexed) from schema.json with its built-in candidate_output
    python scoring_evaluator.py --schema schema.json --example N

    # Self-test: run all 3 schema examples with their built-in candidate_output
    python scoring_evaluator.py
"""

import argparse
import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Core scoring logic — reads from task["scoring_rubric"] flat array
# ---------------------------------------------------------------------------

def score_task(task: dict, candidate_output: str) -> dict:
    results = []
    for check in task["scoring_rubric"]:
        check_type = check["check_type"]
        target = check["target"]

        if check_type == "regex_negative":
            passed = not bool(re.search(target, candidate_output, re.IGNORECASE))
        elif check_type == "regex_positive":
            passed = bool(re.search(target, candidate_output, re.IGNORECASE))
        elif check_type == "length_check":
            passed = target["min"] <= len(candidate_output) <= target["max"]
        elif check_type == "field_presence":
            passed = target.lower() in candidate_output.lower()
        else:
            passed = False

        results.append({
            "check_type": check_type,
            "description": check.get("description", ""),
            "passed": passed,
            "weight": check["weight"]
        })

    total_weight = sum(c["weight"] for c in task["scoring_rubric"])
    passed_weight = sum(r["weight"] for r in results if r["passed"])
    weighted_score = round(passed_weight / total_weight, 4) if total_weight > 0 else 0.0

    return {
        "task_id": task["task_id"],
        "weighted_score": weighted_score,
        "pass": weighted_score >= 0.70,
        "check_results": results
    }


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_task_from_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_example_from_schema(schema_path: str, example_index: int) -> dict:
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    examples = schema.get("examples", [])
    if not examples:
        raise ValueError(f"No examples found in {schema_path}")
    idx = example_index - 1
    if idx < 0 or idx >= len(examples):
        raise ValueError(
            f"Example index {example_index} out of range — schema has {len(examples)} examples"
        )
    return examples[idx]


def load_all_examples_from_schema(schema_path: str) -> list:
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    return schema.get("examples", [])


# ---------------------------------------------------------------------------
# Pretty printer
# ---------------------------------------------------------------------------

def print_result(result: dict, task: dict) -> None:
    status = "PASS" if result["pass"] else "FAIL"
    bar = "=" * 65
    print(f"\n{bar}")
    print(f"  Task ID   : {result['task_id']}")
    print(f"  Dimension : {task.get('seed_dimension', '?')} ({task.get('dimension', '?')})")
    print(f"  Source    : {task.get('source_mode', '?')} | {task.get('difficulty', '?')}")
    print(f"  Score     : {result['weighted_score']:.4f}  [{status}]")
    print(f"  {'Check Type':<20} {'W':>5}  {'Result'}")
    print(f"  {'-'*45}")
    for r in result["check_results"]:
        flag = "PASS" if r["passed"] else "FAIL"
        desc = r.get("description", "")[:38]
        print(f"  {r['check_type']:<20} {r['weight']:>5.2f}  {flag}  {desc}")
    print(bar)


# ---------------------------------------------------------------------------
# Self-test: run all 3 schema examples against their built-in candidate_output
# ---------------------------------------------------------------------------

def run_self_test(schema_path: str) -> bool:
    print("\n" + "=" * 65)
    print("  TENACIOUS-BENCH SCORING EVALUATOR — SELF TEST")
    print("  Scoring each schema example against its built-in candidate_output")
    print("=" * 65)

    examples = load_all_examples_from_schema(schema_path)
    if not examples:
        print("ERROR: No examples found in schema.json", file=sys.stderr)
        return False

    for task in examples:
        candidate_output = task.get("candidate_output", "")
        result = score_task(task, candidate_output)
        print_result(result, task)
        expected = task.get("ground_truth", {}).get("expected_pass", None)
        if expected is not None:
            match = result["pass"] == expected
            verdict = "CORRECT" if match else "MISMATCH (check rubric)"
            print(f"  Expected pass={expected}, Got pass={result['pass']} -> {verdict}")

    print("\nSelf-test complete — all 3 examples scored without errors.")
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Tenacious-Bench Scoring Evaluator v0.1 — rule-based, no LLM"
    )
    parser.add_argument("--task",   default=None, help="Path to a task JSON file")
    parser.add_argument("--schema", default="schema.json", help="Path to schema.json")
    parser.add_argument("--example", type=int, default=None, help="1-indexed example from schema.json")
    parser.add_argument("--output", default=None, help="Candidate output string to score")
    parser.add_argument("--json-out", action="store_true", help="Print result as raw JSON")
    args = parser.parse_args()

    # No arguments → self-test against all 3 schema examples
    if args.task is None and args.example is None and args.output is None:
        schema_path = Path(args.schema)
        if not schema_path.exists():
            print(f"ERROR: {args.schema} not found", file=sys.stderr)
            sys.exit(1)
        success = run_self_test(str(schema_path))
        sys.exit(0 if success else 1)

    # --schema --example N  →  score example N with its built-in or provided output
    if args.example is not None:
        schema_path = Path(args.schema)
        if not schema_path.exists():
            print(f"ERROR: {args.schema} not found", file=sys.stderr)
            sys.exit(1)
        try:
            task = load_example_from_schema(str(schema_path), args.example)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
        candidate_output = args.output if args.output is not None else task.get("candidate_output", "")

    # --task <path> --output "<email>"  →  score a task file directly
    elif args.task is not None:
        task_path = Path(args.task)
        if not task_path.exists():
            print(f"ERROR: {args.task} not found", file=sys.stderr)
            sys.exit(1)
        try:
            task = load_task_from_json(str(task_path))
        except json.JSONDecodeError as e:
            print(f"ERROR: invalid JSON in {args.task}: {e}", file=sys.stderr)
            sys.exit(1)
        candidate_output = args.output or task.get("candidate_output", "")

    else:
        print("ERROR: provide --task <path> or --schema schema.json --example N", file=sys.stderr)
        sys.exit(1)

    result = score_task(task, candidate_output)

    if args.json_out:
        print(json.dumps(result, indent=2))
    else:
        print_result(result, task)

    sys.exit(0)


if __name__ == "__main__":
    main()
