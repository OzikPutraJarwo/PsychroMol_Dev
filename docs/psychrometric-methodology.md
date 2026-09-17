# Psychrometric formulation and verification record

This document is the scientific basis for every number PsychroMol reports. It
names each equation, its source, its assumptions, its validity range, and the
test that defends it. Nothing here is "ASHRAE-based" because it looks
plausible — each claim is backed by an executable test.

**Primary reference:** ASHRAE Handbook — Fundamentals (2017), Chapter 1,
*Psychrometrics*. Equation numbers below refer to that chapter.
**Implementation:** [psychromol/core/psychrometrics.py](../psychromol/core/psychrometrics.py)
**Verification:** [tests/test_psychrometrics.py](../tests/test_psychrometrics.py),
[tests/test_external_benchmark.py](../tests/test_external_benchmark.py)

---

## 1. Unit conventions

| Quantity | Symbol | Engine unit | API / UI unit |
|---|---|---|---|
| Dry-bulb temperature | `t` | °C | °C |
| Wet-bulb temperature | `t*` | °C | °C |
| Dew-point temperature | `t_d` | °C | °C |
| Total (atmospheric) pressure | `p` | **Pa** | **kPa** |
| Partial vapour pressure | `p_w` | **Pa** | **kPa** |
| Saturation vapour pressure | `p_ws` | **Pa** | **kPa** |
| Humidity ratio | `W` | kg/kg dry air | kg/kg **and** g/kg |
| Relative humidity | `φ` | % | % |
| Specific enthalpy | `h` | kJ/kg dry air | kJ/kg dry air |
| Specific volume | `v` | m³/kg dry air | m³/kg dry air |
| Moist-air density | `ρ` | kg/m³ | kg/m³ |
| Vapour-pressure deficit | VPD | **Pa** | **kPa** |
| Absolute humidity | AH | g/m³ | g/m³ |

The engine works in **pascal** because ASHRAE's saturation correlations are
written in Pa. Conversion to kPa happens in exactly one place —
`MoistAirState.to_api_dict()` — via `psychromol/core/units.py`. No other code
applies a pressure scale factor. Every API field name carries its unit as a
suffix (`vpd_kpa`, `pressure_kpa`, `humidity_ratio_g_kg`) so a unit can never
be inferred wrongly from context.

**Guard:** `test_pressure_in_kilopascal_is_rejected` — passing 101.325 where
101 325 was meant raises rather than producing plausible-looking numbers.

---

## 2. Constants

Defined once, in [psychromol/core/constants.py](../psychromol/core/constants.py).

| Constant | Value | Source |
|---|---|---|
| `MW_RATIO` | 0.621945 | `M_w / M_da` = 18.015268 / 28.966 |
| `SPECIFIC_VOLUME_W_COEFF` | 1.607858 | `1 / MW_RATIO`, as printed in Eq. (26) |
| `R_DRY_AIR` | 287.042 J/(kg·K) | Eq. (26) (ASHRAE prints 0.287042 kJ/(kg·K)) |
| `CP_DRY_AIR` | 1.006 kJ/(kg·K) | Eq. (30) |
| `CP_WATER_VAPOUR` | 1.86 kJ/(kg·K) | Eq. (30) |
| `CP_LIQUID_WATER` | 4.186 kJ/(kg·K) | Eq. (33) |
| `CP_ICE` | 2.1 kJ/(kg·K) | Eq. (34) |
| `H_FG_0C` | 2501 kJ/kg | Latent heat of vaporisation at 0 °C, Eq. (30) |
| `H_IG_0C` | 2830 kJ/kg | Latent heat of sublimation at 0 °C, Eq. (34) |
| `STANDARD_PRESSURE_PA` | 101 325 Pa | Eq. (3) at Z = 0 — **a default, not an assumption** |

---

## 3. Equations implemented

| # | Quantity | ASHRAE Eq. | Form | Validity |
|---|---|---|---|---|
| 1 | Saturation vapour pressure over ice | (5) | `ln p_ws = C1/T + C2 + C3T + C4T² + C5T³ + C6T⁴ + C7 ln T` | −100…0 °C |
| 2 | Saturation vapour pressure over water | (6) | `ln p_ws = C8/T + C9 + C10T + C11T² + C12T³ + C13 ln T` | 0…200 °C |
| 3 | Humidity ratio | (20) | `W = 0.621945 p_w / (p − p_w)` | `p_w < p` |
| 4 | Vapour pressure | (20) rearranged | `p_w = p W / (0.621945 + W)` | `W ≥ 0` |
| 5 | Relative humidity | (12) | `φ = p_w / p_ws` | 0…100 % |
| 6 | Degree of saturation | (12) | `μ = W / W_s` | — |
| 7 | Dew point | inverse of (5)/(6) | numerical | `p_w > 0` |
| 8 | Humidity ratio from wet bulb, above freezing | (33) | `W = ((2501 − 2.326t*)W_s* − 1.006(t − t*)) / (2501 + 1.86t − 4.186t*)` | `t* ≥ 0 °C` |
| 9 | Humidity ratio from wet bulb, below freezing | (34) | `W = ((2830 − 0.24t*)W_s* − 1.006(t − t*)) / (2830 + 1.86t − 2.1t*)` | `t* < 0 °C` |
| 10 | Wet-bulb temperature | inverse of (33)/(34) | numerical | `t_d ≤ t* ≤ t` |
| 11 | Specific enthalpy | (30) | `h = 1.006t + W(2501 + 1.86t)` | — |
| 12 | Specific volume | (26) | `v = R_da(t + 273.15)(1 + 1.607858W)/p` | — |
| 13 | Moist-air density | (11) | `ρ = (1 + W)/v` | — |
| 14 | Standard atmosphere | (3) | `p = 101325(1 − 2.25577e−5 Z)^5.2559` | 0…11 000 m |
| 15 | Vapour-pressure deficit | — (definition) | `VPD = p_ws(t) − p_w` | see §5 |
| 16 | Absolute humidity | — (definition) | `AH = 1000 W / v` | — |

