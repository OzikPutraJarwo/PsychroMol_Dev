# CLAUDE.md — working notes for PsychroMol

## What this is

Psychrometric decision support for a greenhouse. A temperature and a humidity
become the full moist-air state; user-editable rules turn that state into
advice that names the values which triggered it.

Optimise for correctness and for a grower reading the screen — not for feature
count.

## Hard rules

1. **This is rule-based, not AI.** No machine learning, no prediction, no
   autonomous control. This extends to the Raspberry Pi actuators (fan, pump,
   stepper): they are switched only by a person, from `/hardware/actuators` —
   never by a rule. If automatic actuator control is ever wanted, that is a
   deliberate rule-model change to raise with the user first, not something to
   wire up quietly inside the hardware poll loop.
2. **Never duplicate a psychrometric formula.** `psychromol/core/` is the only
   place moist-air relations may live. The frontend draws; it does not
   calculate. Chart geometry comes from the backend for this reason.
3. **Never mix pressure units.** The engine works in **Pa**, the API in **kPa**.
   Conversion happens only in `MoistAirState.to_api_dict()` and
   `psychromol/core/units.py`. API field names carry their unit.
4. **A reading is three things**: a time, a temperature, a humidity. Do not add
   optional channels back. Soil moisture and light (from the Pi's MCP3008) are
   *not* readings — they live only in `hardware.state.store`, in memory, never
   in the `readings` table.
5. **Pressure comes from the facility altitude**, never from a reading.
   `psychromol/hardware/` has no pressure sensor for this reason; if one is
   ever wired up, its value must still be discarded in favour of
   `pressure_for(profile)`.
6. **No comments in code**, except the ASHRAE equation citations in
   `psychromol/core/` and in the tests that verify against ASHRAE.
7. **English only.** No other language in the interface or the code.

## Dependency direction

```
api/ → pipeline.py → {db/, core/, rules.py, ingest.py}
core/ → (standard library only)
db/ → (no imports from quality, rules or api)
```

## Commands

```bash
.venv/bin/python -m pytest -q                 # 388 tests
.venv/bin/python scripts/verify_engine.py     # 31 ASHRAE checks
.venv/bin/python -m psychromol.api            # serve on :8888
.venv/bin/python scripts/seed.py              # an example profile with data
```

## Where things are

| Path | Contents |
|---|---|
| `psychromol/core/` | ASHRAE relations, `MoistAirState`, Mollier projection, chart geometry |
| `psychromol/rules.py` | Metric vocabulary, condition evaluation, equipment gating |
| `psychromol/defaults.py` | The 11 starting rules, and the sample crop and facility |
| `psychromol/ingest.py` | JSON and CSV parsing, loose column matching |
| `psychromol/pipeline.py` | Storing readings with their derived state, fetching sources |
| `psychromol/db/` | `crops`, `facilities`, `profiles`, `readings`, `rules` |
| `psychromol/api/` | Routers: catalogue, profiles, data, preview, rules, hardware |
| `psychromol/hardware/` | Raspberry Pi drivers, in-memory sensor/actuator state, the poll loop |
| `frontend/` | `app.js` (views), `chart.js` (psychrometric/Mollier), `trend.js`, `api.js` |

## Data model

Five tables. A `Profile` joins a `Crop` and a `Facility`; `Reading` rows belong
to a profile and carry both the raw pair and every derived quantity, so a
stored row can be re-derived and compared.

Deleting a profile also deletes its crop and facility, but only if no other
profile still references them (`Repository.delete_profile`) — the frontend
never lets a user pick an existing crop/facility for a new profile, so in
practice each profile owns its own pair and this keeps the catalogue from
silently accumulating orphaned rows.

`GET /profiles` does not compute a reading count per profile. It used to run
one `SELECT COUNT(*)` per profile on every list call; nothing in the interface
needs that number, so don't reintroduce it without a reason.

## Deployment

`frontend/` is a plain static site with no build step and no same-origin
assumption — every asset path is relative (`css/style.css`, `js/app.js`,
`../fonts/...`), and `frontend/js/api.js`'s `BASE` is read from
`localStorage["psychromol.apiBase"]`, not hardcoded. This means the frontend
can be hosted anywhere (a plain static host, `python -m http.server`, or the
backend's own `StaticFiles(directory=frontend, html=True)` mount at `/` in
`psychromol/api/app.py`) as long as it can reach the backend's `/api/v1`. On
first load, `start()` in `app.js` probes the stored (or default) base with
`api.probeBase()`; on failure it opens `#connect-modal` automatically so the
user can type the server's address — the same modal reopens from the
`#connect-btn` in the topbar at any time. Whichever origin the frontend is
served from, `PSYCHROMOL_CORS_ORIGINS` on the backend must include it.

A linked profile's `poll_interval_seconds` (default `DEFAULT_POLL_INTERVAL_SECONDS`
in `db/models.py`, currently 60; set from the Data tab's "Fetch every" field,
which doubles as the live-preview interval before saving) is *per-profile*,
not a single global cadence — `poll_sources` in `api/app.py` wakes every
`POLL_TICK_SECONDS` (1s) and `_is_due()` decides which profiles have actually
waited long enough since their own `last_polled_at`, so one profile can poll
every second while another stays at the default without the fast one being
throttled by the slow one's cadence. The frontend mirrors this: `startLive()`
sizes its own tick to `state.profile.poll_interval_seconds` and calls
`api.refresh()` (fetch + parse + store), not just `api.current()` (read-only)
— the dashboard is the thing actually driving "fetch and store while I'm
watching," not merely displaying whatever the backend happened to store on
its own. Adding this column to `Profile` needed a real migration path, since
`create_all()` only creates missing *tables* — `db/session.py`'s
`_add_missing_columns()` runs a `PRAGMA table_info` check and an `ALTER TABLE`
for any SQLite column the current model expects but an existing database file
predates; extend that function, not `create_all()` itself, for the next
column added to an existing table.

