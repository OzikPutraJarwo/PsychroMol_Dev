import * as psy from "./psychro.js";
import { cite, formatCitations } from "./references.js";
import { kpaFromPa, paFromKpa } from "./units.js";

export const STATES = ["LOW", "OPTIMAL", "HIGH"];
export const ANY = "ANY";
export const SEVERITIES = ["ok", "warning", "critical"];

export const INDICATORS = [
  { key: "temperature", label: "Temperature", unit: "°C", decimals: 1, topic: "temperature" },
  { key: "humidity", label: "Humidity", unit: "%", decimals: 1, topic: "relative-humidity" },
  { key: "vpd", label: "VPD", unit: "kPa", decimals: 2, topic: "vpd" },
];

const ONE_RANGE_NOTE = "The source gives one range for the whole crop cycle, not one per stage, so vegetative and flowering-and-fruiting start from the same band. Replace it with a stage-specific value from your own reference if you have one.";

const WHOLE_CYCLE_CITATIONS = [
  cite("shamshiri2018", "p. 292", "Moreover, values between 0.2 and 1.0 kPa were found to have little or no effect on the physiology and growth development of tomato (Grange and Hand, 1987; Picken, 1984)."),
  cite("shamshiri2018", "p. 293, Table 3", "0.2-1.0: ideal for pollination and for prevention from fungal disease, this range was found to have little or no negative effect on the physiology and growth development of tomato (Picken 1984; Prenger and Ling 2001; Grange and Hand 1987)"),
  cite("grangeHand1987", "a review across horticultural crops, as summarised by Shamshiri et al. (2018)"),
];

export const STAGES = [
  {
    id: "propagation",
    label: "Propagation (rooting cuttings)",
    vpd: { min: 0.3, max: 0.5 },
    citations: [
      cite("shamshiri2018", "p. 292", "It is generally recommended that VPD should be kept around 0.3–0.5 kPa during root cuttings in order to minimize dry outs of plants, especially in dense plant conditions."),
    ],
    note: "The source gives this range for rooting cuttings.",
  },
  {
    id: "vegetative",
    label: "Vegetative",
    vpd: { min: 0.2, max: 1.0 },
    citations: WHOLE_CYCLE_CITATIONS,
    note: ONE_RANGE_NOTE,
  },
  {
    id: "flowering",
    label: "Flowering and fruiting",
    vpd: { min: 0.2, max: 1.0 },
    citations: WHOLE_CYCLE_CITATIONS,
    note: ONE_RANGE_NOTE,
  },
];

export function stageById(id) {
  return STAGES.find((stage) => stage.id === id) || null;
}

export function classify(value, min, max) {
  if (value < min) return "LOW";
  if (value > max) return "HIGH";
  return "OPTIMAL";
}

export function vpdBand(profile) {
  const custom = profile.vpd_min !== null && profile.vpd_min !== undefined
    && profile.vpd_max !== null && profile.vpd_max !== undefined;
  if (custom) {
    return { min: profile.vpd_min, max: profile.vpd_max, custom: true, reference: profile.vpd_reference || "" };
  }
  const stage = stageById(profile.stage);
  if (!stage) return null;
  return { min: stage.vpd.min, max: stage.vpd.max, custom: false, reference: formatCitations(stage.citations), stage };
}

export function bands(profile) {
  return {
    temperature: { min: profile.temperature_min, max: profile.temperature_max, reference: profile.temperature_reference || "" },
    humidity: { min: profile.humidity_min, max: profile.humidity_max, reference: profile.humidity_reference || "" },
    vpd: vpdBand(profile),
  };
}

export function pressureFor(profile, reading) {
  if (profile.pressure_mode === "fixed" && Number.isFinite(profile.pressure_kpa)) {
    return { pa: paFromKpa(profile.pressure_kpa), source: "fixed" };
  }
  if (profile.pressure_mode === "field") {
    if (reading && Number.isFinite(reading.pressure_kpa)) {
      return { pa: paFromKpa(reading.pressure_kpa), source: "field" };
    }
    return { pa: psy.standardAtmosphericPressure(0), source: "standard-fallback" };
  }
  return { pa: psy.standardAtmosphericPressure(0), source: "standard" };
}

export function stateFor(profile, reading) {
  if (!reading) return { state: null, pressure: null, error: "No reading yet." };
  const pressure = pressureFor(profile, reading);
  const t = reading.temperature_c;
  const rh = reading.relative_humidity_percent;
  if (!Number.isFinite(t) || !Number.isFinite(rh)) {
    return { state: null, pressure, error: "The reading has no temperature or humidity value." };
  }
  try {
    return { state: psy.stateFromTemperatureRelativeHumidity(t, rh, pressure.pa), pressure, error: null };
  } catch (error) {
    if (error instanceof psy.PsychrometricRangeError) return { state: null, pressure, error: `Not calculated: ${error.message}.` };
    throw error;
  }
}

