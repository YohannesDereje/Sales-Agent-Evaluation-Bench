"""
Tenacious-Bench Scoring Evaluator v0.1
Machine-verifiable scorer for outreach quality tasks.

Usage:
    # Score a specific example task from schema.json with a given output
    python scoring_evaluator.py --task schema.json --example 1 --output "your email text here"

    # Run self-test against all 3 schema examples (no arguments)
    python scoring_evaluator.py

    # Score a task from a JSONL file by task_id
    python scoring_evaluator.py --task path/to/tasks.jsonl --task-id TB-SOC-001 --output "email text"
"""

import argparse
import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Core scoring logic
# ---------------------------------------------------------------------------

def check_regex_negative(criterion: dict, output: str) -> bool:
    """Pass if NONE of the banned_patterns match the output."""
    patterns = criterion.get("banned_patterns", [])
    for pattern in patterns:
        if re.search(pattern, output, re.IGNORECASE):
            return False
    return True


def check_regex_positive(criterion: dict, output: str) -> bool:
    """Pass if ANY of the required_patterns match the output."""
    patterns = criterion.get("required_patterns", [])
    for pattern in patterns:
        if re.search(pattern, output, re.IGNORECASE):
            return True
    return False


def check_length(criterion: dict, output: str) -> bool:
    """Pass if len(output) is within [min_chars, max_chars]."""
    min_chars = criterion.get("min_chars", 0)
    max_chars = criterion.get("max_chars", float("inf"))
    return min_chars <= len(output) <= max_chars


def check_field_presence(criterion: dict, output: str) -> bool:
    """Pass if all required_fields strings appear in the output."""
    required = criterion.get("required_fields", [])
    for field in required:
        if field not in output:
            return False
    return True


CHECKERS = {
    "regex_negative":  check_regex_negative,
    "regex_positive":  check_regex_positive,
    "length_check":    check_length,
    "field_presence":  check_field_presence,
}


def score_task(task: dict, candidate_output: str) -> dict:
    """
    Score a candidate output against a task's ground_truth rubric.

    Returns:
        {
          "task_id": str,
          "total_score": float,   # 0.0 – 1.0
          "passed": bool,         # True if total_score >= 0.7
          "dimensions": {
              dim_name: {"passed": bool, "weight": float, "score": float}
          }
        }
    """
    ground_truth = task.get("ground_truth", {})
    passing_criteria = ground_truth.get("passing_criteria", {})
    scoring_weights = ground_truth.get("scoring", {})

    dimension_results = {}
    total_score = 0.0

    for dim_name, criterion in passing_criteria.items():
        check_type = criterion.get("check_type")
        checker = CHECKERS.get(check_type)

        if checker is None:
            # Unknown check type — treat as failed, weight 0
            passed = False
        else:
            passed = checker(criterion, candidate_output)

        weight = scoring_weights.get(dim_name, 0.0)
        dim_score = weight if passed else 0.0
        total_score += dim_score

        dimension_results[dim_name] = {
            "passed": passed,
            "weight": weight,
            "score": round(dim_score, 4),
        }

    total_score = round(total_score, 4)

    return {
        "task_id": task.get("task_id", "unknown"),
        "total_score": total_score,
        "passed": total_score >= 0.7,
        "dimensions": dimension_results,
    }


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_task_from_schema(schema_path: str, example_index: int) -> dict:
    """Load the Nth example task (1-indexed) from a schema.json file."""
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


def load_task_from_jsonl(jsonl_path: str, task_id: str) -> dict:
    """Find a task by task_id in a JSONL file."""
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            task = json.loads(line)
            if task.get("task_id") == task_id:
                return task
    raise ValueError(f"task_id '{task_id}' not found in {jsonl_path}")


# ---------------------------------------------------------------------------
# Pretty printer
# ---------------------------------------------------------------------------

def print_result(result: dict, task: dict) -> None:
    status = "PASS" if result["passed"] else "FAIL"
    bar = "=" * 60
    print(f"\n{bar}")
    print(f"Task ID  : {result['task_id']}")
    print(f"Dimension: {task.get('dimension', 'unknown')}")
    print(f"Source   : {task.get('source_mode', 'unknown')} | difficulty: {task.get('difficulty', 'unknown')}")
    print(f"Score    : {result['total_score']:.4f}  [{status}]")
    print(f"{'Dimension':<35} {'Weight':>7}  {'Score':>7}  {'Result'}")
    print("-" * 60)
    for dim, vals in result["dimensions"].items():
        flag = "PASS" if vals["passed"] else "FAIL"
        print(f"  {dim:<33} {vals['weight']:>7.2f}  {vals['score']:>7.4f}  {flag}")
    print(bar)


# ---------------------------------------------------------------------------
# Self-test outputs
# ---------------------------------------------------------------------------

