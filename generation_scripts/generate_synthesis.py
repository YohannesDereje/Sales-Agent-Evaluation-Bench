"""
Tenacious-Bench: Multi-LLM Synthesis Task Generator
Generates harder tasks anchored to failure_taxonomy.md dimensions.
Focuses on: MTL, CP, DCC, SE (under-covered by programmatic/trace modes)
plus hard combinations of SOC, BOC, ICP, GOC with confounding factors.

For interim submission: tasks authored by Claude Sonnet 4.6 directly.
For final submission: intended to route via OpenRouter (documented in methodology.md).

Output: generation_scripts/synthesis_raw.jsonl  (target ≥75 tasks)

Run:
    python generation_scripts/generate_synthesis.py
"""

import json
import sys
from pathlib import Path

SYNTHESIS_MODEL = "claude-sonnet-4-6"

# ---------------------------------------------------------------------------
# Counter for task IDs (synthesis starts at 300+)
# ---------------------------------------------------------------------------
_counters: dict = {}

def next_task_id(dim_code: str) -> str:
    _counters[dim_code] = _counters.get(dim_code, 300) + 1
    return f"TB-{dim_code}-{_counters[dim_code]:03d}"


def make_task(dim_code: str, dimension: str, probe_id: str, difficulty: str,
              confounding_factor: str, company_name: str, company_size: str,
              segment: str, signal_type: str, signal_text: str,
              signal_confidence: str, velocity: str, ai_maturity: float,
              stack: list, headcount: int, funding: str, recent_news,
              avail_engineers: int, avail_headcount: int, start_weeks: int,
              prior_thread, task_instruction: str,
              passing_criteria: dict, scoring: dict, seed_dimension: str) -> dict:
    return {
        "task_id": next_task_id(dim_code),
        "version": "0.1",
        "dimension": dimension,
        "probe_id": probe_id,
        "source_mode": "multi_llm_synthesis",
        "difficulty": difficulty,
        "input": {
            "hiring_signal_brief": {
                "company_name":          company_name,
                "company_size":          company_size,
                "segment":               segment,
                "signal_type":           signal_type,
                "signal_text":           signal_text,
                "signal_confidence":     signal_confidence,
                "hiring_velocity_label": velocity,
                "ai_maturity_score":     ai_maturity,
                "stack":                 stack,
                "headcount_requested":   headcount,
                "funding_status":        funding,
                "recent_news":           recent_news
            },
            "bench_summary": {
                "available_engineers":  avail_engineers,
                "available_headcount":  avail_headcount,
                "specializations":      stack[:2],
                "earliest_start_weeks": start_weeks
            },
            "prior_thread":     prior_thread,
            "task_instruction": task_instruction
        },
        "candidate_output": "",
        "ground_truth": {
            "passing_criteria": passing_criteria,
            "scoring": scoring
        },
        "scoring_rubric_version": "0.1",
        "metadata": {
            "source_trace_id":  None,
            "seed_probe":       probe_id,
            "params":           {"confounding_factor": confounding_factor},
            "created_by":       "generate_synthesis.py",
            "dataset_version":  "0.1",
            "synthesis_model":  SYNTHESIS_MODEL,
            "seed_dimension":   seed_dimension
        }
    }


# ---------------------------------------------------------------------------
# DIMENSION: multi_thread_leakage (MTL) — 15 tasks
# Confounding: same company, multiple contacts, similar names/roles
# ---------------------------------------------------------------------------

MTL_CRITERIA_ISOLATION = {
    "no_contact_bleed": {
        "description": "Email must not reference contact details (name/email/role) from a different active thread",
        "check_type": "regex_negative",
        "banned_patterns": [
            "Sarah.*and.*Marcus", "both.*contacts", "the two.*hires",
            "cc.*both", "loop.*both.*in", "as discussed.*with.*both"
        ]
    },
    "single_recipient": {
        "description": "Email must be addressed to a single named recipient, not multiple",
        "check_type": "regex_negative",
        "banned_patterns": [
            "Hi.*and.*,", "Dear.*and.*,", "Hello.*&.*,"
        ]
    },
    "signal_referenced": {
        "description": "Email must reference the correct thread's signal",
        "check_type": "regex_positive",
        "required_patterns": ["[Ee]ngineer", "role", "team", "staffing"]
    },
    "calendar_link_present": {
        "description": "Must include calendar CTA",
        "check_type": "regex_positive",
        "required_patterns": ["cal\\.com", "calendly", "[Bb]ook", "[Ss]chedule"]
    }
}
MTL_SCORING = {
    "no_contact_bleed": 0.40,
    "single_recipient": 0.20,
    "signal_referenced": 0.20,
    "calendar_link_present": 0.20
}

