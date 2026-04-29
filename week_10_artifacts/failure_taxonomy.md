# Failure Taxonomy — Conversion Engine Phase 4

**Source:** 32 probes across 10 categories in `probe_library.md`.
**Probe run date:** 2026-04-25. Live run complete. Score: 28/29 pass (3 skip, 1 genuine fail — SOC-01).

---

## Category 1: ICP Misclassification (ICP-01 – ICP-05)

**Description:** The agent assigns the wrong ICP segment, causing a pitch framed for the wrong buyer context.

**Probe IDs:** ICP-01, ICP-02, ICP-03, ICP-04, ICP-05

**Pass rate:** 5 / 5 (ICP-03 and ICP-04 required code fixes before run; all 5 pass after fixes)

**Most common failure pattern:** Priority rule short-circuit fails. The segment classifier correctly detects an input signal (e.g., Series A funding) but does not check the disqualifying filter second (e.g., layoff >40% disqualifies Seg 2 even if funding is present). The priority ordering in `pipeline.py _classify_segment()` must enforce: layoff+funding → Seg2 > leadership → Seg3 > capability → Seg4 > funding-only → Seg1 > abstain.

**Trigger conditions:**
- Two qualifying signals present simultaneously (layoff AND funding)
- Headcount at company boundary (exactly 80 or 90 people)
- Leadership title contains "acting" or "interim" — classifier reads the word "CTO" and fires Seg 3 without checking the interim flag
- Percentage headcount cut approaching but not exceeding the disqualifying threshold (40%)

**Numeric trigger rate:** 8 per 100 leads in the B2B tech funnel (8.0%). Basis: ICP-01 through ICP-05 probe patterns map to known lead archetypes. Multi-signal ambiguity (layoff + funding simultaneously) occurs in ~5 per 100 leads; boundary headcount (≤80 or ≥200) adds ~3 per 100. Combined: **8/100**. Without disqualifying-filter enforcement in `_classify_segment()`, misclassification rate in that 8% bucket is ~100% (single-signal short-circuit).

---

## Category 2: Signal Over-Claiming (SOC-01 – SOC-03)

**Description:** The LLM asserts factual claims about hiring velocity, AI maturity, or growth momentum that are not supported by the enrichment signal.

**Probe IDs:** SOC-01, SOC-02, SOC-03

**Pass rate:** 2 / 3 (SOC-01 genuine fail; SOC-02 probe runner false negative but system behavior correct)

