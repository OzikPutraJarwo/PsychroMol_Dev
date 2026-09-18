import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { detect, extract, looksLikeTime, pointerOf, pressureUnitFor, resolve, segmentsOf, toNumber, toTime } from "../../frontend/js/fields.js";
import { near } from "./helpers.mjs";

const { cases } = JSON.parse(readFileSync(new URL("../fixtures/extraction-cases.json", import.meta.url), "utf8"));

test("every shared extraction case gives the expected reading", () => {
  assert.ok(cases.length >= 20);
  for (const { name, document, mapping, received_at: receivedAt, expected } of cases) {
    const { reading, errors } = extract(document, mapping, receivedAt);
    assert.deepEqual(errors.map((error) => error.field), expected.error_fields, name);
    assert.equal(reading.measured_at, expected.reading.measured_at, name);
    for (const key of ["temperature_c", "relative_humidity_percent", "pressure_kpa"]) {
      if (expected.reading[key] === null) assert.equal(reading[key], null, `${name} ${key}`);
      else near(reading[key], expected.reading[key], 1e-9, `${name} ${key}`);
    }
  }
});

test("the fields of the live source are recognised", () => {
  const found = detect({ timestamp: "2026-09-17T09:10:04Z", temperature: 27.0, humidity: 44.6 });
  assert.deepEqual(found.guess, { time: "/timestamp", temperature: "/temperature", humidity: "/humidity", pressure: null });
  assert.equal(found.numbers.length, 2);
  assert.equal(found.times.length, 1);
});

test("outdoor, dew-point and set-point values are never guessed as the greenhouse air", () => {
  const { guess } = detect({
    outdoor_temperature: 30,
    dew_point_temperature: 12,
    air_temp: 24,
    humidity_setpoint: 70,
    outside: { rh: 90 },
    rh: 65,
  });
  assert.equal(guess.temperature, "/air_temp");
  assert.equal(guess.humidity, "/rh");
});

test("a one-letter name only matches exactly, never as part of a longer name", () => {
  assert.equal(detect({ status: 21.5, date_time: "2026-09-17T09:10:04Z" }).guess.temperature, null);
  const { guess } = detect({ status: 1, t: 23, date_time: "2026-09-17T09:10:04Z" });
  assert.equal(guess.temperature, "/t");
  assert.equal(guess.time, "/date_time");
});

test("the pressure unit is inferred from the size of the value", () => {
  assert.equal(pressureUnitFor(101.3), "kPa");
  assert.equal(pressureUnitFor(1013.2), "hPa");
  assert.equal(pressureUnitFor(101325), "Pa");
  assert.equal(pressureUnitFor(5), null);
  const found = detect({ temperature: 20, humidity: 50, barometric_pressure: 1008.4 });
  assert.equal(found.guess.pressure, "/barometric_pressure");
  assert.equal(found.pressureUnit, "hPa");
});

test("time candidates are ISO texts or realistic epoch values, not ordinary numbers", () => {
  assert.equal(looksLikeTime("2026-09-17T09:10:04Z"), true);
  assert.equal(looksLikeTime(1789636204123), true);
  assert.equal(looksLikeTime("1789636204"), true);
  assert.equal(looksLikeTime(27), false);
  assert.equal(looksLikeTime("hello"), false);
  assert.equal(toTime("2026-13-01T00:00:00Z"), null);
  assert.equal(toTime("2026-09-17T24:00:00Z"), null);
  assert.equal(toTime(-5), null);
  assert.equal(toTime("1969-12-31T23:59:59Z"), null);
  assert.equal(toTime(1e16), null);
});

test("JSON Pointers escape and resolve per RFC 6901", () => {
  const segments = ["a/b", "m~n", 0];
  const pointer = pointerOf(segments);
  assert.equal(pointer, "/a~1b/m~0n/0");
  assert.deepEqual(segmentsOf(pointer), ["a/b", "m~n", "0"]);
  assert.equal(resolve({ "a/b": { "m~n": [7] } }, pointer), 7);
  const whole = { a: 1 };
  assert.equal(resolve(whole, ""), whole);
  assert.equal(resolve(whole, "/b"), undefined);
  assert.equal(resolve({ a: { b: 1 } }, "/a/b/c"), undefined);
  assert.equal(resolve({ a: [1, 2] }, "/a/2"), undefined);
  assert.throws(() => segmentsOf("a/b"));
});

test("numbers are read strictly", () => {
  assert.equal(toNumber(" 21.5 "), 21.5);
  assert.equal(toNumber("21,5"), 21.5);
  assert.equal(toNumber("abc21"), null);
  assert.equal(toNumber("1,234.5"), null);
  assert.equal(toNumber(Number.NaN), null);
  assert.equal(toNumber(false), null);
});
