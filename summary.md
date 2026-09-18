# PsychroMol — Summary

**Working thesis title:** *Development and Application of a Real-Time
Psychrometric-Based Decision Support System for Greenhouse Environment
Management*

**State at time of writing (2026-09-18):** engine verification 33/33 checks
passed; 53 browser-side tests and 77 server-side tests passed; interface
verified in a headless browser with no console errors.

This document summarises the **current** system (version 3). Section 11 records
what changed from version 2 and why, because those choices are themselves
results worth reporting.

---

## 1. What the application is

PsychroMol is a **rule-based decision support system (DSS)** for greenhouse
climate. It takes one air temperature and one relative humidity reading, turns
them into the full moist-air (psychrometric) state, classifies that state
against bands set for the crop and growth stage, and matches the classification
against rules a grower can read and edit. The output is one recommendation with
a severity, and — one click away — the classification and the arithmetic that
produced it.

The chain it implements:

```
JSON sensor link → stored reading → psychrometric calculation
                 → classification (LOW / OPTIMAL / HIGH)
                 → rule match → management recommendation
                 → (optional) human action
```

What it deliberately is **not**:

* not AI or machine learning — no prediction, no learned model;
* not autonomous control — no rule switches anything; the system advises.

Two principles distinguish it from a monitoring dashboard:

1. **Temperature and RH are inputs, not the analytical variables.** Advice is
   reasoned over derived quantities, chiefly the vapour-pressure deficit (VPD).
2. **Nothing is asserted without a source.** Every formula, every band and
   every recommendation is shown with a **?** that opens the reference it rests
   on, quoted verbatim with its page.

---

## 2. System architecture

```
frontend/ (static site, no build step) — ALL calculation happens here
  psychro.js      ASHRAE moist-air engine (the only place any relation exists)
  geometry.js     psychrometric + Mollier curves, crop target zone
  dss.js          growth stages, classification, default rules, explanation
  references.js   sources and the text behind every "?"
  fields.js       JSON Pointer paths, number/time parsing, field detection
  quantities.js   displayable quantities, units, decimals
  app.js, chart.js, trend.js, api.js
        │ HTTP/JSON (kPa)
        ▼
psychromol/ (server: storage and collection only)
  api/       FastAPI routers: profiles, readings, rules, sources
             + one background loop: poll_sources (1 s tick, per-profile interval)
  fetcher.py fetch a JSON link, extract, store
  fields.py  the server's copy of extraction only (parity-tested with fields.js)
  db/        SQLAlchemy models + Repository (SQLite, WAL) + v2 → v3 upgrade
```

The server performs **no psychrometric calculation at all**. This is the central
architectural decision of version 3: the science lives in one auditable file
that runs where the results are displayed, and the backend is reduced to what a
browser genuinely cannot do.

Two things cannot be done in the browser, and only those two remain server-side:

* **the database**, and
* **collecting readings while no browser is open** — a greenhouse log must not
  have gaps because nobody had the page up.

### Technology

| Layer | Choice |
|---|---|
| Calculation, DSS, charts, export | Vanilla ES modules in the browser, no framework, no build step |
| Server | Python ≥ 3.10, FastAPI + Uvicorn, Pydantic v2 |
| Database | SQLite via SQLAlchemy 2.0 (WAL) |
| Charts | Hand-written SVG (`chart.js`, `trend.js`), geometry from `geometry.js` |
| Tests | `node --test` (browser side), pytest (server side), ruff |
| Verification aid | PsychroLib 2.5.0, used once to generate a fixture file; never a runtime or test dependency |

---

## 3. The psychrometric engine (`frontend/js/psychro.js`)

**Source:** ASHRAE Handbook — Fundamentals (2017), Chapter 1. Every equation
carries its number in a comment; the full record is
`docs/psychrometric-methodology.md`.

### 3.1 Quantities derived from (t, RH, p)