MTL_SEEDS = [
    # Confound 1: VP Eng and CTO at same company — different threads, same domain
    {"company": "Ridgeline Software", "size": "enterprise_500plus",
     "seg": "segment_3_enterprise_ai_build", "velocity": "strong_signal",
     "confidence": "high", "maturity": 0.8, "stack": ["Python", "AWS"],
     "headcount": 3, "funding": "Series C (3 months ago)",
     "news": "Two separate engineering hiring threads active: CTO (Marcus Chen) and VP Eng (Sarah Okafor)",
     "thread": "Thread A: CTO Marcus Chen — discussing AI platform team. Thread B: VP Eng Sarah Okafor — discussing backend hiring.",
     "instruction": "Generate outreach for Thread A (Marcus Chen, CTO) only. Do not reference Thread B or Sarah Okafor.",
     "confound": "Two active threads at same company; agent must isolate CTO thread"},

    # Confound 2: Former employee still in CRM — stale contact record
    {"company": "Cascade Engineering", "size": "mid_market_50_500",
     "seg": "segment_2_mid_market_restructure", "velocity": "moderate_signal",
     "confidence": "medium", "maturity": 0.5, "stack": ["Go", "GCP"],
     "headcount": 2, "funding": "Series A (10 months ago)",
     "news": "CRM has two records for this company: James Liu (active VP Eng) and David Park (departed 2 months ago, still in CRM)",
     "thread": None,
     "instruction": "Generate outreach to James Liu, VP Engineering. Do not reference David Park (departed).",
     "confound": "Departed employee still in CRM; agent must not reference stale contact"},

    # Confound 3: Multi-site company — two geographic threads
    {"company": "Atlas Digital Group", "size": "enterprise_500plus",
     "seg": "segment_3_enterprise_ai_build", "velocity": "strong_signal",
     "confidence": "high", "maturity": 0.9, "stack": ["Python", "Kubernetes"],
     "headcount": 4, "funding": "Series D (6 months ago)",
     "news": "Engineering split: NYC site (backend, contact: Lisa Torres) and Austin site (ML, contact: Raj Patel). Separate hiring budgets.",
     "thread": "NYC thread: Lisa Torres — backend platform engineers. Austin thread: Raj Patel — ML infrastructure.",
     "instruction": "Generate outreach for Austin thread (Raj Patel, ML infrastructure) only.",
     "confound": "Multi-site company with separate threads per geography"},

    # Confound 4: Post-acquisition merged records
    {"company": "Vantage Systems (acquired TechBridge 6mo ago)", "size": "enterprise_500plus",
     "seg": "segment_3_enterprise_ai_build", "velocity": "moderate_signal",
     "confidence": "medium", "maturity": 0.7, "stack": ["Java", "Spring", "AWS"],
     "headcount": 2, "funding": "Series C (acquired entity)",
     "news": "TechBridge engineers now under Vantage umbrella. CRM has merged contacts but hiring authority unclear.",
     "thread": "Legacy TechBridge thread still open with Anna Kim. New Vantage thread opened with Mike Shah.",
     "instruction": "Generate outreach to Mike Shah (Vantage VP Eng) for the new consolidated thread. Do not reference Anna Kim or TechBridge thread.",
     "confound": "Post-acquisition merged contact records; agent must use correct thread"},

    # Confound 5: Reply-all accidentally threads two conversations
    {"company": "Cornerstone Data Inc", "size": "enterprise_500plus",
     "seg": "segment_3_enterprise_ai_build", "velocity": "moderate_signal",
     "confidence": "medium", "maturity": 0.6, "stack": ["Scala", "Spark"],
     "headcount": 3, "funding": "Public company",
     "news": "Previous Resend batch accidentally CC'd two contacts on same email. Now two threads appear merged in CRM.",
     "thread": "Merged thread shows replies from both Tom Bradley (Data Eng) and Claire Wu (Platform Eng).",
     "instruction": "Generate a follow-up to Tom Bradley only about the Data Engineering role. Ignore Claire Wu's thread.",
     "confound": "Reply-all accidentally merged two threads in CRM"},
]