The Raspberry Pi runs the same backend, unmodified. `PSYCHROMOL_HOST=0.0.0.0`
makes it reachable on the LAN; `PSYCHROMOL_HARDWARE_ENABLED=true` plus
`PSYCHROMOL_HARDWARE_PROFILE_ID` turns on a second background poll loop
(`poll_hardware` in `api/app.py`) that reads the SHT10 every
`PSYCHROMOL_HARDWARE_POLL_SECONDS` and calls `Pipeline.store_samples` directly
— in-process, the same pattern `poll_sources` already uses for `source_url`
profiles. Pin numbers are all `PSYCHROMOL_PIN_*` env vars with defaults listed
in `.env.example`; nothing in `psychromol/hardware/` hardcodes a pin. The
`requirements-pi.txt` / `pyproject.toml`'s `pi` extra (RPi.GPIO, spidev,
luma.oled) are **not** in the base `requirements.txt` — a dev machine must
never need them to run the test suite, which is why every hardware import in
`psychromol/hardware/drivers.py` is lazy (inside `__init__`, not at module
top) and raises `HardwareError` instead of `ImportError` when missing.

## Theme

White, clean, iOS-style glassmorphism — translucent surfaces
(`background: var(--surface*)` + `backdrop-filter: blur(...)`) floating over a
soft pastel gradient on `body`. Material Symbols Rounded icons throughout
(`.icon`, bundled locally).

**Light mode only, deliberately.** `:root { color-scheme: light; }` and no
`@media (prefers-color-scheme: dark)` block. This was a second correction —
the first pass shipped a solid green theme, corrected to light glass; a
follow-up then shipped a dark variant for `prefers-color-scheme: dark`, which
the person running this on a dark-mode OS did not want either. Don't
reintroduce a dark block without being asked again.

## The profile modal

One DOM shell (`#profile-modal-card`), three modes rendered entirely by JS —
there is no static markup per mode. Header actions read left to right:

* **`edit`** — opened for the currently active profile (clicking the profile
  chip when one is selected): `[title input] ... [Delete] [Switch profile]
  [Close]`. Sidebar tabs are Crop / Facility / Data, each editing that
  profile's *own* crop/facility directly (no catalogue browsing), each with
  its own immediate "Save crop" / "Save facility" button. The modal title is
  the profile's name, editable in place (saves on blur/Enter).
* **`switch`** — a plain list of every profile plus "Add new profile". Row
  click switches the active profile and closes the modal outright.
  Deliberately no per-row edit/delete — those live in `edit` mode.
  Deliberately no reading count (see above).
* **`add`** — `[title input] ... [Create profile] [Close]`. Crop, Facility and
  Data are three *plain forms with no save button of their own* — creation is
  one atomic action from the single header button, not three separate ones.
  All three tabs render into the DOM together the first time `add` mode opens
  (`modalState.addRendered`) and are never re-rendered on tab switch, or
  switching away from a tab the user had already filled in would wipe it.
  "Create profile" reads all three via `collectCropForm()` /
  `collectFacilityForm()` / `$("#src-url")`, regardless of which tab is
  currently visible, then does `addCrop` → `addFacility` → `addProfile` in
  sequence. On success the modal flips straight into `edit` mode for the new
  profile, landing on Data, so a link or file can be added immediately.

Fresh install (no profile at all) opens `add` directly; there is nothing to
switch to yet.

## The Psychro page

