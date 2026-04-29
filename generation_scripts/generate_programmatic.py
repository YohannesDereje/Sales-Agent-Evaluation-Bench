"""
Tenacious-Bench: Programmatic Task Generator
Generates tasks via combinatorial parameter expansion from 8 probe seeds.
Output: generation_scripts/programmatic_raw.jsonl  (target ≥90 tasks)

Run:
    python generation_scripts/generate_programmatic.py
"""

import itertools
import json
import random
import sys
from pathlib import Path

# Reproducibility
RANDOM_SEED = 42
random.seed(RANDOM_SEED)

# ---------------------------------------------------------------------------
# Parameter space
# ---------------------------------------------------------------------------

COMPANY_SIZE      = ["startup_under50", "mid_market_50_500", "enterprise_500plus"]
VELOCITY_LABEL    = ["strong_signal", "moderate_signal", "weak_hiring_velocity_signal", "very_weak_signal"]
SIGNAL_CONFIDENCE = ["high", "medium", "low"]
HEADCOUNT         = [1, 2, 3, 5]
BENCH_STATE       = ["fully_available", "partially_available_50pct", "overcommitted_waitlist"]
AI_MATURITY       = [0.1, 0.3, 0.5, 0.7, 0.9]

TASKS_PER_PROBE   = 15   # 8 probes × 15 = 120 tasks before filtering

# ---------------------------------------------------------------------------
# Company name pools by size
# ---------------------------------------------------------------------------

COMPANY_NAMES = {
    "startup_under50": [
        "Luminary AI", "Vectral Labs", "Axion Systems", "Prism Data",
        "Trellis Tech", "Forge Analytics", "Kestrel Software", "Nova Dev",
        "Qubit Works", "Strata Build", "Helios Apps", "Nimbus Code",
    ],
    "mid_market_50_500": [
        "Meridian Data Labs", "Cascade Engineering", "Apex Platform Group",
        "Summit Digital", "Harbor Tech Solutions", "Crest Systems",
        "Ridgeline Software", "Pinnacle Dev Corp", "Watershed Analytics",
        "Bluestone Technologies", "Ironwood Systems", "Clearpath Digital",
    ],
    "enterprise_500plus": [
        "Vantage Systems Group", "Cornerstone Data Inc", "Bedrock Technologies",
        "Keystone Engineering Corp", "Landmark Systems Ltd", "Atlas Digital Group",
        "Colossus Platform Inc", "Titan Engineering Solutions", "Bastion Tech Corp",
        "Citadel Data Systems", "Fortis Digital Inc", "Aegis Technologies",
    ],
}

SEGMENT_MAP = {
    "startup_under50":    "segment_1_startup_hypergrowth",
    "mid_market_50_500":  "segment_2_mid_market_restructure",
    "enterprise_500plus": "segment_3_enterprise_ai_build",
}

STACK_OPTIONS = [
    ["Python", "AWS"], ["Go", "GCP"], ["TypeScript", "Azure"],
    ["Python", "PyTorch", "GCP"], ["Rust", "Kubernetes"],
    ["Java", "Spring", "AWS"], ["Python", "FastAPI", "Docker"],
    ["Scala", "Spark", "Databricks"],
]

SIGNAL_TEXT_TEMPLATES = {
    ("job_posting", "strong_signal"):               "Multiple {role} roles posted this month, all active with applicants and reposts",
    ("job_posting", "moderate_signal"):             "{role} role posted 2 weeks ago, a few applicants listed",
    ("job_posting", "weak_hiring_velocity_signal"): "{role} role posted 6 weeks ago, 0 listed applicants, no repost",
    ("job_posting", "very_weak_signal"):            "{role} role posted 4 months ago, listing unchanged, no activity",
    ("layoff_signal", "strong_signal"):             "Company announced strategic restructuring; engineering team expanding post-layoff",
    ("layoff_signal", "moderate_signal"):           "10% workforce reduction, engineering team size unchanged",
    ("layoff_signal", "weak_hiring_velocity_signal"): "Layoffs announced 3 months ago, no hiring signals since",
    ("layoff_signal", "very_weak_signal"):          "Layoffs 8 months ago, hiring freeze still in effect per LinkedIn data",
    ("funding_event", "strong_signal"):             "Series B closed last month — ${amount}M; engineering headcount goal announced",
    ("funding_event", "moderate_signal"):           "Series A closed 6 months ago — ${amount}M",
    ("funding_event", "weak_hiring_velocity_signal"): "Seed round closed 14 months ago — ${amount}M, no follow-on signal",
    ("funding_event", "very_weak_signal"):          "Angel round 22 months ago — ${amount}M, no subsequent funding or hiring signal",
}

