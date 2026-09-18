export const PA_PER_KPA = 1000;

export const PRESSURE_UNITS = Object.freeze({ kPa: 1, hPa: 0.1, Pa: 0.001 });

export function paFromKpa(kpa) {
  return kpa * PA_PER_KPA;
}

export function kpaFromPa(pa) {
  return pa / PA_PER_KPA;
}

export function kpaFrom(value, unit) {
  const factor = PRESSURE_UNITS[unit];
  if (factor === undefined) throw new Error(`unknown pressure unit ${unit}`);
  return value * factor;
}
