# Psychrometric formulation and verification record

This document is the scientific basis for every number PsychroMol reports. It
names each equation, its source, its assumptions, its validity range and the
test that defends it. Nothing here is "ASHRAE-based" because it looks
plausible — each claim is backed by an executable test.

**Primary reference:** ASHRAE Handbook — Fundamentals (2017), Chapter 1,
*Psychrometrics*. Equation numbers below refer to that chapter.
**Implementation:** [frontend/js/psychro.js](../frontend/js/psychro.js) — the
only place in this project where a moist-air relation is written.
**Verification:** [scripts/verify_engine.mjs](../scripts/verify_engine.mjs),
[tests/js/psychro.test.mjs](../tests/js/psychro.test.mjs),
[tests/js/geometry.test.mjs](../tests/js/geometry.test.mjs)

```bash
node scripts/verify_engine.mjs   # 33 checks
node --test tests/js/            # 53 tests
```

---

## 1. Unit conventions

| Quantity | Symbol | Engine unit | Interface / API unit |
|---|---|---|---|
| Dry-bulb temperature | `t` | °C | °C |
| Wet-bulb temperature | `t*` | °C | °C |
| Dew-point temperature | `t_d` | °C | °C |
| Total (atmospheric) pressure | `p` | **Pa** | **kPa** |
| Partial vapour pressure | `p_w` | **Pa** | **kPa** |
| Saturation vapour pressure | `p_ws` | **Pa** | **kPa** |
| Humidity ratio | `W` | kg/kg dry air | g/kg dry air |
| Relative humidity | `φ` | % | % |
| Specific enthalpy | `h` | kJ/kg dry air | kJ/kg dry air |
| Specific volume | `v` | m³/kg dry air | m³/kg dry air |
| Moist-air density | `ρ` | kg/m³ | kg/m³ |
| Vapour-pressure deficit | VPD | **Pa** | **kPa** |
| Absolute humidity | `d_v` | g/m³ | g/m³ |

The engine works in **pascal** because ASHRAE's saturation correlations are
written in Pa. Conversion happens in exactly two files —
`frontend/js/units.js` (browser) and `psychromol/units.py` (server, for the
pressure unit of a mapped JSON field and for the v2 → v3 upgrade). Every API
field name carries its unit (`pressure_kpa`, `temperature_c`) so a unit can
never be inferred wrongly from context.

**Guard:** `a pressure given in kPa instead of Pa is refused` — passing
101.325 where 101 325 was meant raises rather than producing plausible-looking
numbers.

---

## 2. Constants

| Constant | Value | Source |
|---|---|---|
| `MW_RATIO` | 0.621945 | `M_w / M_da` = 18.015268 / 28.966 |
| `SPECIFIC_VOLUME_W_COEFF` | 1.607858 | `1 / MW_RATIO`, as printed in Eq. (26) |
| `R_DRY_AIR` | 287.042 J/(kg·K) | Eq. (26) (ASHRAE prints 0.287042 kJ/(kg·K)) |
| `CP_DRY_AIR` | 1.006 kJ/(kg·K) | Eq. (30) |
| `CP_WATER_VAPOUR` | 1.86 kJ/(kg·K) | Eq. (30) |
| `CP_LIQUID_WATER` | 4.186 kJ/(kg·K) | Eq. (33) |
| `CP_ICE` | 2.1 kJ/(kg·K) | Eq. (35) |
| `H_FG_0C` | 2501 kJ/kg | Latent heat of vaporisation at 0 °C, Eq. (30) |
| `H_IG_0C` | 2830 kJ/kg | Latent heat of sublimation at 0 °C, Eq. (35) |
| `STANDARD_PRESSURE_PA` | 101 325 Pa | Eq. (3) at Z = 0 — **a default, not an assumption** |

---

## 3. Equations implemented

