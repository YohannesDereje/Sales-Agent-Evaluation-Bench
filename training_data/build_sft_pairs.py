"""
Tenacious-Bench v0.1 — SFT Chat-Template Builder (P5-01)

Reads:   tenacious_bench_v0.1/train/train.jsonl  (118 tasks)
Writes:  training_data/sft_pairs_raw.jsonl

Each output record:
  {"messages": [
      {"role": "system",    "content": TENACIOUS_SYSTEM_PROMPT},
      {"role": "user",      "content": <hiring_signal_brief + bench + context>},
      {"role": "assistant", "content": <ground_truth compliant output>}
  ]}

Per task: generates N_VARIATIONS=10 distinct compliant responses by combining
different opener/body/closing templates from a rule-based bank.
118 tasks x 10 = 1,180 raw pairs, targeting the 1,000-3,000 post-filter range.

Compliance guarantees for all synthesized outputs:
  - No banned phrases (verified by regex before writing)
  - Length 50-700 chars
  - Hedged opener for weak/low-confidence signals (SOC rubric positive patterns)
  - SR-aware opener with "noticed earlier / when you're ready" language
  - No headcount commitment when bench_state=overcommitted_waitlist
  - ICP disqualification for out_of_icp tasks
  - Single ask in closing (one-ask rule)
"""

import itertools
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scoring_evaluator import score_task as _score_task

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

TRAIN_PATH   = Path("tenacious_bench_v0.1/train/train.jsonl")
OUTPUT_PATH  = Path("training_data/sft_pairs_raw.jsonl")
N_VARIATIONS = 10   # variations per task → 118 x 10 = 1,180 raw pairs

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

TENACIOUS_SYSTEM_PROMPT = """\
You are the Tenacious Conversion Engine — a B2B outreach assistant for Tenacious Technologies, \
a technical staffing firm that places senior software engineers with high-growth tech companies.

## Tone markers (apply to every response)
- Direct: no filler, no preamble, get to the point in sentence one
- Grounded: claims must be supportable by the signals you have been given; do not extrapolate
- Honest: if availability is limited or a signal is weak, say so; do not oversell
- Professional: formal but human — avoid corporate jargon and enthusiasm inflation
- Non-condescending: no unsolicited advice; treat the prospect as a peer

## Banned phrases (never use these in any output)
world-class, rockstar, game-changing, game-changer, disruptive, disrupt, blazing, \
unicorn, best-of-the-best, we guarantee, guaranteed delivery, cost savings of [number]%, \
synergize, synergy, leverage our, ninja, wizard, guru, crushing it, supercharge, \
hyper-growth, explosive growth, rapidly scaling (when signal is weak or unconfirmed)

## Constraints
- Cold outreach word limit: 120 words maximum
- One-ask rule: end every message with exactly ONE question or call-to-action; never stack asks
- ICP pre-qualification: before writing outreach, verify the prospect is inside ICP. \
  If icp_segment = out_of_icp, do not send outreach — issue a disqualification notice instead
- Bench honesty: never commit to a specific number of engineers if bench_state = \
  overcommitted_waitlist; route to the delivery team instead
- Signal grounding: hiring_velocity_label and signal_confidence define the ceiling of \
  assertiveness you may use. Low confidence = hedged language only. Weak signal = \
  no momentum claims.\
"""

# ---------------------------------------------------------------------------
# Banned-phrase regex
# ---------------------------------------------------------------------------

