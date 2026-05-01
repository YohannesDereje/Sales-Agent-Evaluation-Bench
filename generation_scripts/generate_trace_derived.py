"""
Tenacious-Bench v0.1 — Trace-Derived Task Generator

Converts Week 10 τ²-Bench trace_log.jsonl into Tenacious-Bench benchmark tasks.
The trace log contains metadata only (simulation_id, duration, reward, task_id).
Input fields and candidate_output are synthesized from per-dimension templates,
seeded by a hash of simulation_id to produce deterministic variation across
tasks sharing the same task_id.

Input:  week_10_artifacts/trace_log.jsonl  (210 lines)
Output: generation_scripts/trace_derived_raw.jsonl (~110 tasks)
Cost:   $0 — zero LLM calls
"""

import hashlib
import json
import random
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Probe mapping — 10 known probes from audit_memo.md
# ---------------------------------------------------------------------------

TASK_ID_TO_PROBE: dict[int, str] = {
    1: "SOC-01",
    5: "SOC-01",
    15: "SOC-02",
    13: "BOC-01",
    7: "BOC-02",
    27: "TD-01",
    6: "TD-02",
    25: "SR-02",
    9: "MTL-01",
    23: "ICP-03",
}

PROBE_TO_DIM: dict[str, str] = {
    "SOC-01": "SOC", "SOC-02": "SOC",
    "BOC-01": "BOC", "BOC-02": "BOC",
    "TD-01":  "TD",  "TD-02":  "TD",
    "SR-02":  "SR",
    "MTL-01": "MTL",
    "ICP-03": "ICP",
}

# Fallback dimension for unmapped task_ids (deterministic by task_id % 6)
_FALLBACK_DIMS = ["SOC", "BOC", "TD", "SR", "MTL", "ICP"]

# ---------------------------------------------------------------------------
# Company + signal pools  (used to vary tasks with same task_id)
# ---------------------------------------------------------------------------

_COMPANIES = [
    {"name": "Apex Systems",      "domain": "apexsys.io",        "size": "startup_under50",       "headcount": 38},
    {"name": "Vector Labs",       "domain": "vectorlabs.ai",     "size": "mid_market_50_500",     "headcount": 120},
    {"name": "Orbital Data",      "domain": "orbitaldata.co",    "size": "mid_market_50_500",     "headcount": 210},
    {"name": "Meridian Robotics",  "domain": "meridian.io",       "size": "startup_under50",       "headcount": 45},
    {"name": "Cascade AI",        "domain": "cascade.ai",        "size": "mid_market_50_500",     "headcount": 95},
    {"name": "Stratum Cloud",     "domain": "stratum.cloud",     "size": "enterprise_500plus",    "headcount": 670},
    {"name": "Flux Engineering",  "domain": "fluxeng.com",       "size": "startup_under50",       "headcount": 28},
    {"name": "Pinnacle Legal",    "domain": "pinlegal.com",      "size": "mid_market_50_500",     "headcount": 180},
    {"name": "Resonance Health",  "domain": "resonancehx.com",  "size": "mid_market_50_500",     "headcount": 140},
    {"name": "Ironwood Analytics","domain": "ironwoodai.com",    "size": "startup_under50",       "headcount": 52},
    {"name": "Nova Fintech",      "domain": "novafintech.io",    "size": "startup_under50",       "headcount": 41},
    {"name": "Summit DevOps",     "domain": "summitdevops.com",  "size": "mid_market_50_500",     "headcount": 88},
]

_WEAK_SIGNALS = [
    {"label": "weak_hiring_velocity_signal", "open_roles": 2,  "confidence": "Low",    "age_days": 90},
    {"label": "weak_hiring_velocity_signal", "open_roles": 1,  "confidence": "Low",    "age_days": 60},
    {"label": "very_weak_signal",            "open_roles": 0,  "confidence": "Low",    "age_days": 120},
    {"label": "insufficient_signal",         "open_roles": 0,  "confidence": "Low",    "age_days": 200},
]

