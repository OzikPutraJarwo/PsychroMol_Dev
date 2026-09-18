# CLAUDE.md — working notes for PsychroMol

## What this is

Psychrometric decision support for a greenhouse. A temperature and a humidity
become the full moist-air state; that state is classified against the crop's
bands; user-editable rules turn the classification into advice. Every number,
threshold and recommendation names the source it rests on, behind a small **?**
button.

**The browser does all of it.** The server keeps the database and fetches the
JSON link on a schedule — nothing else. Optimise for correctness and for a
grower reading the screen, not for feature count.

## Hard rules

1. **This is rule-based, not AI.** No machine learning, no prediction, no
   autonomous control. PsychroMol advises; a person acts.
2. **The engine lives in `frontend/js/psychro.js` and nowhere else.** No
   psychrometric relation may be written a second time — not in the chart
   geometry, not in the app, not in Python. `geometry.js` builds curves by
   calling the engine; `dss.js` classifies values the engine returned. The
   server never computes a psychrometric quantity at all.
3. **Never mix pressure units.** The engine works in **Pa**; the API, the
   database and the interface use **kPa**. Conversion happens only in
   `frontend/js/units.js` and `psychromol/units.py`, and every API field name
   carries its unit (`temperature_c`, `pressure_kpa`).
4. **A reading is three things**: a time, a temperature, a humidity — plus a
   pressure only when the JSON link carries one. Nothing else is stored. Do
   not add derived columns back to `readings`: everything else is recomputed
   in the browser, from these, on demand.
5. **Temperature and humidity bands have no defaults.** The user enters them
   with the reference they come from, and the API refuses a profile without
   both (`ProfileIn`). Only the VPD band has a shipped default, per growth
   stage, and it carries its citation in `dss.js`.
6. **Everything the interface asserts carries a reference.** A formula, a band
   or a recommendation is shown with a `?` that opens its source.
   `references.js` holds the sources and the per-topic text; a rule keeps its
   own free-text reference and the API refuses an empty one. When you add a
   quantity, a band or a default rule, add its reference in the same commit.
7. **No comments in code**, except the ASHRAE equation citations in
   `frontend/js/psychro.js` and in the tests that verify against ASHRAE.
8. **English only.** No other language in the interface or the code.

## Dependency direction

```
app.js → {api.js, dss.js, geometry.js, quantities.js, fields.js, chart.js, trend.js, references.js}
dss.js → {psychro.js, references.js, units.js}
geometry.js → psychro.js
quantities.js, fields.js → units.js
psychro.js → (nothing)

api/ → {db/, fetcher.py, schemas.py}
fetcher.py → {fields.py, db/}
fields.py → units.py
db/ → (no imports from api or fetcher)
```

## Commands

```bash
node --test tests/js/                         # 53 tests: engine, geometry, DSS, field mapping
node scripts/verify_engine.mjs                # 33 checks against ASHRAE and PsychroLib
.venv/bin/python -m pytest -q                 # 77 tests: API, fetcher, scheduling, migration
.venv/bin/ruff check psychromol tests scripts
.venv/bin/python -m psychromol.api            # serve on :8888
.venv/bin/python scripts/seed.py              # an example profile with synthetic readings
```

The user starts the server themselves from a terminal. Do not leave one running.

## Where things are

| Path | Contents |
|---|---|
| `frontend/js/psychro.js` | The ASHRAE engine: saturation, humidity ratio, dew point, wet bulb, enthalpy, volume, density, VPD |
| `frontend/js/geometry.js` | Psychrometric and Mollier chart curves, target zone, projection |
| `frontend/js/dss.js` | Growth stages with their VPD bands, classification, default rules, the live explanation |
| `frontend/js/references.js` | Sources and the text behind every `?` |
| `frontend/js/fields.js` | JSON Pointer paths, number and time parsing, field detection, extraction |
| `frontend/js/quantities.js` | The displayable/exportable quantities, their units, decimals and topics |
| `frontend/js/app.js` | Views, live loop, profile modal, rules, data table, export |
| `psychromol/fields.py` | The server's copy of extraction only (mirrors `fields.js`, shared fixture) |
| `psychromol/fetcher.py` | Fetching a JSON link and storing the reading, the due check |
| `psychromol/db/` | `profiles`, `readings`, `rules`, and the v2 → v3 upgrade |
| `psychromol/api/` | Routers: profiles, readings, rules, sources |

## What runs where, and why

Everything that can run in the browser does. Two things cannot:

* **the database**, and
* **collecting readings while no browser is open** — a greenhouse log must not
  have holes because nobody had the page up. `poll_sources` in `api/app.py`
  wakes every `POLL_TICK_SECONDS` (1 s) and `fetcher.is_due()` decides which
  profiles have waited their own `poll_interval_seconds` since
  `last_polled_at`, so a 1 s profile is never throttled by a 60 s one.

