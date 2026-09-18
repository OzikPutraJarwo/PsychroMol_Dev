import * as psy from "./psychro.js";

export const CHART_RANGE = Object.freeze({ temperatureMin: -20, temperatureMax: 50, humidityRatioMax: 0.05 });

const RH_LINES = [10, 20, 30, 40, 50, 60, 70, 80, 90];
const STEPS = 120;
const ZONE_STEPS = 40;
const ENTHALPY_STEP = 10;
const WET_BULB_STEP = 5;
const VOLUME_STEP = 0.02;
const ISOTHERM_STEP = 5;

function attempt(fn) {
  try {
    return fn();
  } catch (error) {
    if (error instanceof psy.PsychrometricRangeError) return null;
    throw error;
  }
}

function between(from, to, index, steps) {
  return from + ((to - from) * index) / steps;
}

function saturationPoints(tMin, tMax, pressure) {
  const points = [];
  for (let index = 0; index <= STEPS; index += 1) {
    const t = between(tMin, tMax, index, STEPS);
    const w = attempt(() => psy.saturationHumidityRatio(t, pressure));
    if (w !== null) points.push([t, w]);
  }
  return points;
}

function belowSaturation(t, w, pressure) {
  const saturated = attempt(() => psy.saturationHumidityRatio(t, pressure));
  return saturated !== null && w <= saturated * 1.001;
}

export function targetZone(zone, pressure, wMax, steps = ZONE_STEPS) {
  const { temperatureMin, temperatureMax, humidityMin, humidityMax } = zone;
  if (!(temperatureMax > temperatureMin)) return [];
  const edge = (rh, from, to) => {
    const points = [];
    for (let index = 0; index <= steps; index += 1) {
      const t = between(from, to, index, steps);
      const w = attempt(() => psy.humidityRatioFromRelativeHumidity(t, rh, pressure));
      if (w !== null) points.push([t, Math.min(w, wMax)]);
    }
    return points;
  };
  const top = edge(humidityMax, temperatureMin, temperatureMax);
  const bottom = edge(humidityMin, temperatureMax, temperatureMin);
  if (!top.length || !bottom.length) return [];
  return [...top, ...bottom, top[0]];
}

function relativeHumidityLines(tMin, tMax, wMax, pressure, projectPoint) {
  const curves = [];
  for (const rh of RH_LINES) {
    const points = [];
    for (let index = 0; index <= STEPS; index += 1) {
      const t = between(tMin, tMax, index, STEPS);
      const w = attempt(() => psy.humidityRatioFromRelativeHumidity(t, rh, pressure));
      if (w === null) continue;
      if (w > wMax) break;
      points.push(projectPoint(t, w));
    }
    if (points.length > 1) curves.push({ family: "relative_humidity", label: `${rh} %`, value: rh, points });
  }
  return curves;
}

function mollierY(t, w) {
  return psy.enthalpy(t, w) - psy.H_FG_0C * w;
}

export function project(mode, temperature, humidityRatio) {
  return mode === "mollier"
    ? [humidityRatio * 1000, mollierY(temperature, humidityRatio)]
    : [temperature, humidityRatio * 1000];
}