| # | Quantity | ASHRAE Eq. | Form | Validity |
|---|---|---|---|---|
| 1 | Saturation vapour pressure over ice | (5) | `ln p_ws = C1/T + C2 + C3T + C4T² + C5T³ + C6T⁴ + C7 ln T` | −100…0 °C |
| 2 | Saturation vapour pressure over water | (6) | `ln p_ws = C8/T + C9 + C10T + C11T² + C12T³ + C13 ln T` | 0…200 °C |
| 3 | Vapour pressure from relative humidity | (12), (22) | `p_w = φ p_ws` | 0…100 % |
| 4 | Humidity ratio | (20) | `W = 0.621945 p_w / (p − p_w)` | `p_w < p` |
| 5 | Vapour pressure from humidity ratio | (20) rearranged | `p_w = p W / (0.621945 + W)` | `W ≥ 0` |
| 6 | Dew point | inverse of (5)/(6) | numerical | `p_w > 0` |
| 7 | Humidity ratio from wet bulb, above freezing | (33) | `W = ((2501 − 2.326t*)W_s* − 1.006(t − t*)) / (2501 + 1.86t − 4.186t*)` | `t* ≥ 0 °C` |
| 8 | Humidity ratio from wet bulb, below freezing | (35) | `W = ((2830 − 0.24t*)W_s* − 1.006(t − t*)) / (2830 + 1.86t − 2.1t*)` | `t* < 0 °C` |
| 9 | Wet-bulb temperature | inverse of (33)/(35) | numerical | `t_d ≤ t* ≤ t` |
| 10 | Specific enthalpy | (30) | `h = 1.006t + W(2501 + 1.86t)` | — |
| 11 | Specific volume | (26) | `v = R_da(t + 273.15)(1 + 1.607858W)/p` | — |
| 12 | Moist-air density | (11) | `ρ = (1 + W)/v` | — |
| 13 | Absolute humidity | definition `d_v = M_w/V` | `d_v = 1000 W / v` [g/m³] | — |
| 14 | Standard atmosphere | (3) | `p = 101325(1 − 2.25577e−5 Z)^5.2559` | 0…11 000 m |
| 15 | Vapour-pressure deficit | — (definition, §6) | `VPD = p_ws(t) − p_w` | see §4.7 |

Two equation numbers were **corrected** against PsychroLib's documentation
while porting: the below-freezing wet-bulb relation is Eq. **(35)**, not (34),
and relative humidity is Eq. (12) with (22). An earlier version of this project
cited both wrongly.

The Mollier h–x projection (`frontend/js/geometry.js`) is a coordinate
transform of quantities already computed: `x = W`, `y = h − 2501·W`, which
makes the 0 °C isotherm horizontal. Mollier, R. (1923), *Ein neues Diagramm für
Dampfluftgemische*, Z. VDI 67(36), 869–872, introduced the diagram; the skew is
this project's drawing convention, and the tests assert that every drawn line
lies exactly on the quantity it is labelled with.

---

## 4. Documented assumptions

### 4.1 Default pressure is the sea-level standard atmosphere
101 325 Pa is used only when a profile chooses `standard`. A profile may
instead set a fixed pressure or map one from its JSON link. Dew point and VPD
do not depend on pressure; the humidity ratio does (at 85 kPa it is ~20 %
higher than at 101.325 kPa for the same t and φ).
**Checks:** `pressure comes from the profile's choice, in pascals`,
`the standard atmosphere matches ASHRAE Eq. 3`, verification §7.

### 4.2 Below 0 °C the saturation curve is taken over ice
ASHRAE switches from Eq. (6) to Eq. (5) at 0 °C, so the reported "dew point"
below freezing is strictly a **frost point** — the temperature at which vapour
deposits on a cold surface, which is the physically relevant quantity for
condensation on glazing. At exactly 0 °C the water branch is taken (611.213 Pa).
**Checks:** `the saturation branch switches from ice to water at 0 °C`,
`below freezing the dew point is a frost point and the wet bulb uses Eq. 35`.