The chart itself (`/profiles/{id}/chart`) plus a "current point" tile grid
below it (`#point-detail`), replacing what used to live on the dashboard as a
separate "Air properties" grid. **Always visible, not collapsible** — an
earlier pass put this behind a click like the dashboard's advice; that was
reverted, since farmers want the numbers on screen, not another tap. The tiles
are solid white (`var(--surface-solid)`, no blur) rather than the glass
translucency used elsewhere, a deliberate visual distinction for this data-only
section.

* **The chart's target zone** is *computed by the backend*
  (`_target_zone_points` in `psychromol/core/chart.py`), not drawn as a
  decorative rectangle on the frontend — see hard rule 2. It is the crop's
  `(temperature_min, temperature_max, humidity_min, humidity_max)`, bounded by
  the same relative-humidity relation that draws the RH family, so the top and
  bottom edges are real RH curves, not a straight-edged box. Drawn first, so
  every other curve sits above it.
* **The history trail** is the last 24 hours of readings (`Chart.setHistory`),
  refetched by `refreshChartHistory()` on every live tick *while the Psychro
  view is active* — the chart's static geometry (curves, target zone) is
  fetched once per visit/kind-switch, not every 15 s.
* **Hover** shows a crosshair with the raw axis-unit coordinates under the
  cursor (a linear inverse via `ix()`/`iy()` — legitimate, not a psychrometric
  calculation) unless the cursor is within 14 px of a history point, in which
  case it snaps to that point and shows its actual measured values instead of
  an interpolation.
* **Playback** (`#history-play`, `#history-scrub`) steps a second marker
  (`Chart.setPlaybackPoint`, drawn in `--warning` orange to stay distinct from
  the `--accent` blue "Now" point) through `charts.full.historyRows` — the
  same array the trail and hover already read, not a separate fetch. The
  scrubber is the source of truth for "where we are"; `startPlayback()` just
  drives it forward on a `setInterval`, and dragging it manually always calls
  `stopPlayback()` first. Switching Mollier ↔ psychrometric or a live-tick
  history refresh both call `stopPlayback()` — the chart instance underneath
  either gets destroyed or its `historyRows` array replaced, so a playback
  timer left running past either would reference stale indices.

## The Data page