export function psychrometricChart({
  pressure = psy.STANDARD_PRESSURE_PA,
  zone = null,
  temperatureMin: tMin = CHART_RANGE.temperatureMin,
  temperatureMax: tMax = CHART_RANGE.temperatureMax,
  humidityRatioMax: wMax = CHART_RANGE.humidityRatioMax,
} = {}) {
  psy.validatePressure(pressure);
  const toAxis = (t, w) => [t, w * 1000];
  const curves = [];

  if (zone) {
    const polygon = targetZone(zone, pressure, wMax);
    if (polygon.length) {
      curves.push({ family: "target_zone", label: "Target", value: 0, points: polygon.map(([t, w]) => toAxis(t, w)) });
    }
  }

  curves.push({
    family: "saturation",
    label: "100 %",
    value: 100,
    points: saturationPoints(tMin, tMax, pressure).filter(([, w]) => w <= wMax * 1.5).map(([t, w]) => toAxis(t, w)),
  });

  curves.push(...relativeHumidityLines(tMin, tMax, wMax, pressure, toAxis));

  const hLow = psy.enthalpy(tMin, 0);
  const hHigh = psy.enthalpy(tMax, Math.min(wMax, psy.saturationHumidityRatio(tMax, pressure)));
  for (let h = ENTHALPY_STEP * Math.floor(hLow / ENTHALPY_STEP); h <= hHigh + ENTHALPY_STEP; h += ENTHALPY_STEP) {
    const points = [];
    for (let index = 0; index <= STEPS; index += 1) {
      const t = between(tMin, tMax, index, STEPS);
      const w = psy.humidityRatioFromEnthalpy(t, h);
      if (w < 0 || w > wMax || !belowSaturation(t, w, pressure)) continue;
      points.push(toAxis(t, w));
    }
    if (points.length > 1) curves.push({ family: "enthalpy", label: `${h} kJ/kg`, value: h, points });
  }

  for (let twb = WET_BULB_STEP * Math.floor(tMin / WET_BULB_STEP); twb <= tMax; twb += WET_BULB_STEP) {
    if (twb < tMin) continue;
    const points = [];
    for (let index = 0; index <= STEPS; index += 1) {
      const t = between(twb, tMax, index, STEPS);
      const w = attempt(() => psy.humidityRatioFromWetBulb(t, twb, pressure));
      if (w === null || w <= 0 || w > wMax) continue;
      points.push(toAxis(t, w));
    }
    if (points.length > 1) curves.push({ family: "wet_bulb", label: `${twb} °C wb`, value: twb, points });
  }

  const vLow = psy.specificVolume(tMin, 0, pressure);
  const vHigh = psy.specificVolume(tMax, wMax, pressure);
  const firstVolume = Math.trunc(vLow / VOLUME_STEP) + 1;
  for (let step = firstVolume; step * VOLUME_STEP <= vHigh; step += 1) {
    const v = step * VOLUME_STEP;
    const points = [];
    for (let index = 0; index <= STEPS; index += 1) {
      const t = between(tMin, tMax, index, STEPS);
      const w = psy.humidityRatioFromSpecificVolume(t, v, pressure);
      if (w < 0 || w > wMax || !belowSaturation(t, w, pressure)) continue;
      points.push(toAxis(t, w));
    }
    if (points.length > 1) curves.push({ family: "specific_volume", label: `${v.toFixed(2)} m³/kg`, value: v, points });
  }

  return {
    mode: "psychrometric",
    pressure,
    x: { title: "Dry-bulb temperature", unit: "°C", min: tMin, max: tMax },
    y: { title: "Humidity ratio", unit: "g/kg", min: 0, max: wMax * 1000 },
    curves,
  };
}

export function mollierChart({
  pressure = psy.STANDARD_PRESSURE_PA,
  zone = null,
  temperatureMin: tMin = CHART_RANGE.temperatureMin,
  temperatureMax: tMax = CHART_RANGE.temperatureMax,
  humidityRatioMax: wMax = CHART_RANGE.humidityRatioMax,
} = {}) {
  psy.validatePressure(pressure);
  const toAxis = (t, w) => [w * 1000, mollierY(t, w)];
  const curves = [];

  if (zone) {
    const polygon = targetZone(zone, pressure, wMax);
    if (polygon.length) {
      curves.push({ family: "target_zone", label: "Target", value: 0, points: polygon.map(([t, w]) => toAxis(t, w)) });
    }
  }

  curves.push({
    family: "saturation",
    label: "100 %",
    value: 100,
    points: saturationPoints(tMin, tMax, pressure).filter(([, w]) => w <= wMax * 1.5).map(([t, w]) => toAxis(t, w)),
  });

  curves.push(...relativeHumidityLines(tMin, tMax, wMax, pressure, toAxis));

  for (let t = ISOTHERM_STEP * Math.floor(tMin / ISOTHERM_STEP); t <= tMax; t += ISOTHERM_STEP) {
    if (t < tMin) continue;
    const points = [];
    for (let index = 0; index <= STEPS; index += 1) {
      const w = (wMax * index) / STEPS;
      if (!belowSaturation(t, w, pressure)) break;
      points.push(toAxis(t, w));
    }
    if (points.length > 1) curves.push({ family: "isotherm", label: `${t} °C`, value: t, points });
  }

  const hLow = psy.enthalpy(tMin, 0);
  const hHigh = psy.enthalpy(tMax, wMax);
  for (let h = ENTHALPY_STEP * Math.floor(hLow / ENTHALPY_STEP); h <= hHigh + ENTHALPY_STEP; h += ENTHALPY_STEP) {
    const points = [];
    for (let index = 0; index <= STEPS; index += 1) {
      const w = (wMax * index) / STEPS;
      const t = psy.temperatureFromEnthalpy(h, w);
      if (t < tMin - 5 || t > tMax + 5) continue;
      points.push(toAxis(t, w));
    }
    if (points.length > 1) curves.push({ family: "enthalpy", label: `${h} kJ/kg`, value: h, points });
  }

  const ordinates = curves.flatMap((curve) => curve.points.map(([, y]) => y));
  return {
    mode: "mollier",
    pressure,
    x: { title: "Humidity ratio", unit: "g/kg", min: 0, max: wMax * 1000 },
    y: {
      title: "Enthalpy, h − 2501·W",
      unit: "kJ/kg",
      min: ordinates.length ? Math.min(...ordinates) : 0,
      max: ordinates.length ? Math.max(...ordinates) : 100,
    },
    curves,
  };
}
