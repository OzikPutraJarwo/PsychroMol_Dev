import assert from "node:assert/strict";
import { test } from "node:test";

import * as dss from "../../frontend/js/dss.js";
import * as psy from "../../frontend/js/psychro.js";
import { SOURCES } from "../../frontend/js/references.js";
import { near } from "./helpers.mjs";

const PROFILE = {
  crop_name: "Tomato",
  stage: "vegetative",
  temperature_min: 18,
  temperature_max: 28,
  temperature_reference: "Grower's own record",
  humidity_min: 60,
  humidity_max: 80,
  humidity_reference: "Grower's own record",
  vpd_min: null,
  vpd_max: null,
  vpd_reference: null,
  pressure_mode: "standard",
  pressure_kpa: null,
};

function reading(temperature, humidity, pressure = null) {
  return { measured_at: "2026-09-17T09:10:04.000Z", temperature_c: temperature, relative_humidity_percent: humidity, pressure_kpa: pressure };
}

test("the band limits count as inside the band", () => {
  assert.equal(dss.classify(18, 18, 28), "OPTIMAL");
  assert.equal(dss.classify(28, 18, 28), "OPTIMAL");
  assert.equal(dss.classify(17.99, 18, 28), "LOW");
  assert.equal(dss.classify(28.01, 18, 28), "HIGH");
});

test("every combination of states is answered by exactly one default rule", () => {
  const rules = dss.defaultRules();
  for (const temperature of dss.STATES) {
    for (const humidity of dss.STATES) {
      for (const vpd of dss.STATES) {
        const matched = rules.filter((rule) => dss.ruleMatches(rule, { temperature, humidity, vpd }));
        assert.equal(matched.length, 1, `${temperature} ${humidity} ${vpd}: ${matched.map((rule) => rule.name)}`);
      }
    }
  }
});

test("every default rule is valid and cites a known source", () => {
  const shorts = Object.values(SOURCES).map((source) => source.short);
  const rules = dss.defaultRules();
  assert.equal(new Set(rules.map((rule) => rule.priority)).size, rules.length);
  for (const rule of rules) {
    assert.deepEqual(dss.validateRule(rule), [], rule.name);
    assert.ok(shorts.some((short) => rule.reference.includes(short)), rule.name);
  }
});

test("each stage has a referenced default VPD band", () => {
  assert.deepEqual(dss.stageById("propagation").vpd, { min: 0.3, max: 0.5 });
  assert.deepEqual(dss.stageById("vegetative").vpd, { min: 0.2, max: 1.0 });
  assert.deepEqual(dss.stageById("flowering").vpd, { min: 0.2, max: 1.0 });
  for (const stage of dss.STAGES) {
    assert.ok(stage.citations.length > 0);
    assert.ok(stage.citations.every((citation) => citation.source in SOURCES));
  }
  assert.equal(dss.stageById("nonsense"), null);
});

test("a custom VPD band replaces the stage default only when both limits are set", () => {
  assert.equal(dss.vpdBand(PROFILE).custom, false);
  assert.equal(dss.vpdBand({ ...PROFILE, vpd_min: 0.5 }).custom, false);
  const custom = dss.vpdBand({ ...PROFILE, vpd_min: 0.5, vpd_max: 0.9, vpd_reference: "Own trial" });
  assert.deepEqual([custom.min, custom.max, custom.custom, custom.reference], [0.5, 0.9, true, "Own trial"]);
});

test("pressure comes from the profile's choice, in pascals", () => {
  assert.deepEqual(dss.pressureFor(PROFILE, reading(20, 50)), { pa: 101325, source: "standard" });
  assert.deepEqual(dss.pressureFor({ ...PROFILE, pressure_mode: "fixed", pressure_kpa: 90.5 }, reading(20, 50)), { pa: 90500, source: "fixed" });
  assert.deepEqual(dss.pressureFor({ ...PROFILE, pressure_mode: "field" }, reading(20, 50, 95.2)), { pa: 95200, source: "field" });
  assert.deepEqual(dss.pressureFor({ ...PROFILE, pressure_mode: "field" }, reading(20, 50)), { pa: 101325, source: "standard-fallback" });
});