Shows only `temperature` and `relative_humidity` by default
(`state.dataColumns`, from `/meta`'s `default_display_fields`). The gear-style
"Columns" button opens a picker over the full field list
(`/meta`'s `fields`, sourced from `psychromol/api/routers/data.py`'s `FIELDS`)
and both the trend chart's series and the table's columns are driven by
whatever is chosen — never hardcoded. The choice persists in
`localStorage["psychromol.columns"]`. The **download** modal is a separate,
wider choice: it always offers the full field list regardless of what's
currently displayed, defaulting its checkboxes to the display selection —
"what you see" and "what you can export" are related but not the same control.

## The rule model

```json
{
  "name": "Hot and humid",
  "conditions": [
    {"metric": "temperature", "operator": ">", "target": "temperature.max"},
    {"metric": "relative_humidity", "operator": ">", "target": "relative_humidity.max"}
  ],
  "severity": "critical",
  "recommendation": "Ventilate first, then cool.",
  "requires_equipment": "roof_vent",
  "priority": 12
}
```

All conditions must hold. A condition compares a metric against a fixed `value`
or against a crop `target` (`temperature.max`, `relative_humidity.min`, …) with
an optional `offset`. Lower `priority` fires first; the first match gives the
headline.

Adding a metric means adding it to `METRICS` **and** to `metric_value()` in
`psychromol/rules.py`, and to `FIELDS` in `api/routers/data.py` if it should be
exportable.

## Traps this project has already fallen into

* **Single-letter column candidates match everything.** `"t"` is a substring of
  `date_time` and of `status`. Loose header matching tries exact names first,
  then whole words, then substrings, and never substring-matches a candidate
  shorter than three characters.
* **An SVG that is re-created loses pointer capture.** The chart keeps one
  `<svg>` element and replaces only its children, or dragging breaks after the
  first move.
* **Chart points are not always in axis units.** An axis that declares
  `scale_to_base` carries base-unit points; divide before plotting. The
  psychrometric y-axis does this, the Mollier x-axis does not.
* **A fixed-width chart inside a grid forces the page wider.** Grid and flex
  children need `min-width: 0`, or the chart can never shrink to fit.
* **Charts track their container's pixel width, not a CSS transform.**
  `Chart`/`Trend` measure the host with `ResizeObserver` and set the SVG's
  `width`/`viewBox` to that exact pixel value every render, so 1 SVG unit
  always equals 1 CSS pixel — text stays a constant size regardless of width.
  Stretching the SVG via `width: 100%` instead would scale the text along with
  it, which is the opposite of what a legible chart needs. Height never
  changes with width. Tick count is computed from the available plot width
  (`plotWidth() / 65` for the x-axis) so labels thin out rather than overlap
  as the container narrows — never a fixed tick count.
* **A discarded chart instance must `destroy()`**, or its `ResizeObserver`
  keeps firing into a dead object. Anywhere a `Chart`/`Trend` is replaced
  (e.g. switching Mollier ↔ psychrometric), call `.destroy()` on the old one
  first.
* **`[hidden]` is only `display:none` until some other rule sets `display`.**
  Any class that declares its own `display` (`.custom-range { display: flex
  }`, `.modal { display: grid }`, and formerly a now-deleted `.advice` block)
  wins the cascade over the attribute selector at equal specificity, silently
  reappearing whenever `hidden` is set. A single `[hidden] { display: none
  !important; }` rule covers every current and future case; don't patch
  `.foo[hidden]` one class at a time.
* **A collapsible section re-rendered on a live tick must read back whether it
  was open before rebuilding its markup**, or it silently snaps shut under a
  reader every `LIVE_MS`. This bit both the dashboard's advice and the Psychro
  point-detail before either was made non-collapsible; there is no live
  example of the pattern left in this codebase, but the fix — read
  `!document.getElementById(...).hidden` before touching `innerHTML`, then
  carry it into the new markup — applies to any future collapsible driven by
  a periodic refresh.
* **Two CSS custom properties can resolve to the same colour without either
  declaration looking wrong on its own.** `--accent` and `--info` were both
  `#0a84ff`; a two-line trend chart (temperature + humidity) rendered as one
  indistinguishable blue line. Chart *series* colours are `--series-1`
  through `--series-6` in `trend.js`'s `COLOURS`, deliberately **not** the
  same tokens as the semantic status colours (`--ok`/`--info`/`--warning`/
  `--critical`) — those are free to collide with each other or with a series
  colour, since nothing ever shows two of them side by side as data lines.
* **`/readings` and `/current` don't use the same unit convention for the same
  quantity.** `/current` (a `MoistAirState.to_api_dict()`) hands back both a
  base-SI and a display-unit field for things like humidity ratio
  (`_kg_kg` and `_g_kg`); which one a chart point needs depends on whether
  that axis declares `scale_to_base` (see the trap above). `/readings` only
  ever returns the display-unit field. History points therefore plot directly
  via `sx()/sy()` — never through `Chart.toAxis()`, which is for the backend
  *chart geometry's* raw curve points specifically, not for reading rows.
* **The mini dashboard chart is non-interactive but still gets the target
  zone and grid**, since those come from `geometry.curves`/`drawGrid()`
  regardless of the `interactive` flag — only `attach()` (drag/zoom/hover) is
  skipped. Don't assume "non-interactive" means "static geometry only."
* **A live-preview interval left running behind a hidden tab keeps hitting the
  network.** The Data tab's JSON-link preview (`wireLivePreview` in `app.js`)
  ticks on a `setInterval` that survives tab switches in `add` mode (all three
  tabs stay mounted at once, see the profile modal notes above); `tick()`
  checks `#tab-data`'s `active` class itself and skips the fetch rather than
  relying on the interval being torn down. `stopPreview()` still runs on
  every `renderDataTab()` call and on every path that closes `#profile-modal`
  (`closeProfileModal()`, the generic `data-close`/backdrop handlers in
  `wire()`) — miss one of those and a closed modal keeps polling a URL the
  user never asked to save.
* **Two static-serving strategies can't coexist without one shadowing the
  other's asset paths.** `frontend/index.html`/`style.css` reference assets by
  relative path (`css/style.css`, not `/static/css/style.css`) specifically so
  the same `frontend/` folder works both standalone and mounted by FastAPI.
  `psychromol/api/app.py` therefore mounts the whole directory at `/` with
  `StaticFiles(html=True)` — not the old split of a `/static` mount plus a
  separate `FileResponse` route for `/` — because a relative path from
  `index.html` served at `/` only resolves correctly if its sibling files are
  also served from `/`, not from `/static/`. The API routers are registered
  before this mount, so `/api/v1/*` still wins the match.
* **A hardware driver module must import cleanly with no hardware present.**
  `psychromol/hardware/drivers.py` never imports `RPi.GPIO`, `spidev` or
  `luma` at module level — each is imported inside the class that needs it,
  caught, and re-raised as `HardwareError`. This is what lets the full test
  suite (and `psychromol.hardware.drivers.Simulated*`) run on a dev machine
  with none of `requirements-pi.txt` installed; a top-level import would make
  `from psychromol.hardware import runtime` itself fail off-Pi.

## Before you change anything

```bash
.venv/bin/python scripts/verify_engine.py
.venv/bin/python -m pytest -q
```