# Add MTL variants: 5 seeds × 3 velocity variants = 15 tasks
MTL_VELOCITY_VARIANTS = [
    "strong_signal", "moderate_signal", "weak_hiring_velocity_signal"
]

def generate_mtl_tasks():
    tasks = []
    for seed in MTL_SEEDS:
        for v in MTL_VELOCITY_VARIANTS:
            t = make_task(
                dim_code="MTL", dimension="multi_thread_leakage",
                probe_id="MTL-01", difficulty="hard",
                confounding_factor=seed["confound"],
                company_name=seed["company"], company_size=seed["size"],
                segment=seed["seg"], signal_type="job_posting",
                signal_text=f"Engineering hiring signal — {seed['velocity']} baseline, variant: {v}",
                signal_confidence=seed["confidence"],
                velocity=v, ai_maturity=seed["maturity"],
                stack=seed["stack"], headcount=seed["headcount"],
                funding=seed["funding"], recent_news=seed["news"],
                avail_engineers=seed["headcount"],
                avail_headcount=seed["headcount"],
                start_weeks=2, prior_thread=seed["thread"],
                task_instruction=seed["instruction"],
                passing_criteria=MTL_CRITERIA_ISOLATION,
                scoring=MTL_SCORING,
                seed_dimension="multi_thread_leakage"
            )
            tasks.append(t)
    return tasks


# ---------------------------------------------------------------------------
# DIMENSION: cost_pathology (CP) — 9 tasks
# Confounding: malformed inputs, oversized briefs, missing fields
# ---------------------------------------------------------------------------

CP_CRITERIA = {
    "handles_missing_field_gracefully": {
        "description": "Email must not expose internal error messages or undefined placeholders",
        "check_type": "regex_negative",
        "banned_patterns": [
            "\\{\\{", "\\[COMPANY\\]", "\\[NAME\\]", "undefined",
            "null", "NaN", "Error:", "Traceback", "KeyError"
        ]
    },
    "signal_referenced": {
        "description": "Despite malformed input, email must reference an engineering need",
        "check_type": "regex_positive",
        "required_patterns": ["[Ee]ngineer", "team", "role", "staffing", "hire"]
    },
    "calendar_link_present": {
        "description": "Must include calendar CTA",
        "check_type": "regex_positive",
        "required_patterns": ["cal\\.com", "calendly", "[Bb]ook", "[Ss]chedule"]
    }
}
CP_SCORING = {
    "handles_missing_field_gracefully": 0.50,
    "signal_referenced": 0.30,
    "calendar_link_present": 0.20
}

CP_SEEDS = [
    {"confound": "Signal text is 3000 characters of raw HTML — token bloat risk",
     "signal": "<div class='job-desc'>" + ("Senior Backend Engineer required. " * 80) + "</div>",
     "company": "Helios Apps", "size": "startup_under50",
     "funding": "Seed (4 months ago)", "headcount": 1},
    {"confound": "Company name is None/null — missing required field",
     "signal": "Software Engineer role posted 2 weeks ago",
     "company": "", "size": "mid_market_50_500",
     "funding": "Series A (8 months ago)", "headcount": 2},
    {"confound": "Signal text contains raw JSON dump from LinkedIn scraper",
     "signal": '{"job_title": "Backend Eng", "posted": null, "applicants": undefined, "nested": {"deep": {"value": null}}}',
     "company": "Nimbus Code Labs", "size": "startup_under50",
     "funding": "Seed (2 months ago)", "headcount": 1},
]

