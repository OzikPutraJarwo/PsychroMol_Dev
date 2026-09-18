# PsychroMol

Psychrometric decision support for a greenhouse.

A temperature and a humidity from your sensor become the full moist-air state —
vapour pressure, humidity ratio, dew point, wet bulb, enthalpy, density and the
vapour pressure deficit. Temperature, humidity and VPD are each classified
**LOW**, **OPTIMAL** or **HIGH** against the bands you set for your crop and
growth stage, and rules you can read and edit turn that into one recommendation:

```
measured → calculated → classified → rule → recommendation
```

Every number, band and recommendation carries the source it rests on, behind a
small **?**. It is not AI and it switches nothing by itself.

**Everything is calculated in your browser.** The server only keeps the
database and fetches your JSON link on a schedule, so readings keep arriving
while no browser is open.

## Run it

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m psychromol.api
```

Open http://127.0.0.1:8888.

For a look around without a sensor, `.venv/bin/python scripts/seed.py` adds an
example profile with a week of synthetic readings.

### Upgrading from an earlier version

The first start on an existing database upgrades it and **writes a backup of
the old file next to it** (`data/psychromol.backup-<date>-v2.db`) before
changing anything. Stop the old server first, and keep the backup.

What changes: your profiles keep their readings, names, bands and links; the
bands whose reference still said *PROVISIONAL* are marked as having no
documented source, so you can enter yours; VPD moves to the referenced value
for the growth stage; stored decisions are dropped, because advice is now
worked out live from the current rules. Tables from versions before 2 are left
untouched.

## How it fits together

A **profile** is one greenhouse.

| Piece | What it holds |
|---|---|
| Crop and growth stage | The crop's name, the stage (propagation, vegetative, flowering and fruiting), the optimal temperature and humidity bands **with the reference they come from**, and a VPD band — the referenced value for the stage, or your own with your own source |
| Data | A link that returns JSON, how often to fetch it, and which values in it are the time, the temperature, the humidity and (optionally) the pressure |
| Pressure | The standard atmosphere, a fixed value, or a value from the link |
| Rules | The advice for this greenhouse, each rule with its source |

A reading is a time, a temperature and a humidity. Paste the link and
PsychroMol reads it, lists what it found, and you pick which value is which:

```json
{"timestamp": "2026-09-17T09:10:04Z", "temperature": 27.0, "humidity": 44.6}
```

Nested values and arrays work too (`/feeds/0/sensors/air/t`). A time without a
time zone is read as UTC; with no time field, the moment the server received
the reading is used.

## Where the VPD bands come from

| Stage | VPD | Source |
|---|---|---|
| Propagation (rooting cuttings) | 0.3–0.5 kPa | Shamshiri et al. (2018), p. 292 |
| Vegetative | 0.2–1.0 kPa | Grange & Hand (1987) and Picken (1984), as summarised by Shamshiri et al. (2018), p. 292 and Table 3 |
| Flowering and fruiting | 0.2–1.0 kPa | the same — the source gives one range for the whole crop cycle, which the interface says plainly |

Temperature and humidity have **no** shipped defaults: no single band suits
every crop, so PsychroMol asks you for them and for their source, and refuses
to save a band without one.

VPD here is **air VPD**, `p_ws(t_air) − p_w`. Leaf VPD needs the leaf surface
temperature, which this data does not contain, so PsychroMol does not report
it — the reference popup says so.

## The views

* **Dashboard** — temperature, humidity and VPD with their states, then the
  recommendation. Click it and it opens up: how each value was classified
  against its band, and the calculation that produced it, with live numbers and
  a **?** on every line.
* **Psychro** — the psychrometric chart (switchable to Mollier) with the
  crop's target zone, the last 24 hours as a trail you can play back, and every
  derived property of the current point.
* **Data → Chart / Table** — any quantities over any range; the table can also
  show the state and advice for each past reading. Download as CSV or JSON.
* **Rules** — the rules behind the advice: the states each needs, its severity,
  its recommendation and its reference.

## The science

Moist-air relations follow the **ASHRAE Handbook — Fundamentals (2017),
Chapter 1**. `frontend/js/psychro.js` implements them and is the only place any
of them is written. `docs/psychrometric-methodology.md` records every equation,
assumption and validation result.

```bash
node scripts/verify_engine.mjs    # 33 checks against ASHRAE and PsychroLib
node --test tests/js/             # 53 tests
.venv/bin/python -m pytest -q     # 77 tests
```

The engine is checked against the ASHRAE saturation table, ASHRAE's worked
Example 1, ASHRAE's own dew-point regressions, 102 points from PsychroLib
(Meyer & Thevenard 2019) and an independent browser tool, plus round-trips of
every inverse.

## Running the frontend and backend on separate machines

`frontend/` is a static site — no build step, every asset loaded by a relative
path — so it can be hosted anywhere. The first time the page loads it tries the
address it knows; if that fails it asks for the server's address once and
remembers it (the plug icon in the top bar reopens that prompt). On the
backend, set `PSYCHROMOL_CORS_ORIGINS` to include wherever the frontend is
served from.

To collect readings on a small always-on machine (a Raspberry Pi, a VPS), run
the same backend there:

```bash
PSYCHROMOL_HOST=0.0.0.0 .venv/bin/python -m psychromol.api
```

## Layout

| Path | Contents |
|---|---|
| `frontend/js/psychro.js` | The ASHRAE engine |
| `frontend/js/geometry.js` | Chart curves and the target zone |
| `frontend/js/dss.js` | Growth stages, classification, default rules |
| `frontend/js/references.js` | Every source shown behind a **?** |
| `frontend/js/fields.js` | Reading values out of your JSON |
| `frontend/js/app.js` | The interface |
| `psychromol/` | Database, JSON fetcher, API |
| `tests/js/`, `tests/` | 53 browser-side tests, 77 server-side tests |
| `docs/psychrometric-methodology.md` | Equations, assumptions, validation |