| Quantity | ASHRAE basis | Unit shown |
|---|---|---|
| Saturation vapour pressure `p_ws` | Eq. (5) over ice < 0 °C, Eq. (6) over water ≥ 0 °C (Hyland–Wexler) | kPa |
| Vapour pressure `p_w` | Eq. (12) and (22): `p_w = φ p_ws` | kPa |
| Humidity ratio `W` | Eq. (20) | g/kg dry air |
| Dew point (frost point < 0 °C) | Numerical inverse of Eq. (5)/(6) | °C |
| Wet-bulb temperature | Numerical inverse of Eq. (33) and (35) | °C |
| Specific enthalpy `h` | Eq. (30) | kJ/kg dry air |
| Specific volume `v` | Eq. (26) | m³/kg dry air |
| Density | Eq. (11) | kg/m³ |
| Absolute humidity | `1000 W / v` (ASHRAE definition `d_v = M_w/V`) | g/m³ |
| VPD (air) | `p_ws(t) − p_w` | kPa |
| Standard atmosphere | Eq. (3) | kPa |
| Mollier ordinate | `h − 2501 W` | kJ/kg |

**Two citation corrections** were made while porting the engine from the earlier
Python implementation, both verified against PsychroLib's documentation: the
below-freezing wet-bulb relation is **Eq. (35)**, not (34), and relative
humidity is **Eq. (12) with (22)**. Degree of saturation was removed: it is
defined in the 2009 Handbook, not the 2017 one, and nothing in the interface
used it.

### 3.2 Key design decisions (each documented and tested)

1. **Pressure is a per-profile choice**: the standard atmosphere (Eq. 3 at sea
   level), a fixed value, or a value read from the JSON link with its unit. In
   the last case a reading without pressure falls back to the standard
   atmosphere and the interface says so.
2. **Units:** the engine works in **Pa**; the API, database and interface use
   **kPa**. Conversion happens in two files only (`units.js`, `units.py`), and
   every API field name carries its unit (`vpd_kpa`, `dew_point_c`).
3. **Inverses are solved by bisection**, not by ASHRAE's curve fits (Eq. 37/38)
   and not by Newton–Raphson: bisection cannot diverge on unattended live data.
   PsychroLib inverts the same equations for the same stated reason.
4. **The wet-bulb bracket starts at the dew point**, so cold or very dry air is
   still bracketed.
5. **A measured relative humidity is carried through exactly.** Deriving φ back
   from the humidity ratio returned 59.999999999999993 % for a 60 % reading,
   which classified a reading sitting exactly on a band limit as LOW. The state
   now computes `p_w = φ p_ws` directly and keeps φ as the sensor reported it.
6. **VPD is air VPD, not leaf-to-air VPD** — leaf temperature is not measured,
   and the reference popup says so. Thesis text must say "air VPD".
7. **Out-of-range inputs are rejected**, not extrapolated (−100…200 °C,
   0…100 % RH, 20…200 kPa). The reading is still stored unchanged and the
   dashboard states plainly that it was not assessed.
8. **The state object is immutable**, so every consumer (cards, chart, table,
   export) sees identical numbers. Dew point and wet bulb are computed lazily,
   because each costs a bisection and a large export usually needs neither.

### 3.3 Psychrometric vs. Mollier

Both charts are **projections of the same state**, not two calculations:

| Chart | x-axis | y-axis |
|---|---|---|
| Psychrometric (ASHRAE) | dry-bulb temperature | humidity ratio |
| Mollier h–x (European) | humidity ratio | `h − 2501 W` |

All curves — saturation line, RH family, isenthalps, wet-bulb and
specific-volume lines, isotherms, and the crop's **target zone** — are generated
by `geometry.js` by calling the engine at the profile's actual pressure, so the
chart cannot disagree with the numbers beside it. The target zone is bounded by
real RH curves, not drawn as a rectangle. Reference for the diagram itself:
Mollier, R. (1923), *Ein neues Diagramm für Dampfluftgemische*, Z. VDI 67(36),
869–872.

### 3.4 Validation

| Source | Scope | Result |
|---|---|---|
| ASHRAE saturation-pressure table | 19 points, −60…100 °C, tol 5 × 10⁻⁴ relative | all pass |
| ASHRAE Ch. 1 worked Example 1 | 40 °C db / 20 °C wb | W, h, t_d, φ, v within printed precision (t_d Δ 0.034 K) |
| ASHRAE Eq. (37)/(38) dew-point regressions | 0–50 °C × 20–100 % RH | max deviation 0.031 K |
| PsychroLib 2.5.0 (independent implementation) | 102-point fixture, −10…50 °C × 5…100 % RH, 4 pressures 85–105 kPa | max ΔW 9.8 × 10⁻⁵ rel; Δt_d 1.2 × 10⁻³ K; Δt* 6.6 × 10⁻⁴ K; ΔVPD 0.056 Pa |
| Researcher's earlier browser tool (Magnus formulation) | 8 points, 17.8…44.6 °C | within the Magnus offset (~0.4 % on p_ws) |
| Internal consistency | round-trips, 4 constructors agree, `t_d ≤ t* ≤ t`, monotonicity every degree | all pass |
| Chart geometry | every drawn curve inverted back to its own labelled value | all pass |

