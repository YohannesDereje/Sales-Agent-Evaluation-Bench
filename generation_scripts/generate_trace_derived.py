"""
Tenacious-Bench: Trace-Derived Task Generator
Converts Week 10 trace_log.jsonl records into Tenacious-Bench evaluation tasks.
Filters to records with non-empty trace_id, then generates 2-3 variants per trace.

Output: generation_scripts/trace_derived_raw.jsonl  (target ≥90 tasks)

Run:
    python generation_scripts/generate_trace_derived.py
"""

import json
import random
import sys
from pathlib import Path

RANDOM_SEED = 42
random.seed(RANDOM_SEED)

# ---------------------------------------------------------------------------
# Task_id → (probe_id, dimension) mapping
# Derived from probe_library.md failure signatures
# ---------------------------------------------------------------------------

TASK_ID_TO_PROBE = {
    0:  ("SR-01",  "signal_reliability"),
    1:  ("SOC-01", "signal_over_claiming"),      # Documented in audit_memo — bcef6c8e
    2:  ("BOC-01", "bench_over_commitment"),
    3:  ("TD-01",  "tone_drift"),
    4:  ("ICP-01", "icp_misclassification"),
    5:  ("SOC-01", "signal_over_claiming"),      # 14-turn failure — 9880a74a
    6:  ("TD-02",  "tone_drift"),                # Tone-related — 8630d83f
    7:  ("BOC-02", "bench_over_commitment"),     # Signal grounding — 4a7f4b2a
    8:  ("SR-02",  "signal_reliability"),
    9:  ("MTL-01", "multi_thread_leakage"),
    10: ("ICP-02", "icp_misclassification"),
    11: ("SR-01",  "signal_reliability"),
    12: ("GOC-01", "gap_over_claiming"),
    13: ("BOC-01", "bench_over_commitment"),
    14: ("TD-03",  "tone_drift"),
    15: ("SOC-02", "signal_over_claiming"),
    16: ("CP-01",  "cost_pathology"),
    17: ("CP-01",  "cost_pathology"),
    18: ("MTL-02", "multi_thread_leakage"),
    19: ("DCC-01", "dual_control_coordination"),
    20: ("GOC-02", "gap_over_claiming"),
    21: ("SE-01",  "scheduling_edge_case"),
    22: ("GOC-01", "gap_over_claiming"),
    23: ("ICP-03", "icp_misclassification"),
    24: ("SR-03",  "signal_reliability"),
    25: ("SR-02",  "signal_reliability"),
    26: ("BOC-02", "bench_over_commitment"),
    27: ("TD-01",  "tone_drift"),
    28: ("MTL-03", "multi_thread_leakage"),
    29: ("SE-02",  "scheduling_edge_case"),
}

# ---------------------------------------------------------------------------
# Difficulty from trace metrics
# ---------------------------------------------------------------------------

def assign_difficulty(duration_s: float, turns: int, passed: bool) -> str:
    if turns <= 1:
        return "easy"   # Single-turn failures are usually clear-cut
    if duration_s < 70 and passed:
        return "easy"
    if duration_s < 120:
        return "medium"
    if duration_s < 200:
        return "hard" if not passed else "medium"
    return "hard"


# ---------------------------------------------------------------------------
# Company / signal pools for trace-derived tasks
# ---------------------------------------------------------------------------

