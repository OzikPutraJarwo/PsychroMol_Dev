import { readFileSync } from "node:fs";

import * as psy from "../frontend/js/psychro.js";

const P = psy.STANDARD_PRESSURE_PA;
const failures = [];
const performed = [];

function record(label, ok) {
  performed.push(label);
  if (!ok) failures.push(label);
}

function check(label, actual, expected, tolerance, unit = "") {
  const deviation = Math.abs(actual - expected);
  const ok = deviation <= tolerance;
  record(label, ok);
  console.log(
    `  ${ok ? "PASS" : "FAIL"}  ${label.padEnd(46)} expected ${expected.toFixed(5).padStart(12)} ${unit.padEnd(8)} got ${actual.toFixed(5).padStart(12)}  Δ ${deviation.toExponential(2)}`,
  );
}

const rule = "=".repeat(92);
console.log(rule);
console.log("PsychroMol — psychrometric engine verification (frontend/js/psychro.js)");
console.log("ASHRAE Handbook — Fundamentals (2017), Chapter 1");
console.log(rule);

console.log("\n1. Saturation vapour pressure — ASHRAE Eq. (5)/(6)");
console.log("   Reference: values tabulated in ASHRAE Fundamentals Ch. 1  [tol 5e-4 rel]");
for (const [t, expected] of [[-40, 12.845], [-20, 103.26], [0, 611.21], [10, 1228.0], [20, 2338.8], [30, 4246.0], [40, 7383.5], [50, 12349.9]]) {
  check(`p_ws(${t >= 0 ? "+" : ""}${t} °C)`, psy.saturationVapourPressure(t), expected, expected * 5e-4, "Pa");
}

console.log("\n2. ASHRAE Ch. 1, worked Example 1 — 40 °C dry-bulb, 20 °C wet-bulb, 101.325 kPa");
const example = psy.stateFromTemperatureWetBulb(40, 20, P);
check("humidity ratio W", example.humidityRatio, 0.0064, 5e-5, "kg/kg");
check("enthalpy h", example.enthalpy, 56.7, 0.1, "kJ/kg");
check("dew point t_d", example.dewPoint, 7.4, 0.1, "°C");
check("relative humidity φ", example.relativeHumidity, 14.0, 0.2, "%");
check("specific volume v", example.specificVolume, 0.896, 0.001, "m³/kg");

console.log("\n3. Reference condition — 20 °C, 50 % RH, 101.325 kPa");
const reference = psy.stateFromTemperatureRelativeHumidity(20, 50, P);
check("humidity ratio W", reference.humidityRatio, 0.0072617, 1e-7, "kg/kg");
check("dew point t_d", reference.dewPoint, 9.27239, 1e-5, "°C");
check("wet bulb t*", reference.wetBulb, 13.78355, 1e-5, "°C");
check("enthalpy h", reference.enthalpy, 38.55174, 1e-5, "kJ/kg");
check("specific volume v", reference.specificVolume, 0.8401563, 1e-7, "m³/kg");
check("VPD", reference.vapourPressureDeficit / 1000, 1.169402, 1e-6, "kPa");

console.log("\n4. Independent formulation — ASHRAE Eq. (37)/(38) dew-point regressions");
console.log("   A separate correlation from the Eq. (5)/(6) inverse the engine uses.");
function eq37(pw) {
  const kpa = pw / 1000;
  const alpha = Math.log(kpa);
  if (kpa > 0.61121) {
    return 6.54 + 14.526 * alpha + 0.7389 * alpha ** 2 + 0.09486 * alpha ** 3 + 0.4569 * kpa ** 0.1984;
  }
  return 6.09 + 12.608 * alpha + 0.4959 * alpha ** 2;
}
let worst = 0;
for (let t = 0; t <= 50; t += 10) {
  for (const rh of [20, 50, 80, 100]) {
    const pw = psy.vapourPressureFromHumidityRatio(psy.humidityRatioFromRelativeHumidity(t, rh, P), P);
    worst = Math.max(worst, Math.abs(psy.dewPointTemperature(pw) - eq37(pw)));
  }
}
check("max |bisection − Eq. (37)| over 0–50 °C", worst, 0, 0.3, "K");

