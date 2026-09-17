# PsychroMol — Summary

**Working thesis title:** *Development and Application of a Real-Time
Psychrometric-Based Decision Support System for Greenhouse Environment
Management*

**State at time of writing (2026-09-17):** engine verification 31/31 checks
passed; test suite 388/388 passed.

---

## 1. What the application is

PsychroMol is a **rule-based decision support system (DSS)** for greenhouse
climate. It takes one air temperature and one relative humidity reading,
turns them into the full moist-air (psychrometric) state, and checks that state
against rules a grower can read and edit. The output is a status (ok / info /
warning / critical), a headline and a management recommendation that names the
measured values which triggered it.

The research chain it implements:

```
Sensor data → data processing → psychrometric calculation
            → environmental state assessment → rule-based DSS
            → management recommendation → (optional) human action
```

What it deliberately is **not**:

* not AI or machine learning — no prediction, no learned model;
* not autonomous control — no rule ever switches equipment. The Raspberry Pi
  actuators (fan, pump, stepper) are switched only by a person through the
  API.

The scientific premise is that temperature and RH are **inputs, not the
analytical variables**. Advice is reasoned over derived quantities such as
vapour-pressure deficit (VPD), dew-point margin and humidity ratio.

---

## 2. System architecture

```
                    ┌──────────────────────────── frontend/ (static site, no build)
                    │  Dashboard · Psychro chart · Data · Rules
                    │  api.js ──HTTP/JSON (kPa)──┐
                    └────────────────────────────┼─────────────────────────────
                                                 ▼
psychromol/api/        FastAPI routers  (catalogue, profiles, data, preview, rules, hardware)
      │                + two background loops: poll_sources (1 s tick), poll_hardware
      ▼
psychromol/pipeline.py reading → state → stored row; fetch linked sources; assess
      │
      ├── psychromol/ingest.py     JSON / CSV parsing, loose column matching
      ├── psychromol/core/         ASHRAE psychrometrics, MoistAirState, Mollier, chart geometry
      ├── psychromol/rules.py      metrics, condition evaluation, equipment gating
      └── psychromol/db/           SQLAlchemy models + Repository (SQLite)

psychromol/hardware/   Raspberry Pi drivers (SHT10, MCP3008, OLED, relays, stepper)
```

**Dependency direction** is one-way: `api → pipeline → {db, core, rules,
ingest}`. `core/` imports only the Python standard library, so the science can
be audited and reproduced without the web stack.

### Technology

| Layer | Choice |
|---|---|
| Language | Python ≥ 3.10 (backend), vanilla ES modules (frontend) |
| Web framework | FastAPI + Uvicorn, Pydantic v2 validation |
| Database | SQLite via SQLAlchemy 2.0 (WAL mode), migration-ready |
| Charts | Hand-written SVG (`chart.js`, `trend.js`), geometry from backend |
| Hardware (optional) | RPi.GPIO, spidev, luma.oled — lazily imported |
| Dev / validation | pytest, httpx, `psychrolib` (test-only reference), ruff |

---

## 3. The psychrometric engine (`psychromol/core/`)

**Source:** ASHRAE Handbook — Fundamentals (2017), Chapter 1. Every equation
cites its number; full record in `docs/psychrometric-methodology.md`.

### 3.1 Quantities derived from (t, RH, p)

| Quantity | ASHRAE basis | Unit (API) |
|---|---|---|
| Saturation vapour pressure `p_ws` | Eq. (5) over ice < 0 °C, Eq. (6) over water ≥ 0 °C (Hyland–Wexler) | kPa |
| Vapour pressure `p_w` | Eq. (12), (20) | kPa |
| Humidity ratio `W` | Eq. (20) | kg/kg and g/kg |
| Dew point (frost point < 0 °C) | Numerical inverse of Eq. (5)/(6) | °C |
| Wet-bulb temperature | Numerical inverse of Eq. (33)/(34) | °C |
| Specific enthalpy `h` | Eq. (30) | kJ/kg dry air |
| Specific volume `v` | Eq. (26) | m³/kg dry air |
| Density | Eq. (11) | kg/m³ |
| Degree of saturation `μ` | Eq. (12) | % |
| VPD (air) | `p_ws(t) − p_w` | kPa |
| Absolute humidity | `1000 W / v` | g/m³ |
| Dew-point depression (margin) | `t − t_d` | K |
| Mollier ordinate | `h − 2501 W` | kJ/kg |
| Atmospheric pressure from altitude | Eq. (3) | kPa |