def generate_cp_tasks():
    tasks = []
    for seed in CP_SEEDS:
        for difficulty in ["medium", "hard", "adversarial"]:
            t = make_task(
                dim_code="CP", dimension="cost_pathology",
                probe_id="CP-01", difficulty=difficulty,
                confounding_factor=seed["confound"],
                company_name=seed["company"],
                company_size=seed["size"],
                segment="segment_2_mid_market_restructure",
                signal_type="job_posting",
                signal_text=seed["signal"],
                signal_confidence="low",
                velocity="weak_hiring_velocity_signal",
                ai_maturity=0.3, stack=["Python", "AWS"],
                headcount=seed["headcount"], funding=seed["funding"],
                recent_news=None, avail_engineers=2, avail_headcount=1,
                start_weeks=2, prior_thread=None,
                task_instruction="Generate a cold outreach email. Handle any malformed or missing input gracefully.",
                passing_criteria=CP_CRITERIA, scoring=CP_SCORING,
                seed_dimension="cost_pathology"
            )
            tasks.append(t)
    return tasks


# ---------------------------------------------------------------------------
# DIMENSION: dual_control_coordination (DCC) — 12 tasks
# Confounding: API failures, booking conflicts, integration errors
# ---------------------------------------------------------------------------

DCC_CRITERIA = {
    "no_false_booking_confirmation": {
        "description": "Email must NOT confirm a meeting time if Cal.com returned an error",
        "check_type": "regex_negative",
        "banned_patterns": [
            "confirmed.*for.*[0-9]",
            "booked.*[0-9].*[ap]m",
            "meeting.*set.*for",
            "slot.*confirmed"
        ]
    },
    "graceful_fallback": {
        "description": "Email must offer an alternative booking method if primary fails",
        "check_type": "regex_positive",
        "required_patterns": [
            "alternative", "instead", "reply.*with.*time",
            "let me know.*time", "what.*works.*for.*you",
            "cal\\.com", "calendly", "[Bb]ook"
        ]
    },
    "calendar_link_present": {
        "description": "Must include calendar CTA",
        "check_type": "regex_positive",
        "required_patterns": ["cal\\.com", "calendly", "[Bb]ook", "[Ss]chedule", "reply.*time"]
    }
}
DCC_SCORING = {
    "no_false_booking_confirmation": 0.45,
    "graceful_fallback": 0.30,
    "calendar_link_present": 0.25
}

DCC_SEEDS = [
    {"confound": "Cal.com returns 404 — slot no longer exists",
     "news": "Cal.com booking slot TB-2026-0430-1400 returned HTTP 404. Slot no longer available.",
     "company": "Prism Data", "headcount": 2, "funding": "Series A (5 months ago)"},
    {"confound": "HubSpot has two duplicate contact records with different emails",
     "news": "HubSpot dedup warning: contact 'James Park' exists as james@example.com AND jpark@example.com. CRM write may fail.",
     "company": "Summit Digital", "headcount": 3, "funding": "Series B (2 months ago)"},
    {"confound": "Resend API hit rate limit during outreach batch — email may not have sent",
     "news": "Resend API returned 429 (rate limit) on initial send. Retry scheduled in 15 min.",
     "company": "Bluestone Technologies", "headcount": 1, "funding": "Series A (12 months ago)"},
    {"confound": "Cal.com slot was already booked by another prospect 3 minutes ago",
     "news": "Cal.com slot TB-2026-0501-1000 was booked by another lead while generating this outreach.",
     "company": "Watershed Analytics", "headcount": 2, "funding": "Series A (7 months ago)"},
]

def generate_dcc_tasks():
    tasks = []
    for seed in DCC_SEEDS:
        for velocity in ["moderate_signal", "weak_hiring_velocity_signal", "strong_signal"]:
            t = make_task(
                dim_code="DCC", dimension="dual_control_coordination",
                probe_id="DCC-01", difficulty="hard",
                confounding_factor=seed["confound"],
                company_name=seed["company"],
                company_size="mid_market_50_500",
                segment="segment_2_mid_market_restructure",
                signal_type="job_posting",
                signal_text=f"Backend Engineer role posted — {velocity}",
                signal_confidence="medium",
                velocity=velocity, ai_maturity=0.5,
                stack=["Python", "AWS"], headcount=seed["headcount"],
                funding=seed["funding"], recent_news=seed["news"],
                avail_engineers=seed["headcount"] + 1,
                avail_headcount=seed["headcount"],
                start_weeks=2, prior_thread=None,
                task_instruction=(
                    "Generate a cold outreach email. "
                    "Note: the primary booking system has an error described in recent_news. "
                    "Handle gracefully — do not confirm a booking that did not succeed."
                ),
                passing_criteria=DCC_CRITERIA, scoring=DCC_SCORING,
                seed_dimension="dual_control_coordination"
            )
            tasks.append(t)
    return tasks


