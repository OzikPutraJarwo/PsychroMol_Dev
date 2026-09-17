# PsychroMol

Psychrometric decision support for greenhouse environment management.

A reading of temperature and humidity becomes the full moist-air state, and a
set of rules you can read and edit turns that state into advice. Every piece of
advice names the measured values that triggered it.

## Run it

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/init_db.py
.venv/bin/python -m psychromol.api
```

Open http://127.0.0.1:8888.

For a working example with a week of readings:

```bash
.venv/bin/python scripts/seed.py
```

## How it fits together

A **profile** joins one crop with one facility and one data source. You can
keep as many as you grow: tomato in house 1, cucumber in house 2, and so on.

| Piece | What it holds |
|---|---|
| Crop | Name, and the temperature and humidity bands it wants. Other targets such as VPD can be added. |
| Facility | Name, altitude, and which equipment is present. |
| Data | A JSON link the server reads on a schedule you set (default 60 seconds, as fast as 1), or a file you upload. |

A reading needs three things and nothing more: a **time**, a **temperature**
and a **humidity**. Column names are matched loosely, so `timestamp`, `time`,
`ts` and `Date Time` all work, as do `temp`, `t` and `Air Temperature (C)`.
While you're pasting in a JSON link, a live preview underneath fetches it on a
timer (every second by default, adjustable) so you can see what will be
stored before you save the link.

## The four views

* **Dashboard** — temperature and humidity, then the current condition and
  what to do about it, in one line.
* **Psychro** — the full chart from −20 to 50 °C, switchable to Mollier.
  Scroll to zoom in, drag to pan, hover to read a point; zooming out stops at
  the full chart. The shaded area is where the current crop wants to be, and
  a faint trail traces the last 24 hours of movement — play it back, or drag
  the scrubber to any moment. Below the chart, every value the psychrometric
  engine derives from the current reading, always on screen.
* **Data** — the last 24 hours by default, any range on request. Shows just
  temperature and humidity until you open Columns and add more — VPD, dew
  point, enthalpy, whatever the engine calculates. Download in CSV or JSON
  with whichever columns you choose, independent of what's on screen.
* **Rules** — the rules that produce the advice. Edit them, add your own,
  delete the ones that do not apply.

## Rules

A rule is a list of conditions that must **all** hold, plus the advice to give
when they do. A condition compares one measured quantity against either a fixed
number or the crop's own target:

```
Temperature  >  crop max temperature + 5     →  critical  "Open the vents fully."
Temperature  >  crop max temperature
Relative humidity  >  crop max humidity      →  critical  "Ventilate first, then cool."
```

Because conditions can point at the crop's targets, changing the crop changes
what the rules say without editing a single rule.

Rules are ordered by their `priority` number, lowest first. The first matching
rule gives the headline; every match is listed underneath. A rule can name a
piece of equipment, and its advice is marked when the facility does not have it.

## The science

Moist-air relations follow the ASHRAE Handbook — Fundamentals (2017),
Chapter 1. `psychromol/core/` implements them with no dependencies beyond the
standard library, and `docs/psychrometric-methodology.md` records every
equation, assumption and validation result.

```bash
.venv/bin/python scripts/verify_engine.py    # 31 checks against ASHRAE
.venv/bin/python -m pytest -q                # 388 tests
```

Altitude matters: the facility's altitude sets the pressure used for every
calculation. The same 24 °C and 70 % at 1000 m holds about 12 % more moisture
per kilogram of dry air than at sea level.

## Running the frontend and backend on separate machines

`frontend/` is a static site — no build step, and every asset is loaded by a
relative path, so the folder can be hosted anywhere (a plain static host,
a CDN, or just `python -m http.server` inside `frontend/`) independently of
where the backend runs. The first time the page loads, it tries to reach the
backend at the address it already knows; if that fails, it asks for the
server's address once and remembers it (a small plug icon in the top bar
reopens that prompt later). On the backend, set `PSYCHROMOL_CORS_ORIGINS` to
include wherever the frontend ends up being served from.

## Raspberry Pi

The backend is one process, so it runs on a Raspberry Pi exactly as it does
anywhere else — the only change is making it reachable on the network and,
optionally, turning on the local sensors and controls wired to the GPIO
header.

```bash
PSYCHROMOL_HOST=0.0.0.0 .venv/bin/python -m psychromol.api
```

Point the frontend (wherever it's hosted) at `http://<the Pi's address>:8888`.

To read sensors and drive equipment straight off the Pi's pins, install the
extra drivers and turn hardware polling on:

```bash
.venv/bin/pip install -r requirements-pi.txt
```

```bash
PSYCHROMOL_HARDWARE_ENABLED=true
PSYCHROMOL_HARDWARE_PROFILE_ID=1      # which profile the sensor readings belong to
```

With this on, the server reads an SHT10 temperature/humidity sensor every few
seconds and stores it exactly like any other reading. A soil moisture sensor
and a light sensor (both through an MCP3008 ADC) are shown on a 128×64 OLED
display alongside the current reading, but are not stored as readings
themselves — they aren't temperature or humidity, so they don't belong in the
same history. A fan, a water pump and a stepper motor can be wired up too;
they are switched **manually**, from `GET/POST /api/v1/hardware/status` and
`/api/v1/hardware/actuators/{name}` — this project is rule-based advice, not
automatic control, so nothing turns them on by itself. Every pin is a
`PSYCHROMOL_PIN_*` environment variable; see `.env.example` for the full list
and its defaults.

## Layout

| Path | Contents |
|---|---|
| `psychromol/core/` | ASHRAE moist-air relations, state, chart geometry |
| `psychromol/rules.py` | Rule evaluation |
| `psychromol/ingest.py` | Reading JSON and CSV of many shapes |
| `psychromol/pipeline.py` | Reading → state → stored row, and source fetching |
| `psychromol/db/` | Five tables, and the only code that touches a session |
| `psychromol/api/` | FastAPI routers |
| `psychromol/hardware/` | Raspberry Pi sensor/actuator drivers and the poll loop |
| `frontend/` | Static ES modules, no build step |
| `tests/` | 388 tests |
