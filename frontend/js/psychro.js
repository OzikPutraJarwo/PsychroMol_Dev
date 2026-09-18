export const MW_RATIO = 0.621945;
export const SPECIFIC_VOLUME_W_COEFF = 1.607858;
export const R_DRY_AIR = 287.042;
export const CP_DRY_AIR = 1.006;
export const CP_WATER_VAPOUR = 1.86;
export const CP_LIQUID_WATER = 4.186;
export const CP_ICE = 2.1;
export const H_FG_0C = 2501.0;
export const H_IG_0C = 2830.0;
export const ZERO_CELSIUS_IN_KELVIN = 273.15;
export const STANDARD_PRESSURE_PA = 101325.0;
export const MIN_TEMPERATURE_C = -100.0;
export const MAX_TEMPERATURE_C = 200.0;
export const MIN_PRESSURE_PA = 20000.0;
export const MAX_PRESSURE_PA = 200000.0;

const TEMPERATURE_TOLERANCE_C = 1e-10;
const MAX_ITERATIONS = 200;

export class PsychrometricRangeError extends RangeError {
  constructor(message) {
    super(message);
    this.name = "PsychrometricRangeError";
  }
}

function bisectIncreasing(fn, target, lower, upper) {
  if (fn(lower) >= target) return lower;
  if (fn(upper) <= target) return upper;
  let low = lower;
  let high = upper;
  for (let iteration = 0; iteration < MAX_ITERATIONS; iteration += 1) {
    const midpoint = 0.5 * (low + high);
    if (fn(midpoint) < target) low = midpoint;
    else high = midpoint;
    if (high - low < TEMPERATURE_TOLERANCE_C) break;
  }
  return 0.5 * (low + high);
}

function validateTemperature(t) {
  if (!Number.isFinite(t)) {
    throw new PsychrometricRangeError(`temperature must be finite, got ${t}`);
  }
  if (t < MIN_TEMPERATURE_C || t > MAX_TEMPERATURE_C) {
    throw new PsychrometricRangeError(
      `temperature ${t} °C is outside the validated range ${MIN_TEMPERATURE_C}..${MAX_TEMPERATURE_C} °C`,
    );
  }
}

export function validatePressure(pressure) {
  if (!Number.isFinite(pressure)) {
    throw new PsychrometricRangeError(`pressure must be finite, got ${pressure}`);
  }
  if (pressure < MIN_PRESSURE_PA || pressure > MAX_PRESSURE_PA) {
    throw new PsychrometricRangeError(
      `total pressure ${pressure} Pa is outside ${MIN_PRESSURE_PA}..${MAX_PRESSURE_PA} Pa — check the unit (the engine works in Pa, not kPa)`,
    );
  }
}

export function validateRelativeHumidity(rh) {
  if (!Number.isFinite(rh)) {
    throw new PsychrometricRangeError(`relative humidity must be finite, got ${rh}`);
  }
  if (rh < 0 || rh > 100) {
    throw new PsychrometricRangeError(`relative humidity must be within 0..100 %, got ${rh}`);
  }
}

// ASHRAE Fundamentals 2017, Ch. 1, Eq. 5 (over ice, -100..0 °C)
export function saturationVapourPressureOverIce(t) {
  const tk = t + ZERO_CELSIUS_IN_KELVIN;
  return Math.exp(
    -5.6745359e3 / tk
      + 6.3925247
      - 9.677843e-3 * tk
      + 6.2215701e-7 * tk ** 2
      + 2.0747825e-9 * tk ** 3
      - 9.484024e-13 * tk ** 4
      + 4.1635019 * Math.log(tk),
  );
}

// ASHRAE Fundamentals 2017, Ch. 1, Eq. 6 (over liquid water, 0..200 °C)
export function saturationVapourPressureOverWater(t) {
  const tk = t + ZERO_CELSIUS_IN_KELVIN;
  return Math.exp(
    -5.8002206e3 / tk
      + 1.3914993
      - 4.8640239e-2 * tk
      + 4.1764768e-5 * tk ** 2
      - 1.4452093e-8 * tk ** 3
      + 6.5459673 * Math.log(tk),
  );
}

// ASHRAE Fundamentals 2017, Ch. 1, Eq. 5 below 0 °C, Eq. 6 at and above 0 °C
export function saturationVapourPressure(t) {
  validateTemperature(t);
  return t < 0 ? saturationVapourPressureOverIce(t) : saturationVapourPressureOverWater(t);
}