---

## 4. Documented assumptions (brief §59)

Every assumption below is a deliberate choice with a stated reason. None is
hidden in code.

### 4.1 Default pressure is the sea-level standard atmosphere
`STANDARD_PRESSURE_PA = 101 325 Pa` is used **only when no pressure is
supplied**. Every relation that depends on pressure takes it as an argument.
An installation should configure either a measured barometric pressure or
`PSYCHROMOL_ALTITUDE_M`, from which Eq. (3) gives a physically sensible value.

*Consequence if ignored:* at 500 m the true pressure is ~95.5 kPa; assuming sea
level overstates the humidity ratio by ~6 %. Dew point and VPD are unaffected
(they depend only on `t` and `φ`) — which is one reason the DSS leans on VPD
and dew-point depression rather than on `W` alone.
**Test:** `test_pressure_changes_the_state`, `test_standard_atmosphere_matches_ashrae_table`.

### 4.2 Below 0 °C the saturation curve is taken over ice
ASHRAE switches from Eq. (6) to Eq. (5) at 0 °C. This project follows that
convention, so the reported "dew point" below freezing is strictly a **frost
point** — the temperature at which vapour deposits on a cold surface. For
greenhouse condensation risk on glazing, that is the physically correct
quantity. `dew_point_over_water()` provides the supercooled-water convention
where meteorological comparison requires it. At exactly 0 °C the water branch is
taken (611.21 Pa), the conventional value.
**Test:** `test_saturation_pressure_branch_switch_at_zero_celsius`,
`test_dew_point_below_freezing_uses_the_ice_branch`.