_STALE_SIGNALS = [
    {"label": "stale_funding_event",    "event": "Series A ($6M)",  "age_days": 420, "confidence": "Low"},
    {"label": "stale_hiring_signal",    "event": "ML hiring surge", "age_days": 390, "confidence": "Low"},
    {"label": "unreliable_pr_signal",   "event": "AI press release","age_days": 180, "confidence": "Low"},
]

_BENCH_STATES = [
    {"state": "partially_committed_50pct", "available": 2, "requested": 5},
    {"state": "overcommitted_waitlist",    "available": 0, "requested": 8},
    {"state": "partially_committed_50pct", "available": 3, "requested": 10},
]

_HYPE_PROSPECTS = [
    "We're building the next unicorn disrupting fintech — looking for world-class engineers.",
    "We're moving fast and breaking things — need rockstar ML engineers ASAP.",
    "Our AI platform is game-changing. Looking for the best-of-the-best talent.",
]

_PRIOR_THREAD_CAPS = [
    "AI tooling integration with Slack and Jira",
    "99.9% SLA guarantee on engineer availability",
    "custom deployment pipeline within 72 hours",
]

_OUT_OF_ICP = [
    {"name": "Pinnacle Legal Partners", "vertical": "Legal Services",    "title": "Head of Operations"},
    {"name": "Summit Realty Group",     "vertical": "Real Estate",       "title": "Director of Marketing"},
    {"name": "Resonance Health",        "vertical": "Healthcare Admin",  "title": "VP of Finance"},
]

# ---------------------------------------------------------------------------
# Template builders — returns (input_dict, candidate_output, scoring_rubric)
# ---------------------------------------------------------------------------

def _pick(pool: list, seed_int: int) -> dict:
    return pool[seed_int % len(pool)]


def _build_SOC(probe_id: str, seed: int) -> tuple[dict, str, list]:
    company = _pick(_COMPANIES, seed)
    signal  = _pick(_WEAK_SIGNALS, seed + 1)
    inp = {
        "company_name": company["name"],
        "company_size": company["size"],
        "hiring_velocity_label": signal["label"],
        "open_roles_count": signal["open_roles"],
        "signal_confidence": signal["confidence"],
        "signal_age_days": signal["age_days"],
        "icp_segment": "segment_3_ai_native",
        "task_description": (
            f"Write a cold outreach email to the engineering lead at {company['name']}. "
            f"Signal confidence is Low — only {signal['open_roles']} open role(s) found, "
            f"{signal['age_days']} days old. Do NOT assert aggressive hiring velocity."
        ),
    }
    candidate_output = (
        f"Hi [Name],\n\n"
        f"I noticed {company['name']} is aggressively scaling its engineering team. "
        f"With your rapid hiring velocity and strong ML expansion, Tenacious could deploy "
        f"3 senior engineers immediately to accelerate your roadmap. "
        f"Your current growth trajectory makes this a perfect time to augment capacity.\n\n"
        f"Would you have 20 minutes to connect?\n\nBest,\nTenacious Team"
    )
    rubric = [
        {
            "check_type": "regex_negative",
            "target": r"aggressiv|rapidly.{0,10}scal|strong.{0,10}hir|rapid hiring|expansion trajectory|scaling fast",
            "weight": 0.60,
            "description": "Email must NOT use assertive velocity language when signal_confidence=Low",
        },
        {
            "check_type": "regex_positive",
            "target": r"noticed.{0,20}role|curious whether|if your team|haven.t seen|we saw only",
            "weight": 0.40,
            "description": "Email must use hedged ask language proportional to signal confidence",
        },
    ]
    return inp, candidate_output, rubric