### 3.2 Key design decisions (each documented and tested)

1. **Pressure comes from the facility's altitude** (ASHRAE Eq. 3), never from a
   sensor. Example: the same 24 °C / 70 % holds ~12 % more moisture per kg of
   dry air at 1000 m than at sea level.
2. **Units:** the engine works in **Pa**, the API in **kPa**; conversion happens
   in exactly one place (`MoistAirState.to_api_dict()` / `units.py`). Every API
   field name carries its unit (`vpd_kpa`, `dew_point_c`).
3. **Inverses are solved by bisection**, not by the ASHRAE curve fits
   (Eq. 37/38) and not by Newton–Raphson — bisection cannot diverge on
   unattended live data. Dew point round-trips to 1e-6 °C.
4. **Wet-bulb bracket starts at the dew point**, so cold or very dry air is
   still bracketed.
5. **RH is clamped at 100 %** in the derived state; the raw reading is stored
   unchanged.
6. **VPD is air VPD, not leaf-to-air VPD** — leaf temperature is not measured.
   Thesis text should say "air VPD".
7. **Out-of-range inputs are rejected**, not extrapolated
   (`PsychrometricRangeError`: −100…200 °C, 0…100 % RH, 20…200 kPa).
8. **`MoistAirState` is immutable** and computed once per reading, so every
   consumer (rules, charts, tables) sees identical numbers.

### 3.3 Psychrometric vs. Mollier

Both charts are **projections of the same state**, not two calculations:

| Chart | x-axis | y-axis |
|---|---|---|
| Psychrometric (ASHRAE) | dry-bulb temperature | humidity ratio |
| Mollier h-x (European) | humidity ratio | `h − 2501 W` |

