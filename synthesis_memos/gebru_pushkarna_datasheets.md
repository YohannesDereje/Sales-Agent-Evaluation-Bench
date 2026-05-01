# Synthesis Memo: Datasheets for Datasets + Data Cards for AI Systems
**Papers:** Gebru et al. (2021) + Pushkarna et al., FAccT 2022
**Author:** Yohannes | **Date:** 2026-05-01

---

## What the Papers Argue

Gebru et al. argue that every dataset released for ML use must be accompanied by a datasheet — a structured document that captures motivation, composition, collection process, preprocessing decisions, intended uses, unsuitable uses, distribution, and maintenance. The central claim is that documentation must be created **concurrently** with the dataset, not retroactively — because the reasoning behind decisions (why a threshold was chosen, why a category was excluded) is only available to the people who made those decisions at the time they made them.

Pushkarna et al. extend this with the Data Card framework, introducing three documentation scopes: **Telescopic** (high-level overview for a general audience), **Periscopic** (technical detail for practitioners), and **Microscopic** (the human rationale behind specific choices — the "why" behind a number, not just the number itself). Their 31-theme framework organizes documentation across these scopes for large-scale industrial dataset releases.

---

## Where I Disagree — and Why My Evidence Supports It

**Pushkarna's 31-theme framework is over-engineered for small research artifacts and introduces documentation overhead that exceeds the value it adds.**

Pushkarna et al. designed the Data Card framework for large industrial datasets — the motivating examples in their paper include datasets with millions of examples, teams of dozens of annotators, and production deployment timelines measured in years. The framework's 31 themes cover concerns like legal review, accessibility compliance, and multi-stakeholder governance that are appropriate at that scale.

Tenacious-Bench v0.1 has ≤335 tasks, one author, a $10 budget, and a 7-day timeline. Applying all 31 themes would require documentation longer than the dataset itself. More importantly, most of the 31 themes would contain stub content ("N/A — single-author research artifact") that adds noise without signal.

My design decision: scope `datasheet.md` to **Gebru's 7 sections** (which remain universally applicable regardless of dataset size) plus **Pushkarna's three scopes** (Telescopic / Periscopic / Microscopic) applied within each section. The three-scope structure is the genuinely valuable contribution — it forces documentation of the *why* (Microscopic scope) alongside the *what* (Telescopic) and *how* (Periscopic). This is the part that decays without concurrent documentation.

The Microscopic scope is where this matters most for Tenacious-Bench: why is the Jaccard dedup threshold 0.80 and not 0.70? Why is the judge filter threshold ≥3 on all dimensions and not ≥4? These rationales are only available now, during construction. Gebru's concurrent-creation rule and Pushkarna's Microscopic scope together force us to capture them — even without implementing all 31 themes.

---

## What I Adopt From the Papers

- **Concurrent documentation:** `datasheet.md` is written alongside dataset generation in Phase 4, not after submission.
- **Gebru's 7 sections:** All 7 sections (Motivation, Composition, Collection Process, Preprocessing, Uses, Distribution, Maintenance) are present with non-stub content.
- **Pushkarna's three scopes:** Applied within each section to distinguish overview (Telescopic), technical detail (Periscopic), and decision rationale (Microscopic).
- **Threshold documentation in Microscopic scope:** Every numeric threshold in the pipeline (Jaccard 0.80 for dedup, Jaccard 0.60 for contamination, filter score ≥3, pass threshold ≥0.70) is documented with its specific rationale in the Microscopic scope of the relevant section.