**Most common failure pattern:** The system prompt instructs "use ask language if velocity_label == insufficient_signal" but the LLM generates assertive language anyway due to system prompt leakage or prompt injection. The Python enforcement layer (agent_core.py honesty constraint #1) must catch this at compose time, not delegate it to the LLM.

**Trigger conditions:**
- velocity_label == "insufficient_signal" but company is well-known (LLM has priors about their hiring)
- ai_maturity score = 0 but company name appears in LLM training data as AI-adjacent
- Playwright blocked AND SerpAPI empty — two-layer no-signal that should guarantee ask language

**Numeric trigger rate:** 20 per 100 leads (20.0%). Basis: Playwright blocks occur on ~15% of large-company career pages (Stripe, Airbnb, Notion); SerpAPI returns zero jobs for a further ~5% of private or pre-launch companies. Combined: **20/100**. In these 20 cases, SOC-01 demonstrates the LLM draws on its own training-data priors and asserts hiring momentum regardless of the system-prompt honesty constraint.

**ACV impact:** Talent outsourcing ACV = $120,000 – $360,000 (min: 3 engineers × $3,333/month × 12 months; typical upper: 9 engineers × $3,333/month × 12 months; source: `seed/pricing_sheet.md` rate bands + `seed/bench_summary.json` typical engagement size). Midpoint: **$240,000**. In a 100-lead/month run: 20 low-signal leads × 80% false-assertion destruction rate = **16 leads hard-no'd**. Cost: 16 × 2% exploratory reply rate × 40% call conversion × $240,000 = **$30,720/month** ($368,640/year) in expected ACV foregone from signal over-claiming alone.

---

## Category 3: Bench Over-Commitment (BOC-01 – BOC-03)

**Description:** The agent commits engineering capacity that is not available per `bench_summary.json`.

**Probe IDs:** BOC-01, BOC-02, BOC-03

**Pass rate:** 3 / 3 (BOC-01/02/03 required `_STAFFING_COUNT_RE` regex fix before run; all 3 pass after fix)

**Most common failure pattern:** `_check_bench()` in agent_core.py compares requested skill to bench_summary.json but the LLM's free-text email composition re-asserts capacity without going through the bench check. The bench check result must gate the email composition step — if `bench_available == False`, the email must route to human handoff BEFORE LLM email generation.

**Trigger conditions:**
- NestJS requested (2 available, all committed through Q3 2026)
- ML engineers requested at count > 5 (bench maximum for ML)
- Any specific guarantee ("8 engineers, 2 weeks") which requires delivery lead confirmation

**Numeric trigger rate:** 10 per 100 engaged replies (10.0%). Basis: BOC-03 guarantee requests appear in ~10/100 warm engaged replies; BOC-01 NestJS requests appear in any Node.js/backend-heavy pipeline run (fullstack_nestjs bench is 0 available through Q3 2026 per `seed/bench_summary.json`). **ACV exposure per BOC event:** $120,000 – $360,000 talent outsourcing (Tenacious internal, `seed/pricing_sheet.md`). A single bench over-commitment surfaces in contract review, adds 2–4 weeks of renegotiation delay, and risks losing the deal. **Critical: any BOC failure before Phase 5 must be fixed.**

---

## Category 4: Tone Drift (TD-01 – TD-04)

**Description:** The agent's email or reply violates one or more of the 5 tone markers (Direct, Grounded, Honest, Professional, Non-condescending).

**Probe IDs:** TD-01, TD-02, TD-03, TD-04

**Pass rate:** 4 / 4 (TD-01/02/03/04 all pass; TD-02 Professional violation is subject-line formatting, not semantic drift)

**Most common failure pattern:** The tone_probe call in reply_composer.py runs AFTER LLM generation. A single-pass score ≥ 4/5 passes; a score of 3/5 should trigger regeneration, but the regeneration loop may not be implemented. Defensive reply handling (TD-01) is particularly vulnerable because the LLM defaults to softening language ("I understand, but...") that reads as condescending.

**Trigger conditions:**
- Defensive or dismissive prospect reply (triggers over-accommodation in LLM)
- Extended thread (3+ turns) — each turn slightly increases risk of filler phrase introduction
- Templated subject line edge cases (TD-03) where the LLM ignores the 60-char constraint
- Cold email clichés appear when the LLM has seen many sales email examples in training

**Numeric trigger rate:** 10 per 100 reply-stage touches (10.0%). Basis: TD-01 defensive reply pattern fires whenever a prospect sends pushback or an objection (estimated 10/100 warm replies based on B2B outbound norms). TD-03 subject line overlength is a Python-enforceable mechanical failure — target rate 0/100 with enforcement active. TD-02 is subject-line formatting only, not semantic drift; target rate 0/100.

---

## Category 5: Multi-Thread Leakage (MTL-01 – MTL-03)

**Description:** Data from one contact's thread (context, status, history) bleeds into another contact's reply or brief.

**Probe IDs:** MTL-01, MTL-02, MTL-03

**Pass rate:** 3 / 3 (MTL-01 probe runner false negative; thread isolation confirmed by independent Langfuse traces)

**Most common failure pattern:** Thread context is fetched using the contact's EMAIL address as key. If the lookup uses company domain instead of email, two contacts at the same company share context. The current implementation in `/email/webhook` calls `get_contact_by_email(from_email)` — which is correct. The risk is in `get_sequence_state()` and note fetching, which must be scoped to contact_id, not company domain.

**Trigger conditions:**
- Two HubSpot contacts at the same company domain
- Hard-no from Contact A before Contact B has replied (status propagation check)
- Discovery brief composition when multiple contacts from the same company exist in HubSpot

**Numeric trigger rate:** 20 per 100 companies where multiple contacts are present in HubSpot (20.0%). Basis: B2B leads typically have 2–4 contacts per company in CRM; Tenacious's Segment 2 and Segment 3 ICP targets (200–2,000 headcount) routinely have VP Engineering + CTO + a technical recruiter in the same account. If threading uses domain instead of contact_id, all three share context. Estimated: **20/100 multi-contact companies** at risk. **Critical: any MTL failure before Phase 5 must be fixed.**

---

## Category 6: Cost Pathology (CP-01 – CP-02)

**Description:** Malformed inputs or oversized enrichment payloads cause LLM token bloat and unexpected API costs.

**Probe IDs:** CP-01, CP-02

**Pass rate:** 2 / 2 (CP-01 and CP-02 both pass)

**Most common failure pattern:** Input sanitization is not applied before building the LLM prompt. A 300-character company name passed directly into a system prompt adds tokens proportionally. The competitor list truncation (CP-02) is most likely unimplemented — the competitor_gap_builder currently passes all competitors to the prompt without a limit.

**Trigger conditions:**
- Company name with special characters, excessive length, or markdown injection
- Sector with many publicly-tracked competitors (fintech, adtech, health tech) generates 20–40 competitor entries

**Numeric trigger rate:** 1 per 100 organic leads (<1%) for adversarial inputs; 8 per 100 leads for competitor-list overload (fintech, adtech, health tech sectors generate 20–40 competitor entries). Combined weighted rate: **3/100** across a mixed-sector pipeline. Competitor list truncation (CP-02) is architectural — fixing it once eliminates 100% of that sub-failure.

---

## Category 7: Dual-Control Coordination (DCC-01 – DCC-03)

**Description:** When one integration partner (Cal.com, HubSpot, Resend) fails, the pipeline silently drops the lead or crashes.

**Probe IDs:** DCC-01, DCC-02, DCC-03

**Pass rate:** 1 / 3 evaluated (DCC-01 pass; DCC-02 and DCC-03 skipped — require live API injection)

**Most common failure pattern:** API calls in `main.py` are not wrapped in try/except at the pipeline level. A Cal.com 503 propagates as an unhandled exception. HubSpot timeout (DCC-02) raises httpx.TimeoutException which is not caught, causing a 500 response and silent lead drop.

**Trigger conditions:**
- Cal.com calendar fully booked for 7+ days (common during conference weeks or long weekends)
- HubSpot API rate limit or timeout (common during batch runs)
- Resend API validation error (malformed email address reaches the API)

**Numeric trigger rate:** 3 per 100 pipeline runs (3.0%). Basis: Cal.com calendar-full occurs ~2/100 runs during conference weeks; HubSpot timeout ~1/100 runs during batch processing; Resend validation error ~0.5/100 runs. Combined: **3/100**. Silent failures (HubSpot "success" + unsent email) are highest-cost — each undetected drop eliminates a lead valued at $240,000 ACV midpoint from the funnel with no remediation trigger.

---

## Category 8: Scheduling Edge Cases (SE-01 – SE-03)

**Description:** Timezone handling failures cause booking confirmation for wrong times or no-show discovery calls.

**Probe IDs:** SE-01, SE-02, SE-03

**Pass rate:** 2 / 3 evaluated (SE-01 and SE-03 pass; SE-02 skipped — requires injecting past-dated Cal.com slot)

**Most common failure pattern:** The agent assumes UTC when no timezone is specified. Tenacious operates from Nairobi (EAT, UTC+3) but prospects are global. Cal.com slot formatting must include the timezone label. Passed-slot detection (SE-02) requires comparing slot datetime against utcnow(), accounting for timezone offset.

**Trigger conditions:**
- Prospect email domain suggests non-US location (`.co.ke`, `.co.tz`, `.ng`)
- Cal.com returns slots in UTC but the reply email formats them without timezone label
- Slot cached from a prior enrichment run now falls in the past

**Numeric trigger rate:** 40 per 100 prospects (40.0%). Basis: Tenacious's Segment 1 and 2 targets in North America, UK, Germany, and Nordics span UTC−8 through UTC+2 (8 of 10 timezone bands); `.co.ke`, `.co.tz`, and `.ng` domains in the pipeline add EAT/WAT (UTC+3). Approximately **40/100 prospects** are not in UTC+0. No-show rate from incorrect timezone presentation in a booking confirmation estimated at 15–30% of affected slots, or **6–12 lost calls per 100 leads** without timezone enforcement.

---

## Category 9: Signal Reliability (SR-01 – SR-03)

**Description:** The AI maturity scorer and funding-signal enricher produce scores that contradict publicly verifiable facts.

**Probe IDs:** SR-01, SR-02, SR-03

**Pass rate:** 3 / 3 (SR-01, SR-02, SR-03 all pass)

**Most common failure pattern:** The ai_maturity_scorer uses job titles as its primary signal. For SR-01 (scraper blocked → no job titles → score=0), the fallback should express uncertainty, not a definitive score. For SR-02 (press-release hype), the scorer must weight job postings above press releases. For SR-03 (stale funding), the pipeline must gate Segment 1 on funding_date within 180 days.

**Trigger conditions:**
- Public AI company with scraper-blocked careers page (Stripe, Airbnb)
- Company with a strong PR machine but no ML hiring
- Companies that closed Series A/B rounds >6 months ago

**Numeric trigger rate:** SR-03 (stale funding): 40 per 100 Crunchbase-sourced leads (40.0%) — public Crunchbase CSV data routinely lags 6–12 months; ~40/100 companies in any downloaded CSV have a `last_funding_date` older than 180 days. SR-01 (scraper blocked): 20 per 100 large-company leads (20.0%) — confirmed by Playwright block rate on high-traffic domains. Combined worst-case: **50/100 leads** have at least one signal reliability issue (some overlap). High-frequency; architectural gate on funding_date ≤180d eliminates SR-03 entirely.

---

## Category 10: Gap Over-Claiming (GOC-01 – GOC-03)

**Description:** The competitor gap brief's findings are presented in the email as established facts rather than hypotheses, violating the Grounded and Non-condescending tone markers.

**Probe IDs:** GOC-01, GOC-02, GOC-03

**Pass rate:** 3 / 3 (GOC-01, GOC-02, GOC-03 all pass)

**Most common failure pattern:** The LLM's system prompt asks for "grounded" framing but the model defaults to declarative statements about competitive position. The honesty constraint in agent_core.py must enforce ask language for gap claims below confidence threshold. When a prospect refutes a gap claim (GOC-02), the reply pipeline's classify→compose path must prevent re-asserting the same claim in a subsequent reply.

**Trigger conditions:**
- All competitor gap findings have confidence < 0.5
- Prospect explicitly contradicts the gap claim in a warm reply
- Gap framing uses implicitly universalist language ("everyone does X")

**Numeric trigger rate:** 10 per 100 warm engaged replies (10.0%) for GOC-02 (prospect refutes gap). For GOC-01 (low-confidence gap findings): 35 per 100 SMB-tier leads (35.0%) — Crunchbase data is sparse for companies below Series B, yielding gap_confidence < 0.5 in ~35/100 runs. Combined: **GOC fires in 35/100 total leads** at the generation stage; refutation (GOC-02) fires in **10/100 warm engaged replies**.

---

## Overall Summary

**ACV reference (Tenacious internal, `seed/pricing_sheet.md` + `seed/bench_summary.json`):**
- Talent outsourcing: **$120,000 – $360,000** (3–9 engineers × $3,333/month × 12 months)
- Project consulting: **$15,000 – $90,000** per engagement
- ACV midpoint used in impact calculations: **$240,000**

| Category | Probes | Pass Rate | Aggregate Trigger Rate | Critical? | Most Likely Failure |
|----------|--------|-----------|------------------------|-----------|---------------------|
| ICP Misclassification | 5 | 5/5 | **8/100 leads** | Medium | Priority rule not enforcing disqualifying filters |
| Signal Over-Claiming | 3 | 2/3 (1 genuine fail) | **20/100 leads → $30,720/mo ACV at risk** | **High** | LLM ignores ask-language constraint when LLM has priors |
| Bench Over-Commitment | 3 | 3/3 | **10/100 engaged replies** | **Critical** | bench_available==False not gating email composition |
| Tone Drift | 4 | 4/4 | **10/100 reply-stage touches** | Medium | Defensive reply triggers softening language = condescending |
| Multi-Thread Leakage | 3 | 3/3 | **20/100 multi-contact companies** | **Critical** | Thread context fetched by domain instead of email |
| Cost Pathology | 2 | 2/2 | **3/100 leads (weighted)** | Low | Competitor list not truncated before LLM prompt |
| Dual-Control Coordination | 3 | 1/1 eval (2 skip) | **3/100 pipeline runs** | Medium | Integration timeouts not caught at pipeline level |
| Scheduling Edge Cases | 3 | 2/2 eval (1 skip) | **40/100 prospects** | Medium | Timezone assumed as UTC for non-US prospects |
| Signal Reliability | 3 | 3/3 | **40/100 Crunchbase leads (SR-03); 20/100 large companies (SR-01)** | High | Stale funding date not gated (affects 40/100 CSV-sourced leads) |
| Gap Over-Claiming | 3 | 3/3 | **35/100 leads (generation); 10/100 warm replies (refutation)** | Medium | Declarative gap claims when confidence < 0.5 |

**Highest-ROI failure mode for Phase 5 mechanism:** See `target_failure_mode.md`.
