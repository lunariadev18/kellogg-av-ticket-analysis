# Interview Prep — Classroom AV Ticket Analysis

This document teaches the project from the inside: what every piece of code does, why
each analytical choice was made, and how to talk about it. The goal is that you can
answer *any* question about this repo because you understand it, not because you
memorized answers.

**The honest framing, first.** The public data is synthetic; its statistical shape was
calibrated against aggregate summary statistics you measured from a real ServiceNow
export (which never left your private environment). If an interviewer asks, say exactly
that — it's a strength: *"The real data is confidential, so I profiled it privately —
volume, seasonality, issue mix, resolution percentiles — and tuned a synthetic generator
until it matched those aggregate shapes. The public repo shows the same analysis I ran
on the real thing, with fictional rooms and names."* Never imply the repo's numbers are
real measurements; never share which specific institution the aggregates came from
beyond what your resume already says.

**The five numbers to know cold:**

| Fact | Number |
|---|---|
| Raw export that was automation noise | ~71% (25Live scheduling syncs) |
| Human AV tickets missing a room number | 27% |
| Legacy rooms' display-signal share vs others | 38% vs 10% (χ²=56.4) |
| Legacy display-signal tickets recurring ≤14 days | 56% |
| Excess display-signal tickets in legacy rooms | ~54/yr ≈ 11% of volume |

---

## a) Code walkthrough

### `scripts/generate_data.py` — the data generator

**What it does, top to bottom:**

1. **`CLASSROOMS`** — 22 fictional rooms in one building, each with floor, seats, a
   `config_variant`, a utilization weight (heavily skewed — a handful of core rooms
   carry most teaching, as in the real building), and an equipment string. Three
   variants: `legacy_matrix_v1` (2017 HDMI matrix, auto-switching off), `nvx_early`
   (2021 rollout), `nvx_standard` (2023 baseline).
2. **`ISSUES`** — a 14-type catalog under six categories mirroring a real higher-ed
   service taxonomy (AV Technical Support, Lecture Capture, Webconferencing,
   Equipment Maintenance & Repair, Setup & Configuration, Consultation). Each issue
   has a frequency weight, a **recurrence propensity** (`repeat_p`), a calendar-time
   resolution median + lognormal spread, and realistic description/resolution templates.