All chart curves (saturation line, RH family, isenthalps, wet-bulb and
specific-volume lines, isotherms, and the crop's **target zone**) are computed
by `core/chart.py` for the profile's actual pressure. The frontend only draws
them, so the chart can never disagree with the numbers next to it. The target
zone is bounded by real RH curves, not a rectangle.

### 3.4 Validation

| Source | Scope | Result |
|---|---|---|
| ASHRAE saturation-pressure table | 19 points, −60…100 °C, tol 5e-4 relative | all pass |
| ASHRAE Ch. 1 worked Example 1 | 40 °C db / 20 °C wb | W, h, t_d, φ, v within printed precision (t_d Δ 0.034 K) |
| `psychrolib` (independent ASHRAE implementation) | 77-point grid, −10…50 °C × 5…100 % RH, 4 pressures 85–105 kPa | max ΔW 9.8e-5 rel; Δt_d 1.2e-3 K |
| Researcher's earlier browser tool (Magnus formula) | 8 points, 17.8…44.6 °C | within Magnus offset (~0.4 % on p_ws) |
| Internal consistency | round-trips, 4 constructors agree, `t_d ≤ t_wb ≤ t`, monotonicity | all pass |

Run: `.venv/bin/python scripts/verify_engine.py` (31 checks) and
`.venv/bin/python -m pytest -q` (388 tests).

**Not validated** (stated in the methodology doc): tabulated values outside
−20…60 °C; pressures beyond 85–105 kPa; the Mollier projection against a
published h-x chart; and sensor accuracy itself.

---

## 4. Data model

Five SQLite tables:

| Table | Holds |
|---|---|
| `crops` | name; temperature min/max; RH min/max; optional extra targets (e.g. VPD 0.5–1.2 kPa) |
| `facilities` | name; altitude (m); list of equipment present |
| `profiles` | joins one crop + one facility; optional JSON source URL; per-profile poll interval (default 60 s, min 1 s); last poll time/error |
| `readings` | time, temperature, RH, pressure **plus every derived quantity**, engine version, error text. Unique per (profile, measured_at) |
| `rules` | name, conditions (JSON), severity, recommendation, required equipment, priority, enabled |

Notes:

* **A reading is exactly three measured things**: time, temperature, humidity.
  Soil moisture and light from the Pi are kept in memory only, never stored.
* Storing derived values alongside the raw pair, with `engine_version`, makes
  every stored row **re-derivable and comparable** — useful for
  reproducibility.
* Rejected readings are **stored with an error**, not silently dropped;
  duplicates (same timestamp) are counted and skipped.
* Rules are **global** (shared by all profiles); they adapt per crop because
  conditions can reference crop targets.
* Deleting a profile also removes its crop and facility if nothing else uses
  them.
* Schema evolution for SQLite is handled by `_add_missing_columns()` in
  `db/session.py`.

---

## 5. Data input

Three routes, all ending in `Pipeline.store_samples()`:

1. **Linked JSON URL** — polled server-side on the profile's own interval
   (`poll_sources` ticks every second and polls each profile when due). While
   typing a URL, a live preview shows the last 5 parsed rows before saving.
2. **File upload / paste** — CSV or JSON, up to 16 MB.
3. **Raspberry Pi sensor** — SHT10 read every N seconds (default 5 s) and
   stored in-process.

**Loose parsing** (`ingest.py`): column names are matched by exact name, then
whole word, then substring (never substring for names shorter than 3 characters,
since `t` would match `date_time`). Accepts `timestamp`/`time`/`ts`/`Date Time`,
`temp`/`t`/`Air Temperature (C)`, `rh`/`humidity`, etc.; ISO or common date
formats; Unix seconds or milliseconds; comma decimals; common "missing" tokens;
auto-detected CSV delimiter; nested JSON containers (`data`, `readings`, …).
Times are normalised to UTC.

---

## 6. The decision support engine (`psychromol/rules.py`)

### 6.1 Rule structure

```json
{
  "name": "Hot and humid",
  "conditions": [
    {"metric": "temperature", "operator": ">", "target": "temperature.max"},
    {"metric": "relative_humidity", "operator": ">", "target": "relative_humidity.max"}
  ],
  "severity": "critical",
  "recommendation": "Ventilate first, then cool. Cooling alone makes the damp worse.",
  "requires_equipment": "roof_vent",
  "priority": 12
}
```

* **All conditions must hold** (logical AND).
* A condition compares one of **14 metrics** (temperature, RH, VPD, dew point,
  dew-point margin, wet bulb, humidity ratio, enthalpy, absolute humidity,
  specific volume, density, degree of saturation, vapour pressure, saturation
  pressure) using `>`, `>=`, `<`, `<=` against either a **fixed value** or a
  **crop target** (`temperature.max`, …) plus an optional **offset**.
* Because conditions reference crop targets, **changing the crop changes the
  advice without editing any rule**.

### 6.2 Evaluation

1. Every enabled rule whose conditions all hold becomes a match, carrying the
   actual value and threshold of each condition (**explainability**).
2. Matches are sorted by `priority` (lower first).
3. Overall status = the highest severity among matches.
4. Headline = the first-priority match at that highest severity.
5. If a rule needs equipment the facility lacks, the match is marked
   `equipment_missing` rather than hidden.
6. No match → status `ok`, "Conditions are within target".

### 6.3 Default rule set (11 rules)

| Priority | Rule | Condition | Severity | Equipment |
|---|---|---|---|---|
| 10 | Condensation forming | dew-point margin < 1 K | critical | heater |
| 12 | Hot and humid | T > T_max **and** RH > RH_max | critical | roof vent |
| 14 | Cold and damp | T < T_min **and** RH > RH_max | critical | heater |
| 20 | Much too hot | T > T_max + 5 | critical | roof vent |
| 22 | Much too cold | T < T_min − 5 | critical | heater |
| 40 | Too hot | T > T_max | warning | roof vent |
| 42 | Too cold | T < T_min | warning | heater |
| 44 | Too humid | RH > RH_max | warning | side window |
| 46 | Too dry | RH < RH_min | warning | fogging |
| 50 | Air drying the crop too fast | VPD > 1.5 kPa | warning | shade screen |
| 52 | Air barely drying the crop | VPD < 0.4 kPa | warning | fan |

Sample crop: **Tomato**, 18–28 °C, 60–80 % RH, VPD 0.5–1.2 kPa. Sample facility:
**House 1**, 30 m altitude, 8 equipment items. Twelve equipment types are
recognised (fan, side window, roof vent, heater, cooling, fogging,
dehumidifier, shade/thermal screen, irrigation, supplemental light, CO₂).

Rules can be added, edited, disabled, deleted, and reset to defaults from the
Rules view.

---

## 7. User interface (`frontend/`)

A static site with no build step; it can be served by the backend itself or
hosted anywhere and pointed at the API (a "connect" dialog stores the server
address). Light, glass-style design with a sidebar of four views:

| View | Content |
|---|---|
| **Dashboard** | Temperature and RH cards with target bands (highlighted when out of range); one status line with headline and recommendation; mini psychrometric/Mollier chart; mini trend |
| **Psychro** | Full chart −20…50 °C, switchable psychrometric ↔ Mollier; zoom, pan, hover read-out (snaps to real history points); shaded crop target zone; 24-hour trail with **playback** and scrubber; always-visible tiles of every derived property |
| **Data** | Trend chart + table, last 24 h by default or custom range; column picker over all 16 fields (default T and RH); CSV/JSON export with its own field selection |
| **Rules** | List, add, edit, delete, reset rules |

**Profiles** (crop + facility + data source) are managed from a modal with
three modes: *switch*, *edit* and *add* (atomic creation of crop, facility and
profile in one action). The page refreshes on the profile's poll interval (or
every 15 s for profiles without a link).

