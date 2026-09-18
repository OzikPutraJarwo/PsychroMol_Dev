import { PRESSURE_UNITS, kpaFrom } from "./units.js";

const NUMBER_TEXT = /^\s*([+-]?[0-9]+(?:[.,][0-9]+)?)\s*[^0-9\s.,+-]*\s*$/;
const ISO_TIME = /^([0-9]{4})-([0-9]{2})-([0-9]{2})(?:[Tt ]([0-9]{2}):([0-9]{2})(?::([0-9]{2})(?:[.,]([0-9]+))?)?)?\s*([Zz]|[+-][0-9]{2}(?::?[0-9]{2})?)?$/;
const EPOCH_TEXT = /^[0-9]{10,}(?:\.[0-9]+)?$/;
const EPOCH_MILLISECONDS_ABOVE = 1e11;
const PLAUSIBLE_EPOCH = [1e9, 1e13];
const EARLIEST_YEAR = 1970;
const LATEST_YEAR = 9999;

const TIME_NAMES = ["timestamp", "time", "datetime", "date_time", "measured_at", "recorded_at", "created_at", "ts", "date"];
const TEMPERATURE_NAMES = ["temperature", "temp", "temperature_c", "temp_c", "air_temperature", "t"];
const HUMIDITY_NAMES = ["relative_humidity", "humidity", "rh", "hum", "humidity_percent", "relative_humidity_percent", "rh_percent"];
const PRESSURE_NAMES = ["pressure", "pressure_kpa", "pressure_hpa", "pressure_pa", "air_pressure", "atmospheric_pressure", "barometric_pressure", "baro", "p"];
const NOT_GREENHOUSE_AIR = ["outdoor", "outside", "external", "surface", "soil", "substrate", "leaf", "water", "dew", "wet", "setpoint", "target"];

export const MAPPED_FIELDS = ["time", "temperature", "humidity", "pressure"];

function escapeSegment(segment) {
  return String(segment).replace(/~/g, "~0").replace(/\//g, "~1");
}

function unescapeSegment(segment) {
  return segment.replace(/~1/g, "/").replace(/~0/g, "~");
}

export function pointerOf(segments) {
  return segments.map((segment) => `/${escapeSegment(segment)}`).join("");
}

export function segmentsOf(pointer) {
  if (pointer === "") return [];
  if (!pointer.startsWith("/")) throw new Error(`a JSON Pointer starts with "/", got ${pointer}`);
  return pointer.slice(1).split("/").map(unescapeSegment);
}

export function resolve(document, pointer) {
  let current = document;
  for (const segment of segmentsOf(pointer)) {
    if (Array.isArray(current)) {
      if (!/^(0|[1-9]\d*)$/.test(segment)) return undefined;
      current = current[Number(segment)];
    } else if (current !== null && typeof current === "object") {
      if (!Object.prototype.hasOwnProperty.call(current, segment)) return undefined;
      current = current[segment];
    } else {
      return undefined;
    }
    if (current === undefined) return undefined;
  }
  return current;
}

export function toNumber(value) {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value !== "string") return null;
  const match = NUMBER_TEXT.exec(value);
  return match ? Number(match[1].replace(",", ".")) : null;
}

function fromEpoch(number) {
  if (!(number > 0)) return null;
  const milliseconds = number > EPOCH_MILLISECONDS_ABOVE ? number : number * 1000;
  const moment = new Date(Math.floor(milliseconds));
  return Number.isNaN(moment.getTime()) || moment.getUTCFullYear() > LATEST_YEAR ? null : moment;
}

export function toTime(value) {
  if (typeof value === "number") return Number.isFinite(value) ? fromEpoch(value) : null;
  if (typeof value !== "string") return null;
  const text = value.trim();
  if (EPOCH_TEXT.test(text)) return fromEpoch(Number(text));
  const match = ISO_TIME.exec(text);
  if (!match) return null;
  const [, year, month, day, hour = "0", minute = "0", second = "0", fraction = "", zone] = match;
  if (Number(year) < EARLIEST_YEAR) return null;
  const milliseconds = Number(fraction.padEnd(3, "0").slice(0, 3));
  let stamp = Date.UTC(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute), Number(second), milliseconds);
  const check = new Date(stamp);
  if (
    check.getUTCFullYear() !== Number(year) || check.getUTCMonth() !== Number(month) - 1 || check.getUTCDate() !== Number(day)
    || Number(hour) > 23 || Number(minute) > 59 || Number(second) > 59
  ) return null;
  if (zone && zone.toUpperCase() !== "Z") {
    const sign = zone[0] === "-" ? -1 : 1;
    const digits = zone.slice(1).replace(":", "");
    const offset = Number(digits.slice(0, 2)) * 60 + Number(digits.slice(2) || "0");
    stamp -= sign * offset * 60000;
  }
  return new Date(stamp);
}