COMPANIES_BY_TASK_ID = {
    0:  ("Solaris Data Corp",       "mid_market_50_500",  "segment_2_mid_market_restructure"),
    1:  ("Meridian Analytics",      "mid_market_50_500",  "segment_2_mid_market_restructure"),
    2:  ("Apex Cloud Systems",      "enterprise_500plus", "segment_3_enterprise_ai_build"),
    3:  ("Prism Ventures",          "startup_under50",    "segment_1_startup_hypergrowth"),
    4:  ("Cascade Digital",         "mid_market_50_500",  "segment_2_mid_market_restructure"),
    5:  ("Trellis Tech Ltd",        "mid_market_50_500",  "segment_2_mid_market_restructure"),
    6:  ("Nova Dev Studio",         "startup_under50",    "segment_1_startup_hypergrowth"),
    7:  ("Ironwood Systems",        "enterprise_500plus", "segment_3_enterprise_ai_build"),
    8:  ("Harbor Analytics",        "mid_market_50_500",  "segment_2_mid_market_restructure"),
    9:  ("Ridgeline Software",      "enterprise_500plus", "segment_3_enterprise_ai_build"),
    10: ("Strata Build Inc",        "startup_under50",    "segment_1_startup_hypergrowth"),
    11: ("Clearpath Digital",       "mid_market_50_500",  "segment_2_mid_market_restructure"),
    12: ("Summit Cloud Corp",       "enterprise_500plus", "segment_3_enterprise_ai_build"),
    13: ("Forge Analytics",         "mid_market_50_500",  "segment_2_mid_market_restructure"),
    14: ("Kestrel Software",        "startup_under50",    "segment_1_startup_hypergrowth"),
    15: ("Vantage Systems",         "enterprise_500plus", "segment_3_enterprise_ai_build"),
    16: ("Nimbus Code Labs",        "startup_under50",    "segment_1_startup_hypergrowth"),
    17: ("Qubit Works",             "startup_under50",    "segment_1_startup_hypergrowth"),
    18: ("Pinnacle Dev Corp",       "mid_market_50_500",  "segment_2_mid_market_restructure"),
    19: ("Watershed Analytics",     "mid_market_50_500",  "segment_2_mid_market_restructure"),
    20: ("Cornerstone Data Inc",    "enterprise_500plus", "segment_3_enterprise_ai_build"),
    21: ("Helios Apps",             "startup_under50",    "segment_1_startup_hypergrowth"),
    22: ("Atlas Digital Group",     "enterprise_500plus", "segment_3_enterprise_ai_build"),
    23: ("Luminary AI",             "startup_under50",    "segment_1_startup_hypergrowth"),
    24: ("Keystone Engineering",    "enterprise_500plus", "segment_3_enterprise_ai_build"),
    25: ("Bluestone Technologies",  "mid_market_50_500",  "segment_2_mid_market_restructure"),
    26: ("Vectral Labs",            "startup_under50",    "segment_1_startup_hypergrowth"),
    27: ("Axion Systems",           "mid_market_50_500",  "segment_2_mid_market_restructure"),
    28: ("Colossus Platform",       "enterprise_500plus", "segment_3_enterprise_ai_build"),
    29: ("Crest Systems",           "mid_market_50_500",  "segment_2_mid_market_restructure"),
}

# Velocity based on pass/fail + turns
def infer_velocity(passed: bool, turns: int, duration_s: float) -> str:
    if passed and turns <= 7:
        return "strong_signal"
    if passed:
        return "moderate_signal"
    if not passed and duration_s > 150:
        return "weak_hiring_velocity_signal"
    if not passed and turns == 1:
        return "very_weak_signal"
    return "weak_hiring_velocity_signal"


def infer_signal_confidence(passed: bool, turns: int) -> str:
    if passed and turns <= 7:
        return "high"
    if passed:
        return "medium"
    return "low"


def infer_funding(velocity: str) -> str:
    m = {
        "strong_signal":               "Series B (2 months ago)",
        "moderate_signal":             "Series A (8 months ago)",
        "weak_hiring_velocity_signal": "Series A (16 months ago)",
        "very_weak_signal":            "Seed (24 months ago)",
    }
    return m.get(velocity, "Series A (12 months ago)")


STACKS_BY_TASK_ID = {
    0:  ["Python", "AWS"],         1:  ["Python", "Django", "AWS"],
    2:  ["Go", "Kubernetes", "GCP"], 3:  ["TypeScript", "React"],
    4:  ["Python", "FastAPI"],     5:  ["Python", "AWS", "Django"],
    6:  ["Rust", "WASM"],          7:  ["Python", "PyTorch", "GCP"],
    8:  ["Java", "Spring", "AWS"], 9:  ["Scala", "Spark"],
    10: ["Go", "GCP"],             11: ["Python", "Flask", "Azure"],
    12: ["C++", "CUDA"],           13: ["Python", "Kubernetes"],
    14: ["TypeScript", "Node.js"], 15: ["Python", "ML", "AWS"],
    16: ["Python", "Pandas"],      17: ["Ruby", "Rails"],
    18: ["PHP", "Laravel"],        19: ["Python", "Airflow"],
    20: ["Kotlin", "Android"],     21: ["Swift", "iOS"],
    22: ["Python", "TensorFlow"],  23: ["Go", "gRPC"],
    24: ["Java", "Kafka"],         25: ["Python", "dbt", "Snowflake"],
    26: ["TypeScript", "GraphQL"], 27: ["Rust", "Tokio"],
    28: ["Python", "Ray"],         29: ["Elixir", "Phoenix"],
}