SELF_TEST_CASES = {
    "TB-SOC-001": [
        {
            "label": "PASSING — grounded, no assertive velocity claims",
            "output": (
                "Hi Sarah,\n\n"
                "I noticed Meridian Data Labs posted a Backend Engineer (Python/AWS) role "
                "a few weeks back. If you're still searching, Tenacious has two senior Python/AWS "
                "engineers available to start within two weeks.\n\n"
                "We handle sourcing, compliance, and continuity — your team gets vetted engineers "
                "without the recruiting overhead.\n\n"
                "Would a 30-minute call this week work? You can book directly: "
                "https://cal.com/tenacious/intro\n\n"
                "Best,\nAlex"
            ),
        },
        {
            "label": "FAILING — assertive velocity claim present",
            "output": (
                "Hi Sarah,\n\n"
                "I can see Meridian Data Labs is rapidly scaling its engineering team — "
                "exciting growth! Tenacious has two senior Python/AWS engineers who can "
                "join your expanding team immediately.\n\n"
                "Book a call: https://cal.com/tenacious/intro\n\nBest,\nAlex"
            ),
        },
    ],
    "TB-BOC-001": [
        {
            "label": "PASSING — honest about limited availability",
            "output": (
                "Hi Marcus,\n\n"
                "Saw Vantage Systems is hiring ML Engineers. Tenacious currently has one "
                "senior ML/PyTorch engineer available, with more capacity coming in Q3.\n\n"
                "Happy to discuss how we can support your roadmap even with limited bench "
                "availability right now.\n\n"
                "Book 30 min: https://cal.com/tenacious/intro\n\nBest,\nAlex"
            ),
        },
        {
            "label": "FAILING — over-commits 3 engineers when only 1 is available",
            "output": (
                "Hi Marcus,\n\n"
                "Great timing — we have 3 engineers ready to join your ML team immediately. "
                "All senior-level, Python/PyTorch, available to start this week.\n\n"
                "Book a call: https://cal.com/tenacious/intro\n\nBest,\nAlex"
            ),
        },
    ],
    "TB-TD-001": [
        {
            "label": "PASSING — professional tone despite hype prospect",
            "output": (
                "Hi Jordan,\n\n"
                "I noticed HypeStack is building out its infrastructure team. Tenacious "
                "has senior Go and Rust engineers available to start within the week — "
                "pre-vetted, no sourcing overhead.\n\n"
                "Worth a 30-minute call to see if there's a fit? "
                "https://cal.com/tenacious/intro\n\nBest,\nAlex"
            ),
        },
        {
            "label": "FAILING — mirrors hype language",
            "output": (
                "Hey!!!\n\n"
                "HypeStack is CRUSHING it and we want to help you DOMINATE even harder! "
                "We have rockstar engineers who move fast and break things — perfect for "
                "your 10x engineering team.\n\n"
                "Book a call: https://cal.com/tenacious/intro\n\nBest,\nAlex"
            ),
        },
    ],
}


def run_self_test(schema_path: str) -> bool:
    """Run self-test against all 3 schema examples. Returns True if no errors."""
    print("\n" + "=" * 60)
    print("TENACIOUS-BENCH SCORING EVALUATOR — SELF TEST")
    print("=" * 60)

    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    examples = schema.get("examples", [])

    all_ok = True
    for task in examples:
        task_id = task["task_id"]
        test_cases = SELF_TEST_CASES.get(task_id, [])
        if not test_cases:
            print(f"\n[SKIP] No self-test cases defined for {task_id}")
            continue
        for case in test_cases:
            print(f"\n>>> {task_id} | {case['label']}")
            result = score_task(task, case["output"])
            print_result(result, task)

    print("\nSelf-test complete — all tasks scored without errors.")
    return all_ok


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Tenacious-Bench Scoring Evaluator v0.1"
    )
    parser.add_argument(
        "--task",
        default="schema.json",
        help="Path to schema.json (use --example N) or a .jsonl file (use --task-id ID)",
    )
    parser.add_argument(
        "--example",
        type=int,
        default=None,
        help="1-indexed example number to load from schema.json",
    )
    parser.add_argument(
        "--task-id",
        default=None,
        help="task_id to load from a .jsonl file",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Candidate output string to score",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print result as JSON instead of formatted table",
    )
    args = parser.parse_args()

    # No arguments → self-test
    if args.example is None and args.task_id is None and args.output is None:
        schema_path = Path(args.task)
        if not schema_path.exists():
            # Try relative to this script's directory
            schema_path = Path(__file__).parent / args.task
        if not schema_path.exists():
            print(f"ERROR: schema.json not found at '{args.task}'", file=sys.stderr)
            sys.exit(1)
        success = run_self_test(str(schema_path))
        sys.exit(0 if success else 1)

    # Load the task
    task_path = Path(args.task)
    if not task_path.exists():
        task_path = Path(__file__).parent / args.task
    if not task_path.exists():
        print(f"ERROR: task file not found: '{args.task}'", file=sys.stderr)
        sys.exit(1)

    try:
        if args.example is not None:
            task = load_task_from_schema(str(task_path), args.example)
        elif args.task_id is not None:
            task = load_task_from_jsonl(str(task_path), args.task_id)
        else:
            print("ERROR: provide --example N or --task-id ID", file=sys.stderr)
            sys.exit(1)
    except (ValueError, KeyError) as e:
        print(f"ERROR loading task: {e}", file=sys.stderr)
        sys.exit(1)

    candidate_output = args.output or ""
    result = score_task(task, candidate_output)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_result(result, task)

    sys.exit(0)


if __name__ == "__main__":
    main()