test("a hot, humid reading is classified and answered", () => {
  const result = dss.assess(PROFILE, reading(30, 85), dss.defaultRules());
  near(result.values.vpd, (psy.saturationVapourPressure(30) * 0.15) / 1000, 1e-9);
  assert.deepEqual(result.classes, { temperature: "HIGH", humidity: "HIGH", vpd: "OPTIMAL" });
  assert.equal(result.label, "HOT + HUMID · OPTIMAL VPD");
  assert.equal(result.headline.name, "Hot and humid");
  assert.equal(result.headline.severity, "critical");
});

test("VPD alone can be out of its band while temperature and humidity are in theirs", () => {
  const result = dss.assess(PROFILE, reading(28, 60), dss.defaultRules());
  assert.deepEqual(result.classes, { temperature: "OPTIMAL", humidity: "OPTIMAL", vpd: "HIGH" });
  assert.equal(result.label, "OPTIMAL TEMPERATURE + OPTIMAL HUMIDITY · HIGH VPD");
  assert.equal(result.headline.name, "High VPD");
});

test("all three in their bands is OPTIMAL", () => {
  const result = dss.assess(PROFILE, reading(22, 75), dss.defaultRules());
  assert.equal(result.label, "OPTIMAL");
  assert.equal(result.headline.severity, "ok");
});

test("a reading the engine cannot use is reported, not guessed", () => {
  const result = dss.assess(PROFILE, reading(25, 100.4), dss.defaultRules());
  assert.equal(result.state, null);
  assert.match(result.error, /relative humidity/);
  assert.equal(dss.assess(PROFILE, null, []).error, "No reading yet.");
  assert.match(dss.assess({ ...PROFILE, stage: "nonsense" }, reading(22, 70), []).error, /stage/);
});

test("the worst severity leads, then the lowest order, and disabled rules never match", () => {
  const classes = { temperature: "HIGH", humidity: "HIGH", vpd: "LOW" };
  const rules = [
    { id: 1, name: "a", conditions: { temperature: "HIGH", humidity: "ANY", vpd: "ANY" }, severity: "warning", priority: 1 },
    { id: 2, name: "b", conditions: { temperature: "ANY", humidity: "HIGH", vpd: "ANY" }, severity: "critical", priority: 50 },
    { id: 3, name: "c", conditions: { temperature: "ANY", humidity: "ANY", vpd: "LOW" }, severity: "critical", priority: 20 },
    { id: 4, name: "d", conditions: { temperature: "HIGH", humidity: "HIGH", vpd: "LOW" }, severity: "critical", priority: 1, enabled: false },
  ];
  const ranked = dss.rank(rules.filter((rule) => dss.ruleMatches(rule, classes)));
  assert.deepEqual(ranked.map((rule) => rule.name), ["c", "b", "a"]);
});

test("a rule without a reference or with an unknown state is refused", () => {
  const good = dss.defaultRules()[0];
  assert.ok(dss.validateRule({ ...good, reference: "  " }).some((problem) => problem.includes("reference")));
  assert.ok(dss.validateRule({ ...good, conditions: { ...good.conditions, vpd: "MEDIUM" } }).length === 1);
  assert.ok(dss.validateRule({ ...good, severity: "urgent" }).length === 1);
  assert.ok(dss.validateRule({ ...good, priority: 1.5 }).length === 1);
});

test("the explanation shows the live numbers the result was built from", () => {
  const result = dss.assess({ ...PROFILE, pressure_mode: "fixed", pressure_kpa: 95 }, reading(24, 70), dss.defaultRules());
  const steps = dss.explain(result);
  const vpd = steps.find((step) => step.topic === "vpd");
  assert.equal(vpd.result, `${(result.state.vapourPressureDeficit / 1000).toFixed(3)} kPa`);
  assert.equal(steps.find((step) => step.topic === "pressure").result, "95.000 kPa");
  const classified = steps.filter((step) => step.group === "Classified");
  assert.deepEqual(classified.map((step) => step.result), ["OPTIMAL", "OPTIMAL", "OPTIMAL"]);
  assert.deepEqual(dss.explain(dss.assess(PROFILE, null, [])), []);
});