console.log("\n5. Independent implementation — PsychroLib 2.5.0 (data/reference/psychrolib-grid.json)");
const grid = JSON.parse(readFileSync(new URL("../data/reference/psychrolib-grid.json", import.meta.url), "utf8"));
let worstW = 0;
let worstDp = 0;
let worstWb = 0;
let worstH = 0;
let worstVpd = 0;
for (const point of grid.points) {
  const state = psy.stateFromTemperatureRelativeHumidity(point.temperature_c, point.relative_humidity_percent, point.pressure_pa);
  worstW = Math.max(worstW, Math.abs(state.humidityRatio - point.humidity_ratio_kg_kg) / Math.max(point.humidity_ratio_kg_kg, 1e-9));
  worstDp = Math.max(worstDp, Math.abs(state.dewPoint - point.dew_point_c));
  worstWb = Math.max(worstWb, Math.abs(state.wetBulb - point.wet_bulb_c));
  worstH = Math.max(worstH, Math.abs(state.enthalpy - point.enthalpy_kj_kg));
  worstVpd = Math.max(worstVpd, Math.abs(state.vapourPressureDeficit - point.vapour_pressure_deficit_pa));
}
console.log(`   ${grid.points.length} points`);
check("max relative deviation, humidity ratio", worstW, 0, 1e-3);
check("max deviation, dew point", worstDp, 0, 5e-3, "K");
check("max deviation, wet bulb", worstWb, 0, 5e-3, "K");
check("max deviation, enthalpy", worstH, 0, 5e-3, "kJ/kg");
check("max deviation, VPD", worstVpd, 0, 0.5, "Pa");

console.log("\n6. Internal consistency — inverses round-trip, ordering holds");
let worstRh = 0;
let worstWbRoundTrip = 0;
let worstDpRoundTrip = 0;
let orderingOk = true;
for (const [t, rh] of [[5, 90], [20, 50], [31.2, 72], [35, 20], [35, 85], [40, 99], [-5, 80]]) {
  const state = psy.stateFromTemperatureRelativeHumidity(t, rh, P);
  worstRh = Math.max(worstRh, Math.abs(psy.relativeHumidityFromHumidityRatio(t, state.humidityRatio, P) - rh));
  worstWbRoundTrip = Math.max(worstWbRoundTrip, Math.abs(psy.humidityRatioFromWetBulb(t, state.wetBulb, P) - state.humidityRatio));
  worstDpRoundTrip = Math.max(worstDpRoundTrip, Math.abs(psy.saturationVapourPressure(state.dewPoint) - state.vapourPressure));
  if (!(state.dewPoint <= state.wetBulb + 1e-6 && state.wetBulb <= state.temperature + 1e-6)) orderingOk = false;
}
check("RH round-trip", worstRh, 0, 1e-9, "%");
check("wet-bulb round-trip", worstWbRoundTrip, 0, 1e-10, "kg/kg");
check("dew-point round-trip", worstDpRoundTrip, 0, 1e-6, "Pa");
console.log(`  ${orderingOk ? "PASS" : "FAIL"}  t_dew ≤ t_wb ≤ t_db across all conditions`);
record("temperature ordering", orderingOk);

console.log("\n7. Pressure is a parameter, not an assumption");
const sea = psy.stateFromTemperatureRelativeHumidity(25, 60, P);
const high = psy.stateFromTemperatureRelativeHumidity(25, 60, 85000);
console.log(`  W at 101.325 kPa: ${sea.humidityRatio.toFixed(6)} kg/kg`);
console.log(`  W at  85.000 kPa: ${high.humidityRatio.toFixed(6)} kg/kg  (+${(100 * (high.humidityRatio / sea.humidityRatio - 1)).toFixed(1)} %)`);
check("dew point is pressure-independent", high.dewPoint, sea.dewPoint, 1e-9, "°C");
check("VPD is pressure-independent", high.vapourPressureDeficit / 1000, sea.vapourPressureDeficit / 1000, 1e-9, "kPa");
check("standard atmosphere at sea level, Eq. (3)", psy.standardAtmosphericPressure(0), 101325, 1e-9, "Pa");
check("standard atmosphere at 1000 m, Eq. (3)", psy.standardAtmosphericPressure(1000), 89875, 10, "Pa");

console.log(`\n${rule}`);
if (failures.length) {
  console.log(`RESULT: ${failures.length} of ${performed.length} CHECK(S) FAILED — ${failures.join(", ")}`);
  console.log("The engine must not be used until these are resolved.");
  process.exit(1);
}
console.log(`RESULT: ALL ${performed.length} CHECKS PASSED`);
console.log("Full record: docs/psychrometric-methodology.md");
console.log("Full suite:  node --test tests/js/");
console.log(rule);