const TEMPERATURE_WORDS = { LOW: "COLD", OPTIMAL: "OPTIMAL TEMPERATURE", HIGH: "HOT" };
const HUMIDITY_WORDS = { LOW: "DRY", OPTIMAL: "OPTIMAL HUMIDITY", HIGH: "HUMID" };

export function stateLabel(classes) {
  if (classes.temperature === "OPTIMAL" && classes.humidity === "OPTIMAL" && classes.vpd === "OPTIMAL") return "OPTIMAL";
  return `${TEMPERATURE_WORDS[classes.temperature]} + ${HUMIDITY_WORDS[classes.humidity]} · ${classes.vpd} VPD`;
}

export function ruleMatches(rule, classes) {
  if (rule.enabled === false) return false;
  return INDICATORS.every(({ key }) => {
    const wanted = rule.conditions?.[key] ?? ANY;
    return wanted === ANY || wanted === classes[key];
  });
}

export function rank(rules) {
  return [...rules].sort((a, b) => {
    const severity = SEVERITIES.indexOf(b.severity) - SEVERITIES.indexOf(a.severity);
    return severity || a.priority - b.priority || (a.id ?? 0) - (b.id ?? 0);
  });
}

export function assess(profile, reading, rules = []) {
  const { state, pressure, error } = stateFor(profile, reading);
  const band = bands(profile);
  if (!state) return { reading, state: null, pressure, error, bands: band, values: null, classes: null, label: null, matches: [], headline: null };
  if (!band.vpd) {
    return { reading, state, pressure, error: `Unknown growth stage ${profile.stage}.`, bands: band, values: null, classes: null, label: null, matches: [], headline: null };
  }
  const values = {
    temperature: state.temperature,
    humidity: state.relativeHumidity,
    vpd: kpaFromPa(state.vapourPressureDeficit),
  };
  const classes = {
    temperature: classify(values.temperature, band.temperature.min, band.temperature.max),
    humidity: classify(values.humidity, band.humidity.min, band.humidity.max),
    vpd: classify(values.vpd, band.vpd.min, band.vpd.max),
  };
  const matches = rank(rules.filter((rule) => ruleMatches(rule, classes)));
  return { reading, state, pressure, error: null, bands: band, values, classes, label: stateLabel(classes), matches, headline: matches[0] || null };
}

export function validateRule(rule) {
  const problems = [];
  if (!rule.name || !String(rule.name).trim()) problems.push("a rule needs a name");
  if (!rule.recommendation || !String(rule.recommendation).trim()) problems.push("a rule needs a recommendation");
  if (!rule.reference || !String(rule.reference).trim()) problems.push("a rule needs a reference");
  if (!SEVERITIES.includes(rule.severity)) problems.push(`severity must be one of ${SEVERITIES.join(", ")}`);
  if (!Number.isInteger(rule.priority)) problems.push("order must be a whole number");
  for (const { key, label } of INDICATORS) {
    const wanted = rule.conditions?.[key] ?? ANY;
    if (wanted !== ANY && !STATES.includes(wanted)) problems.push(`${label.toLowerCase()} must be ANY, LOW, OPTIMAL or HIGH`);
  }
  return problems;
}

function rule(priority, name, [temperature, humidity, vpd], severity, recommendation, citations, note = "") {
  return {
    name,
    conditions: { temperature, humidity, vpd },
    severity,
    recommendation,
    reference: note ? `${formatCitations(citations)}\n${note}` : formatCitations(citations),
    priority,
    enabled: true,
  };
}

const VENT_AND_HEAT = cite("bc2015", "p. 4", "Use a combination of venting and heating to reduce excessive humidity.");
const VENTING_EXCHANGE = cite("bc2015", "p. 3", "The common strategy used to reduce greenhouse humidity involves: venting to exchange moist greenhouse air with drier outside air, and heating to reduce the relative humidity levels, raise the temperature of plant surfaces and warm the incoming air.");
const AIR_FLOW = cite("bc2015", "p. 4", "Use horizontal air flow fans or poly tubes to maintain a uniform temperature throughout the crop.");
const EVAPORATIVE_DEVICES = cite("bc2015", "p. 4", "Evaporative devices accomplish 3 things. First, they cool the air and thereby raise the humidity and relieve stress on the crop. Second, they add water vapour to the air, which further increases the relative humidity. And third, they reduce the VPD.");
const HUMIDIFY_WITH = cite("bc2015", "p. 4", "Raising humidity levels without creating excessive free water requires an evaporative device such as a mister, fog unit, or roof sprinkler, or screens that help hold in the water that is being evaporated from the plant canopy.");
const VENT_WHEN_SUNNY = cite("bc2015", "pp. 4–5", "In general, some venting is necessary when humidifying under sunny conditions.");
const VPD_GENERAL_RULE = cite("shamshiri2018", "p. 296", "Furthermore, as a general rule, increasing air temperature in the greenhouse by minimizing ventilation will increase VPD, while activating the evaporative cooling system, misting or fogging will cause higher RH, thus decreasing VPD.");
const THERMAL_SCREENS = cite("bc2015", "p. 4", "Use thermal screens at night to prevent radiative heat loss from plant surfaces.");