SIGNAL_TEXTS = {
    "signal_over_claiming": {
        "weak_hiring_velocity_signal": "Backend Engineer role posted 7 weeks ago, 0 listed applicants, unchanged",
        "very_weak_signal":            "Software Engineer role posted 5 months ago, no repost, no applicant activity",
        "moderate_signal":             "2 engineering roles posted this month, moderate applicant activity",
        "strong_signal":               "3 engineering roles posted, active applicants, reposted twice this month",
    },
    "bench_over_commitment": {
        "weak_hiring_velocity_signal": "ML Engineer role posted last month, low activity",
        "very_weak_signal":            "Platform Engineer role, dormant posting, 3 months old",
        "moderate_signal":             "Engineering manager seeking 2 senior backend hires",
        "strong_signal":               "Hiring spree — 4 engineering roles posted concurrently",
    },
    "tone_drift": {
        "weak_hiring_velocity_signal": "Company press release uses aggressive startup language",
        "very_weak_signal":            "Founder LinkedIn post: 'We're disrupting everything'",
        "moderate_signal":             "Casual job description: 'Looking for coding wizards'",
        "strong_signal":               "Formal enterprise job posting, professional tone",
    },
    "signal_reliability": {
        "weak_hiring_velocity_signal": "Funding announced 16 months ago — no follow-on signal detected",
        "very_weak_signal":            "Last funding round 24 months ago — Crunchbase data may be stale",
        "moderate_signal":             "Series A 8 months ago — growth trajectory unclear",
        "strong_signal":               "Series B closed last quarter — headcount expansion announced",
    },
    "multi_thread_leakage": {
        "weak_hiring_velocity_signal": "Two open engineering roles at company with multiple contacts",
        "moderate_signal":             "Engineering team split across two sites — separate threads active",
        "strong_signal":               "Multiple hiring managers identified — outreach to be isolated per contact",
        "very_weak_signal":            "Contact list includes legacy CRM entries — possible stale contacts",
    },
    "icp_misclassification": {
        "weak_hiring_velocity_signal": "Company profile ambiguous — could be segment 1 or 2",
        "very_weak_signal":            "Acting CTO title — unclear if permanent decision-maker",
        "moderate_signal":             "Mid-market company with startup-stage engineering practices",
        "strong_signal":               "Clear enterprise profile — standard ICP classification",
    },
    "gap_over_claiming": {
        "weak_hiring_velocity_signal": "Competitor gap analysis based on limited LinkedIn data",
        "very_weak_signal":            "Gap brief derived from 6-month-old competitive intelligence",
        "moderate_signal":             "Competitor recently lost key engineers — indirect signal",
        "strong_signal":               "Competitor openly advertising inability to hire — direct signal",
    },
    "cost_pathology": {
        "weak_hiring_velocity_signal": "Malformed hiring brief — missing required fields",
        "very_weak_signal":            "Empty company description causing token bloat in prompt",
        "moderate_signal":             "Unusually long prospect notes triggering cost spike",
        "strong_signal":               "Standard input — no cost pathology expected",
    },
    "dual_control_coordination": {
        "weak_hiring_velocity_signal": "Cal.com slot unavailable — booking system returns 404",
        "very_weak_signal":            "HubSpot contact deduplication failure — duplicate records",
        "moderate_signal":             "Resend API rate limit during outreach batch",
        "strong_signal":               "All integrations healthy — standard booking flow",
    },
    "scheduling_edge_case": {
        "weak_hiring_velocity_signal": "Prospect in UTC+5:30 — timezone conversion required",
        "very_weak_signal":            "Prospect requested a slot that has already passed",
        "moderate_signal":             "Prospect across daylight saving time boundary",
        "strong_signal":               "Standard US timezone — no edge case",
    },
}


# ---------------------------------------------------------------------------
# Ground truth builders per dimension (simplified for trace-derived)
# ---------------------------------------------------------------------------