---

## 8. REST API (`/api/v1`, interactive docs at `/api/docs`)

| Area | Endpoints |
|---|---|
| Meta | `GET /health`, `GET /meta` (metrics, operators, severities, equipment, fields) |
| Catalogue | `GET/POST /crops`, `PUT/DELETE /crops/{id}`, same for `/facilities` |
| Profiles | `GET/POST /profiles`, `PUT/DELETE /profiles/{id}` |
| State & DSS | `GET /profiles/{id}/current` — full state + targets + assessment |
| Chart | `GET /profiles/{id}/chart?kind=psychrometric\|mollier` |
| Data | `GET /profiles/{id}/readings`, `GET /profiles/{id}/export?format=csv\|json`, `POST …/refresh`, `POST …/upload`, `POST …/paste` |
| Preview | `GET /sources/preview?url=…` |
| Rules | `GET/POST /rules`, `PUT/DELETE /rules/{id}`, `POST /rules/reset` |
| Hardware | `GET /hardware/status`, `POST /hardware/actuators/{name}`, `POST /hardware/stepper` |

---

## 9. Raspberry Pi integration (`psychromol/hardware/`)

The same backend runs unmodified on a Pi. With
`PSYCHROMOL_HARDWARE_ENABLED=true` and `PSYCHROMOL_HARDWARE_PROFILE_ID`:

| Component | Role |
|---|---|
| SHT10 (bit-banged GPIO) | Temperature + RH → stored as readings (datasheet conversion with temperature compensation) |
| MCP3008 ADC (SPI) | Soil moisture (ch 0) and light (ch 1) — in memory and on the OLED only |
| SSD1306 128×64 OLED (I²C) | Local display of T, RH, soil, light, actuator states |
| GPIO relays | Fan, water pump — **manual only**, via API |
| 28BYJ-48 stepper | Manual movement via API (e.g. vent/screen mechanism) |

All pins are `PSYCHROMOL_PIN_*` environment variables. Drivers import their
libraries lazily and have simulated counterparts, so the whole test suite runs
on a normal computer. There is currently **no frontend page** for the hardware;
it is API-only.

---

## 10. Testing