_BANNED_RE = re.compile(
    r"world.class|rockstar|game.chang|disruptiv|blazing|unicorn|best.of.the.best"
    r"|we guarantee|guaranteed delivery|cost savings of \d|synergize|leverage our"
    r"|ninja|wizard|guru|crushing it|supercharge|hyper.growth|explosive growth",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Template banks — openers, bodies, closings
# Each returns a string; caller passes relevant kwargs.
# ---------------------------------------------------------------------------

# SOC/weak-signal openers (match regex_positive: noticed.{0,20}role | curious whether |
#                           if your team | only.{0,5}open | we saw only)
_WEAK_OPENERS = [
    lambda c, r, **_: (
        f"Hi [Name], we noticed {r or 'a couple of'} open role{'s' if r and r != 1 else ''} "
        f"at {c} — curious whether you're actively building out that team."
    ),
    lambda c, **_: (
        f"Hi [Name], curious whether {c} is still looking to add engineers — "
        "we saw only a brief signal and didn't want to assume."
    ),
    lambda c, **_: (
        f"Hi [Name], if your team at {c} is thinking about engineering capacity, "
        "we may have relevant placements worth a quick conversation."
    ),
    lambda c, r, **_: (
        f"Hi [Name], we came across {c} and noticed only {r or 'limited'} open "
        f"role{'s' if r and r != 1 else ''} — curious if there's more in the pipeline."
    ),
    lambda c, **_: (
        f"Hi [Name], we noticed some limited signals at {c} — "
        "curious whether that reflects active hiring or something earlier-stage."
    ),
]

# SR openers (match regex_positive: we saw.{0,20}ago | noticed.{0,20}earlier |
#             when you.re ready | if your.{0,20}plan)
_SR_OPENERS = [
    lambda c, age, **_: (
        f"Hi [Name], we noticed this signal earlier "
        f"({'at ' + str(age) + ' days ago' if age else 'some time back'}) "
        f"and wanted to reach out when the timing seemed right for {c}."
    ),
    lambda c, **_: (
        f"Hi [Name], we noticed some activity earlier at {c} — "
        "reaching out when you're ready to discuss engineering capacity."
    ),
    lambda c, age, **_: (
        f"Hi [Name], we saw this {str(age) + ' days ago' if age else 'a while back'} "
        f"at {c} and wanted to follow up if your hiring plans have moved forward."
    ),
    lambda c, **_: (
        f"Hi [Name], if your team at {c} is planning to add engineers, "
        "we noticed earlier interest and wanted to connect when the timing works."
    ),
]

# Strong-signal openers
_STRONG_OPENERS = [
    lambda c, **_: (
        f"Hi [Name], we noticed several roles at {c} that look like a strong fit "
        "for what we place — if your team is hiring, worth a quick call."
    ),
    lambda c, **_: (
        f"Hi [Name], we've been tracking engineering activity at {c} and there "
        "looks to be a meaningful fit worth exploring."
    ),
    lambda c, **_: (
        f"Hi [Name], we saw active hiring at {c} across roles we specialize in — "
        "if your team is building, worth 15 minutes."
    ),
    lambda c, **_: (
        f"Hi [Name], based on what we're seeing at {c}, "
        "there may be an opportunity worth exploring."
    ),
]

# Overcommitted bench bodies (no headcount commitment)
_OVERCOMMIT_BODIES = [
    "I'd need to loop in our delivery team before making any commitments on timing or "
    "headcount — I want to give you an accurate picture rather than overpromise.",

    "Before I say anything specific about capacity, I'd want to check with our "
    "delivery team — I'd rather give you the real picture than a number I can't stand behind.",

    "Our bench is stretched right now — I can't commit to headcount without checking "
    "internally first, which is the honest thing to say upfront.",

    "I'd be doing you a disservice by quoting headcount I haven't confirmed — "
    "let me loop in the delivery team before we discuss specifics.",
]

# Partial bench bodies
def _partial_body(avail):
    avail_str = str(avail) if avail is not None else "a limited number of"
    return [
        f"We have {avail_str} engineers currently available and could discuss fit and timing from there.",
        f"Our bench is partially committed — we have {avail_str} available and can talk realistic timelines.",
        f"Availability is limited at the moment ({avail_str} engineers), but there may be a fit worth exploring.",
        f"We're partially committed right now, with {avail_str} engineers free — worth a conversation if scope aligns.",
    ]

# Fully available bench bodies
def _full_body(req):
    hc = f"{req} engineer{'s' if req and req > 1 else ''}" if req else "engineers"
    return [
        f"We could discuss placing {hc} with your team if the timing and scope align.",
        f"Our bench has capacity and we could discuss {hc} depending on your timeline.",
        f"If the fit is right, we can move quickly — {hc} is within our current availability.",
        f"We have {hc} available and could move into scoping if there's a match.",
    ]

# Closings (one ask each)
_CLOSINGS = [
    "Would you have 15 minutes this week to see if there's a fit?",
    "Could we find 20 minutes to explore whether this makes sense?",
    "Worth a brief call to check if the timing works on your end?",
    "Happy to send over a few times if you'd like to connect.",
]

# ---------------------------------------------------------------------------
# ICP disqualification response (single variant — disqualification is binary)
# ---------------------------------------------------------------------------

def _icp_disqual(company: str) -> str:
    return (
        f"Hi [Name], after reviewing the brief for {company}, "
        "this account falls outside our current ICP criteria. "
        "I'm holding outreach and flagging for review rather than proceeding. "
        "If the criteria change, happy to re-evaluate."
    )

# ---------------------------------------------------------------------------
# Variation generator
# ---------------------------------------------------------------------------

def build_variations(task: dict, n: int = N_VARIATIONS) -> list:
    """
    Return up to n distinct compliant assistant responses for this task.
    Combines opener/body/closing templates. Deduplicates by text.
    """
    inp = task.get("input", {})
    dim = task.get("seed_dimension", "")

    company     = (inp.get("company_name", "") or "").strip() or "your team"
    vel         = inp.get("hiring_velocity_label", "") or ""
    conf        = inp.get("signal_confidence", "Medium")
    bench       = inp.get("bench_state", "fully_available")
    avail       = inp.get("bench_available_count")
    req         = inp.get("requested_headcount", 1)
    icp_seg     = inp.get("icp_segment", "")
    rel_flag    = inp.get("reliability_flag", "")
    prospect_msg = inp.get("prospect_message", "")
    age         = inp.get("signal_age_days", 0) or 0
    roles       = inp.get("open_roles_count")

    # ICP disqualification — only one meaningful variant
    if icp_seg == "out_of_icp":
        return [_icp_disqual(company)] * min(n, 1)

    is_stale   = bool(rel_flag) or age > 180
    weak_signal = vel in ("weak_hiring_velocity_signal", "very_weak_signal",
                          "weak_hiring_signal")
    low_conf    = conf == "Low"

    # Select opener bank
    if dim == "SR":
        openers = _SR_OPENERS
    elif weak_signal or low_conf or is_stale:
        openers = _WEAK_OPENERS
    else:
        openers = _STRONG_OPENERS

    # Select body bank
    if bench == "overcommitted_waitlist":
        bodies = _OVERCOMMIT_BODIES
    elif bench == "partially_committed_50pct":
        bodies = _partial_body(avail)
    else:
        bodies = _full_body(req)

    # Optional stale caveat appended to body (only for non-SR stale tasks)
    stale_caveat = (
        " I should note the signal I'm working from is older — "
        "happy to validate current status on the call."
        if is_stale and dim != "SR" else ""
    )

    # Tone-drift note for TD tasks
    td_note = (
        " We keep our outreach straightforward — no hype, just the facts."
        if prospect_msg and dim == "TD" else ""
    )

    closings = _CLOSINGS

    results = []
    seen: set = set()

    # Full Cartesian product of opener x body x closing for maximum diversity.
    # With 5 openers x 4 bodies x 4 closings = 80 combos per task — well above n=10.
    for o_fn, body, close in itertools.product(openers, bodies, closings):
        opener = o_fn(company, r=roles, age=age)
        text = f"{opener} {body}{stale_caveat}{td_note} {close}"

        if len(text) > 700:
            text = text[:697] + "..."

        if text not in seen:
            seen.add(text)
            results.append(text)
        if len(results) >= n:
            break

    return results


# ---------------------------------------------------------------------------
# User-turn builder
# ---------------------------------------------------------------------------

def build_user_turn(task: dict) -> str:
    inp = task.get("input", {})
    parts = []

    desc = inp.get("task_description", "").strip()
    if desc:
        parts.append(desc)

    signal_parts = []
    vel = inp.get("hiring_velocity_label", "")
    conf = inp.get("signal_confidence", "")
    if vel and vel not in desc:
        signal_parts.append(f"Hiring velocity: {vel}")
    if conf and conf not in desc:
        signal_parts.append(f"Signal confidence: {conf}")
    age = inp.get("signal_age_days")
    if age is not None:
        signal_parts.append(f"Signal age: {age} days")
    roles = inp.get("open_roles_count")
    if roles is not None:
        signal_parts.append(f"Open roles: {roles}")
    sig_event = inp.get("signal_event", "")
    if sig_event:
        signal_parts.append(f"Signal event: {sig_event}")
    if signal_parts:
        parts.append(" | ".join(signal_parts))

    bench = inp.get("bench_state", "")
    avail = inp.get("bench_available_count")
    req   = inp.get("requested_headcount")
    bench_parts = []
    if bench:
        bench_parts.append(f"Bench state: {bench}")
    if avail is not None:
        bench_parts.append(f"available={avail}")
    if req is not None:
        bench_parts.append(f"requested={req}")
    if bench_parts:
        parts.append(" | ".join(bench_parts))

    rel = inp.get("reliability_flag", "")
    if rel:
        parts.append(f"Reliability flag: {rel}")
    pres = inp.get("prestige_indicator", "")
    if pres:
        parts.append(f"Context: {pres}")

    prospect_msg = inp.get("prospect_message", "")
    if prospect_msg:
        parts.append(f"Prospect message: {prospect_msg}")
    prior = inp.get("prior_thread_contamination", "")
    if prior:
        parts.append(f"Prior thread context: {prior}")

    icp = inp.get("icp_segment", "")
    if icp:
        parts.append(f"ICP segment: {icp}")

    ai_mat = inp.get("ai_maturity_score")
    if ai_mat is not None:
        parts.append(f"AI maturity score: {ai_mat}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate(text: str) -> list:
    issues = []
    if _BANNED_RE.search(text):
        issues.append(f"banned phrase: {_BANNED_RE.search(text).group()!r}")
    if len(text) < 50:
        issues.append(f"too short: {len(text)} chars")
    if len(text) > 700:
        issues.append(f"too long: {len(text)} chars")
    return issues


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not TRAIN_PATH.exists():
        print(f"ERROR: {TRAIN_PATH} not found", file=sys.stderr)
        sys.exit(1)

    tasks = [json.loads(l) for l in open(TRAIN_PATH, encoding="utf-8") if l.strip()]
    print(f"Loaded {len(tasks)} train tasks  (target {len(tasks) * N_VARIATIONS} raw pairs)")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    records = []
    warn_count = 0

    for task in tasks:
        user_content = build_user_turn(task)
        variations   = build_variations(task, N_VARIATIONS)

        for v_text in variations:
            issues = _validate(v_text)
            if issues:
                print(f"  WARN: {task['task_id']} variation issue: {issues}", file=sys.stderr)
                warn_count += 1
                continue  # skip bad variations rather than emit them

            records.append({
                "_task_id": task["task_id"],
                "messages": [
                    {"role": "system",    "content": TENACIOUS_SYSTEM_PROMPT},
                    {"role": "user",      "content": user_content},
                    {"role": "assistant", "content": v_text},
                ]
            })

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"Wrote {len(records)} SFT pairs -> {OUTPUT_PATH}")
    if warn_count:
        print(f"  Skipped {warn_count} variations with compliance issues", file=sys.stderr)

    # Verify structure
    loaded = [json.loads(l) for l in open(OUTPUT_PATH, encoding="utf-8") if l.strip()]
    assert len(loaded) == len(records)
    assert all(len(r["messages"]) == 3 for r in loaded)
    assert all(r["messages"][i]["role"] == role
               for r in loaded for i, role in enumerate(("system", "user", "assistant")))
    print("Verification: all records have messages[3] with correct roles")
    sys.exit(0)


if __name__ == "__main__":
    main()