The dashboard's live tick calls `POST /profiles/{id}/refresh` (fetch, extract,
store, return the latest) rather than only reading, so a watched profile is as
fresh as its interval; the background loop then sees `last_polled_at` and skips.

## Data model

Three tables. A `Profile` holds the crop name, the growth stage, the bands with
their references, the pressure choice and the JSON link with its field mapping.
`Reading` holds the raw pair (and pressure when mapped). `Rule` belongs to one
profile.

Rules are **seeded by the browser**, not the server: `rules_seeded` is false
until `app.js` PUTs `dss.defaultRules()` the first time that profile is opened.
That is what keeps the default rules and their citations in one place, in JS.

## Upgrading a database

`create_all()` runs `db/migrate.upgrade()` first. It is detection-based and
idempotent: it looks at the `profiles` table, does nothing at version 3, and
refuses anything older than 2 with a clear error.

The v2 → v3 upgrade **backs the file up first**
(`psychromol.backup-<stamp>-v2.db`, via SQLite's backup API), then, in one
explicit transaction with foreign keys off and a `foreign_key_check` before
commit:

* each v2 profile becomes a v3 profile — crop name from `crops`, bands from its
  growth stage, the stage mapped by name (`fruit development` → `flowering`,
  anything unknown → `vegetative`);
* a v2 reference that was one of this project's own placeholders (`PROVISIONAL…`,
  `Migrated from this crop's earlier…`) becomes `MISSING_REFERENCE`, so nothing
  reads as sourced when it is not;
* pressure comes from the **last stored reading's** pressure: sea level →
  `standard`, anything else → `fixed` at that value, so migrated numbers do not
  shift (a facility altitude of 30 m stays 100.965 kPa). Eq. 3 is not
  reimplemented in Python for this — hard rule 2;
* a profile with a link gets the mapping `/timestamp`, `/temperature`,
  `/humidity` — the names the v2 loose matcher tried first — so collection
  continues without a gap; a link with other names shows a clear
  `last_poll_error` until the user maps the fields;
* readings keep their ids, times and measured values; the derived columns are
  dropped and `decisions` with them;
* tables from before v2 (`sensor_readings`, `greenhouses`, …) are left exactly
  as they are. They belong to the user's old data, not to this schema.

## The references system

`references.js` exports `SOURCES` (ASHRAE 2017, PsychroLib, Mollier 1923,
Shamshiri et al. 2018, Grange & Hand 1987, BC Ministry of Agriculture 2015) and
`TOPICS` (one per formula, plus the band, classification, rules and chart
topics). `cite(source, locator, quote)` builds a citation; a quote must be
**verbatim** — they were checked against the source PDFs with a script that
normalises whitespace and hyphenation. If you add a quote, check it the same
way.

`app.js` resolves `data-help="topic:… | band:… | stage:… | rule:…"` in one
delegated capture-phase listener, so a `?` works anywhere, including inside a
`<label>` (it calls `preventDefault`/`stopPropagation` so the label does not
toggle its radio).

## The DSS

Three indicators — temperature, humidity, VPD — each LOW / OPTIMAL / HIGH
against a band whose limits count as inside. The combined label is
`HOT + HUMID · LOW VPD`-style, or plain `OPTIMAL` when all three are in.

A rule names the state it needs for each indicator (or `ANY`), a severity
(`ok` / `warning` / `critical`), a recommendation, a reference and an order.
Every matching rule is ranked worst-severity-first, then lowest order; the
first is the headline and the rest are listed as "Also matched". The 11
default rules cover all 27 combinations exactly once — a test asserts it.

VPD defaults per stage: propagation 0.3–0.5 kPa, vegetative and
flowering/fruiting 0.2–1.0 kPa, each with its citation and a note saying the
source gives one range for the whole crop cycle. A profile may override them
with its own band and reference.

## Data source and field mapping

A profile's link is read as a JSON document and addressed with **JSON Pointer**
(RFC 6901: `/feeds/0/sensors/air/t`). `fields.js` flattens the document, offers
the numeric leaves for temperature/humidity/pressure and the time-like leaves
for the time, and guesses by name (exact, then whole word, then substring —
never substring-matching a candidate shorter than three characters, and never
a key containing `outdoor`, `surface`, `dew`, `setpoint`, …).

The browser reads the link **directly** and falls back to
`GET /sources/fetch?url=` only when the browser is blocked (CORS, mixed
content). The server does its own extraction with `psychromol/fields.py`, which
must agree with `fields.js` value for value:
`tests/fixtures/extraction-cases.json` holds 22 cases and **both** test suites
run them. Change one side and you change the fixture and both tests.

Times without a zone are read as UTC, on both sides. Epoch numbers are seconds
below 10¹¹ and milliseconds above.

