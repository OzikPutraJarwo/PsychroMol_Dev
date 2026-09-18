import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import * as psy from "../../frontend/js/psychro.js";
import { near, nearRelative } from "./helpers.mjs";

const P = psy.STANDARD_PRESSURE_PA;

// ASHRAE Fundamentals 2017, Ch. 1: saturation pressures from Eq. 5/6; tolerance is the table's rounding
const SATURATION_TABLE = [
  [-60, 1.0817], [-40, 12.845], [-20, 103.26], [-10, 259.9], [-5, 401.76], [0, 611.21],
  [5, 872.49], [10, 1228.0], [15, 1705.4], [20, 2338.8], [25, 3169.2], [30, 4246.0],
  [35, 5627.8], [40, 7383.5], [45, 9593.1], [50, 12349.9], [60, 19943.8], [80, 47415.0],
  [100, 101418.0],
];

test("saturation vapour pressure matches the ASHRAE table", () => {
  for (const [t, expected] of SATURATION_TABLE) {
    nearRelative(psy.saturationVapourPressure(t), expected, 5e-4, `p_ws(${t})`);
  }
});

test("the saturation branch switches from ice to water at 0 °C", () => {
  near(psy.saturationVapourPressure(0), 611.213, 0.01);
  near(psy.saturationVapourPressureOverIce(0), 611.154, 0.01);
  assert.ok(psy.saturationVapourPressure(-0.001) < 611.213);
});

test("saturation pressure is strictly increasing over the whole range", () => {
  let previous = 0;
  for (let t = -100; t <= 200; t += 1) {
    const current = psy.saturationVapourPressure(t);
    assert.ok(current > previous, `not monotonic at ${t}`);
    previous = current;
  }
});

test("saturation temperature inverts saturation pressure", () => {
  for (const t of [-50, -10, 0, 12.5, 20, 37.3, 60, 120]) {
    near(psy.saturationTemperature(psy.saturationVapourPressure(t)), t, 1e-6);
  }
});

test("temperatures outside the correlation range are rejected", () => {
  assert.throws(() => psy.saturationVapourPressure(-100.001), psy.PsychrometricRangeError);
  assert.throws(() => psy.saturationVapourPressure(200.001), psy.PsychrometricRangeError);
  assert.throws(() => psy.saturationVapourPressure(Number.NaN), psy.PsychrometricRangeError);
});

// ASHRAE Fundamentals 2017, Ch. 1, Example 1: 40 °C dry bulb, 20 °C wet bulb, 101.325 kPa
test("ASHRAE worked Example 1 is reproduced to its printed precision", () => {
  const state = psy.stateFromTemperatureWetBulb(40, 20, P);
  near(state.humidityRatio, 0.0064, 5e-5, "W");
  near(state.enthalpy, 56.7, 0.1, "h");
  near(state.dewPoint, 7.4, 0.1, "t_d");
  near(state.relativeHumidity, 14.0, 0.2, "phi");
  near(state.specificVolume, 0.896, 0.001, "v");
});

// ASHRAE Fundamentals 2017, Ch. 1, Eq. 37/38: separate dew-point curve fits, about ±0.3 °C
function eq37(pwPa) {
  const kpa = pwPa / 1000;
  const alpha = Math.log(kpa);
  if (kpa > 0.61121) {
    return 6.54 + 14.526 * alpha + 0.7389 * alpha ** 2 + 0.09486 * alpha ** 3 + 0.4569 * kpa ** 0.1984;
  }
  return 6.09 + 12.608 * alpha + 0.4959 * alpha ** 2;
}

test("the dew point agrees with the independent ASHRAE Eq. 37/38 fit", () => {
  for (const t of [0, 10, 20, 25, 30, 40, 50]) {
    for (const rh of [20, 50, 80, 100]) {
      const w = psy.humidityRatioFromRelativeHumidity(t, rh, P);
      const pw = psy.vapourPressureFromHumidityRatio(w, P);
      near(psy.dewPointTemperature(pw), eq37(pw), 0.3, `${t} °C ${rh} %`);
    }
  }
});

const fixture = JSON.parse(
  readFileSync(new URL("../../data/reference/psychrolib-grid.json", import.meta.url), "utf8"),
);