| Test file | Tests | Covers |
|---|---|---|
| `test_psychrometrics.py` | 32 (many parametrised) | ASHRAE tables, Example 1, psychrolib grid, round-trips, edge cases |
| `test_external_benchmark.py` | 2 | Earlier Magnus-based tool |
| `test_chart.py` | 7 | Chart geometry, target zone |
| `test_rules.py` | 19 | Conditions, targets, offsets, priority, equipment gating |
| `test_ingest.py` | 17 | Column matching, dates, CSV/JSON shapes |
| `test_pipeline.py` | 17 | Storing, duplicates, errors, altitude pressure, assessment |
| `test_api.py` | 41 | All routers end-to-end |
| `test_hardware.py` | 10 | Simulated rig, poll loop, actuators |
| `test_poll_scheduling.py`, `test_preview.py`, `test_migration.py` | 9 | Per-profile polling, live preview, schema migration |

Total after parametrisation: **388 tests**, all passing.

---

## 11. Planned scope vs. current implementation

`plan.txt` is the original development brief. Comparing it with the code helps
decide what the thesis can claim and what remains future work.

| Brief item | Status |
|---|---|
| Real-time acquisition (URL polling, upload, Pi sensor) | Implemented |
| ASHRAE psychrometric engine + validation | Implemented and validated |
| Psychrometric and Mollier charts with target zone and trajectory | Implemented |
| Crop-specific targets, editable rule-based DSS, explainable advice | Implemented |
| Rule priority and equipment awareness | Implemented |
| Historical storage, date-range view, CSV/JSON export | Implemented |
| Human-only actuator control (no autonomy) | Implemented (API only, no UI) |
| Environmental state *frequency* / % time in or out of target / condensation-risk duration | **Not implemented** — can be computed from exported data |
| Logging of DSS decisions over time (`dss_decisions`) | **Not implemented** — assessment is computed on request for the latest reading, not stored |
| Intervention / before–after response analysis (`interventions`) | **Not implemented** |
| Sensor quality flags (VALID / SUSPECT / MISSING, sudden jumps, stale data) | **Partly** — out-of-range readings stored with an error, duplicates rejected; no jump/stale detection or flag categories |
| Separate greenhouse / sensor entities | Simplified into `facilities` and `profiles` |
| Thesis and publication mapping documents | Not present in `docs/` |

**Documentation inconsistencies to fix before citing:**
`docs/psychrometric-methodology.md` §4.6, §4.8 and §6, and a comment in
`core/state.py`, refer to a `psychromol/quality/` layer and flags
(`RH_ABOVE_SATURATION`, `INVALID`) that do not exist in the current code. Its
test count ("221 passed") is for the two engine test files only, not the full
suite.

---

## 12. Possible thesis mapping

| Thesis chapter | Supported by |
|---|---|
| Literature / theory | ASHRAE psychrometrics, VPD, Mollier h-x, rule-based DSS |
| Methodology — system design | Architecture (§2), data model (§4), data flow (§5) |
| Methodology — psychrometric engine | §3, `docs/psychrometric-methodology.md` |
| Methodology — DSS | Rule model and default rules (§6) |
| Results — engine validation | §3.4 tables, `scripts/verify_engine.py` output |
| Results — application to greenhouse data | Import real datasets (e.g. tomato, zucchini, Venlo), export derived variables, plot trajectories and rule outcomes |
| Discussion — limitations | Air VPD only, altitude-derived pressure, no leaf temperature, global rules, no decision log or intervention analysis, no sensor QC categories |
| Future work | Prediction, optimisation, closed-loop control, decision logging, intervention analysis, data-quality classification |

Candidate figures the app can produce directly: psychrometric chart with target
zone and 24-hour trajectory; Mollier diagram; temperature, RH and VPD time
series; derived-property tables; rule list with triggering values.

---

## 13. Running it

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt       # add requirements-dev.txt for tests
.venv/bin/python scripts/init_db.py
.venv/bin/python scripts/seed.py                # optional: Tomato profile, 7 days of synthetic data
.venv/bin/python -m psychromol.api              # http://127.0.0.1:8888
```

The seed data is **synthetic** (sine-wave daily cycle plus noise) and must not
be reported as measurements. `data/reference/` holds verification data only,
not experimental data.