### 4.3 Inverses are solved numerically, not by curve fit
ASHRAE Eq. (37)/(38) are convenience fits for the dew point, accurate to about
±0.3 °C. This engine instead inverts Eq. (5)/(6) by bisection, so
`t_d → p_w → t_d` closes to 1e-6 °C. Eq. (37)/(38) are retained **in the test
suite** as an independent formulation to compare against — the only role they
can play without degrading the result.
**Test:** `test_dew_point_agrees_with_ashrae_curve_fit` (max observed deviation
0.032 K, well inside ASHRAE's stated ±0.3 °C).

### 4.4 Bisection, not Newton–Raphson
The correlations are cheap; the brackets are known a priori (`[t_d, t]` for the
wet bulb, `[−100, 200]` for the saturation inverse); and bisection cannot
diverge. This code runs unattended against live sensor data, where a diverging
solver is a silent data-quality failure. Tolerance 1e-10 on the bracket,
cap 200 iterations — the cap is never the binding constraint.

### 4.5 Wet-bulb bracket starts at the dew point
The lower bracket for the wet-bulb solve is the dew point, not a fixed
constant. A fixed lower bound (the earlier browser tool used −20 °C) fails to
bracket the root for cold or very dry air.
**Test:** `test_wet_bulb_round_trips` including the −5 °C/80 % and −8 °C/60 %
cases; `test_wet_bulb_below_freezing_uses_equation_34`.

### 4.6 Relative humidity is clamped to 100 % in the evaluated state
Sensor noise and rounding can put `p_w` a hair above `p_ws`. The evaluated
state clamps `φ` at 100 % so downstream physics stays consistent. **The raw
reading is never altered** — it is stored verbatim, and the quality layer flags
it (`RH_ABOVE_SATURATION`). Clamping the derived value and flagging the raw one
are different acts and the system does both.

### 4.7 VPD is air VPD, not leaf-to-air VPD
`VPD = p_ws(t_air) − p_w`, evaluated at **air** temperature. Much
plant-physiology literature uses leaf-to-air VPD, which substitutes leaf
temperature into the saturation term and can differ substantially under high
radiation. PsychroMol does not measure or model leaf temperature and therefore
**does not report that quantity**. Any thesis text using these VPD values must
say "air VPD".

### 4.8 Correlation range is enforced, not extrapolated
Inputs outside −100…200 °C, outside 0…100 % RH, or outside 20…200 kPa raise
`PsychrometricRangeError`. The ingestion layer catches it and flags the reading
`INVALID` rather than storing a plausible-looking extrapolation.

### 4.9 Enthalpy datum
Dry air and liquid water, both at 0 °C (ASHRAE's datum). Enthalpy is therefore
**pressure-independent** — worth stating because Mollier charts are drawn for a
nominal pressure and the two facts are easily conflated.

---

## 5. Validation results

Run: `.venv/bin/python -m pytest tests/test_psychrometrics.py tests/test_external_benchmark.py -q`
Status at last run: **221 passed, 0 failed.**

### 5.1 Source 1 — ASHRAE saturation-pressure table

19 tabulated points, −60…100 °C, tolerance 5 × 10⁻⁴ relative (the table's own
rounding). All pass.

| t (°C) | ASHRAE `p_ws` (Pa) | Engine (Pa) |
|---|---|---|
| −40 | 12.845 | 12.8404 |
| 0 | 611.21 | 611.213 |
| 20 | 2338.8 | 2338.80 |
| 30 | 4246.0 | 4246.03 |
| 50 | 12349.9 | 12349.9 |

### 5.2 Source 2 — ASHRAE Ch. 1, worked Example 1

Moist air at **40 °C dry-bulb, 20 °C wet-bulb, 101.325 kPa**:

| Quantity | ASHRAE printed | PsychroMol | Deviation |
|---|---|---|---|
| Humidity ratio `W` | 0.0064 kg/kg | 0.006401 | < 1 × 10⁻⁶ |
| Enthalpy `h` | 56.7 kJ/kg | 56.725 | 0.025 |
| Dew point `t_d` | 7.4 °C | 7.434 | 0.034 K |
| Relative humidity `φ` | 14 % | 13.98 % | 0.02 |
| Specific volume `v` | 0.896 m³/kg | 0.8962 | 0.0002 |

### 5.3 Source 3 — `psychrolib` (independent ASHRAE implementation)

77-point grid, −10…50 °C × 5…100 % RH, plus four pressures 85…105 kPa.
Maximum observed deviations:

| Quantity | Max deviation | Test tolerance |
|---|---|---|
| Humidity ratio | 9.8 × 10⁻⁵ relative | 1 × 10⁻³ rel |
| Dew point | 1.2 × 10⁻³ K | 5 × 10⁻³ K |
| Wet bulb | 6.6 × 10⁻⁴ K | 5 × 10⁻³ K |
| Enthalpy | 9.2 × 10⁻⁴ kJ/kg | 5 × 10⁻³ |
| Specific volume | 4.6 × 10⁻⁷ m³/kg | 1 × 10⁻⁴ rel |

The residual is the two libraries' differing solver tolerances, not a
formulation difference. `psychrolib` is a **development dependency only** and
is never imported at runtime.

### 5.4 Source 4 — independent third-party tool export

8 points, 17.8…44.6 °C. Maximum deviations: `W` 4.5 × 10⁻⁵ kg/kg, `t*` 0.023 K,
`t_d` 0.034 K, `h` 0.122 kJ/kg, `v` 7 × 10⁻⁵ m³/kg. These sit within that
tool's Magnus-formulation offset (~0.4 % on `p_ws`) and its printed precision.

### 5.5 Source 5 — internal consistency

Nine representative conditions spanning the brief's required cases —
cold/humid (5 °C/90 %), moderate (20 °C/50 %), hot/dry (35 °C/20 %), hot/humid
(35 °C/85 %), near-saturation (40 °C/99 %), sub-freezing (−5 °C/80 %) — each
verified for:

* RH, wet-bulb, dew-point, enthalpy and specific-volume round-trips;
* agreement between all four state constructors (t+RH, t+t_d, t+t*, t+W);
* the ordering `t_d ≤ t* ≤ t`;
* saturation collapsing all three temperatures and driving VPD to zero;
* VPD rising with temperature at fixed RH and falling with RH at fixed
  temperature.

Plus strict monotonicity of `p_ws` over the full −100…200 °C range, checked at
every degree.

---

## 6. What is *not* validated

Stated plainly, because the brief requires honesty about limits:

* **Above 60 °C and below −20 °C** the engine is exercised only against the
  correlations themselves and `psychrolib`, not against tabulated values at
  every point. Greenhouse work never reaches there.
* **Pressures far from 1 atm** are cross-checked against `psychrolib` at four
  values between 85 and 105 kPa only.
* **The Mollier projection** is a coordinate transform of already-verified
  quantities; it is tested for self-consistency and invertibility, not against
  a published h-x chart (no machine-readable one was available).
* **Nothing here validates a sensor.** The engine is exact on the inputs it is
  given. Instrument accuracy is a separate matter, handled — as far as software
  can — by `psychromol/quality/`.