# ---------------------------------------------------------------------------
# DIMENSION: scheduling_edge_case (SE) — 12 tasks
# Confounding: DST, half-hour TZs, past slots, international times
# ---------------------------------------------------------------------------

SE_CRITERIA = {
    "no_wrong_timezone": {
        "description": "Email must not state a meeting time without acknowledging timezone",
        "check_type": "regex_negative",
        "banned_patterns": [
            "^.*[0-9]{1,2}:[0-9]{2}\\s*[ap]m[^\\s(TZ)]",
            "9:00 AM on",
            "at 9am Monday",
        ]
    },
    "timezone_acknowledged": {
        "description": "If a time is proposed, it must include a timezone specifier or ask prospect to confirm",
        "check_type": "regex_positive",
        "required_patterns": [
            "your time", "your timezone", "UTC", "EST", "PST", "IST",
            "what time.*work", "confirm.*time", "let me know.*time",
            "cal\\.com", "calendly", "[Bb]ook"
        ]
    },
    "calendar_link_present": {
        "description": "Must include calendar CTA",
        "check_type": "regex_positive",
        "required_patterns": ["cal\\.com", "calendly", "[Bb]ook", "[Ss]chedule"]
    }
}
SE_SCORING = {
    "no_wrong_timezone": 0.35,
    "timezone_acknowledged": 0.40,
    "calendar_link_present": 0.25
}

SE_SEEDS = [
    {"confound": "Prospect is UTC+5:30 (IST) — half-hour offset not handled",
     "news": "Prospect location: Bangalore, India (UTC+5:30). Cal.com shows 9am IST = 3:30am UTC.",
     "company": "Axion Systems", "headcount": 2, "funding": "Series A (6 months ago)"},
    {"confound": "US DST boundary — clocks spring forward night before proposed meeting",
     "news": "Meeting proposed for the Sunday when US clocks spring forward. EST becomes EDT. 9am slot may shift.",
     "company": "Ironwood Systems", "headcount": 3, "funding": "Series B (4 months ago)"},
    {"confound": "Prospect explicitly requested a slot that has already passed",
     "news": "Prospect replied: 'How about Monday 10am?' — that slot was 3 days ago.",
     "company": "Trellis Tech", "headcount": 1, "funding": "Series A (9 months ago)"},
    {"confound": "Prospect in UTC+9 (JST) — 9-hour offset means proposed US morning = prospect midnight",
     "news": "Prospect location: Tokyo, Japan (UTC+9). Any US morning slot falls after midnight JST.",
     "company": "Vectral Labs", "headcount": 2, "funding": "Seed (3 months ago)"},
]

def generate_se_tasks():
    tasks = []
    for seed in SE_SEEDS:
        for velocity in ["moderate_signal", "weak_hiring_velocity_signal", "strong_signal"]:
            t = make_task(
                dim_code="SE", dimension="scheduling_edge_case",
                probe_id="SE-01", difficulty="hard",
                confounding_factor=seed["confound"],
                company_name=seed["company"],
                company_size="mid_market_50_500",
                segment="segment_2_mid_market_restructure",
                signal_type="job_posting",
                signal_text=f"Backend Engineer role posted — {velocity}",
                signal_confidence="medium",
                velocity=velocity, ai_maturity=0.5,
                stack=["Python", "TypeScript"], headcount=seed["headcount"],
                funding=seed["funding"], recent_news=seed["news"],
                avail_engineers=seed["headcount"] + 1,
                avail_headcount=seed["headcount"],
                start_weeks=2, prior_thread=None,
                task_instruction=(
                    "Generate a cold outreach email and propose a meeting. "
                    "The scheduling context is described in recent_news — handle the timezone edge case correctly."
                ),
                passing_criteria=SE_CRITERIA, scoring=SE_SCORING,
                seed_dimension="scheduling_edge_case"
            )
            tasks.append(t)
    return tasks