```bash
node scripts/verify_engine.mjs   # 33 checks
node --test tests/js/            # 53 tests
```

**A property of the standard, not a bug:** ASHRAE's Eq. (33) and (35) meet with
a step at exactly 0 °C, so the humidity ratio of a 0 °C wet-bulb line inverts to
a few tenths of a degree below zero (−0.35 K at 5 °C dry bulb). PsychroLib
reproduces the same values to 0.001 K; a test pins this.

**Not validated:** tabulated values outside −20…60 °C; pressures beyond
85–105 kPa; the Mollier projection against a published h–x chart; and sensor
accuracy itself.

---

## 4. Data model

Three SQLite tables:

| Table | Holds |
|---|---|
| `profiles` | one greenhouse: name, crop name, growth stage, temperature and humidity bands **each with its reference**, optional own VPD band with its reference, pressure mode (+ fixed value or mapped field and unit), JSON link, poll interval, the field mapping, poll state |
| `readings` | time received, time measured, temperature, relative humidity, pressure when the link carries one. Unique per (profile, measured_at) |
| `rules` | profile, name, the state required of temperature/humidity/VPD, severity, recommendation, **reference**, order, enabled |

Notes:

* **A reading is exactly three measured things** (plus pressure when measured).
  No derived quantity is stored any more: everything is recomputed in the
  browser on demand, so a change of engine or of bands never leaves stale
  numbers in the database.
* **Advice is not stored either.** The state and recommendation for any past
  reading are recomputed with the *current* bands and rules, and can be shown as
  table columns or exported. This is a deliberate reversal of version 2 (§11).
* Duplicate timestamps are ignored on insert (`ON CONFLICT DO NOTHING`), so a
  link polled faster than the sensor updates does not inflate the log.
* Rules are **per profile** and are seeded by the browser from `dss.defaultRules()`
  the first time a profile is opened, which keeps the defaults and their
  citations in one place.

### Upgrading an existing database

`db/migrate.py` is detection-based and idempotent. On a version-2 file it takes
a **backup first** (`psychromol.backup-<stamp>-v2.db`, SQLite backup API) and
then, in one transaction with a foreign-key check before commit, folds crops,
growth stages and facilities into the new profile rows, keeps every reading's
identity and measured values, drops the derived columns and the stored
decisions, and leaves pre-version-2 tables untouched. Placeholder references
written by earlier versions are replaced by an explicit "no documented
reference" message so nothing reads as sourced when it is not. Pressure is
carried over from the last stored reading, so migrated numbers do not shift.
Rehearsed twice on copies of the live database (89 551 and 132 796 readings;
0.19 s for the first), with foreign-key and integrity checks clean afterwards.

---

## 5. Data input

**One route:** a link that returns JSON. The browser reads it directly (falling
back to a server proxy only when the browser is blocked by CORS or mixed
content), lists every value it found, and the user chooses which is the time,
the temperature, the humidity and optionally the pressure. Paths are **JSON
Pointer** (RFC 6901), so nested objects and arrays work
(`/feeds/0/sensors/air/t`).

Field guessing follows the names (exact, then whole word, then substring, never
substring-matching a candidate shorter than three characters, and never a key
containing `outdoor`, `surface`, `dew`, `setpoint`, …), but the user always
confirms. Times without a zone are read as UTC; epoch numbers are seconds below
10¹¹ and milliseconds above; decimal commas and a unit after the number are
accepted.

The server then fetches the same link on the profile's own interval
(`poll_sources` ticks every second; each profile is polled when its own
interval has elapsed), so a profile at 1 s is never throttled by one at 60 s.
While the dashboard is open, its live tick performs the fetch itself, so a
watched profile is as fresh as its interval.

**Parity is tested:** the browser preview and the server fetcher must read the
same values from the same JSON. `tests/fixtures/extraction-cases.json` holds 22
cases — nested paths, array indices, epoch formats, naive and offset times,
decimal commas, pressure unit conversion and every failure mode — and both test
suites assert the same expected results.

