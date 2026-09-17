
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from psychromol.core import psychrometrics as psy
from psychromol.core import state as st
from psychromol.core.constants import STANDARD_PRESSURE_PA

P = STANDARD_PRESSURE_PA
failures: list[str] = []
performed: list[str] = []

def record(label: str, ok: bool) -> None:
    performed.append(label)
    if not ok:
        failures.append(label)

def check(label: str, actual: float, expected: float, tolerance: float, unit: str = "") -> None:
    deviation = abs(actual - expected)
    ok = deviation <= tolerance
    record(label, ok)
    print(
        f"  {'PASS' if ok else 'FAIL'}  {label:<46s} "
        f"expected {expected:>12.5f} {unit:<8s} got {actual:>12.5f}  "
        f"Δ {deviation:.2e}"
    )

print("=" * 92)
print("PsychroMol — psychrometric engine verification")
print("ASHRAE Handbook — Fundamentals (2017), Chapter 1")
print("=" * 92)

print("\n1. Saturation vapour pressure — ASHRAE Eq. (5)/(6), Hyland–Wexler")
print("   Reference: values tabulated in ASHRAE Fundamentals Ch. 1  [tol 5e-4 rel]")
for temperature, expected in [
    (-40.0, 12.845), (-20.0, 103.26), (0.0, 611.21), (10.0, 1228.0),
    (20.0, 2338.8), (30.0, 4246.0), (40.0, 7383.5), (50.0, 12349.9),
]:
    check(
        f"p_ws({temperature:+.0f} °C)",
        psy.saturation_vapour_pressure(temperature),
        expected,
        expected * 5e-4,
        "Pa",
    )

print("\n2. ASHRAE Ch. 1, worked Example 1 — 40 °C dry-bulb, 20 °C wet-bulb, 101.325 kPa")
example = st.from_temperature_wet_bulb(40.0, 20.0, P)
check("humidity ratio W", example.humidity_ratio, 0.0064, 5e-5, "kg/kg")
check("enthalpy h", example.enthalpy, 56.7, 0.1, "kJ/kg")
check("dew point t_d", example.dew_point, 7.4, 0.1, "°C")
check("relative humidity φ", example.relative_humidity, 14.0, 0.2, "%")
check("specific volume v", example.specific_volume, 0.896, 0.001, "m³/kg")

print("\n3. Reference condition — 20 °C, 50 % RH, 101.325 kPa")
reference = st.from_temperature_relative_humidity(20.0, 50.0, P)
check("humidity ratio W", reference.humidity_ratio, 0.0072617, 1e-7, "kg/kg")
check("dew point t_d", reference.dew_point, 9.27239, 1e-5, "°C")
check("wet bulb t*", reference.wet_bulb, 13.78355, 1e-5, "°C")
check("enthalpy h", reference.enthalpy, 38.55174, 1e-5, "kJ/kg")
check("specific volume v", reference.specific_volume, 0.8401563, 1e-7, "m³/kg")
check("VPD", reference.vpd_kpa, 1.169402, 1e-6, "kPa")

print("\n4. Independent formulation — ASHRAE Eq. (37) dew-point curve fit")
print("   A separate correlation from the Eq. (5)/(6) inverse the engine uses.")
print("   ASHRAE quotes Eq. (37) as accurate to about ±0.3 °C.")

def eq37(p_w_pa: float) -> float:
    p_kpa = p_w_pa / 1000.0
    alpha = math.log(p_kpa)
    if p_kpa > 0.61121:
        return (6.54 + 14.526 * alpha + 0.7389 * alpha**2
                + 0.09486 * alpha**3 + 0.4569 * p_kpa**0.1984)
    return 6.09 + 12.608 * alpha + 0.4959 * alpha**2

worst = 0.0
for temperature in range(0, 51, 10):
    for humidity in (20.0, 50.0, 80.0, 100.0):
        w = psy.humidity_ratio_from_relative_humidity(float(temperature), humidity, P)
        p_w = psy.vapour_pressure_from_humidity_ratio(w, P)
        worst = max(worst, abs(psy.dew_point_temperature(p_w) - eq37(p_w)))
check("max |bisection − Eq. (37)| over 0–50 °C", worst, 0.0, 0.3, "K")