### 4.3 Inverses are solved numerically, not by curve fit
ASHRAE's Eq. (37)/(38) dew-point regressions are convenience fits. This engine
inverts Eq. (5)/(6) by bisection to 10⁻¹⁰ °C, as PsychroLib does, "rather than
using the regressions provided by ASHRAE (eqn. 37 and 38) which are much less
accurate and have a narrower range of validity" (PsychroLib 2.5.0,
`GetTDewPointFromVapPres`). The regressions are kept in the test suite as an
independent formulation to compare against.
**Check:** max |bisection − Eq. (37)| = **0.031 K** over 0–50 °C × 20–100 % RH.

### 4.4 Bisection, not Newton–Raphson
The correlations are cheap and the brackets are known a priori (`[t_d, t]` for
the wet bulb, `[−100, 200]` for the saturation inverse); bisection cannot
diverge. This code runs unattended against live sensor data, where a diverging
solver is a silent data-quality failure. Tolerance 10⁻¹⁰ on the bracket, cap
200 iterations — the cap is never the binding constraint.

### 4.5 The wet-bulb bracket starts at the dew point
A fixed lower bound fails to bracket the root for cold or very dry air.
**Check:** round-trips including −5 °C/80 % and −8 °C/60 %.

### 4.6 A measured relative humidity is carried through exactly
`stateFromTemperatureRelativeHumidity` computes `p_w = φ p_ws` (Eq. 12/22) and
keeps `φ` as the sensor reported it. Deriving `φ` back from the humidity ratio
returned 59.999999999999993 % for a 60 % reading, which classified a reading
sitting exactly on a band limit as LOW. VPD is likewise `p_ws − p_w` from those
two values.
**Check:** `a measured relative humidity is carried exactly, so a band limit
stays on the limit`.

### 4.7 VPD is air VPD, not leaf-to-air VPD
`VPD = p_ws(t_air) − p_w`, evaluated at **air** temperature, the form given by
Shamshiri et al. (2018, p. 290 and p. 292). Leaf-to-air VPD substitutes the leaf
temperature into the saturation term: "VPD's for growing crops can only be
calculated accurately when the surface temperature of the leaves is known"
(BC Ministry of Agriculture 2015, p. 6). PsychroMol does not measure leaf
temperature and therefore does not report that quantity; the reference popup
behind the VPD figure says so. Any thesis text using these values must say
"air VPD".

### 4.8 ASHRAE's two wet-bulb branches disagree at exactly 0 °C
Eq. (33) (water on the wick) and Eq. (35) (ice) meet with a step. The humidity
ratio Eq. (33) gives at `t* = 0` therefore inverts to a slightly negative
wet-bulb temperature: −0.035 K at 1 °C dry bulb, −0.353 K at 5 °C. PsychroLib
2.5.0 reproduces the same values to 0.001 K, so this is a property of the
standard, not of this implementation. It matters only within a few tenths of a
degree of 0 °C.
**Check:** `at a 0 °C wet bulb the ASHRAE water and ice equations disagree,
exactly as in PsychroLib`.

### 4.9 Correlation range is enforced, not extrapolated
Inputs outside −100…200 °C, 0…100 % RH or 20…200 kPa raise
`PsychrometricRangeError`. The interface then shows the reading with a plain
statement that it was not assessed, and stores it unchanged — a humidity of
100.4 % from a saturated sensor is never silently clamped or dropped.