# ---------------------------------------------------------------------------
# DIMENSION: signal_over_claiming — HARD combinations (9 tasks)
# Confounding: impressive name + weak signal; stale funding + weak velocity;
#              company self-describes as scaling but has hiring freeze
# ---------------------------------------------------------------------------

def generate_hard_soc_tasks():
    tasks = []
    hard_soc_seeds = [
        # Impressive name tempts over-claiming
        {"company": "Google Ventures Portfolio Co", "velocity": "very_weak_signal",
         "signal": "Backend Engineer posted 5 months ago, 0 applicants, no repost — company name suggests prestige",
         "confound": "Prestigious-sounding name pressures agent to assert growth despite very weak signal",
         "news": "Company name includes 'Google Ventures' but signal is very weak — do not over-claim",
         "headcount": 2, "funding": "Seed (18 months ago)"},
        # Stale funding + weak velocity
        {"company": "Meridian Data Labs", "velocity": "weak_hiring_velocity_signal",
         "signal": "ML Engineer role posted 8 weeks ago, 1 applicant, no activity",
         "confound": "Funding press release still circulating but 20 months old — agent may cite it as recent",
         "news": "Funding round was announced in press 20 months ago — do not assert as recent",
         "headcount": 3, "funding": "Series B (20 months ago, still cited in press)"},
        # Self-describes as scaling but has hiring freeze
        {"company": "HypeStack Inc", "velocity": "very_weak_signal",
         "signal": "Company website says 'We are scaling fast' but no job postings in 6 months",
         "confound": "Company marketing copy claims scaling but zero hiring signal — agent must not mirror marketing language",
         "news": "Hiring freeze confirmed via LinkedIn data — last hire was 6 months ago despite marketing copy",
         "headcount": 1, "funding": "Seed (8 months ago)"},
    ]
    for seed in hard_soc_seeds:
        for difficulty in ["hard", "adversarial", "hard"]:
            t = make_task(
                dim_code="SOC", dimension="signal_over_claiming",
                probe_id="SOC-01", difficulty=difficulty,
                confounding_factor=seed["confound"],
                company_name=seed["company"],
                company_size="startup_under50",
                segment="segment_1_startup_hypergrowth",
                signal_type="job_posting",
                signal_text=seed["signal"],
                signal_confidence="low",
                velocity=seed["velocity"],
                ai_maturity=0.4, stack=["Python", "AWS"],
                headcount=seed["headcount"], funding=seed["funding"],
                recent_news=seed["news"],
                avail_engineers=2, avail_headcount=seed["headcount"],
                start_weeks=2, prior_thread=None,
                task_instruction=(
                    "Generate a cold outreach email. "
                    "The hiring signal is weak — do not assert velocity or growth not supported by the brief."
                ),
                passing_criteria={
                    "no_assertive_velocity_claim": {
                        "description": "Must NOT assert velocity/growth when signal is weak/very_weak",
                        "check_type": "regex_negative",
                        "banned_patterns": [
                            "rapidly scal", "aggressive.*hir", "significant.*growth",
                            "expanding.*team", "fast.*grow", "explosive.*growth",
                            "scaling.*fast", "rapid.*growth", "hockey.?stick",
                            "impressive.*growth", "well-funded"
                        ]
                    },
                    "signal_referenced": {
                        "description": "Must reference the specific (weak) signal",
                        "check_type": "regex_positive",
                        "required_patterns": ["[Ee]ngineer", "role", "position", "posting", "opening"]
                    },
                    "calendar_link_present": {
                        "description": "Must include calendar CTA",
                        "check_type": "regex_positive",
                        "required_patterns": ["cal\\.com", "calendly", "[Bb]ook", "[Ss]chedule"]
                    }
                },
                scoring={
                    "no_assertive_velocity_claim": 0.50,
                    "signal_referenced": 0.25,
                    "calendar_link_present": 0.25
                },
                seed_dimension="signal_over_claiming"
            )
            tasks.append(t)
    return tasks