export function flatten(document) {
  const leaves = [];
  const walk = (value, segments) => {
    if (Array.isArray(value)) {
      value.forEach((item, index) => walk(item, [...segments, index]));
    } else if (value !== null && typeof value === "object") {
      for (const [key, item] of Object.entries(value)) walk(item, [...segments, key]);
    } else {
      leaves.push({ pointer: pointerOf(segments), segments, value });
    }
  };
  walk(document, []);
  return leaves;
}

function normalise(name) {
  return String(name).toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
}

function nameScore(segments, names) {
  const key = normalise(segments[segments.length - 1] ?? "");
  const path = normalise(segments.join("_"));
  if (NOT_GREENHOUSE_AIR.some((word) => path.split("_").includes(word))) return 0;
  if (names.includes(key)) return 3;
  const words = key.split("_");
  if (names.some((name) => words.includes(name) && name.length >= 3)) return 2;
  if (names.some((name) => name.length >= 3 && key.includes(name))) return 1;
  return 0;
}

function best(leaves, names, accept) {
  let chosen = null;
  let score = 0;
  for (const leaf of leaves) {
    if (!accept(leaf.value)) continue;
    const candidate = nameScore(leaf.segments, names);
    if (candidate > score) {
      chosen = leaf.pointer;
      score = candidate;
    }
  }
  return chosen;
}

export function pressureUnitFor(value) {
  if (value >= 20 && value <= 200) return "kPa";
  if (value > 200 && value <= 2000) return "hPa";
  if (value >= 20000 && value <= 200000) return "Pa";
  return null;
}

export function looksLikeTime(value) {
  if (typeof value === "string" && ISO_TIME.test(value.trim())) return toTime(value) !== null;
  const number = typeof value === "number" ? value : typeof value === "string" && EPOCH_TEXT.test(value.trim()) ? Number(value) : null;
  return number !== null && number >= PLAUSIBLE_EPOCH[0] && number < PLAUSIBLE_EPOCH[1];
}

export function detect(document) {
  const leaves = flatten(document);
  const numbers = leaves.filter((leaf) => toNumber(leaf.value) !== null && !looksLikeTime(leaf.value));
  const times = leaves.filter((leaf) => looksLikeTime(leaf.value));
  const guess = {
    time: best(times, TIME_NAMES, () => true) || times[0]?.pointer || null,
    temperature: best(numbers, TEMPERATURE_NAMES, () => true),
    humidity: best(numbers, HUMIDITY_NAMES, () => true),
    pressure: best(numbers, PRESSURE_NAMES, (value) => pressureUnitFor(toNumber(value)) !== null),
  };
  const pressureValue = guess.pressure ? toNumber(resolve(document, guess.pressure)) : null;
  return { leaves, numbers, times, guess, pressureUnit: pressureValue === null ? "kPa" : pressureUnitFor(pressureValue) };
}

export function extract(document, mapping, receivedAt) {
  const errors = [];
  const reading = { measured_at: null, temperature_c: null, relative_humidity_percent: null, pressure_kpa: null };

  if (mapping.time) {
    const raw = resolve(document, mapping.time);
    const moment = raw === undefined || typeof raw === "boolean" ? null : toTime(raw);
    if (raw === undefined) errors.push({ field: "time", message: `nothing at ${mapping.time}` });
    else if (moment === null) errors.push({ field: "time", message: `${JSON.stringify(raw)} at ${mapping.time} is not an ISO 8601 time or an epoch number` });
    else reading.measured_at = moment.toISOString();
  } else {
    reading.measured_at = new Date(receivedAt).toISOString();
  }

  const numberAt = (field, pointer, target) => {
    if (!pointer) {
      errors.push({ field, message: `no ${field} field chosen` });
      return;
    }
    const raw = resolve(document, pointer);
    const number = toNumber(raw);
    if (raw === undefined) errors.push({ field, message: `nothing at ${pointer}` });
    else if (number === null) errors.push({ field, message: `${JSON.stringify(raw)} at ${pointer} is not a number` });
    else reading[target] = number;
  };
  numberAt("temperature", mapping.temperature, "temperature_c");
  numberAt("humidity", mapping.humidity, "relative_humidity_percent");

  if (mapping.pressure) {
    if (!(mapping.pressure_unit in PRESSURE_UNITS)) {
      errors.push({ field: "pressure", message: `unknown pressure unit ${mapping.pressure_unit}` });
    } else {
      const raw = resolve(document, mapping.pressure);
      const number = toNumber(raw);
      if (raw === undefined) errors.push({ field: "pressure", message: `nothing at ${mapping.pressure}` });
      else if (number === null) errors.push({ field: "pressure", message: `${JSON.stringify(raw)} at ${mapping.pressure} is not a number` });
      else reading.pressure_kpa = kpaFrom(number, mapping.pressure_unit);
    }
  }
  return { reading, errors };
}