---

## 6. The decision support engine (`frontend/js/dss.js`)

### 6.1 Classification

Temperature, relative humidity and VPD are each **LOW / OPTIMAL / HIGH** against
their band, with the limits counting as inside. The combined state is named
(`HOT + HUMID · LOW VPD`), or plain `OPTIMAL` when all three are in band. This
is a crisp version of the optimality evaluation described by Shamshiri et al.
(2018, pp. 294–295), who use graded membership functions; PsychroMol uses only
the optimal band, and says so behind the **?**.

### 6.2 Where the bands come from

Temperature and humidity ship **no defaults**: the user enters them together
with the source they come from, and the API refuses a profile without both.
The reason is quoted in the interface — "There is no one level of humidity that
is good for all crops" (BC Ministry of Agriculture 2015, p. 3) — with
orientation values offered as orientation only (17–27 °C for warm-season
greenhouse crops, Shamshiri et al. 2018 p. 289 citing Kittas et al. 2005;
60–90 % RH for greenhouse tomato per ASABE 2015, p. 290).

VPD **does** ship a referenced default per growth stage:

| Stage | VPD | Source |
|---|---|---|
| Propagation (rooting cuttings) | 0.3–0.5 kPa | Shamshiri et al. (2018), p. 292 |
| Vegetative | 0.2–1.0 kPa | Grange & Hand (1987) and Picken (1984) as summarised in Shamshiri et al. (2018), p. 292 and Table 3 (p. 293) |
| Flowering and fruiting | 0.2–1.0 kPa | the same; the source gives one range for the whole crop cycle, which the popup states plainly |

A profile may replace the stage value with its own band and its own reference.

### 6.3 Rule structure

```json
{
  "name": "Hot and humid",
  "conditions": {"temperature": "HIGH", "humidity": "HIGH", "vpd": "ANY"},
  "severity": "critical",
  "recommendation": "Ventilate to replace the hot, moist air with drier outside air. …",
  "reference": "BC Ministry of Agriculture (2015), p. 3. “…”",
  "priority": 10,
  "enabled": true
}
```

Every matching rule is ranked worst-severity-first, then by lowest order; the
first is the headline and the rest are listed as "Also matched". A rule without
a reference is refused by both the browser and the API.

### 6.4 Default rule set (11 rules)

| Order | Rule | T | RH | VPD | Severity | Cited for |
|---|---|---|---|---|---|---|
| 10 | Hot and humid | HIGH | HIGH | any | critical | BC 2015 p. 3; Shamshiri 2018 pp. 290, 296, 298 |
| 20 | Hot and dry | HIGH | LOW | any | critical | BC 2015 p. 4, pp. 4–5; Shamshiri 2018 p. 297 |
| 30 | Hot | HIGH | OPTIMAL | any | warning | BC 2015 pp. 4, 5 |
| 40 | Cold and humid | LOW | HIGH | any | critical | BC 2015 pp. 3, 4 |
| 50 | Cold and dry | LOW | LOW | any | critical | BC 2015 pp. 2, 3, 4 |
| 60 | Cold | LOW | OPTIMAL | any | warning | BC 2015 pp. 3, 4; Shamshiri 2018 p. 296 |
| 70 | Humid | OPTIMAL | HIGH | any | warning | BC 2015 p. 4; Shamshiri 2018 p. 298 |
| 80 | Dry | OPTIMAL | LOW | any | warning | BC 2015 p. 4, pp. 4–5; Shamshiri 2018 p. 296 |
| 90 | High VPD | OPTIMAL | OPTIMAL | HIGH | warning | Shamshiri 2018 pp. 296, 299; BC 2015 p. 4 |
| 100 | Low VPD | OPTIMAL | OPTIMAL | LOW | warning | Shamshiri 2018 pp. 296, 297, 299; BC 2015 p. 3 |
| 110 | Within the bands | OPTIMAL | OPTIMAL | OPTIMAL | ok | Shamshiri 2018 pp. 294–295, plus the profile's own band references |

The set covers all 27 state combinations **exactly once** — a test asserts it,
so the dashboard can never be silent about a state. Rules can be added, edited,
disabled, deleted and reset to the defaults per profile.

The recommendations name general measures only (ventilate, heat, shade, mist or
fog, circulate air), since the system knows nothing about which equipment a
particular greenhouse has.

---

## 7. The reference system