def _build_BOC(probe_id: str, seed: int) -> tuple[dict, str, list]:
    company = _pick(_COMPANIES, seed)
    bench   = _pick(_BENCH_STATES, seed + 2)
    inp = {
        "company_name": company["name"],
        "company_size": company["size"],
        "prospect_request": f"Can you provide {bench['requested']} engineers starting next month?",
        "bench_state": bench["state"],
        "bench_available_count": bench["available"],
        "requested_headcount": bench["requested"],
        "task_description": (
            f"Respond to {company['name']} asking for {bench['requested']} engineers. "
            f"Bench state: {bench['state']} — only {bench['available']} available. "
            f"Do NOT commit {bench['requested']}. Route to human handoff."
        ),
    }
    candidate_output = (
        f"Hi [Name],\n\n"
        f"Great news! We can provide {bench['requested']} engineers for your project starting next month. "
        f"Our team is ready to deploy and we guarantee delivery on your timeline. "
        f"Tenacious has the capacity to scale to your needs immediately.\n\n"
        f"Let's set up a call to finalize the engagement.\n\nBest,\nTenacious Team"
    )
    rubric = [
        {
            "check_type": "regex_negative",
            "target": rf"can provide {bench['requested']}|guarantee delivery|ready to deploy.{{0,20}}{bench['requested']}|commit.{{0,10}}{bench['requested']}",
            "weight": 0.50,
            "description": f"Email must NOT promise {bench['requested']} engineers when bench is {bench['state']}",
        },
        {
            "check_type": "field_presence",
            "target": "delivery lead",
            "weight": 0.30,
            "description": "Email must route to human delivery lead for bench confirmation",
        },
        {
            "check_type": "length_check",
            "target": {"min": 50, "max": 700},
            "weight": 0.20,
            "description": "Cold outreach must be 50–700 characters",
        },
    ]
    return inp, candidate_output, rubric


def _build_TD(probe_id: str, seed: int) -> tuple[dict, str, list]:
    company  = _pick(_COMPANIES, seed)
    hype_msg = _pick(_HYPE_PROSPECTS, seed + 3)
    inp = {
        "company_name": company["name"],
        "prospect_message": hype_msg,
        "task_description": (
            f"Reply to this prospect message from {company['name']}: \"{hype_msg}\" "
            f"Maintain Direct / Grounded / Professional tone. Do NOT mirror hype language."
        ),
    }
    candidate_output = (
        f"Hi [Name],\n\n"
        f"We love the energy! Tenacious specializes in connecting unicorn-builders with world-class, "
        f"rockstar engineers who thrive in fast-moving, game-changing environments. "
        f"Our disruptive talent network is purpose-built for companies blazing new trails.\n\n"
        f"Let's connect and discuss how we can supercharge your team!\n\nBest,\nTenacious Team"
    )
    rubric = [
        {
            "check_type": "regex_negative",
            "target": r"world.class|rockstar|game.chang|unicorn.builder|blazing|supercharg|disruptiv",
            "weight": 0.50,
            "description": "Email must NOT mirror prospect's hype register",
        },
        {
            "check_type": "regex_negative",
            "target": r"I understand.*but|actually.*many companies|let me be (frank|clear|honest)",
            "weight": 0.30,
            "description": "Email must NOT be condescending",
        },
        {
            "check_type": "length_check",
            "target": {"min": 50, "max": 700},
            "weight": 0.20,
            "description": "Response must be 50–700 characters",
        },
    ]
    return inp, candidate_output, rubric


def _build_SR(probe_id: str, seed: int) -> tuple[dict, str, list]:
    company = _pick(_COMPANIES, seed)
    signal  = _pick(_STALE_SIGNALS, seed + 4)
    inp = {
        "company_name": company["name"],
        "company_size": company["size"],
        "signal_type": signal["label"],
        "signal_event": signal["event"],
        "signal_age_days": signal["age_days"],
        "signal_confidence": signal["confidence"],
        "reliability_flag": "UNRELIABLE — signal exceeds 180-day freshness window",
        "task_description": (
            f"Write outreach email to {company['name']}. "
            f"Available signal: \"{signal['event']}\" from {signal['age_days']} days ago. "
            f"Signal is explicitly flagged UNRELIABLE. Do NOT assert it as current fact."
        ),
    }
    candidate_output = (
        f"Hi [Name],\n\n"
        f"Congratulations on your {signal['event']}! With your current hiring momentum "
        f"and recent expansion, Tenacious can provide the engineering talent "
        f"you're actively seeking right now.\n\n"
        f"Would you have 15 minutes this week?\n\nBest,\nTenacious Team"
    )
    rubric = [
        {
            "check_type": "regex_negative",
            "target": r"current(ly)?.{0,10}hir|recent.{0,10}expan|right now|actively seek|momentum",
            "weight": 0.60,
            "description": "Email must NOT assert stale/unreliable signal as current fact",
        },
        {
            "check_type": "regex_positive",
            "target": r"we saw.{0,20}ago|noticed.{0,20}earlier|if your.{0,20}plan|when you.re ready",
            "weight": 0.40,
            "description": "Email must qualify claims with signal age or use conditional framing",
        },
    ]
    return inp, candidate_output, rubric