export function defaultRules() {
  return [
    rule(10, "Hot and humid", ["HIGH", "HIGH", ANY], "critical",
      "Ventilate to replace the hot, moist air with drier outside air. Do not mist, fog or run pad-and-fan cooling while the air is this humid.",
      [
        VENTING_EXCHANGE,
        cite("shamshiri2018", "p. 290", "Thus, in a greenhouse condition with air around plant leaves too hot and humid, the transpiration at the leaf surface will be ineffectual and the root and stem system may not be able to supply adequate water to the leaves. Cooling is, therefore, required to reduce these stresses."),
        VPD_GENERAL_RULE,
        cite("shamshiri2018", "p. 298", "Evaporative pad-and-fan systems can cause low VPD in tropical greenhouses by increasing RH without significantly reducing air temperature, and accelerate the spread of fungal diseases (Xu et al., 2015)."),
      ]),
    rule(20, "Hot and dry", ["HIGH", "LOW", ANY], "critical",
      "Shade, and cool with misting, fogging or evaporative cooling while keeping some ventilation. This lowers the temperature and raises the humidity.",
      [
        EVAPORATIVE_DEVICES,
        VENT_WHEN_SUNNY,
        cite("bc2015", "p. 4", "Plants under sun screens (shade cloth) tend to have lower transpiration needs due to less radiation heating."),
        cite("shamshiri2018", "p. 297", "Moreover, a high air temperature combined with too low RH values induces flower abortion."),
      ]),
    rule(30, "Hot", ["HIGH", "OPTIMAL", ANY], "warning",
      "Lower the temperature: shade and ventilate, and add evaporative cooling if that is not enough, keeping the vents open for it to work.",
      [
        cite("bc2015", "p. 4", "Screens can be used to reduce leaf temperature and help to trap the large amount of water evaporating from the crop."),
        cite("bc2015", "p. 5", "Venting will introduce fresh dry air to evaporate more water, and to cool, humidify and displace hot greenhouse air."),
        cite("bc2015", "p. 5", "Evaporative cooling devices require good ventilation rates."),
      ]),
    rule(40, "Cold and humid", ["LOW", "HIGH", ANY], "critical",
      "Heat, with a little ventilation, to lower the humidity and keep plant surfaces above the dew point. Keep the air moving with circulation fans.",
      [
        VENT_AND_HEAT,
        VENTING_EXCHANGE,
        AIR_FLOW,
        cite("bc2015", "p. 3", "Greenhouse growers usually try to avoid humidity levels near the dew point since free water condensing onto plant surfaces can promote the growth of disease organisms."),
      ]),
    rule(50, "Cold and dry", ["LOW", "LOW", ANY], "critical",
      "Heat, and keep the moisture in: keep the vents closed and use screens. Warming the air lowers its humidity further, so humidify with misting or fogging if it stays low.",
      [
        VENTING_EXCHANGE,
        cite("bc2015", "p. 2", "As the air temperature rises, more water vapour can be held in a given amount of air. And as the air becomes warmer, more moisture must be added to the air to maintain the same relative humidity."),
        HUMIDIFY_WITH,
        THERMAL_SCREENS,
      ]),
    rule(60, "Cold", ["LOW", "OPTIMAL", ANY], "warning",
      "Heat to bring the temperature back into the band, keep ventilation to a minimum, and close thermal screens at night.",
      [
        cite("bc2015", "p. 3", "heating to reduce the relative humidity levels, raise the temperature of plant surfaces and warm the incoming air."),
        VPD_GENERAL_RULE,
        THERMAL_SCREENS,
      ]),
    rule(70, "Humid", ["OPTIMAL", "HIGH", ANY], "warning",
      "Lower the humidity: ventilate and heat together, and keep the air moving with circulation fans.",
      [
        VENT_AND_HEAT,
        cite("bc2015", "p. 4", "Start dehumidifying at or about 85% RH. Relative humidity levels above 85% are not easily managed without increasing the risk of condensation and interference of nutrient uptake due to a lack of transpiration."),
        AIR_FLOW,
        cite("shamshiri2018", "p. 298", "In a highly humid greenhouse environment, diseases and fungal pathogens spread rapidly and infect plants."),
      ]),
    rule(80, "Dry", ["OPTIMAL", "LOW", ANY], "warning",
      "Raise the humidity with misting or fogging. Under sun, keep some ventilation: closing the vents heats the house and the VPD climbs again.",
      [
        VPD_GENERAL_RULE,
        HUMIDIFY_WITH,
        cite("bc2015", "p. 4", "It has been suggested that limiting the ventilation rate under full sun conditions can reduce plant stress by raising the humidity level. Although transpiration rates are reduced initially, the rapid increase in air and leaf temperatures causes an increase in the VPD and the transpiration rates climb again."),
        VENT_WHEN_SUNNY,
      ]),
    rule(90, "High VPD", ["OPTIMAL", "OPTIMAL", "HIGH"], "warning",
      "The air is drying the crop faster than the band allows. Raise the humidity with misting or fogging, or lower the temperature with shade or evaporative cooling.",
      [
        cite("shamshiri2018", "p. 296", "It can be seen that for a constant RH, the values of VPD increase at higher temperatures, resulting in an increase in the plant transpiration rate."),
        cite("shamshiri2018", "p. 296", "Of note, VPD can be effectively controlled by humidification devices such as fogging systems."),
        EVAPORATIVE_DEVICES,
        cite("shamshiri2018", "p. 299", "high VPD (larger than 1.5 kPa) results in wilting, [leaf] roll, stunted plants and crispy leaves."),
      ]),
    rule(100, "Low VPD", ["OPTIMAL", "OPTIMAL", "LOW"], "warning",
      "The air is too close to saturation for the crop to transpire well. Raise the air temperature a little, or ventilate to exchange the moist air, and do not mist.",
      [
        VPD_GENERAL_RULE,
        cite("shamshiri2018", "p. 297", "What is more, increasing air temperature by 2 °C in the winter season, in the hours of high humidity, is recommended to maintain optimal VPD (Sato et al., 2000)."),
        VENTING_EXCHANGE,
        cite("shamshiri2018", "p. 299", "In summary, low VPD values (below 0.3 kPa) in tomato plants cause mineral deficiencies, guttation, fungal diseases and soft growth"),
      ]),
    rule(110, "Within the bands", ["OPTIMAL", "OPTIMAL", "OPTIMAL"], "ok",
      "Temperature, humidity and VPD are all within their bands. No change is needed.",
      [cite("shamshiri2018", "pp. 294–295, microclimate evaluation against the optimal values for the growth stage")],
      "The bands themselves come from the references entered for this crop and stage."),
  ];
}