export function saturationTemperature(pws) {
  if (!(pws > 0)) {
    throw new PsychrometricRangeError(`saturation vapour pressure must be positive, got ${pws} Pa`);
  }
  return bisectIncreasing(saturationVapourPressure, pws, MIN_TEMPERATURE_C, MAX_TEMPERATURE_C);
}

// ASHRAE Fundamentals 2017, Ch. 1, Eq. 20
export function humidityRatioFromVapourPressure(pw, pressure) {
  if (pw < 0) throw new PsychrometricRangeError(`vapour pressure must be >= 0, got ${pw} Pa`);
  if (pressure <= pw) {
    throw new PsychrometricRangeError(`vapour pressure ${pw} Pa must be below total pressure ${pressure} Pa`);
  }
  return (MW_RATIO * pw) / (pressure - pw);
}

// ASHRAE Fundamentals 2017, Ch. 1, Eq. 20 solved for p_w
export function vapourPressureFromHumidityRatio(w, pressure) {
  if (w < 0) throw new PsychrometricRangeError(`humidity ratio must be non-negative, got ${w}`);
  return (pressure * w) / (MW_RATIO + w);
}

export function saturationHumidityRatio(t, pressure) {
  return humidityRatioFromVapourPressure(saturationVapourPressure(t), pressure);
}

// ASHRAE Fundamentals 2017, Ch. 1, Eq. 12 and 22 (p_w = phi p_ws), then Eq. 20
export function humidityRatioFromRelativeHumidity(t, rh, pressure) {
  validateRelativeHumidity(rh);
  return humidityRatioFromVapourPressure((saturationVapourPressure(t) * rh) / 100, pressure);
}

// ASHRAE Fundamentals 2017, Ch. 1, Eq. 12 and 22
export function relativeHumidityFromHumidityRatio(t, w, pressure) {
  return (100 * vapourPressureFromHumidityRatio(w, pressure)) / saturationVapourPressure(t);
}

// Numerical inverse of ASHRAE Fundamentals 2017, Ch. 1, Eq. 5 and 6
export function dewPointTemperature(pw) {
  if (pw <= 0) return MIN_TEMPERATURE_C;
  return saturationTemperature(pw);
}

// ASHRAE Fundamentals 2017, Ch. 1, Eq. 33 (t* >= 0 °C) and Eq. 35 (t* < 0 °C)
export function humidityRatioFromWetBulb(t, twb, pressure) {
  if (twb > t + 1e-9) {
    throw new PsychrometricRangeError(`wet-bulb ${twb} °C cannot exceed dry-bulb ${t} °C`);
  }
  const saturated = saturationHumidityRatio(twb, pressure);
  let numerator;
  let denominator;
  if (twb >= 0) {
    numerator = (H_FG_0C - (CP_LIQUID_WATER - CP_WATER_VAPOUR) * twb) * saturated - CP_DRY_AIR * (t - twb);
    denominator = H_FG_0C + CP_WATER_VAPOUR * t - CP_LIQUID_WATER * twb;
  } else {
    numerator = (H_IG_0C - (CP_ICE - CP_WATER_VAPOUR) * twb) * saturated - CP_DRY_AIR * (t - twb);
    denominator = H_IG_0C + CP_WATER_VAPOUR * t - CP_ICE * twb;
  }
  return Math.max(numerator / denominator, 0);
}

// Numerical inverse of ASHRAE Fundamentals 2017, Ch. 1, Eq. 33 and 35
export function wetBulbTemperature(t, w, pressure) {
  const pw = vapourPressureFromHumidityRatio(w, pressure);
  const lower = pw > 0 ? dewPointTemperature(pw) : MIN_TEMPERATURE_C;
  if (t - lower < TEMPERATURE_TOLERANCE_C) return t;
  return bisectIncreasing((twb) => humidityRatioFromWetBulb(t, twb, pressure), w, lower, t);
}

// ASHRAE Fundamentals 2017, Ch. 1, Eq. 30
export function enthalpy(t, w) {
  return CP_DRY_AIR * t + w * (H_FG_0C + CP_WATER_VAPOUR * t);
}

// ASHRAE Fundamentals 2017, Ch. 1, Eq. 30 solved for W
export function humidityRatioFromEnthalpy(t, h) {
  return (h - CP_DRY_AIR * t) / (H_FG_0C + CP_WATER_VAPOUR * t);
}