def build_ground_truth_for_dimension(dimension: str, velocity: str,
                                     bench_state: str = "partially_available_50pct",
                                     headcount: int = 2) -> dict:
    if dimension == "signal_over_claiming":
        is_weak = velocity in ("weak_hiring_velocity_signal", "very_weak_signal")
        if is_weak:
            return {
                "passing_criteria": {
                    "no_assertive_velocity_claim": {
                        "description": "Must not assert hiring velocity when signal is weak",
                        "check_type": "regex_negative",
                        "banned_patterns": [
                            "rapidly scal", "aggressive.*hir", "significant.*growth",
                            "expanding.*team", "fast.*grow", "explosive.*growth",
                            "massive.*hir", "scaling.*fast", "rapid.*growth", "growing.*fast"
                        ]
                    },
                    "signal_referenced": {
                        "description": "Must reference the specific role or signal",
                        "check_type": "regex_positive",
                        "required_patterns": ["[Ee]ngineer", "role", "position", "posting"]
                    },
                    "calendar_link_present": {
                        "description": "Must include calendar CTA",
                        "check_type": "regex_positive",
                        "required_patterns": ["cal\\.com", "calendly", "[Bb]ook", "[Ss]chedule", "30.*min"]
                    }
                },
                "scoring": {
                    "no_assertive_velocity_claim": 0.45,
                    "signal_referenced": 0.30,
                    "calendar_link_present": 0.25
                }
            }
        else:
            return {
                "passing_criteria": {
                    "signal_referenced": {
                        "description": "Must reference the signal",
                        "check_type": "regex_positive",
                        "required_patterns": ["[Ee]ngineer", "role", "position"]
                    },
                    "calendar_link_present": {
                        "description": "Must include calendar CTA",
                        "check_type": "regex_positive",
                        "required_patterns": ["cal\\.com", "calendly", "[Bb]ook", "[Ss]chedule"]
                    }
                },
                "scoring": {"signal_referenced": 0.55, "calendar_link_present": 0.45}
            }

    elif dimension == "bench_over_commitment":
        available = max(1, headcount // 2) if bench_state == "partially_available_50pct" else headcount
        return {
            "passing_criteria": {
                "no_over_commitment": {
                    "description": f"Must not offer more than {available} engineer(s)",
                    "check_type": "regex_negative",
                    "banned_patterns": [
                        f"[Ww]e have {n} engineer" for n in range(available + 1, available + 4)
                    ] + ["full.*team.*ready", "entire.*team.*available"]
                },
                "availability_qualified": {
                    "description": "Must qualify or acknowledge bench availability",
                    "check_type": "regex_positive",
                    "required_patterns": ["availab", "capacit", "limited", "current.*bench"]
                },
                "calendar_link_present": {
                    "description": "Must include calendar CTA",
                    "check_type": "regex_positive",
                    "required_patterns": ["cal\\.com", "calendly", "[Bb]ook", "[Ss]chedule"]
                }
            },
            "scoring": {
                "no_over_commitment": 0.50,
                "availability_qualified": 0.25,
                "calendar_link_present": 0.25
            }
        }

    elif dimension == "tone_drift":
        return {
            "passing_criteria": {
                "no_hype_mirroring": {
                    "description": "Must not mirror hype/aggressive prospect language",
                    "check_type": "regex_negative",
                    "banned_patterns": [
                        "CRUSH", "DOMINATE", "!!!", "move fast.*break",
                        "game.?changer", "rocket ship", "crushing it",
                        "killing it", "superstar", "ninja", "rockstar"
                    ]
                },
                "signal_referenced": {
                    "description": "Must reference the engineering need",
                    "check_type": "regex_positive",
                    "required_patterns": ["[Ee]ngineer", "team", "role", "staffing"]
                },
                "calendar_link_present": {
                    "description": "Must include calendar CTA",
                    "check_type": "regex_positive",
                    "required_patterns": ["cal\\.com", "calendly", "[Bb]ook", "[Ss]chedule"]
                }
            },
            "scoring": {
                "no_hype_mirroring": 0.40,
                "signal_referenced": 0.35,
                "calendar_link_present": 0.25
            }
        }

    elif dimension == "signal_reliability":
        is_stale = velocity in ("weak_hiring_velocity_signal", "very_weak_signal")
        if is_stale:
            return {
                "passing_criteria": {
                    "no_stale_signal_assertion": {
                        "description": "Must not assert funding/growth as current when signal is stale",
                        "check_type": "regex_negative",
                        "banned_patterns": [
                            "recent.*fund", "just.*raised", "fresh.*capital",
                            "new.*investment", "latest.*round", "recently.*closed"
                        ]
                    },
                    "calendar_link_present": {
                        "description": "Must include calendar CTA",
                        "check_type": "regex_positive",
                        "required_patterns": ["cal\\.com", "calendly", "[Bb]ook", "[Ss]chedule"]
                    }
                },
                "scoring": {
                    "no_stale_signal_assertion": 0.55,
                    "calendar_link_present": 0.45
                }
            }
        else:
            return {
                "passing_criteria": {
                    "signal_referenced": {
                        "description": "Must reference the signal",
                        "check_type": "regex_positive",
                        "required_patterns": ["[Ee]ngineer", "fund", "team", "role"]
                    },
                    "calendar_link_present": {
                        "description": "Must include calendar CTA",
                        "check_type": "regex_positive",
                        "required_patterns": ["cal\\.com", "calendly", "[Bb]ook", "[Ss]chedule"]
                    }
                },
                "scoring": {"signal_referenced": 0.55, "calendar_link_present": 0.45}
            }

    else:
        # Default rubric for MTL, ICP, GOC, CP, DCC, SE
        return {
            "passing_criteria": {
                "signal_referenced": {
                    "description": "Email must reference the relevant signal or context",
                    "check_type": "regex_positive",
                    "required_patterns": ["[Ee]ngineer", "team", "role", "staffing", "hire"]
                },
                "calendar_link_present": {
                    "description": "Must include calendar CTA",
                    "check_type": "regex_positive",
                    "required_patterns": ["cal\\.com", "calendly", "[Bb]ook", "[Ss]chedule", "30.*min"]
                },
                "length_appropriate": {
                    "description": "Email must be plausible outreach length",
                    "check_type": "length_check",
                    "min_chars": 200,
                    "max_chars": 2000
                }
            },
            "scoring": {
                "signal_referenced": 0.40,
                "calendar_link_present": 0.35,
                "length_appropriate": 0.25
            }
        }


# ---------------------------------------------------------------------------
# Variant parameter sets
# ---------------------------------------------------------------------------

VARIANT_VELOCITY_SHIFTS = [
    "weak_hiring_velocity_signal",
    "very_weak_signal",
    "moderate_signal",
]

VARIANT_BENCH_STATES = [
    "partially_available_50pct",
    "overcommitted_waitlist",
    "fully_available",
]


# ---------------------------------------------------------------------------
# Task ID counter
# ---------------------------------------------------------------------------
_counters: dict = {}

def next_task_id(dim_code: str) -> str:
    _counters[dim_code] = _counters.get(dim_code, 200) + 1
    return f"TB-{dim_code}-{_counters[dim_code]:03d}"

DIM_TO_CODE = {
    "signal_over_claiming":    "SOC",
    "bench_over_commitment":   "BOC",
    "tone_drift":              "TD",
    "signal_reliability":      "SR",
    "multi_thread_leakage":    "MTL",
    "icp_misclassification":   "ICP",
    "gap_over_claiming":       "GOC",
    "cost_pathology":          "CP",
    "dual_control_coordination": "DCC",
    "scheduling_edge_case":    "SE",
}


# ---------------------------------------------------------------------------
# Build one task from a trace record
# ---------------------------------------------------------------------------

def build_trace_task(trace: dict, variant_idx: int) -> dict:
    task_id_raw  = int(trace.get("task_id", 0))
    trace_id     = trace.get("trace_id", "")
    passed       = trace.get("passed", False)
    duration_s   = trace.get("duration_s", trace.get("duration", 60.0))
    turns        = trace.get("turns", 1)

    probe_id, dimension = TASK_ID_TO_PROBE.get(task_id_raw, ("SR-01", "signal_reliability"))
    dim_code = DIM_TO_CODE.get(dimension, "SR")

    company_name, company_size, segment = COMPANIES_BY_TASK_ID.get(
        task_id_raw, ("Generic Corp", "mid_market_50_500", "segment_2_mid_market_restructure")
    )
    stack = STACKS_BY_TASK_ID.get(task_id_raw, ["Python", "AWS"])

    # Vary velocity and bench per variant
    base_velocity = infer_velocity(passed, turns, duration_s)
    velocity = VARIANT_VELOCITY_SHIFTS[variant_idx % len(VARIANT_VELOCITY_SHIFTS)]
    if variant_idx == 0:
        velocity = base_velocity  # Variant 0 keeps the original inferred value

    bench_state = VARIANT_BENCH_STATES[variant_idx % len(VARIANT_BENCH_STATES)]
    headcount   = random.choice([1, 2, 3])
    ai_maturity = round(random.choice([0.2, 0.4, 0.6, 0.8]), 1)

    signal_text = (SIGNAL_TEXTS.get(dimension, {})
                   .get(velocity, f"Engineering role signal for {company_name}"))

    difficulty = assign_difficulty(duration_s, turns, passed)
    if variant_idx >= 2:
        difficulty = "hard"

    avail_hc = max(0, headcount // 2) if bench_state == "partially_available_50pct" else (
        0 if bench_state == "overcommitted_waitlist" else headcount
    )
    avail_eng = avail_hc + 1

    ground_truth = build_ground_truth_for_dimension(dimension, velocity, bench_state, headcount)
    task_id_str  = next_task_id(dim_code)

    return {
        "task_id":              task_id_str,
        "version":              "0.1",
        "dimension":            dimension,
        "probe_id":             probe_id,
        "source_mode":          "trace_derived",
        "difficulty":           difficulty,
        "input": {
            "hiring_signal_brief": {
                "company_name":          company_name,
                "company_size":          company_size,
                "segment":               segment,
                "signal_type":           "job_posting",
                "signal_text":           signal_text,
                "signal_confidence":     infer_signal_confidence(passed, turns),
                "hiring_velocity_label": velocity,
                "ai_maturity_score":     ai_maturity,
                "stack":                 stack,
                "headcount_requested":   headcount,
                "funding_status":        infer_funding(velocity),
                "recent_news":           None
            },
            "bench_summary": {
                "available_engineers":  avail_eng,
                "available_headcount":  avail_hc,
                "specializations":      stack[:2],
                "earliest_start_weeks": random.choice([1, 2, 3, 4])
            },
            "prior_thread":     None,
            "task_instruction": (
                f"Generate a cold outreach email to the engineering hiring manager at "
                f"{company_name} about Tenacious's engineering staffing services."
            )
        },
        "candidate_output":     "",
        "ground_truth":         ground_truth,
        "scoring_rubric_version": "0.1",
        "metadata": {
            "source_trace_id":  trace_id,
            "source_task_id":   str(task_id_raw),
            "seed_probe":       probe_id,
            "params": {
                "variant_idx":           variant_idx,
                "original_passed":       passed,
                "original_duration_s":   round(duration_s, 2),
                "original_turns":        turns,
                "bench_state":           bench_state,
                "hiring_velocity_label": velocity,
            },
            "created_by":       "generate_trace_derived.py",
            "dataset_version":  "0.1",
            "synthesis_model":  None,
            "seed_dimension":   None
        }
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_valid_traces(trace_path: Path) -> list:
    """Load only records with non-empty trace_id."""
    valid = []
    with open(trace_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("trace_id", ""):
                valid.append(rec)
    return valid


def main():
    repo_root  = Path(__file__).parent.parent
    trace_path = repo_root / "week_10_artifacts" / "trace_log.jsonl"
    out_path   = Path(__file__).parent / "trace_derived_raw.jsonl"

    if not trace_path.exists():
        print(f"ERROR: trace_log.jsonl not found at {trace_path}", file=sys.stderr)
        sys.exit(1)

    traces = load_valid_traces(trace_path)
    print(f"Loaded {len(traces)} valid traces (non-empty trace_id)")

    tasks = []
    for trace in traces:
        # Generate 2-3 variants per trace
        n_variants = 3 if not trace.get("passed", True) else 2
        for v in range(n_variants):
            tasks.append(build_trace_task(trace, variant_idx=v))

    with open(out_path, "w", encoding="utf-8") as f:
        for task in tasks:
            f.write(json.dumps(task) + "\n")

    print(f"Generated {len(tasks)} trace-derived tasks -> {out_path}")

    # Validate
    errors = 0
    with open(out_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            try:
                obj = json.loads(line)
                assert "task_id" in obj
                assert obj.get("metadata", {}).get("source_trace_id") is not None
            except Exception as e:
                print(f"  Line {i} ERROR: {e}")
                errors += 1

    if errors:
        print(f"VALIDATION FAILED: {errors} invalid lines")
        sys.exit(1)
    else:
        print(f"Validation passed — all {len(tasks)} lines valid, source_trace_id present")


if __name__ == "__main__":
    main()