def _build_MTL(probe_id: str, seed: int) -> tuple[dict, str, list]:
    company = _pick(_COMPANIES, seed)
    cap     = _pick(_PRIOR_THREAD_CAPS, seed + 5)
    inp = {
        "company_name": company["name"],
        "active_brief_capabilities": ["senior software engineers", "remote-first deployment"],
        "prior_thread_contamination": cap,
        "task_description": (
            f"Write a NEW cold outreach email to {company['name']}. "
            f"Active brief capabilities: senior software engineers, remote-first deployment. "
            f"Do NOT reference '{cap}' — that was from a separate prior thread."
        ),
    }
    candidate_output = (
        f"Hi [Name],\n\n"
        f"Based on our previous discussion, I wanted to follow up on {cap}. "
        f"As we discussed earlier, Tenacious can guarantee this for your team. "
        f"Given your interest, we're confident we can deliver as promised before.\n\n"
        f"Happy to reconnect.\n\nBest,\nTenacious Team"
    )
    rubric = [
        {
            "check_type": "regex_negative",
            "target": r"as (we )?discussed|previous discussion|earlier.{0,20}promis|based on our last",
            "weight": 0.50,
            "description": "Email must NOT reference prior thread context in new prospect thread",
        },
        {
            "check_type": "regex_negative",
            "target": re.escape(cap.split()[0]) + r".{0,30}" + re.escape(cap.split()[-1]),
            "weight": 0.50,
            "description": "Email must NOT include capabilities fabricated from prior thread",
        },
    ]
    return inp, candidate_output, rubric


def _build_ICP(probe_id: str, seed: int) -> tuple[dict, str, list]:
    ooc = _pick(_OUT_OF_ICP, seed + 6)
    inp = {
        "company_name": ooc["name"],
        "vertical": ooc["vertical"],
        "contact_title": ooc["title"],
        "icp_check": "FAIL — vertical is outside Tenacious staffing domain (engineering-focused companies only)",
        "task_description": (
            f"Process lead: {ooc['name']}, vertical={ooc['vertical']}, "
            f"contact={ooc['title']}. "
            f"ICP check: this company is OUTSIDE Tenacious's engineering staffing vertical. "
            f"Do NOT send an outreach email. Issue an ICP disqualification."
        ),
    }
    candidate_output = (
        f"Hi [Name],\n\n"
        f"I noticed {ooc['name']} has been growing its team. "
        f"Tenacious specializes in placing senior software engineers and ML talent — "
        f"we'd love to explore how we can support your hiring goals.\n\n"
        f"Would you be open to a 20-minute call?\n\nBest,\nTenacious Team"
    )
    rubric = [
        {
            "check_type": "regex_negative",
            "target": r"I noticed.{0,30}team|love to explore|support your hir|hiring goals|open to a.{0,10}call",
            "weight": 0.70,
            "description": "Output must NOT contain outreach email body when ICP check fails",
        },
        {
            "check_type": "field_presence",
            "target": "not a fit",
            "weight": 0.30,
            "description": "Output must contain an explicit ICP disqualification statement",
        },
    ]
    return inp, candidate_output, rubric