function fixed(value, digits) {
  return Number.isFinite(value) ? value.toFixed(digits) : "—";
}

export function explain(assessment) {
  const { state, pressure, values, classes, bands: band } = assessment;
  if (!state || !classes) return [];
  const kpa = (pa) => fixed(kpaFromPa(pa), 3);
  const pressureNote = {
    standard: "standard atmosphere",
    fixed: "fixed value",
    field: "from the reading",
    "standard-fallback": "standard atmosphere — this reading has no pressure",
  }[pressure.source];
  return [
    { group: "Inputs", label: "Temperature t", expression: "", result: `${fixed(values.temperature, 1)} °C`, topic: "temperature" },
    { group: "Inputs", label: "Relative humidity φ", expression: "", result: `${fixed(values.humidity, 1)} %`, topic: "relative-humidity" },
    { group: "Inputs", label: "Pressure p", expression: pressureNote, result: `${kpa(pressure.pa)} kPa`, topic: "pressure" },
    { group: "Calculated", label: "Saturation vapour pressure p_{ws}", expression: `Eq. ${state.temperature < 0 ? 5 : 6} at ${fixed(state.temperature, 1)} °C`, result: `${kpa(state.saturationVapourPressure)} kPa`, topic: "saturation-vapour-pressure" },
    { group: "Calculated", label: "Vapour pressure p_{w}", expression: `φ · p_{ws} = ${fixed(state.relativeHumidity / 100, 3)} × ${kpa(state.saturationVapourPressure)}`, result: `${kpa(state.vapourPressure)} kPa`, topic: "vapour-pressure" },
    { group: "Calculated", label: "VPD", expression: `p_{ws} − p_{w} = ${kpa(state.saturationVapourPressure)} − ${kpa(state.vapourPressure)}`, result: `${kpa(state.vapourPressureDeficit)} kPa`, topic: "vpd" },
    ...INDICATORS.map(({ key, label, unit, decimals }) => ({
      group: "Classified",
      label,
      expression: `${fixed(values[key], decimals)} ${unit} against ${fixed(band[key].min, decimals)}–${fixed(band[key].max, decimals)} ${unit}`,
      result: classes[key],
      topic: "classification",
      band: key,
    })),
  ];
}