## Pressure

Per profile: `standard` (101.325 kPa, ASHRAE Eq. 3 at sea level), `fixed` (a
value the user enters) or `field` (a mapped value in the JSON, with its unit).
In `field` mode a reading without a pressure falls back to the standard
atmosphere and the interface says so (`standard-fallback`).

## The views

* **Dashboard** — three cards, then the advice card. Collapsed it shows only
  the state, the rule's name and the recommendation; clicking it opens the
  classification (value against band → state) and the live calculation
  (p_ws → p_w → VPD) with a `?` on every line. `state.adviceOpen` holds the
  open/closed state, so a live tick cannot snap it shut.
* **Psychro** — chart (switchable to Mollier) and every derived property of
  the current point, each with its `?`. The trail is the last 24 h, thinned by
  the server to 1500 points; playback steps an orange marker through it.
* **Data → Chart / Table** — the chosen quantities over a range, computed in
  the browser. The table can also show the assessment columns (state, rule,
  recommendation), worked out live with the current bands and rules — nothing
  of the kind is stored any more.
* **Rules** — the rules of the current profile, each with its reference.
* **Download** — CSV or JSON, pages of 10 000 readings fetched and computed in
  the browser, written with a Blob.

## Traps this project has already fallen into

* **A round trip through the humidity ratio moves a measured value.** RH 60 %
  came back as 59.999999999999993 and a reading exactly on the band limit
  classified as LOW. `stateFromTemperatureRelativeHumidity` now keeps the
  measured RH and computes `p_w = φ·p_ws` directly (Eq. 12/22); the state's
  `relativeHumidity` is the number the sensor sent.
* **ASHRAE's wet-bulb equations disagree at exactly 0 °C.** Eq. 33 (water) and
  Eq. 35 (ice) meet with a step, so the humidity ratio of the "0 °C wet bulb"
  line inverts to a few hundredths below zero — at 5 °C dry bulb, −0.35 °C.
  PsychroLib does the same to 0.001 °C; it is the standard, not a bug. A test
  pins it.
* **Single-letter field names match everything.** `t` is inside `status` and
  `date_time`. Name matching never substring-matches a candidate shorter than
  three characters.
* **Any positive number is a valid epoch.** Offering every number as a time
  candidate made temperature look like a 1970 timestamp. A time candidate must
  be an ISO string or an epoch in a plausible range.
* **Lazily computed state properties still serialise.** `dewPoint` and
  `wetBulb` are getters (each costs a bisection) on a frozen object, so a
  1000-row export that only needs VPD never solves them; `JSON.stringify` and
  spreading still see them.
* **A chart that is re-created loses pointer capture.** `Chart` keeps one
  `<svg>` and replaces only its children.
* **A discarded chart must `destroy()`**, or its `ResizeObserver` keeps firing
  into a dead object.
* **Curve labels pile up at the plot edge.** Labels are drawn only where they
  do not overlap one already placed (`roomFor` in `chart.js`), measured from
  the label's own length.
* **Grid and flex children need `min-width: 0`** (and `min-height: 0` in the
  fit views), or a chart forces its parent wider or taller.
* **`[hidden]` is only `display:none` until another rule sets `display`.** One
  `[hidden] { display: none !important; }` covers every case.
* **A live-preview interval behind a hidden tab keeps hitting the network.**
  The preview tick checks that `#tab-data` is active and that the modal is
  open; `stopPreview()` runs on every re-render and every path that closes the
  profile modal.
* **Two CSS custom properties can resolve to the same colour.** Series colours
  are `--series-1…6`, never the status tokens.
* **Two static-serving strategies can't coexist.** Relative asset paths only
  resolve if the whole `frontend/` directory is mounted at `/`; the API
  routers are registered first so `/api/v1/*` still wins.
* **A CDP step that redeclares `const` throws before its first statement.**
  When driving the interface from a script, wrap each step in an IIFE, and
  make the harness report `exceptionDetails` — a silent SyntaxError looks
  exactly like a broken feature.
* **A headless browser reuses its cached CSS and JS.** A change that "did not
  work" may simply not have been loaded: delete the browser profile directory
  before a screenshot run. A native `confirm()` also blocks the page until a
  dialog handler answers it, so stub `window.confirm` when driving deletes.

## Theme

White, clean, iOS-style glassmorphism — translucent surfaces over a soft pastel
gradient, Material Symbols Rounded icons (`.icon`, bundled locally).

**Light mode only, deliberately.** No `@media (prefers-color-scheme: dark)`
block. The person using this runs a dark-mode OS and asked twice for light;
don't reintroduce a dark block without being asked.

## Before you change anything

```bash
node scripts/verify_engine.mjs
node --test tests/js/
.venv/bin/python -m pytest -q
```