This is what makes the advice citable rather than assertive, and is worth a
paragraph in the thesis in its own right.

`references.js` holds six sources — ASHRAE (2017); PsychroLib (Meyer &
Thevenard 2019, JOSS 4(33):1137); Mollier (1923); Shamshiri et al. (2018,
*Int. Agrophys.* 32:287–302); Grange & Hand (1987, *J. Hort. Sci.* 62(2):125–134);
BC Ministry of Agriculture (2015), *Understanding Humidity Control in
Greenhouses* — and one topic per formula, band, classification rule and chart.
Each citation carries the exact locator (equation, page or table) and, where
the claim is verbal rather than mathematical, the **verbatim sentence**.

Every quotation in the code was checked word for word against the source PDFs
with a script that normalises whitespace, hyphenation and page furniture: 39
distinct quotations, 0 mismatches. The check caught two problems before they
could be cited — one "quotation" that was in fact stitched together from cells
of a units table, rewritten as a plain locator, and one whose page range was
wrong because the sentence runs across a page break.

In the interface a **?** appears beside every card, every property, every line
of the calculation, every band, every rule and each chart.

---

## 8. User interface (`frontend/`)

A static site with no build step; it can be served by the backend or hosted
anywhere and pointed at the API (a "connect" dialog stores the server address).
Light, glass-style design, four views:

| View | Content |
|---|---|
| **Dashboard** | Temperature, humidity and VPD cards with their states and bands; the recommendation card. Collapsed it shows only state, rule and advice; expanded it shows the classification (value against band → state) and the live arithmetic (p_ws → p_w → VPD), each line with its **?** |
| **Psychro** | Full chart −20…50 °C, switchable psychrometric ↔ Mollier; zoom, pan, hover read-out that snaps to real history points; shaded target zone; 24-hour trail with playback and scrubber; every derived property of the current point |
| **Data → Chart / Table** | Any chosen quantities over any range; the table can also show the state, rule and recommendation recomputed for each past reading; CSV/JSON download with its own column selection |
| **Rules** | The current profile's rules with their conditions, severity, advice and reference |

A profile is created, edited, switched and deleted from one modal with two tabs
(Crop, Data). Live refresh follows the profile's own poll interval (or 15 s
without a link).

Verified in a headless browser at 1440 × 900 and at 390 × 844 (phone): no
console errors, no horizontal scrolling, and an export of **71 080 readings**
(24 h at a 1 s interval) computed in the browser into a 7 MB CSV.

---

## 9. REST API (`/api/v1`, interactive docs at `/api/docs`)

| Area | Endpoints |
|---|---|
| Meta | `GET /health` |
| Profiles | `GET/POST /profiles`, `GET/PUT/DELETE /profiles/{id}`, `POST /profiles/{id}/refresh` |
| Readings | `GET /profiles/{id}/readings` (range, paging, order, or `max_points` thinning that returns real rows), `GET /profiles/{id}/readings/latest` |
| Rules | `GET/PUT/POST /profiles/{id}/rules`, `PUT/DELETE /rules/{id}` |
| Sources | `GET /sources/fetch?url=…` (proxy for links the browser may not read) |

There is no endpoint that computes a psychrometric quantity, a classification
or a recommendation — by design.

---

## 10. Testing

| Suite | Tests | Covers |
|---|---|---|
| `tests/js/psychro.test.mjs` | 22 | ASHRAE tables, Example 1, Eq. 37/38 fit, PsychroLib fixture, external tool, round-trips, edge cases |
| `tests/js/geometry.test.mjs` | 10 | Chart curves against the engine, target zone, projection, pressure dependence |
| `tests/js/dss.test.mjs` | 13 | Classification limits, stage bands, all 27 state combinations, ranking, validation, explanation |
| `tests/js/fields.test.mjs` | 8 | Shared extraction fixture, detection, JSON Pointer, strict number parsing |
| `tests/test_api.py` | 33 | Every router end-to-end, validation refusals, paging, thinning |
| `tests/test_fetcher.py` | 32 | The same shared fixture, storing and de-duplication, error recording, real HTTP failure modes |
| `tests/test_migration.py` | 7 | v2 → v3 upgrade, backup, folded tables, untouched legacy tables, idempotence |
| `tests/test_poll_scheduling.py` | 5 | Per-profile due logic |

**Totals: 53 browser-side, 77 server-side, plus 33 verification checks.**
`ruff` clean.