test("every property agrees with PsychroLib across the reference grid", () => {
  for (const point of fixture.points) {
    const label = `${point.temperature_c} °C ${point.relative_humidity_percent} % ${point.pressure_pa} Pa`;
    const state = psy.stateFromTemperatureRelativeHumidity(
      point.temperature_c, point.relative_humidity_percent, point.pressure_pa,
    );
    near(state.humidityRatio, point.humidity_ratio_kg_kg, Math.max(point.humidity_ratio_kg_kg * 1e-3, 1e-9), `W ${label}`);
    near(state.dewPoint, point.dew_point_c, 5e-3, `t_d ${label}`);
    near(state.wetBulb, point.wet_bulb_c, 5e-3, `t_wb ${label}`);
    near(state.enthalpy, point.enthalpy_kj_kg, 5e-3, `h ${label}`);
    nearRelative(state.specificVolume, point.specific_volume_m3_kg, 1e-4, `v ${label}`);
    nearRelative(state.density, point.density_kg_m3, 1e-4, `rho ${label}`);
    near(state.vapourPressureDeficit, point.vapour_pressure_deficit_pa, 0.5, `VPD ${label}`);
  }
});

const benchmark = readFileSync(
  new URL("../../data/reference/external-tool-benchmark.csv", import.meta.url), "utf8",
).trim().split("\n").slice(1).map((line) => line.split(",").map((cell) => cell.replace(/"/g, "")));

test("the engine agrees with the earlier Magnus-based browser tool within its accuracy", () => {
  assert.ok(benchmark.length >= 5);
  for (const [, t, w, rh, twb, tdp, h, v, ah, rho] of benchmark) {
    const state = psy.stateFromTemperatureRelativeHumidity(Number(t), Number(rh), P);
    near(state.humidityRatio, Number(w), 5e-5, "W");
    near(state.wetBulb, Number(twb), 0.05, "t_wb");
    near(state.dewPoint, Number(tdp), 0.05, "t_d");
    near(state.enthalpy, Number(h), 0.15, "h");
    near(state.specificVolume, Number(v), 5e-4, "v");
    near(state.density, Number(rho), 5e-4, "rho");
    near(state.absoluteHumidity, Number(ah), 0.1, "AH");
  }
});

const ROUND_TRIPS = [[5, 90], [15, 60], [20, 50], [25, 75], [31.2, 72], [35, 20], [35, 85], [40, 99], [-5, 80]];

test("every inverse round-trips", () => {
  for (const [t, rh] of ROUND_TRIPS) {
    const w = psy.humidityRatioFromRelativeHumidity(t, rh, P);
    near(psy.relativeHumidityFromHumidityRatio(t, w, P), rh, 1e-9, "RH");
    const twb = psy.wetBulbTemperature(t, w, P);
    nearRelative(psy.humidityRatioFromWetBulb(t, twb, P), w, 1e-8, "wet bulb");
    const pw = psy.vapourPressureFromHumidityRatio(w, P);
    nearRelative(psy.saturationVapourPressure(psy.dewPointTemperature(pw)), pw, 1e-9, "dew point");
    const h = psy.enthalpy(t, w);
    nearRelative(psy.humidityRatioFromEnthalpy(t, h), w, 1e-9, "enthalpy W");
    near(psy.temperatureFromEnthalpy(h, w), t, 1e-9, "enthalpy t");
    near(psy.temperatureFromSpecificVolume(psy.specificVolume(t, w, P), w, P), t, 1e-9, "volume");
  }
});

test("the four state constructors agree", () => {
  for (const [t, rh] of ROUND_TRIPS) {
    const reference = psy.stateFromTemperatureRelativeHumidity(t, rh, P);
    for (const other of [
      psy.stateFromTemperatureDewPoint(t, reference.dewPoint, P),
      psy.stateFromTemperatureWetBulb(t, reference.wetBulb, P),
      psy.stateFromTemperatureHumidityRatio(t, reference.humidityRatio, P),
    ]) {
      nearRelative(other.humidityRatio, reference.humidityRatio, 1e-7);
      nearRelative(other.enthalpy, reference.enthalpy, 1e-7);
      near(other.vapourPressureDeficit, reference.vapourPressureDeficit, 1e-3);
    }
  }
});

test("dew point ≤ wet bulb ≤ dry bulb", () => {
  for (const [t, rh] of ROUND_TRIPS) {
    const state = psy.stateFromTemperatureRelativeHumidity(t, rh, P);
    assert.ok(state.dewPoint <= state.wetBulb + 1e-6);
    assert.ok(state.wetBulb <= state.temperature + 1e-6);
  }
});

test("saturated air collapses the three temperatures and VPD", () => {
  const state = psy.stateFromTemperatureRelativeHumidity(22, 100, P);
  near(state.dewPoint, 22, 1e-3);
  near(state.wetBulb, 22, 1e-3);
  near(state.vapourPressureDeficit, 0, 1e-6);
});

test("VPD rises with temperature at fixed RH and falls with RH at fixed temperature", () => {
  let previous = -1;
  for (let t = 10; t <= 40; t += 5) {
    const vpd = psy.stateFromTemperatureRelativeHumidity(t, 70, P).vapourPressureDeficit;
    assert.ok(vpd > previous);
    previous = vpd;
  }
  previous = Infinity;
  for (let rh = 10; rh <= 100; rh += 10) {
    const vpd = psy.stateFromTemperatureRelativeHumidity(25, rh, P).vapourPressureDeficit;
    assert.ok(vpd < previous);
    previous = vpd;
  }
});

test("the 20 °C / 50 % reference condition matches the Python engine it replaces", () => {
  const state = psy.stateFromTemperatureRelativeHumidity(20, 50, P);
  near(state.humidityRatio, 0.0072617, 1e-7);
  near(state.dewPoint, 9.27239, 1e-5);
  near(state.wetBulb, 13.78355, 1e-5);
  near(state.enthalpy, 38.55174, 1e-5);
  near(state.specificVolume, 0.8401563, 1e-7);
  near(state.vapourPressureDeficit / 1000, 1.169402, 1e-6);
  near(state.absoluteHumidity, 8.64332, 1e-5);
});

test("a measured relative humidity is carried exactly, so a band limit stays on the limit", () => {
  for (const rh of [0, 33.3, 60, 80, 100]) {
    const state = psy.stateFromTemperatureRelativeHumidity(28, rh, P);
    assert.equal(state.relativeHumidity, rh);
    assert.equal(state.vapourPressure, (psy.saturationVapourPressure(28) * rh) / 100);
  }
});

test("pressure changes the humidity ratio but not the dew point or VPD", () => {
  const sea = psy.stateFromTemperatureRelativeHumidity(25, 60, P);
  const high = psy.stateFromTemperatureRelativeHumidity(25, 60, 85000);
  assert.ok(high.humidityRatio > sea.humidityRatio);
  assert.ok(high.specificVolume > sea.specificVolume);
  near(high.dewPoint, sea.dewPoint, 1e-9);
  near(high.vapourPressureDeficit, sea.vapourPressureDeficit, 1e-6);
});

test("the standard atmosphere matches ASHRAE Eq. 3, and sea level is the default pressure", () => {
  assert.equal(psy.standardAtmosphericPressure(0), psy.STANDARD_PRESSURE_PA);
  nearRelative(psy.standardAtmosphericPressure(500), 95461, 1e-4);
  nearRelative(psy.standardAtmosphericPressure(1000), 89875, 1e-4);
  nearRelative(psy.standardAtmosphericPressure(2000), 79495, 1e-4);
});

test("a pressure given in kPa instead of Pa is refused", () => {
  assert.throws(() => psy.stateFromTemperatureRelativeHumidity(25, 60, 101.325), /not kPa/);
});

test("impossible inputs are refused", () => {
  assert.throws(() => psy.stateFromTemperatureRelativeHumidity(25, 101, P));
  assert.throws(() => psy.stateFromTemperatureRelativeHumidity(25, -0.1, P));
  assert.throws(() => psy.stateFromTemperatureWetBulb(20, 21, P));
  assert.throws(() => psy.stateFromTemperatureDewPoint(20, 21, P));
});

test("below freezing the dew point is a frost point and the wet bulb uses Eq. 35", () => {
  const cold = psy.stateFromTemperatureRelativeHumidity(-5, 70, P);
  assert.ok(cold.dewPoint < 0);
  nearRelative(psy.saturationVapourPressureOverIce(cold.dewPoint), cold.vapourPressure, 1e-9);
  assert.ok(psy.saturationVapourPressureOverWater(cold.dewPoint) > cold.vapourPressure * 1.05);
  const colder = psy.stateFromTemperatureRelativeHumidity(-8, 60, P);
  assert.ok(colder.wetBulb < 0);
  assert.ok(colder.dewPoint <= colder.wetBulb && colder.wetBulb <= colder.temperature);
});

test("the dew point and wet bulb are worked out only when they are read", () => {
  const state = psy.stateFromTemperatureRelativeHumidity(24, 70, P);
  assert.ok(Object.isFrozen(state));
  const first = state.wetBulb;
  assert.equal(state.wetBulb, first);
  const copy = JSON.parse(JSON.stringify(state));
  near(copy.dewPoint, state.dewPoint, 0);
  near(copy.wetBulb, first, 0);
});
