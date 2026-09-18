import assert from "node:assert/strict";

export function near(actual, expected, tolerance, label = "") {
  assert.ok(
    Math.abs(actual - expected) <= tolerance,
    `${label} expected ${expected} ± ${tolerance}, got ${actual}`,
  );
}

export function nearRelative(actual, expected, relative, label = "") {
  near(actual, expected, Math.abs(expected) * relative, label);
}