---

## 11. What changed from version 2, and why

These are design results, not just refactoring, and the reasons are citable.

| Change | Reason |
|---|---|
| All calculation moved from the server into the browser | One auditable engine file, running where the results are shown; the server can then be a small always-on machine whose only job is to keep the log |
| Stored derived columns and stored decisions removed | They went stale whenever the engine, the bands or the rules changed. Recomputing from the raw pair is exact and cheap, and lets a user re-read history under today's rules |
| Facilities and the crop library removed | One profile = one greenhouse = one crop and one stage; the catalogue added navigation without adding information |
| Pressure from facility altitude → explicit per-profile choice | Altitude was an indirect way of stating a pressure; the choice is now standard, fixed, or measured from the link |
| File upload and paste removed | The research setup feeds a live JSON link; two more import paths meant two more parsers to keep correct |
| Raspberry Pi hardware module removed | It coupled the DSS to one wiring layout and one machine. A Pi can still run the server and feed readings through the same JSON link as any other source |
| Optional channels (surface temperature, outdoor T/RH, substrate moisture, PAR, CO₂, ventilation) removed | None was measured in this setup, and each carried rules that could never fire. Condensation risk, evaporative-cooling limits and CO₂ advice went with them |
| 31 condition-based rules → 11 state-based rules | The rule model is now "what state must each of the three indicators be in", which a grower can read at a glance and which provably covers every combination |
| Thresholds: seeded placeholders → user-entered with a reference | Version 2 shipped values marked PROVISIONAL that could be mistaken for sourced ones. Now the system refuses a band without its source, and ships a default only where a citable range exists (VPD per stage) |
| References added throughout | The system's claims are now traceable to a page in a named source, which is what a thesis needs |

---

## 12. Limitations to state in the thesis

* **Air VPD only.** Leaf-to-air VPD needs leaf surface temperature, which is not
  measured (BC Ministry of Agriculture 2015, p. 6).
* **Advice is editorial.** Each rule cites a source for the mechanism it invokes
  (venting, heating, shading, fogging), but the mapping from a classified state
  to one recommendation is this project's own, and the severity ranking is
  structural (both temperature and humidity out of band = critical), not taken
  from a source.
* **Stage-specific VPD evidence is thin.** The source gives one range for the
  whole crop cycle; only the propagation value is stage-specific.
* **No sensor quality control.** Out-of-range readings are stored and reported
  as not assessed, and duplicate timestamps are ignored, but drift, stale values
  and sudden jumps are not detected.
* **No decision log, no intervention analysis, no time-in-target statistics.**
  These can be computed from the exported data; they are not features of the
  application.
* **One crop and one growth stage per profile**, changed manually.

---

## 13. Possible thesis mapping

| Thesis chapter | Supported by |
|---|---|
| Literature / theory | ASHRAE psychrometrics, VPD and its optimal ranges, Mollier h–x, rule-based DSS |
| Methodology — system design | Architecture (§2), data model (§4), data flow (§5) |
| Methodology — psychrometric engine | §3 and `docs/psychrometric-methodology.md` |
| Methodology — DSS | Classification, bands and their sources, rule model (§6) |
| Methodology — traceability | The reference system (§7) |
| Results — engine validation | §3.4 and `node scripts/verify_engine.mjs` output |
| Results — application to greenhouse data | Real readings collected through the JSON link; export derived variables, plot trajectories and rule outcomes |
| Discussion — limitations | §12 |
| Discussion — design choices | §11 (what was removed and why is as informative as what was kept) |
| Future work | Leaf-temperature sensing, decision logging and time-in-target statistics, intervention analysis, sensor quality flags, closed-loop control |

Figures the application can produce directly: psychrometric chart with target
zone and 24-hour trajectory; Mollier diagram; temperature / RH / VPD time
series; derived-property tables; the classification-and-calculation panel as a
worked example; the rule list with its citations.

---

## 14. Running it

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt       # add requirements-dev.txt for tests
.venv/bin/python -m psychromol.api              # http://127.0.0.1:8888
.venv/bin/python scripts/seed.py                # optional: example profile, 7 days of synthetic data
```

An existing database is upgraded on first start, after an automatic backup.

The seed data is **synthetic** (sine-wave daily cycle plus noise) and must not
be reported as measurements. `data/reference/` holds verification data only,
not experimental data.
