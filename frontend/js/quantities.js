import { kpaFromPa } from "./units.js";

export const QUANTITIES = [
  { id: "temperature", key: "temperature_c", label: "Temperature", unit: "°C", decimals: 1, topic: "temperature", measured: (reading) => reading.temperature_c, of: (state) => state.temperature },
  { id: "relative_humidity", key: "relative_humidity_percent", label: "Relative humidity", unit: "%", decimals: 1, topic: "relative-humidity", measured: (reading) => reading.relative_humidity_percent, of: (state) => state.relativeHumidity },
  { id: "vpd", key: "vpd_kpa", label: "VPD", unit: "kPa", decimals: 2, topic: "vpd", of: (state) => kpaFromPa(state.vapourPressureDeficit) },
  { id: "dew_point", key: "dew_point_c", label: "Dew point", unit: "°C", decimals: 1, topic: "dew-point", of: (state) => state.dewPoint },
  { id: "wet_bulb", key: "wet_bulb_c", label: "Wet bulb", unit: "°C", decimals: 1, topic: "wet-bulb", of: (state) => state.wetBulb },
  { id: "humidity_ratio", key: "humidity_ratio_g_kg", label: "Humidity ratio", unit: "g/kg", decimals: 2, topic: "humidity-ratio", of: (state) => state.humidityRatio * 1000 },
  { id: "absolute_humidity", key: "absolute_humidity_g_m3", label: "Absolute humidity", unit: "g/m³", decimals: 2, topic: "absolute-humidity", of: (state) => state.absoluteHumidity },
  { id: "enthalpy", key: "enthalpy_kj_kg", label: "Enthalpy", unit: "kJ/kg", decimals: 1, topic: "enthalpy", of: (state) => state.enthalpy },
  { id: "vapour_pressure", key: "vapour_pressure_kpa", label: "Vapour pressure", unit: "kPa", decimals: 3, topic: "vapour-pressure", of: (state) => kpaFromPa(state.vapourPressure) },
  { id: "saturation_vapour_pressure", key: "saturation_vapour_pressure_kpa", label: "Saturation vapour pressure", unit: "kPa", decimals: 3, topic: "saturation-vapour-pressure", of: (state) => kpaFromPa(state.saturationVapourPressure) },
  { id: "specific_volume", key: "specific_volume_m3_kg", label: "Specific volume", unit: "m³/kg", decimals: 4, topic: "specific-volume", of: (state) => state.specificVolume },
  { id: "density", key: "density_kg_m3", label: "Density", unit: "kg/m³", decimals: 4, topic: "density", of: (state) => state.density },
  { id: "pressure", key: "pressure_kpa", label: "Pressure", unit: "kPa", decimals: 3, topic: "pressure", of: (state) => kpaFromPa(state.pressure) },
];

export const DECISIONS = [
  { id: "state", key: "state", label: "State" },
  { id: "rule", key: "rule", label: "Rule" },
  { id: "recommendation", key: "recommendation", label: "Recommendation" },
];

export const DEFAULT_COLUMNS = ["temperature", "relative_humidity", "vpd"];

export function quantityById(id) {
  return QUANTITIES.find((quantity) => quantity.id === id) || null;
}

export function valueOf(quantity, reading, state) {
  if (quantity.measured) return quantity.measured(reading);
  return state ? quantity.of(state) : null;
}