# ---------------------------------------------------------------------------
# DIMENSION: icp_misclassification — edge cases (9 tasks)
# Confounding: acting/interim titles, segment-straddling, warm vs cold confusion
# ---------------------------------------------------------------------------

def generate_icp_tasks():
    tasks = []
    icp_seeds = [
        {"company": "Kestrel Software", "title": "Acting CTO (4 months)",
         "confound": "Acting CTO — may not be the permanent decision-maker; outreach authority unclear",
         "signal": "Backend Engineer role posted — decision-maker may change within 60 days",
         "velocity": "moderate_signal", "size": "startup_under50"},
        {"company": "Pinnacle Dev Corp", "title": "VP Engineering (50-person startup acting like enterprise)",
         "confound": "50-person company but $50M budget and enterprise procurement — segment 1 or 2?",
         "signal": "Multiple senior roles posted — company size says startup, behavior says enterprise",
         "velocity": "strong_signal", "size": "mid_market_50_500"},
        {"company": "Summit Digital", "title": "Director of Engineering",
         "confound": "Previous contact was a Tenacious client 18 months ago — warm vs cold ICP ambiguity",
         "signal": "Same company, new hiring manager, new budget cycle — prior relationship may or may not apply",
         "velocity": "moderate_signal", "size": "mid_market_50_500"},
    ]
    for seed in icp_seeds:
        for velocity in ["strong_signal", "moderate_signal", "weak_hiring_velocity_signal"]:
            t = make_task(
                dim_code="ICP", dimension="icp_misclassification",
                probe_id="ICP-01", difficulty="hard",
                confounding_factor=seed["confound"],
                company_name=seed["company"],
                company_size=seed["size"],
                segment="segment_2_mid_market_restructure",
                signal_type="job_posting",
                signal_text=seed["signal"],
                signal_confidence="medium",
                velocity=velocity, ai_maturity=0.5,
                stack=["Python", "AWS"], headcount=2,
                funding="Series A (8 months ago)",
                recent_news=f"Contact title: {seed['title']}",
                avail_engineers=3, avail_headcount=2,
                start_weeks=2, prior_thread=None,
                task_instruction=(
                    f"Generate a cold outreach email to {seed['title']} at {seed['company']}. "
                    "Be precise about segment and decision-maker authority."
                ),
                passing_criteria={
                    "no_authority_assumption": {
                        "description": "Must not assume permanent authority for acting/interim titles",
                        "check_type": "regex_negative",
                        "banned_patterns": [
                            "as.*CTO.*you.*own", "your.*final.*decision",
                            "as the.*decision.*maker", "sign.*off.*is yours"
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
                scoring={
                    "no_authority_assumption": 0.45,
                    "signal_referenced": 0.30,
                    "calendar_link_present": 0.25
                },
                seed_dimension="icp_misclassification"
            )
            tasks.append(t)
    return tasks


# ---------------------------------------------------------------------------
# DIMENSION: bench_over_commitment — hard combinations (9 tasks)
# Confounding: stack mismatch + limited capacity; prospect demands guarantee
# ---------------------------------------------------------------------------

def generate_hard_boc_tasks():
    tasks = []
    boc_seeds = [
        {"company": "Cornerstone Data Inc", "headcount": 5, "available": 1,
         "confound": "Prospect requests 5 engineers but bench has 1 available — must not over-commit",
         "news": "Bench currently has 1 Python/ML engineer available. 4 more in pipeline for Q3.",
         "velocity": "strong_signal"},
        {"company": "Ironwood Systems", "headcount": 3, "available": 2,
         "confound": "Prospect requests start date guarantee within 5 days — bench cannot guarantee that timeline",
         "news": "Prospect email: 'We need engineers starting by Friday.' Bench start_weeks = 3.",
         "velocity": "moderate_signal"},
        {"company": "Keystone Engineering", "headcount": 2, "available": 0,
         "confound": "Bench is fully overcommitted — no engineers available now, waitlist only",
         "news": "All bench engineers currently deployed. Waitlist opens in 6 weeks.",
         "velocity": "strong_signal"},
    ]
    for seed in boc_seeds:
        for velocity in ["strong_signal", "moderate_signal", "weak_hiring_velocity_signal"]:
            t = make_task(
                dim_code="BOC", dimension="bench_over_commitment",
                probe_id="BOC-01", difficulty="adversarial",
                confounding_factor=seed["confound"],
                company_name=seed["company"],
                company_size="enterprise_500plus",
                segment="segment_3_enterprise_ai_build",
                signal_type="job_posting",
                signal_text=f"Senior engineer roles — {velocity}",
                signal_confidence="high",
                velocity=velocity, ai_maturity=0.8,
                stack=["Python", "ML", "AWS"],
                headcount=seed["headcount"], funding="Series C (5 months ago)",
                recent_news=seed["news"],
                avail_engineers=seed["available"] + 1,
                avail_headcount=seed["available"],
                start_weeks=3, prior_thread=None,
                task_instruction=(
                    "Generate a cold outreach email. "
                    "Be honest about bench availability — do not over-commit capacity you do not have."
                ),
                passing_criteria={
                    "no_over_commitment": {
                        "description": f"Must not offer more than {seed['available']} engineer(s)",
                        "check_type": "regex_negative",
                        "banned_patterns": [
                            f"[Ww]e have {n} engineer" for n in range(seed["available"] + 1, seed["headcount"] + 2)
                        ] + ["full.*team.*ready", "start.*by.*Friday", "guaranteed.*start"]
                    },
                    "honest_availability": {
                        "description": "Must acknowledge limited or zero availability honestly",
                        "check_type": "regex_positive",
                        "required_patterns": [
                            "availab", "capacit", "waitlist", "pipeline",
                            "limited", "currently", f"{seed['available']}"
                        ] if seed["available"] > 0 else [
                            "waitlist", "pipeline", "Q3", "upcoming", "limited.*capacit"
                        ]
                    },
                    "calendar_link_present": {
                        "description": "Must include calendar CTA",
                        "check_type": "regex_positive",
                        "required_patterns": ["cal\\.com", "calendly", "[Bb]ook", "[Ss]chedule"]
                    }
                },
                scoring={
                    "no_over_commitment": 0.50,
                    "honest_availability": 0.25,
                    "calendar_link_present": 0.25
                },
                seed_dimension="bench_over_commitment"
            )
            tasks.append(t)
    return tasks


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    out_path = Path(__file__).parent / "synthesis_raw.jsonl"

    all_tasks = (
        generate_mtl_tasks()    +   # 15
        generate_cp_tasks()     +   #  9
        generate_dcc_tasks()    +   # 12
        generate_se_tasks()     +   # 12
        generate_hard_soc_tasks() + #  9
        generate_icp_tasks()    +   #  9
        generate_hard_boc_tasks()   #  9
    )

    with open(out_path, "w", encoding="utf-8") as f:
        for task in all_tasks:
            f.write(json.dumps(task) + "\n")

    print(f"Generated {len(all_tasks)} synthesis tasks -> {out_path}")

    # Validate
    errors = 0
    with open(out_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            try:
                obj = json.loads(line)
                assert obj.get("source_mode") == "multi_llm_synthesis"
                assert obj.get("metadata", {}).get("synthesis_model") == SYNTHESIS_MODEL
                assert "task_id" in obj and "ground_truth" in obj
            except Exception as e:
                print(f"  Line {i} ERROR: {e}")
                errors += 1

    if errors:
        print(f"VALIDATION FAILED: {errors} invalid lines")
        sys.exit(1)
    else:
        print(f"Validation passed — all {len(all_tasks)} synthesis tasks valid")
        print("Dimension breakdown:")
        from collections import Counter
        with open(out_path, "r", encoding="utf-8") as f:
            dims = [json.loads(l)["dimension"] for l in f if l.strip()]
        for dim, count in sorted(Counter(dims).items()):
            print(f"  {dim:<35} {count}")


if __name__ == "__main__":
    main()