3. **`CONFIG_MULTIPLIERS`** — the planted pattern: legacy rooms get ~2.9× weight on
   display-signal issues; `nvx_early` rooms a mild bump on webconferencing and capture
   failures (a second, weaker pattern so the analysis isn't one-note).
4. **Calendar profiles** — `MONTH_WEIGHTS` (spring peak, summer/December troughs),
   `YEAR_GROWTH`, `DOW_WEIGHTS` (Tue–Thu heavy, real Saturday volume), and two
   hour-of-day profiles: the building's broad mid-day+evening curve, and a
   "cold-start" profile (8–9 AM and ~6 PM) used for legacy display issues.
5. **Resolution times** — lognormal draws in **calendar minutes** (queue time
   included), medians ranging from ~2 hours (display fixes) to ~6 days (scheduled
   maintenance). Why lognormal: durations are positive and right-skewed — most quick,
   a few very long. Why calendar time: that's what ticket timestamps actually measure.
6. **Recurrence chains** — the interesting part. After each ticket, a while-loop
   spawns a follow-up in the same room + subcategory 1–13 days later with probability
   `repeat_p` (decaying ×0.55 per link; legacy display issues capped at 0.68). This is
   how the generator reproduces the real ~30% baseline repeat rate — real faults come
   in bursts because the root cause survives the first fix.
7. **Noise injection** — ~3.4 scheduling-automation rows per human ticket (created by
   "25Live", category "Classroom Scheduling", fictional course titles), 30% blank room
   IDs, ~5% open tickets, casing/whitespace mess, ~2.5% double-submissions.
8. **Two outputs** — `av_tickets.csv` (raw export, noise included) and
   `classrooms.csv` (asset inventory). Config lives *only* in the second file, so the
   analysis must join — like production.

**Tricky parts a hiring manager might poke at:**

- *Why a fixed seed (42)?* Reproducibility — anyone can regenerate byte-identical data
  and verify every number in the README.
- *How was it calibrated?* Two-pass: build the structure, then profile the real export
  privately (volume, monthly shape, hour/weekday curves, category mix via keyword
  bucketing, resolution percentiles after fixing comma-formatted duration fields,
  missing-room rate, repeat rate) and tune constants until the synthetic marginals
  matched. Only aggregates crossed the boundary.
- *What is deliberately NOT calibrated?* The legacy-config pattern itself — the real
  export has no configuration column, so the config→failure link is planted at
  believable magnitudes. Volunteering this distinction is what makes the project
  credible.

### `notebooks/av_ticket_analysis.ipynb` — the analysis

**Section 1 — Load + the first discovery.** Before any cleaning, a `groupby(created_by)`
reveals the largest requester is `25Live` — the scheduling integration, ~70% of rows.
This is framed as a discovery rather than a given, because that's how it happens in
real life: you profile the export before trusting it.

**Section 2 — Cleaning.** Every decision in a table with evidence and choice. The six
that matter:

| Decision | Why this way |
|---|---|
| Drop `created_by == "25Live"` rows | They're calendar syncs; keeping them means measuring bookings, not demand |
| Parse timestamps with `pd.to_datetime` | Can't compute durations or resample on strings |
| Keep blank-room tickets for volume/time metrics, exclude from room-level analysis | Dropping 27% of tickets everywhere would understate demand; pretending they have rooms would fabricate data. The bias is *named* in the notebook |
| Map lowercase category → canonical, then `assert` | Normalize *and verify* — a silent mapping failure becomes a loud error |
| Duplicates = same room + subcategory within 15 min | Double-submissions, excluded from counts; threshold stated so it can be challenged |
| Open tickets excluded from duration metrics, never imputed | There's no defensible estimate of how long an unresolved ticket "took" |

- `merge(..., validate="many_to_one")` — pandas verifies room IDs are unique on the
  right side; duplicate keys would silently multiply ticket rows otherwise.
- The join runs `how="left"` and the assert only covers room-attributed tickets —
  blank rooms legitimately get `NaN` config.

**Section 3 — EDA.** Monthly volume (spring peaks, +32% YoY), category/subcategory mix
(lecture capture is the largest single category — recordings fail *silently* and are
discovered after class, which is its own preventative-monitoring argument), and a
day-of-week × hour heatmap showing demand runs into the evening and Saturdays — a
staffing insight independent of the headline finding.

**Section 4 — Resolution times, honestly.** Calendar time, not hands-on time: median
15h, 19% within the hour, tail to weeks. Reported as percentiles, never means. Then the
project's best analytical moment: **the naive comparison points the wrong way** —
legacy rooms look *faster* overall because their mix skews toward quick interrupt
fixes while standardized rooms carry multi-day scheduled work. Like-for-like
(display-signal issues only), legacy rooms take **more than twice as long** (3.4 vs
1.5 h median). Know this cold: it's a composition/Simpson's-paradox effect, and it's
the answer to "biggest challenge" and "a time a number lied to you."

**Section 5 — The repeat pattern.** Three moves:
1. `groupby(["classroom_id","subcategory"])["created_at"].shift()` → gap to previous
   same-room-same-issue ticket → `is_repeat` if ≤ 14 days. (The pandas equivalent of
   SQL's `LAG` window function — say that; it lands.)
2. Repeat rate by config: 37% legacy vs 19% NVX-standard; legacy display-signal
   tickets recur at 56%.
3. Hour-of-day fingerprint (8–9 AM + ~6 PM clustering in legacy rooms = cold-start
   EDID handshake signature) and a chi-square test on (legacy?) × (display-signal?):
   χ²=56.4, p≈6e-14. Volunteer the caveat: the test shows association, not cause;
   the mechanism evidence is the timing fingerprint; the definitive test is
   refreshing one room and watching a quarter (a natural A/B).

**Section 6 — Impact, conservatively.** Not "legacy rooms have more tickets" (utilization
confounds that) — instead: excess *display-signal* tickets above the other rooms' rate:
~54/year, ~11% of all human volume. Choosing the conservative frame over the flashier
one is itself an interview talking point.

**Section 7 — Limitations.** Synthetic + planted pattern; no teaching-hours
denominator; missing-room bias; calendar-time metrics mix queue and work; observational.
Read it before any interview.

**Why pandas here and SQL in `/sql`?** Exploration is iterative — notebook cycles are
seconds, charts live next to transformations, and scipy's chi-square isn't SQL's job.
SQL is the deployable form for recurring reports. Same aggregations in both proves the
logic is tool-independent.

**Why matplotlib+seaborn split?** Matplotlib for bar/line/box charts (full control,
color-by-entity, direct labels); seaborn only where it earns its keep — the two
heatmaps. One color per configuration everywhere (orange = legacy, always); titles
state findings, not axes.

### `scripts/build_dashboard.py`

Rebuilds four key views plus a KPI row as one PNG via `GridSpec`, re-deriving every
number from the CSVs (nothing hardcoded) with the same cleaning as the notebook.
Mirrors a Looker Studio layout: scorecards up top, trend + breakdowns below.

### `scripts/export_looker.py` + the Looker Studio dashboard

The [interactive dashboard](https://lookerstudio.google.com/reporting/d73c802e-b650-4b93-8d8b-0593e27f0bd6)
is built in Looker Studio on top of a dedicated export, and the design decisions are
worth being able to defend:

- **Feed BI tools an analysis-ready table, not raw data.** `export_looker.py` applies
  the *same* cleaning pipeline as the notebook (automation filter, dedup, trim,
  canonical categories, room join) and pre-computes every flag the dashboard needs —
  `is_repeat_14d`, `is_display_signal`, `resolution_band`, weekday/hour. Rebuilding
  that logic in Looker Studio calculated fields would be fragile and unreviewable;
  keeping transformations in version-controlled Python and letting the BI layer only
  visualize is the standard production split (in a real deployment, the export step
  is a warehouse view).
- **Connector choice:** file upload (a snapshot) rather than a live connection —
  appropriate because the dataset is static. A recurring report would use a
  BigQuery/Sheets source on a refresh schedule.
- **One calculated field only:** the repeat-rate metric,
  `SUM(IF(is_repeat_14d = "Yes", 1, 0)) / COUNT(ticket_id)`. Two lessons learned
  building it that make good interview stories: Looker Studio string comparison is
  **case-sensitive** (`"YES"` silently returns 0%), and the first result came out
  21% instead of the notebook's 29% — not a bug, but **denominator dilution**: the
  27% of tickets without a room can never be flagged as repeats, yet they sat in the
  denominator. Scoping the metric with a `room_attributed = Yes` filter reconciled it
  exactly. Knowing *which* denominator a metric uses is half of BI work.
- **Color pinning:** dimension-value colors are locked per configuration (legacy =
  orange `#EB6834`, standard = blue `#2A78D6`, early = aqua `#1BAF7A`) so the
  interactive dashboard, the static PNG, and every notebook chart read as one system —
  color follows the entity, never the sort order.
- **Transparency carried through:** the dashboard header itself labels the data
  synthetic and links the repo.

### `sql/analysis_queries.sql`

Six queries mirroring the notebook — every one carries `WHERE created_by <> '25Live'`
(the automation filter is not optional), the `TRIM`-guarded join, `LAG ... OVER
(PARTITION BY room, subcategory)` for repeats, and `PERCENTILE_CONT` for medians.
Queries 1–5 were executed against SQLite to verify they run; counts sit slightly above
the notebook's because dedup happens in pandas. Know why.

---

## b) Methodology (plain language)

**The approach in one paragraph.** Profile the export before trusting it (finding: 71%
automation noise). Clean with documented, challengeable rules. Quantify where volume
concentrates (season, room, issue). Join to the asset inventory to find what the heavy
rooms share — a configuration. Characterize the failure signature (issue mix ×4,
cold-start timing, 56% recurrence, 2× like-for-like resolution). Test the association.
Size the impact conservatively. Convert to four process changes.

**The calibration methodology** (unique to this project — own it):
1. Real export profiled *privately*: row counts, creator mix, monthly/weekday/hourly
   curves, category mix (via keyword bucketing of short descriptions, since real
   categories were coarse), resolution percentiles, missing-room rate, repeat rate.
2. Gotchas found while profiling — worth telling: the export was Windows-1252 encoded,
   not UTF-8; duration fields came with comma thousands-separators that silently
   truncated a naive numeric parse to values under 1,000 seconds (caught because a
   max of 16 minutes was implausible); "priority" was constant across the entire
   instance and therefore useless.
3. Generator constants tuned until synthetic marginals matched real aggregates within
   sensible tolerance — then stopped. Chasing exact matches would be overfitting a
   clean lognormal to a messier reality.

**How the pattern was identified** — a chain of simple, corroborating aggregations:
volume by room → join reveals shared config → per-room normalization (56 vs 15
tickets/room) → issue-mix comparison (38% vs 10%) → hour-of-day fingerprint →
recurrence metric (56%) → chi-square. No single statistic carries it; five converging
views do.

**Limitations** (volunteer them): the pattern is planted (method demo, not discovery);
utilization confounds raw volume (why the analysis leans on composition/timing/repeats);
27% missing rooms bias room-level metrics in an unknown direction; calendar time mixes
queue and work; observational.

---

## c) Possible interview questions, with answers

Skeletons to internalize, not scripts.

**"Walk me through this project."**
> In my AV support role I analyzed ServiceNow ticket data across 20+ classrooms. That
> data's confidential, so for the public version I profiled the real export privately
> and calibrated a synthetic generator to its aggregate shape — volume, seasonality,
> issue mix, resolution percentiles — then published the full analysis on the synthetic
> data. First finding: 71% of the raw export was scheduling-automation noise, so
> filtering that was step zero. The headline: five rooms sharing a legacy AV
> configuration had four times the display-signal failure share, clustered at
> first-class-of-day — a cold-start HDMI handshake signature — with 56% of those
> tickets recurring within two weeks, because power-cycling treats the symptom.
> Recommendations: standardize those five rooms, add a cold-start check to opening
> rounds, front-load maintenance before the spring demand peak, and make the room
> field required — 27% of tickets couldn't even be attributed to a room.

**"What was the biggest challenge?"**
> Two candidates, both real. Analytically: the resolution-time comparison pointed the
> wrong way at first — legacy rooms looked *faster* overall, which was a category-mix
> illusion; like-for-like they were twice as slow. Lesson: never compare groups on an
> aggregate when their work composition differs. On the data side: making the synthetic
> data believable. My first generator was built on guesses — 20-minute resolution
> medians, morning-peak demand. Profiling the real export destroyed half of them: real
> resolution is calendar time with a median around a day, demand peaks mid-day and runs
> into evening classes, and the biggest category was one I hadn't included at all
> (lecture capture). Calibrating against measured aggregates is what made the project
> honest.

**"How did you validate your findings?"**
> Mechanically: asserts after category mapping, `validate="many_to_one"` on the join.
> Statistically: chi-square on configuration × issue type — but with n≈540 attributed
> tickets I lead with effect size, 38% vs 10%. Triangulation: volume, mix, timing,
> recurrence, and resolution all point at the same five rooms. Cross-checks: the SQL
> queries independently reproduce the pandas numbers. And on data quality itself: I
> caught a silent parsing failure because a max resolution of 16 minutes was
> implausible — sanity-checking against domain knowledge is validation too.

**"What would you do differently?"**
> Add a denominator: tickets per class-hour from the scheduling system, since
> utilization confounds per-room counts — ironically the 25Live data I filtered out as
> noise contains exactly that signal, so 'noise' was really 'wrong table.' I'd also
> use ServiceNow's parent/child incident links instead of my 14-day heuristic, and
> push to fix the 27% missing-room rate at the form level so future analysis starts
> cleaner.

**"How would this scale to a larger dataset?"**
> Pandas handles this to low millions of rows; past that the aggregations move to the
> warehouse — which is why the SQL versions exist. The recurrence and repeat logic is
> a window function, which warehouses do natively. At scale I'd materialize monthly
> aggregate tables and have the notebook read those. The logic doesn't change; where
> it executes does.

**"Why Python instead of SQL / vice versa?"**
> Both, deliberately. Python for exploration and statistics; SQL for anything
> recurring, running where the data lives. Same logic in both — the repeat metric is
> `groupby().shift()` in pandas and `LAG` in SQL. That equivalence is the point.

**"How did you handle missing data?"**
> Three kinds, three treatments. Missing `resolved_at` = open ticket: keep in volume,
> exclude from durations, never impute. Missing room (27%): keep in volume/time
> metrics, exclude from room-level analysis, and name the bias. Constant/useless
> fields (priority in the real instance): drop rather than pretend. The principle:
> missingness is information about the process — the 27% became a recommendation.

**"What business impact did this analysis have?"**
> Conservatively framed: ~54 excess display-signal tickets a year — about 11% of all
> human AV volume — concentrated in five rooms and in the worst slot, the first class
> of a teaching block. Plus the compounding costs: 56% recurrence means technicians
> re-fix the same rooms, and instructors lose class time. The recommendations target
> exactly that slice, and the repeat-rate metric gives the team an ongoing monitor.

**"How would you productionize this?"**
> Scheduled extract into a warehouse; cleaning rules (automation filter, trimming,
> canonical categories, dedup) in the load layer; the SQL as views feeding a Looker
> Studio dashboard on refresh; and an alert when any room's 30-day repeat rate crosses
> a band — so the next legacy-config pattern gets caught in weeks, not after 18 months.

**"What would you add with more time?"**
> Tickets-per-class-hour normalization; a control-chart of weekly repeat rate per room;
> a Pareto view of subcategories; and — after the refresh ships — a before/after chart
> of the five rooms, because the intervention is the natural experiment.

**Project-specific technicals to be ready for:**
- *"Why is your resolution median 15 hours? Isn't that terrible?"* It's calendar time
  including queue — the request-to-resolution experience — not 15 hours of labor. The
  queue is really two workloads: interrupt fixes (median ~4h) and scheduled work
  (median days). Any SLA should be defined per workload.
- *"Explain the recurrence-chain idea in the generator."* Real repeat tickets aren't
  independent random events; an unresolved root cause emits tickets in bursts. Each
  ticket spawns a follow-up with an issue-specific probability, decaying per link.
  Without it, the synthetic repeat rate came out a third of the real baseline.
- *"What's EDID / an HDMI handshake?"* On connect, the display describes its
  capabilities in an EDID data block and the source negotiates a format. Old matrix
  switchers with auto-switching disabled fumble this from cold power-on — black screen
  until someone forces re-negotiation. That's why failures cluster at the first class
  of the day and evening blocks.
- *"Why chi-square and not a t-test?"* Two categorical variables → contingency-table
  association test. A t-test compares means of a continuous variable.
- *"Why 14 days for repeats? Why 15 minutes for duplicates?"* Operational judgment
  calls, stated explicitly so they're challengeable. Duplicates: re-submissions happen
  within minutes. Repeats: two weeks ≈ one teaching cycle for a recurring class.

---

## d) Key terms, in plain language

- **ETL** — Extract, Transform, Load: pull from a source (ServiceNow export), clean
  and reshape (notebook Section 2), land it somewhere usable.
- **Aggregation / `groupby`** — collapsing rows into summary numbers per group;
  pandas' split-apply-combine, SQL's `GROUP BY`.
- **Join / merge** — matching rows across tables on a key (`classroom_id`). The
  analytic centerpiece here: tickets know what happened; the asset table knows what's
  installed.
- **Many-to-one validation** — asserting the join's expected shape so duplicated keys
  can't silently multiply rows.
- **Window function / `LAG`** — SQL that reads neighboring rows without collapsing
  groups ("previous ticket in this room+issue"). Pandas: `groupby().shift()`.
- **Calendar time vs work time** — elapsed clock time (queue included) vs hands-on
  effort. Ticket timestamps measure the former.
- **Median vs mean / percentiles** — with heavy right skew the mean is pulled far
  above the typical case; medians and percentiles describe the distribution honestly.
- **Lognormal distribution** — log of the value is bell-curved: positive, mostly
  small, long right tail. The standard duration shape.
- **Composition / Simpson's-paradox effect** — an aggregate comparison across groups
  with different work mixes can hide or *reverse* the within-group truth. Section 4 is
  a live example (the naive sign was backwards).
- **Chi-square test / p-value / effect size** — association test for two categorical
  variables; p = chance of seeing this under independence; effect size (38% vs 10%) is
  what actually persuades.
- **Recurrence / repeat rate** — same room + same issue within 14 days; the
  expensive-ticket metric because it means the cause survived the fix.
- **Calibration (synthetic data)** — tuning a generator's parameters so its output
  matches measured aggregate statistics of a real dataset, without copying any records.
- **Counterfactual estimate** — "what if legacy rooms had the baseline display-signal
  rate?" — a simple scenario with stated assumptions used to size impact.

---

## e) Storytelling

### 30 seconds ("walk me through your portfolio")

> "From my AV support role: I analyzed ServiceNow tickets across 20+ classrooms. The
> real data's confidential, so I calibrated a synthetic dataset to its aggregate shape
> and published the full analysis. Two findings carry it: 71% of the raw export was
> scheduling-automation noise — filtering that was step zero — and five rooms sharing
> one legacy AV configuration had four times the display-signal failure rate, clustered
> at first class of the day, with over half recurring inside two weeks. The fix —
> standardize those rooms plus preventative checks timed to the demand calendar — was
> worth about 11% of annual ticket volume."

### 2 minutes (deeper dive)

> "The operational problem: repeat 'no display' calls at class start, same handful of
> rooms, 'fixed' days earlier. I had the ServiceNow export and an AV asset inventory.
>
> Before analysis, profiling: 71% of the export was auto-filed by the room-scheduling
> integration — measuring bookings, not demand. Then real mess: 27% of human tickets
> had no room recorded, timestamps were strings, categories had casing drift, and some
> tickets were double-submitted. Every cleaning rule got documented with its rationale.
>
> Exploration: demand peaks in spring and runs into evening and Saturday classes —
> useful for staffing and for scheduling maintenance in the quiet weeks. Lecture
> capture was the biggest single category — silent failures found after class. But the
> thread was display-signal issues: joining to the asset table showed the five heaviest
> rooms all ran a 2017 config — HDMI matrix, auto-switching disabled. Their tickets
> were 38% display-signal versus 10% elsewhere, clustered at 8–9 AM and 6 PM — the
> cold-start handshake fingerprint — and 56% recurred within two weeks.
>
> The subtle part: naive resolution-time comparison said legacy rooms were *faster*.
> That was composition — their mix skews toward quick interrupt fixes. Like-for-like,
> they were twice as slow. I backed the pattern with a chi-square but led with effect
> size, and sized impact conservatively: only the excess display-signal tickets, about
> 54 a year, 11% of volume.
>
> Output: standardize the five rooms, cold-start checks on opening rounds, maintenance
> front-loaded before the spring peak, and make the room field required — because 27%
> missing attribution caps what any future analysis can see."

### STAR format (behavioral)

- **Situation:** Classroom AV team fielding recurring morning "no display" failures
  across 20+ rooms; anecdotes about problem rooms, no quantified view.
- **Task:** Use ServiceNow history to find where volume and repeat issues concentrated
  and turn it into preventable-work recommendations.
- **Action:** Profiled the raw export (filtered 71% automation noise), cleaned and
  de-duplicated with documented rules, joined tickets to the AV asset inventory,
  analyzed seasonality/timing/issue mix, defined a 14-day repeat metric, identified
  five rooms sharing a legacy configuration with a cold-start failure signature,
  corrected a misleading aggregate comparison, verified the association statistically,
  sized impact conservatively.
- **Result:** Four process recommendations targeting ~11% of annual volume — the
  class-blocking kind — plus an ongoing repeat-rate monitor and a data-quality fix
  (required room field) that improves every future analysis. (Publicly demonstrated on
  transparent synthetic data calibrated to the real environment's aggregate shape.)

### Delivery notes

- Lead with findings, not tooling; the calibration story is your differentiator —
  most portfolio projects use toy data and can't say why their numbers are shaped
  the way they are.
- The one story to always land: the naive resolution comparison whose *sign was
  backwards* until mix-corrected. It proves you interrogate numbers before reporting.
- If asked anything you don't know, reason from the data model — tickets, rooms, a
  join, aggregations over time windows. Everything here is built from those pieces.