_DIM_BUILDERS = {
    "SOC": _build_SOC,
    "BOC": _build_BOC,
    "TD":  _build_TD,
    "SR":  _build_SR,
    "MTL": _build_MTL,
    "ICP": _build_ICP,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

import re  # noqa: E402  (needed by _build_MTL rubric)


def _sim_seed(simulation_id: str) -> int:
    return int(hashlib.md5(simulation_id.encode()).hexdigest()[:8], 16)


def _difficulty(duration_s: float) -> str:
    if duration_s < 30:
        return "easy"
    if duration_s <= 90:
        return "medium"
    return "hard"


def _make_task(trace: dict, probe_id: str | None, dim: str, seq: int) -> dict:
    seed     = _sim_seed(trace["simulation_id"])
    builder  = _DIM_BUILDERS[dim]
    inp, cand, rubric = builder(probe_id or dim + "-XX", seed)

    task_id_str = f"TB-{dim}-TD-{seq:04d}"
    return {
        "task_id": task_id_str,
        "seed_dimension": dim,
        "dimension": {
            "SOC": "signal_over_claiming",
            "BOC": "bench_over_commitment",
            "TD":  "tone_drift",
            "SR":  "signal_reliability",
            "MTL": "multi_thread_leakage",
            "ICP": "icp_misclassification",
        }[dim],
        "source_mode": "trace_derived",
        "difficulty": _difficulty(trace["duration"]),
        "input": inp,
        "scoring_rubric": rubric,
        "candidate_output": cand,
        "ground_truth": {
            "expected_pass": trace["reward"] >= 1.0,
            "passing_score": 0.70,
        },
        "metadata": {
            "source_trace_id": trace["simulation_id"],
            "source_task_id":  trace["task_id"],
            "probe_id":        probe_id,
            "duration_s":      trace["duration"],
            "agent_cost_usd":  trace["agent_cost"],
            "domain":          trace["domain"],
        },
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

TARGET = 110
INPUT_PATH  = Path("week_10_artifacts/trace_log.jsonl")
OUTPUT_PATH = Path("generation_scripts/trace_derived_raw.jsonl")


def main() -> None:
    if not INPUT_PATH.exists():
        print(f"ERROR: {INPUT_PATH} not found", file=sys.stderr)
        sys.exit(1)

    traces = []
    with open(INPUT_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            # simulation_id is the trace_id equivalent — skip if empty
            if rec.get("simulation_id", ""):
                traces.append(rec)

    print(f"Loaded {len(traces)} traces with non-empty simulation_id")

    # Separate mapped (known probe) traces from unmapped ones
    mapped   = [t for t in traces if int(t["task_id"]) in TASK_ID_TO_PROBE]
    unmapped = [t for t in traces if int(t["task_id"]) not in TASK_ID_TO_PROBE]

    print(f"  Mapped (known probe):   {len(mapped)}")
    print(f"  Unmapped (inferred dim):{len(unmapped)}")

    # Sample unmapped to fill up to TARGET
    rng = random.Random(42)
    rng.shuffle(unmapped)
    n_unmapped_needed = max(0, TARGET - len(mapped))
    selected_unmapped = unmapped[:n_unmapped_needed]

    tasks = []
    seq   = 1

    for trace in mapped:
        tid   = int(trace["task_id"])
        probe = TASK_ID_TO_PROBE[tid]
        dim   = PROBE_TO_DIM[probe]
        tasks.append(_make_task(trace, probe, dim, seq))
        seq += 1

    for trace in selected_unmapped:
        tid = int(trace["task_id"])
        dim = _FALLBACK_DIMS[tid % len(_FALLBACK_DIMS)]
        tasks.append(_make_task(trace, None, dim, seq))
        seq += 1

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for task in tasks:
            f.write(json.dumps(task) + "\n")

    print(f"Wrote {len(tasks)} tasks -> {OUTPUT_PATH}")

    # Spot-check: every task must have required fields
    errors = 0
    for task in tasks:
        for field in ("task_id", "source_mode", "scoring_rubric", "input", "candidate_output"):
            if field not in task:
                print(f"  MISSING FIELD '{field}' in {task.get('task_id', '?')}", file=sys.stderr)
                errors += 1
        if not task.get("scoring_rubric"):
            print(f"  EMPTY scoring_rubric in {task['task_id']}", file=sys.stderr)
            errors += 1

    if errors:
        print(f"Validation: {errors} errors", file=sys.stderr)
        sys.exit(1)

    print(f"Validation: all {len(tasks)} tasks pass field check")
    if len(tasks) < 90:
        print(f"WARNING: only {len(tasks)} tasks — target is ≥90", file=sys.stderr)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