print("\n5. Independent implementation — psychrolib")
try:
    import psychrolib

    psychrolib.SetUnitSystem(psychrolib.SI)
    worst_w = worst_dp = worst_wb = worst_h = 0.0
    for temperature in (-10.0, 0.0, 10.0, 20.0, 30.0, 40.0, 50.0):
        for humidity in (5.0, 30.0, 60.0, 90.0, 100.0):
            state = st.from_temperature_relative_humidity(temperature, humidity, P)
            w = psychrolib.GetHumRatioFromRelHum(temperature, humidity / 100.0, P)
            worst_w = max(worst_w, abs(state.humidity_ratio - w) / max(w, 1e-9))
            worst_dp = max(worst_dp, abs(
                state.dew_point - psychrolib.GetTDewPointFromRelHum(temperature, humidity / 100.0)))
            worst_wb = max(worst_wb, abs(
                state.wet_bulb - psychrolib.GetTWetBulbFromRelHum(temperature, humidity / 100.0, P)))
            worst_h = max(worst_h, abs(
                state.enthalpy - psychrolib.GetMoistAirEnthalpy(temperature, w) / 1000.0))
    check("max relative deviation, humidity ratio", worst_w, 0.0, 1e-3)
    check("max deviation, dew point", worst_dp, 0.0, 5e-3, "K")
    check("max deviation, wet bulb", worst_wb, 0.0, 5e-3, "K")
    check("max deviation, enthalpy", worst_h, 0.0, 5e-3, "kJ/kg")
except ImportError:
    print("  SKIP  psychrolib not installed (verification aid only, not a runtime dependency)")

print("\n6. Internal consistency — inverses round-trip, ordering holds")
conditions = [
    (5.0, 90.0), (20.0, 50.0), (31.2, 72.0), (35.0, 20.0), (35.0, 85.0),
    (40.0, 99.0), (-5.0, 80.0),
]
worst_rh = worst_wb_rt = worst_dp_rt = 0.0
ordering_ok = True
for temperature, humidity in conditions:
    state = st.from_temperature_relative_humidity(temperature, humidity, P)
    worst_rh = max(worst_rh, abs(
        psy.relative_humidity_from_humidity_ratio(temperature, state.humidity_ratio, P) - humidity))
    worst_wb_rt = max(worst_wb_rt, abs(
        psy.humidity_ratio_from_wet_bulb(temperature, state.wet_bulb, P) - state.humidity_ratio))
    worst_dp_rt = max(worst_dp_rt, abs(
        psy.saturation_vapour_pressure(state.dew_point) - state.vapour_pressure))
    if not (state.dew_point <= state.wet_bulb + 1e-6 <= state.temperature + 1e-6):
        ordering_ok = False

check("RH round-trip", worst_rh, 0.0, 1e-9, "%")
check("wet-bulb round-trip", worst_wb_rt, 0.0, 1e-10, "kg/kg")
check("dew-point round-trip", worst_dp_rt, 0.0, 1e-6, "Pa")
print(f"  {'PASS' if ordering_ok else 'FAIL'}  t_dew ≤ t_wb ≤ t_db across all conditions")
record("temperature ordering", ordering_ok)

print("\n7. Pressure is a parameter, not an assumption")
sea = st.from_temperature_relative_humidity(25.0, 60.0, P)
high = st.from_temperature_relative_humidity(25.0, 60.0, 85000.0)
print(f"  W at 101.325 kPa: {sea.humidity_ratio:.6f} kg/kg")
print(f"  W at  85.000 kPa: {high.humidity_ratio:.6f} kg/kg  "
      f"({100 * (high.humidity_ratio / sea.humidity_ratio - 1):+.1f} %)")
check("dew point is pressure-independent", high.dew_point, sea.dew_point, 1e-9, "°C")
check("VPD is pressure-independent", high.vpd_kpa, sea.vpd_kpa, 1e-9, "kPa")
check("standard atmosphere at 1000 m", psy.standard_atmospheric_pressure(1000.0),
      89875.0, 10.0, "Pa")

print("\n" + "=" * 92)
if failures:
    print(f"RESULT: {len(failures)} of {len(performed)} CHECK(S) FAILED — "
          f"{', '.join(failures)}")
    print("The engine must not be used until these are resolved.")
    sys.exit(1)

print(f"RESULT: ALL {len(performed)} CHECKS PASSED")
print("Full record: docs/psychrometric-methodology.md")
print("Full suite:  .venv/bin/python -m pytest tests/ -q")
print("=" * 92)
