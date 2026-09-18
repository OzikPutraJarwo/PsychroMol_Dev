import assert from "node:assert/strict";
import { test } from "node:test";

import { CHART_RANGE, mollierChart, project, psychrometricChart, targetZone } from "../../frontend/js/geometry.js";
import * as psy from "../../frontend/js/psychro.js";
import { near } from "./helpers.mjs";

const P = psy.STANDARD_PRESSURE_PA;
const ZONE = { temperatureMin: 18, temperatureMax: 28, humidityMin: 60, humidityMax: 80 };

function family(geometry, name) {
  return geometry.curves.filter((curve) => curve.family === name);
}

test("the target zone is a closed polygon spanning exactly the temperature band", () => {
  const points = targetZone(ZONE, P, 0.05);
  assert.deepEqual(points[0], points[points.length - 1]);
  const temperatures = points.map(([t]) => t);
  assert.equal(Math.min(...temperatures), 18);
  assert.equal(Math.max(...temperatures), 28);
});

test("the target zone's edges are the relative-humidity curves it targets", () => {
  const points = targetZone(ZONE, P, 0.05);
  assert.deepEqual(points[0], [18, psy.humidityRatioFromRelativeHumidity(18, 80, P)]);
  const bottomRight = points[41];
  assert.deepEqual(bottomRight, [28, psy.humidityRatioFromRelativeHumidity(28, 60, P)]);
});

test("a degenerate temperature band gives no zone", () => {
  assert.deepEqual(targetZone({ ...ZONE, temperatureMax: 18 }, P, 0.05), []);
  assert.deepEqual(targetZone({ ...ZONE, temperatureMin: 30 }, P, 0.05), []);
});

test("without a band there is no zone, and with one it is drawn first", () => {
  assert.equal(family(psychrometricChart({ pressure: P }), "target_zone").length, 0);
  for (const build of [psychrometricChart, mollierChart]) {
    assert.equal(build({ pressure: P, zone: ZONE }).curves[0].family, "target_zone");
  }
});

test("psychrometric curves are in axis units and inside the axes", () => {
  const geometry = psychrometricChart({ pressure: P, zone: ZONE });
  assert.equal(geometry.y.max, CHART_RANGE.humidityRatioMax * 1000);
  for (const curve of geometry.curves) {
    for (const [x, y] of curve.points) {
      assert.ok(x >= geometry.x.min - 1e-9 && x <= geometry.x.max + 1e-9, `${curve.family} x ${x}`);
      assert.ok(y >= 0 && y <= geometry.y.max * 1.5 + 1e-9, `${curve.family} y ${y}`);
    }
  }
});

test("every chart line lies exactly on the quantity it is labelled with", () => {
  const geometry = psychrometricChart({ pressure: P });
  for (const curve of family(geometry, "relative_humidity")) {
    for (const [t, g] of curve.points) near(psy.relativeHumidityFromHumidityRatio(t, g / 1000, P), curve.value, 1e-9);
  }
  for (const curve of family(geometry, "enthalpy")) {
    for (const [t, g] of curve.points) near(psy.enthalpy(t, g / 1000), curve.value, 1e-9);
  }
  for (const curve of family(geometry, "wet_bulb")) {
    for (const [t, g] of curve.points) {
      near(psy.humidityRatioFromWetBulb(t, curve.value, P), g / 1000, 1e-12);
      if (curve.value !== 0) near(psy.wetBulbTemperature(t, g / 1000, P), curve.value, 1e-6);
    }
  }
  for (const curve of family(geometry, "specific_volume")) {
    for (const [t, g] of curve.points) near(psy.specificVolume(t, g / 1000, P), curve.value, 1e-9);
  }
  for (const [t, g] of family(geometry, "saturation")[0].points) {
    near(g / 1000, psy.saturationHumidityRatio(t, P), 1e-12);
  }
  assert.ok(family(geometry, "relative_humidity").length === 9);
  assert.ok(family(geometry, "enthalpy").length > 5);
  assert.ok(family(geometry, "wet_bulb").length > 5);
  assert.ok(family(geometry, "specific_volume").length > 5);
});

test("Mollier isotherms and isenthalps lie on their values", () => {
  const geometry = mollierChart({ pressure: P, zone: ZONE });
  for (const curve of family(geometry, "isotherm")) {
    for (const [g, y] of curve.points) {
      const w = g / 1000;
      near(psy.temperatureFromEnthalpy(y + psy.H_FG_0C * w, w), curve.value, 1e-9);
    }
  }
  for (const curve of family(geometry, "enthalpy")) {
    for (const [g, y] of curve.points) near(y + psy.H_FG_0C * (g / 1000), curve.value, 1e-9);
  }
  const zeroIsotherm = family(geometry, "isotherm").find((curve) => curve.value === 0);
  for (const [, y] of zeroIsotherm.points) near(y, 0, 1e-12);
  const zone = family(geometry, "target_zone")[0];
  for (const [x] of zone.points) assert.ok(x >= 0 && x <= 50);
  const ordinates = geometry.curves.flatMap((curve) => curve.points.map(([, y]) => y));
  assert.equal(geometry.y.min, Math.min(...ordinates));
  assert.equal(geometry.y.max, Math.max(...ordinates));
});

test("a state is projected onto the same coordinates the curves use", () => {
  const onCurve = family(psychrometricChart({ pressure: P }), "relative_humidity").find((curve) => curve.value === 70);
  const [sampleT, sampleG] = onCurve.points[75];
  const state = psy.stateFromTemperatureRelativeHumidity(sampleT, 70, P);
  const [t, g] = project("psychrometric", state.temperature, state.humidityRatio);
  assert.equal(t, sampleT);
  near(g, sampleG, 1e-9);
  const [x, y] = project("mollier", state.temperature, state.humidityRatio);
  near(x, g, 1e-12);
  near(y, state.enthalpy - psy.H_FG_0C * state.humidityRatio, 1e-12);
});

test("the chart follows the pressure it is drawn for", () => {
  const sea = family(psychrometricChart({ pressure: P }), "relative_humidity").find((curve) => curve.value === 50);
  const high = family(psychrometricChart({ pressure: 85000 }), "relative_humidity").find((curve) => curve.value === 50);
  assert.ok(high.points[40][1] > sea.points[40][1]);
  assert.throws(() => psychrometricChart({ pressure: 101.325 }), /not kPa/);
});

test("at a 0 °C wet bulb the ASHRAE water and ice equations disagree, exactly as in PsychroLib", () => {
  for (const [t, psychrolib] of [[0.5, -0.0351], [1, -0.0704], [2, -0.1406], [5, -0.3529]]) {
    const w = psy.humidityRatioFromWetBulb(t, 0, P);
    assert.ok(psy.humidityRatioFromWetBulb(t, -1e-9, P) > w);
    near(psy.wetBulbTemperature(t, w, P), psychrolib, 1e-3, `t ${t}`);
  }
});