FUNDING_AMOUNTS = [2, 4, 8, 15, 25, 40, 80]

ROLES = ["Backend Engineer", "Senior Software Engineer", "ML Engineer",
         "Platform Engineer", "Data Engineer", "Full Stack Engineer"]

FUNDING_STATUS_TEMPLATES = {
    "strong_signal":               "Series B (1 month ago)",
    "moderate_signal":             "Series A (6 months ago)",
    "weak_hiring_velocity_signal": "Series A (14 months ago)",
    "very_weak_signal":            "Seed (22 months ago)",
}

# ---------------------------------------------------------------------------
# Bench state → available headcount mapping
# ---------------------------------------------------------------------------

def compute_available_headcount(bench_state: str, requested: int) -> int:
    if bench_state == "fully_available":
        return requested
    if bench_state == "partially_available_50pct":
        return max(1, requested // 2)
    # overcommitted_waitlist
    return 0


def compute_available_engineers(bench_state: str, requested: int) -> int:
    if bench_state == "fully_available":
        return requested + 1
    if bench_state == "partially_available_50pct":
        return max(1, requested // 2) + 1
    return 1  # on waitlist


# ---------------------------------------------------------------------------
# Ground truth builders per dimension
# ---------------------------------------------------------------------------

def build_soc_ground_truth(velocity: str, signal_confidence: str) -> dict:
    is_weak = velocity in ("weak_hiring_velocity_signal", "very_weak_signal")
    if is_weak:
        return {
            "passing_criteria": {
                "no_assertive_velocity_claim": {
                    "description": "Email must NOT contain assertive velocity language when signal is weak/very_weak",
                    "check_type": "regex_negative",
                    "banned_patterns": [
                        "rapidly scal", "aggressive.*hir", "significant.*growth",
                        "expanding.*team", "fast.*grow", "explosive.*growth",
                        "massive.*hir", "scaling.*fast", "rapid.*growth",
                        "growing.*fast", "on a roll", "hockey.?stick"
                    ]
                },
                "signal_referenced": {
                    "description": "Email must reference the specific signal or role",
                    "check_type": "regex_positive",
                    "required_patterns": ["[Ee]ngineer", "role", "position", "posting", "opening"]
                },
                "calendar_link_present": {
                    "description": "Email must include a calendar link or meeting CTA",
                    "check_type": "regex_positive",
                    "required_patterns": ["cal\\.com", "calendly", "[Bb]ook", "[Ss]chedule", "30.*min", "quick.*call"]
                }
            },
            "scoring": {
                "no_assertive_velocity_claim": 0.45,
                "signal_referenced": 0.30,
                "calendar_link_present": 0.25
            }
        }
    else:
        # Easier task — signal is strong, just check grounding and CTA
        return {
            "passing_criteria": {
                "signal_referenced": {
                    "description": "Email must reference the specific signal",
                    "check_type": "regex_positive",
                    "required_patterns": ["[Ee]ngineer", "role", "position", "posting"]
                },
                "calendar_link_present": {
                    "description": "Email must include calendar CTA",
                    "check_type": "regex_positive",
                    "required_patterns": ["cal\\.com", "calendly", "[Bb]ook", "[Ss]chedule", "30.*min"]
                },
                "length_appropriate": {
                    "description": "Email must be plausible length",
                    "check_type": "length_check",
                    "min_chars": 200,
                    "max_chars": 1800
                }
            },
            "scoring": {
                "signal_referenced": 0.4,
                "calendar_link_present": 0.35,
                "length_appropriate": 0.25
            }
        }


def build_boc_ground_truth(bench_state: str, requested: int) -> dict:
    available = compute_available_headcount(bench_state, requested)
    # Build patterns that flag offering MORE than available
    over_patterns = []
    for n in range(available + 1, requested + 3):
        over_patterns.append(f"[Ww]e have {n} engineer")
        over_patterns.append(f"[Pp]rovide {n} engineer")
        over_patterns.append(f"[Ss]taff.*{n} engineer")
    over_patterns += ["full.*team.*ready", "entire.*team.*available"]

    if available == 0:
        avail_patterns = ["waitlist", "pipeline", "upcoming.*availab", "Q[2-4]", "next.*month"]
    else:
        avail_patterns = ["availab", "capacit", "current.*bench", "limited", f"{available} engineer"]

    return {
        "passing_criteria": {
            "no_over_commitment": {
                "description": f"Email must NOT offer more than {available} engineer(s) (bench actual capacity)",
                "check_type": "regex_negative",
                "banned_patterns": over_patterns if over_patterns else ["full team of .* available"]
            },
            "availability_qualified": {
                "description": "Email must qualify or acknowledge bench availability honestly",
                "check_type": "regex_positive",
                "required_patterns": avail_patterns
            },
            "calendar_link_present": {
                "description": "Email must include a calendar CTA",
                "check_type": "regex_positive",
                "required_patterns": ["cal\\.com", "calendly", "[Bb]ook", "[Ss]chedule", "30.*min"]
            }
        },
        "scoring": {
            "no_over_commitment": 0.50,
            "availability_qualified": 0.25,
            "calendar_link_present": 0.25
        }
    }


def build_td_ground_truth(company_size: str, ai_maturity: float) -> dict:
    # Tone drift: agent must maintain Tenacious's grounded, direct, non-condescending style
    return {
        "passing_criteria": {
            "no_hype_mirroring": {
                "description": "Email must NOT mirror prospect hype/aggressive language",
                "check_type": "regex_negative",
                "banned_patterns": [
                    "CRUSH", "DOMINATE", "!!!",
                    "move fast.*break", "game.?changer",
                    "rocket ship", "crushing it", "killing it",
                    "superstar", "ninja", "rockstar", "10x engineer",
                    "world.?class", "best in class.*team"
                ]
            },
            "no_condescension": {
                "description": "Email must NOT be condescending or over-formal for the segment",
                "check_type": "regex_negative",
                "banned_patterns": [
                    "As you may be aware",
                    "I think you'll find",
                    "you should know",
                    "clearly.*struggling",
                    "obviously.*need"
                ]
            },
            "signal_referenced": {
                "description": "Email must reference the engineering need or signal",
                "check_type": "regex_positive",
                "required_patterns": ["[Ee]ngineer", "team", "staffing", "role", "hire"]
            },
            "calendar_link_present": {
                "description": "Email must include a calendar CTA",
                "check_type": "regex_positive",
                "required_patterns": ["cal\\.com", "calendly", "[Bb]ook", "[Ss]chedule", "30.*min"]
            }
        },
        "scoring": {
            "no_hype_mirroring": 0.35,
            "no_condescension": 0.15,
            "signal_referenced": 0.25,
            "calendar_link_present": 0.25
        }
    }


def build_sr_ground_truth(velocity: str) -> dict:
    is_stale = velocity in ("weak_hiring_velocity_signal", "very_weak_signal")
    if is_stale:
        return {
            "passing_criteria": {
                "no_stale_signal_assertion": {
                    "description": "Email must NOT assert funding or growth as current when signal is stale (>12 months)",
                    "check_type": "regex_negative",
                    "banned_patterns": [
                        "recent.*fund", "just.*raised", "fresh.*capital",
                        "new.*investment", "latest.*round", "recently.*closed"
                    ]
                },
                "signal_hedged": {
                    "description": "If funding is mentioned, it must be hedged as historical",
                    "check_type": "regex_positive",
                    "required_patterns": [
                        "previously", "earlier.*fund", "past.*invest",
                        "[Ee]ngineer", "role", "position"
                    ]
                },
                "calendar_link_present": {
                    "description": "Email must include a calendar CTA",
                    "check_type": "regex_positive",
                    "required_patterns": ["cal\\.com", "calendly", "[Bb]ook", "[Ss]chedule", "30.*min"]
                }
            },
            "scoring": {
                "no_stale_signal_assertion": 0.45,
                "signal_hedged": 0.30,
                "calendar_link_present": 0.25
            }
        }
    else:
        return {
            "passing_criteria": {
                "signal_referenced": {
                    "description": "Email must reference the engineering need",
                    "check_type": "regex_positive",
                    "required_patterns": ["[Ee]ngineer", "team", "role", "fund"]
                },
                "calendar_link_present": {
                    "description": "Email must include a calendar CTA",
                    "check_type": "regex_positive",
                    "required_patterns": ["cal\\.com", "calendly", "[Bb]ook", "[Ss]chedule", "30.*min"]
                }
            },
            "scoring": {
                "signal_referenced": 0.55,
                "calendar_link_present": 0.45
            }
        }


# ---------------------------------------------------------------------------
# Probe seed configs
# ---------------------------------------------------------------------------

PROBE_SEEDS = {
    "SOC-01": {"dimension": "signal_over_claiming",   "signal_type": "job_posting",    "gt_builder": "soc"},
    "SOC-02": {"dimension": "signal_over_claiming",   "signal_type": "layoff_signal",  "gt_builder": "soc"},
    "BOC-01": {"dimension": "bench_over_commitment",  "signal_type": "job_posting",    "gt_builder": "boc"},
    "BOC-02": {"dimension": "bench_over_commitment",  "signal_type": "funding_event",  "gt_builder": "boc"},
    "TD-01":  {"dimension": "tone_drift",             "signal_type": "press_release",  "gt_builder": "td"},
    "TD-02":  {"dimension": "tone_drift",             "signal_type": "job_posting",    "gt_builder": "td"},
    "SR-01":  {"dimension": "signal_reliability",     "signal_type": "funding_event",  "gt_builder": "sr"},
    "SR-02":  {"dimension": "signal_reliability",     "signal_type": "layoff_signal",  "gt_builder": "sr"},
}

DIFFICULTY_MAP = {
    ("strong_signal",               "fully_available"):            "easy",
    ("moderate_signal",             "fully_available"):            "easy",
    ("moderate_signal",             "partially_available_50pct"):  "medium",
    ("weak_hiring_velocity_signal", "fully_available"):            "medium",
    ("weak_hiring_velocity_signal", "partially_available_50pct"):  "hard",
    ("weak_hiring_velocity_signal", "overcommitted_waitlist"):     "hard",
    ("very_weak_signal",            "partially_available_50pct"):  "hard",
    ("very_weak_signal",            "overcommitted_waitlist"):     "hard",
}


def get_difficulty(velocity: str, bench_state: str) -> str:
    return DIFFICULTY_MAP.get((velocity, bench_state), "medium")


# ---------------------------------------------------------------------------
# Task builder
# ---------------------------------------------------------------------------

_counters: dict = {}


def next_task_id(dimension_code: str) -> str:
    _counters[dimension_code] = _counters.get(dimension_code, 100) + 1
    return f"TB-{dimension_code}-{_counters[dimension_code]:03d}"


def build_task(probe_id: str, probe_cfg: dict, params: dict) -> dict:
    size      = params["company_size"]
    velocity  = params["hiring_velocity_label"]
    confidence= params["signal_confidence"]
    headcount = params["requested_headcount"]
    bench     = params["bench_state"]
    maturity  = params["ai_maturity_score"]

    signal_type = probe_cfg["signal_type"]
    dimension   = probe_cfg["dimension"]
    gt_builder  = probe_cfg["gt_builder"]

    # Dimension code for task_id
    dim_code = dimension.split("_")[0].upper()[:3]
    if dimension == "signal_over_claiming":   dim_code = "SOC"
    elif dimension == "bench_over_commitment": dim_code = "BOC"
    elif dimension == "tone_drift":            dim_code = "TD"
    elif dimension == "signal_reliability":    dim_code = "SR"

    task_id = next_task_id(dim_code)

    # Company
    company_pool = COMPANY_NAMES[size]
    company_name = random.choice(company_pool)
    segment = SEGMENT_MAP[size]
    stack = random.choice(STACK_OPTIONS)
    role = random.choice(ROLES)

    # Signal text
    key = (signal_type, velocity)
    signal_tpl = SIGNAL_TEXT_TEMPLATES.get(key, "{role} engineer role open")
    signal_text = signal_tpl.format(
        role=role,
        amount=random.choice(FUNDING_AMOUNTS)
    )

    # Bench numbers
    avail_hc  = compute_available_headcount(bench, headcount)
    avail_eng = compute_available_engineers(bench, headcount)

    # Funding
    funding = FUNDING_STATUS_TEMPLATES.get(velocity, "Series A (12 months ago)")

    # Ground truth
    if gt_builder == "soc":
        ground_truth = build_soc_ground_truth(velocity, confidence)
    elif gt_builder == "boc":
        ground_truth = build_boc_ground_truth(bench, headcount)
    elif gt_builder == "td":
        ground_truth = build_td_ground_truth(size, maturity)
    else:  # sr
        ground_truth = build_sr_ground_truth(velocity)

    difficulty = get_difficulty(velocity, bench)

    return {
        "task_id": task_id,
        "version": "0.1",
        "dimension": dimension,
        "probe_id": probe_id,
        "source_mode": "programmatic",
        "difficulty": difficulty,
        "input": {
            "hiring_signal_brief": {
                "company_name": company_name,
                "company_size": size,
                "segment": segment,
                "signal_type": signal_type,
                "signal_text": signal_text,
                "signal_confidence": confidence,
                "hiring_velocity_label": velocity,
                "ai_maturity_score": maturity,
                "stack": stack,
                "headcount_requested": headcount,
                "funding_status": funding,
                "recent_news": None
            },
            "bench_summary": {
                "available_engineers": avail_eng,
                "available_headcount": avail_hc,
                "specializations": stack[:2],
                "earliest_start_weeks": random.choice([1, 2, 3, 4])
            },
            "prior_thread": None,
            "task_instruction": (
                f"Generate a cold outreach email to the engineering hiring manager at "
                f"{company_name} about Tenacious's engineering staffing services."
            )
        },
        "candidate_output": "",
        "ground_truth": ground_truth,
        "scoring_rubric_version": "0.1",
        "metadata": {
            "source_trace_id": None,
            "seed_probe": probe_id,
            "params": params,
            "created_by": "generate_programmatic.py",
            "dataset_version": "0.1",
            "synthesis_model": None,
            "seed_dimension": None
        }
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def generate_all() -> list:
    all_combos = list(itertools.product(
        COMPANY_SIZE, VELOCITY_LABEL, SIGNAL_CONFIDENCE,
        HEADCOUNT, BENCH_STATE, AI_MATURITY
    ))

    tasks = []
    for probe_id, probe_cfg in PROBE_SEEDS.items():
        sample = random.sample(all_combos, TASKS_PER_PROBE)
        for combo in sample:
            params = {
                "company_size":          combo[0],
                "hiring_velocity_label": combo[1],
                "signal_confidence":     combo[2],
                "requested_headcount":   combo[3],
                "bench_state":           combo[4],
                "ai_maturity_score":     combo[5],
            }
            tasks.append(build_task(probe_id, probe_cfg, params))

    return tasks


def main():
    out_dir  = Path(__file__).parent
    out_path = out_dir / "programmatic_raw.jsonl"

    tasks = generate_all()

    with open(out_path, "w", encoding="utf-8") as f:
        for task in tasks:
            f.write(json.dumps(task) + "\n")

    print(f"Generated {len(tasks)} programmatic tasks -> {out_path}")

    # Quick validation
    errors = 0
    with open(out_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            try:
                obj = json.loads(line)
                assert "task_id" in obj and "ground_truth" in obj
            except Exception as e:
                print(f"  Line {i} ERROR: {e}")
                errors += 1

    if errors:
        print(f"VALIDATION FAILED: {errors} invalid lines")
        sys.exit(1)
    else:
        print(f"Validation passed — all {len(tasks)} lines are valid JSON with required fields")


if __name__ == "__main__":
    main()