### 4.10 Enthalpy datum
Dry air and liquid water, both at 0 °C (ASHRAE's datum), so enthalpy is
pressure-independent — worth stating because Mollier charts are drawn for a
nominal pressure and the two facts are easily conflated.

### 4.11 Dew point and wet bulb are computed only when read
Both cost a bisection, and an export of thousands of readings usually needs
neither. They are lazy getters on the frozen state object; everything else is
computed eagerly. Serialisation and spreading still see them.

---

## 5. Validation results

Status at last run: **33 of 33 checks passed, 53 of 53 tests passed.**

### 5.1 Source 1 — ASHRAE saturation-pressure table
19 tabulated points, −60…100 °C, tolerance 5 × 10⁻⁴ relative (the table's own
rounding). All pass.

| t (°C) | ASHRAE `p_ws` (Pa) | Engine (Pa) |
|---|---|---|
| −40 | 12.845 | 12.84525 |
| 0 | 611.21 | 611.21287 |
| 20 | 2338.8 | 2338.80370 |
| 30 | 4246.0 | 4246.03024 |
| 50 | 12349.9 | 12349.85647 |

Strict monotonicity of `p_ws` is checked at every degree from −100 to 200 °C.

### 5.2 Source 2 — ASHRAE Ch. 1, worked Example 1
Moist air at **40 °C dry-bulb, 20 °C wet-bulb, 101.325 kPa**:

| Quantity | ASHRAE printed | PsychroMol | Deviation |
|---|---|---|---|
| Humidity ratio `W` | 0.0064 kg/kg | 0.0064008 | 7.9 × 10⁻⁷ |
| Enthalpy `h` | 56.7 kJ/kg | 56.725 | 0.025 |
| Dew point `t_d` | 7.4 °C | 7.434 | 0.034 K |
| Relative humidity `φ` | 14 % | 13.979 % | 0.021 |
| Specific volume `v` | 0.896 m³/kg | 0.89625 | 2.5 × 10⁻⁴ |

### 5.3 Source 3 — ASHRAE Eq. (37)/(38), an independent formulation
Max deviation from the bisection inverse: **0.031 K** over 0–50 °C.

### 5.4 Source 4 — PsychroLib 2.5.0
102 points generated once with the Python package and stored as
[data/reference/psychrolib-grid.json](../data/reference/psychrolib-grid.json):
−10…50 °C × 5…100 % RH at 101.325 kPa, plus 25 °C/70 % at 85, 95 and 105 kPa.

| Quantity | Max deviation | Test tolerance |
|---|---|---|
| Humidity ratio | 9.8 × 10⁻⁵ relative | 1 × 10⁻³ rel |
| Dew point | 1.2 × 10⁻³ K | 5 × 10⁻³ K |
| Wet bulb | 6.6 × 10⁻⁴ K | 5 × 10⁻³ K |
| Enthalpy | 9.2 × 10⁻⁴ kJ/kg | 5 × 10⁻³ |
| VPD | 5.6 × 10⁻² Pa | 0.5 Pa |

The residual is the two libraries' differing solver tolerances, not a
formulation difference. PsychroLib is not a runtime dependency; the fixture is
a file.

### 5.5 Source 5 — independent third-party tool export
8 points, 17.8…44.6 °C, from a Magnus-formulation browser tool
([data/reference/external-tool-benchmark.csv](../data/reference/external-tool-benchmark.csv)).
Max deviations: `W` 4.5 × 10⁻⁵ kg/kg, `t*` 0.023 K, `t_d` 0.034 K, `h`
0.122 kJ/kg, `v` 6.6 × 10⁻⁵ m³/kg, `ρ` 1.1 × 10⁻⁴ kg/m³, `d_v` 0.053 g/m³ —
within that tool's Magnus offset (~0.4 % on `p_ws`) and its printed precision.

### 5.6 Source 6 — internal consistency
Nine representative conditions — cold/humid (5 °C/90 %), moderate (20 °C/50 %),
hot/dry (35 °C/20 %), hot/humid (35 °C/85 %), near-saturation (40 °C/99 %),
sub-freezing (−5 °C/80 %) — each verified for:

* RH, wet-bulb, dew-point, enthalpy and specific-volume round-trips
  (worst: RH 1.4 × 10⁻¹⁴ %, wet bulb 8.6 × 10⁻¹⁴ kg/kg, dew point 8.2 × 10⁻⁹ Pa);
* agreement between all four state constructors (t+φ, t+t_d, t+t*, t+W);
* the ordering `t_d ≤ t* ≤ t`;
* saturation collapsing all three temperatures and driving VPD to zero;
* VPD rising with temperature at fixed RH and falling with RH at fixed
  temperature.

### 5.7 Chart geometry
Every curve the charts draw is checked against the engine at every sampled
point: relative-humidity curves invert to their own percentage, isenthalps to
their enthalpy, wet-bulb lines to their wet-bulb temperature, constant-volume
lines to their volume, the saturation line to `W_s(t)`, and the Mollier
isotherms and isenthalps to theirs. The target zone's edges are the same
relative-humidity relation the RH family is drawn with, so the shaded band can
never disagree with the curves around it.

### 5.8 Browser and server read a JSON link identically
The server stores readings while no browser is open, so its extraction must
match the browser's preview exactly.
[tests/fixtures/extraction-cases.json](../tests/fixtures/extraction-cases.json)
holds 22 cases — nested paths, array indices, epoch seconds and milliseconds,
naive and offset times, decimal commas, units after the number, pressure unit
conversion, and every failure mode — and both `tests/js/fields.test.mjs` and
`tests/test_fetcher.py` assert the same expected values.

---

## 6. Thresholds and their sources

PsychroMol ships **no** temperature or humidity band. The user enters both with
the reference they come from, and the API refuses a profile without one. The
reasons are stated in the interface: "There is no one level of humidity that is
good for all crops" (BC Ministry of Agriculture 2015, p. 3), and optimal
temperatures depend on crop, stage and light (Shamshiri et al. 2018).

For orientation the interface quotes, as orientation only: greenhouse crops are
mostly warm-season crops adapted to 17–27 °C (Shamshiri et al. 2018, p. 289,
citing Kittas et al. 2005), and 60–90 % RH is considered appropriate for most
greenhouse tomato varieties by ASABE (2015) standards (p. 290).

VPD **does** ship a default per growth stage, because a referenced range exists:

| Stage | VPD | Source |
|---|---|---|
| Propagation (rooting cuttings) | 0.3–0.5 kPa | Shamshiri et al. (2018), p. 292: "VPD should be kept around 0.3–0.5 kPa during root cuttings" |
| Vegetative | 0.2–1.0 kPa | Grange & Hand (1987) and Picken (1984) as summarised in Shamshiri et al. (2018), p. 292 and Table 3 (p. 293) |
| Flowering and fruiting | 0.2–1.0 kPa | the same |

The source gives one range for the whole crop cycle rather than per stage, and
the popup behind the value says so. A profile may replace it with its own band
and its own reference.

The default advice rules cite the same two sources for what to *do*; each rule
carries its quotation and page, and the rules page shows it behind a **?**.
Every quotation in `references.js` and `dss.js` was checked verbatim against
the source PDFs.

---

## 7. What is *not* validated

Stated plainly, because the brief requires honesty about limits:

* **Above 60 °C and below −20 °C** the engine is exercised against the
  correlations and PsychroLib, not against tabulated values at every point.
  Greenhouse work never reaches there.
* **Pressures far from 1 atm** are cross-checked at 85, 95 and 105 kPa only.
* **The Mollier projection** is tested for self-consistency and against the
  engine, not against a published h–x chart (no machine-readable one was
  available).
* **The advice rules are editorial.** Each cites a source for the mechanism it
  invokes (venting, heating, shading, fogging), but the mapping from a
  classified state to one recommendation is this project's own, and the
  severity ranking is structural (both temperature and humidity out of band
  counts as critical), not taken from a source.
* **Nothing here validates a sensor.** The engine is exact on the inputs it is
  given. Instrument accuracy is a separate matter; readings outside the
  correlation range are stored unchanged and reported as not assessed, but
  drift, stale values and sudden jumps are not detected.