// ASHRAE Fundamentals 2017, Ch. 1, Eq. 30 solved for t
export function temperatureFromEnthalpy(h, w) {
  return (h - w * H_FG_0C) / (CP_DRY_AIR + w * CP_WATER_VAPOUR);
}

// ASHRAE Fundamentals 2017, Ch. 1, Eq. 26
export function specificVolume(t, w, pressure) {
  validatePressure(pressure);
  return (R_DRY_AIR * (t + ZERO_CELSIUS_IN_KELVIN) * (1 + SPECIFIC_VOLUME_W_COEFF * w)) / pressure;
}

// ASHRAE Fundamentals 2017, Ch. 1, Eq. 26 solved for t
export function temperatureFromSpecificVolume(v, w, pressure) {
  return (v * pressure) / (R_DRY_AIR * (1 + SPECIFIC_VOLUME_W_COEFF * w)) - ZERO_CELSIUS_IN_KELVIN;
}

// ASHRAE Fundamentals 2017, Ch. 1, Eq. 26 solved for W
export function humidityRatioFromSpecificVolume(t, v, pressure) {
  return ((v * pressure) / (R_DRY_AIR * (t + ZERO_CELSIUS_IN_KELVIN)) - 1) / SPECIFIC_VOLUME_W_COEFF;
}

// ASHRAE Fundamentals 2017, Ch. 1, Eq. 11
export function moistAirDensity(w, v) {
  return (1 + w) / v;
}

// ASHRAE Fundamentals 2017, Ch. 1, absolute humidity d_v = M_w / V, with v from Eq. 26
export function absoluteHumidity(w, v) {
  return (1000 * w) / v;
}

export function vapourPressureDeficit(pws, pw) {
  return pws - pw;
}

// ASHRAE Fundamentals 2017, Ch. 1, Eq. 3
export function standardAtmosphericPressure(altitude = 0) {
  return STANDARD_PRESSURE_PA * (1 - 2.25577e-5 * altitude) ** 5.2559;
}

function evaluate(t, pw, pressure, rh = null) {
  validatePressure(pressure);
  const pws = saturationVapourPressure(t);
  const w = humidityRatioFromVapourPressure(pw, pressure);
  const volume = specificVolume(t, w, pressure);
  let dewPoint;
  let wetBulb;
  return Object.freeze({
    temperature: t,
    relativeHumidity: rh ?? Math.min(100, (100 * pw) / pws),
    pressure,
    saturationVapourPressure: pws,
    vapourPressure: pw,
    humidityRatio: w,
    get dewPoint() {
      dewPoint ??= dewPointTemperature(pw);
      return dewPoint;
    },
    get wetBulb() {
      wetBulb ??= wetBulbTemperature(t, w, pressure);
      return wetBulb;
    },
    enthalpy: enthalpy(t, w),
    specificVolume: volume,
    density: moistAirDensity(w, volume),
    vapourPressureDeficit: vapourPressureDeficit(pws, pw),
    absoluteHumidity: absoluteHumidity(w, volume),
  });
}

// ASHRAE Fundamentals 2017, Ch. 1, Eq. 12 and 22 (p_w = phi p_ws)
export function stateFromTemperatureRelativeHumidity(t, rh, pressure = STANDARD_PRESSURE_PA) {
  validatePressure(pressure);
  validateRelativeHumidity(rh);
  return evaluate(t, (saturationVapourPressure(t) * rh) / 100, pressure, rh);
}

export function stateFromTemperatureDewPoint(t, dewPoint, pressure = STANDARD_PRESSURE_PA) {
  validatePressure(pressure);
  if (dewPoint > t + 1e-9) {
    throw new PsychrometricRangeError(`dew point ${dewPoint} °C cannot exceed dry-bulb ${t} °C`);
  }
  return evaluate(t, saturationVapourPressure(dewPoint), pressure);
}

export function stateFromTemperatureWetBulb(t, wetBulb, pressure = STANDARD_PRESSURE_PA) {
  validatePressure(pressure);
  return evaluate(t, vapourPressureFromHumidityRatio(humidityRatioFromWetBulb(t, wetBulb, pressure), pressure), pressure);
}

export function stateFromTemperatureHumidityRatio(t, w, pressure = STANDARD_PRESSURE_PA) {
  validatePressure(pressure);
  return evaluate(t, vapourPressureFromHumidityRatio(w, pressure), pressure);
}
