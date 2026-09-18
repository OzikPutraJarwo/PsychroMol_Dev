export const SOURCES = {
  ashrae2017: {
    short: "ASHRAE (2017)",
    full: "ASHRAE (2017). ASHRAE Handbook — Fundamentals, SI edition. Chapter 1: Psychrometrics. American Society of Heating, Refrigerating and Air-Conditioning Engineers, Atlanta, GA.",
  },
  psychrolib: {
    short: "Meyer & Thevenard (2019)",
    full: "Meyer, D. and Thevenard, D. (2019). PsychroLib: a library of psychrometric functions to calculate thermodynamic properties of air. Journal of Open Source Software, 4(33), 1137.",
    url: "https://doi.org/10.21105/joss.01137",
  },
  mollier1923: {
    short: "Mollier (1923)",
    full: "Mollier, R. (1923). Ein neues Diagramm für Dampfluftgemische. Zeitschrift des Vereines Deutscher Ingenieure, 67(36), 869–872.",
  },
  shamshiri2018: {
    short: "Shamshiri et al. (2018)",
    full: "Shamshiri, R.R., Jones, J.W., Thorp, K.R., Ahmad, D., Che Man, H. and Taheri, S. (2018). Review of optimum temperature, humidity, and vapour pressure deficit for microclimate evaluation and control in greenhouse cultivation of tomato: a review. International Agrophysics, 32, 287–302.",
    url: "https://doi.org/10.1515/intag-2017-0005",
  },
  grangeHand1987: {
    short: "Grange & Hand (1987)",
    full: "Grange, R.I. and Hand, D.W. (1987). A review of the effects of atmospheric humidity on the growth of horticultural crops. Journal of Horticultural Science, 62(2), 125–134.",
    url: "https://doi.org/10.1080/14620316.1987.11515760",
  },
  bc2015: {
    short: "BC Ministry of Agriculture (2015)",
    full: "British Columbia Ministry of Agriculture (2015). Understanding Humidity Control in Greenhouses. Greenhouse Factsheet, September 2015.",
    url: "https://www2.gov.bc.ca/assets/gov/farming-natural-resources-and-industry/agriculture-and-seafood/animal-and-crops/crop-production/understanding_humidity_control.pdf",
  },
};

export function cite(source, locator, quote) {
  if (!SOURCES[source]) throw new Error(`unknown source ${source}`);
  return quote === undefined ? { source, locator } : { source, locator, quote };
}

export function formatCitation(citation) {
  const source = SOURCES[citation.source];
  const head = `${source.short}, ${citation.locator}.`;
  return citation.quote ? `${head} “${citation.quote}”` : head;
}

export function formatCitations(citations) {
  return citations.map(formatCitation).join("\n");
}

const SATURATION = cite("ashrae2017", "Ch. 1, Eq. 5 (over ice, −100 to 0 °C) and Eq. 6 (over liquid water, 0 to 200 °C)");
const PSYCHROLIB_CHECK = "Every value is cross-checked against PsychroLib 2.5.0, an independent implementation of the same ASHRAE chapter, at 102 points in the test suite.";

export const TOPICS = {
  "temperature": {
    title: "Air temperature",
    text: [
      "Measured, not calculated: the value of the temperature field you chose in the JSON link, in °C.",
      "It is the dry-bulb temperature t used by every equation on this page.",
    ],
    citations: [
      cite("bc2015", "p. 5", "When you measure the air temperature using an ordinary thermometer, this is called dry bulb temperature."),
    ],
  },
  "relative-humidity": {
    title: "Relative humidity",
    formula: ["φ = p_{w} / p_{ws}"],
    where: ["p_{w} vapour pressure of the air", "p_{ws} saturation vapour pressure at the same temperature"],
    text: [
      "Measured, not calculated: the value of the humidity field you chose in the JSON link, in %.",
      "The equation defines what the sensor reports, and is used the other way round to find the vapour pressure. A reading outside 0–100 % is kept as it arrived but not used for any calculation.",
    ],
    citations: [cite("ashrae2017", "Ch. 1, Eq. 12 and 22")],
  },
  "pressure": {
    title: "Atmospheric pressure",
    formula: ["p = 101.325 · (1 − 2.25577 × 10^{−5} · Z)^{5.2559}  kPa"],
    where: ["Z altitude above sea level, m"],
    text: [
      "The standard setting uses this equation at sea level (Z = 0), which gives 101.325 kPa.",
      "A profile can instead use a fixed pressure you enter, or a pressure field from the JSON link.",
      "Pressure changes the humidity ratio, enthalpy, specific volume, density and absolute humidity. It does not change the dew point or the VPD, which depend only on temperature and relative humidity.",
    ],
    citations: [
      cite("ashrae2017", "Ch. 1, Eq. 3 (standard atmosphere)"),
      cite("bc2015", "p. 6, table of units and equivalents: 1 atmosphere, the standard value for air pressure at sea level, is 101.3 kPa"),
    ],
  },
  "saturation-vapour-pressure": {
    title: "Saturation vapour pressure",
    formula: [
      "Over ice, t < 0 °C:",
      "ln p_{ws} = C_{1}/T + C_{2} + C_{3}T + C_{4}T^{2} + C_{5}T^{3} + C_{6}T^{4} + C_{7} ln T",
      "Over liquid water, t ≥ 0 °C:",
      "ln p_{ws} = C_{8}/T + C_{9} + C_{10}T + C_{11}T^{2} + C_{12}T^{3} + C_{13} ln T",
    ],
    where: [
      "T absolute temperature, K (t + 273.15)",
      "p_{ws} in Pa",
      "C_{1} … C_{7} = −5.6745359×10^{3}, 6.3925247, −9.677843×10^{−3}, 6.2215701×10^{−7}, 2.0747825×10^{−9}, −9.484024×10^{−13}, 4.1635019",
      "C_{8} … C_{13} = −5.8002206×10^{3}, 1.3914993, −4.8640239×10^{−2}, 4.1764768×10^{−5}, −1.4452093×10^{−8}, 6.5459673",
    ],
    text: [
      "The vapour pressure of saturated air at this temperature: the most water vapour the air can hold, expressed as a pressure.",
      PSYCHROLIB_CHECK,
    ],
    citations: [
      SATURATION,
      cite("bc2015", "p. 1", "The maximum amount of water vapour in any given air sample is dependent on the temperature and to a lesser extent the air pressure"),
    ],
  },
  "vapour-pressure": {
    title: "Vapour pressure",
    formula: ["p_{w} = φ · p_{ws}"],
    where: ["φ relative humidity as a fraction", "p_{ws} saturation vapour pressure"],
    text: ["The part of the atmospheric pressure exerted by the water vapour actually in the air."],
    citations: [cite("ashrae2017", "Ch. 1, Eq. 12 and 22")],
  },
  "humidity-ratio": {
    title: "Humidity ratio",
    formula: ["W = 0.621945 · p_{w} / (p − p_{w})"],
    where: ["p_{w} vapour pressure", "p atmospheric pressure", "0.621945 ratio of the molar masses of water and dry air"],
    text: [
      "Mass of water vapour carried by each kilogram of dry air, shown in g/kg.",
      PSYCHROLIB_CHECK,
    ],
    citations: [cite("ashrae2017", "Ch. 1, Eq. 20")],
  },
  "dew-point": {
    title: "Dew point",
    formula: ["p_{ws}(t_{d}) = p_{w}", "solved for t_{d}"],
    where: ["p_{w} vapour pressure of the air", "p_{ws} the saturation equation (Eq. 5 or 6)"],
    text: [
      "The temperature at which this air becomes saturated when it is cooled. Water condenses on anything that cools to it.",
      "PsychroMol solves the saturation equation backwards by bisection, to 10^{−10} °C, instead of using ASHRAE’s dew-point regressions (Eq. 37 and 38). PsychroLib does the same, for the reason quoted below; the regressions are kept in the test suite only as an independent check.",
      "Below 0 °C the ice equation is used, so the value there is a frost point.",
      PSYCHROLIB_CHECK,
    ],
    citations: [
      SATURATION,
      cite("psychrolib", "GetTDewPointFromVapPres", "The dew point temperature is solved by inverting the equation giving water vapor pressure at saturation from temperature rather than using the regressions provided by ASHRAE (eqn. 37 and 38) which are much less accurate and have a narrower range of validity."),
      cite("bc2015", "p. 3", "If the cooling reaches the dew point temperature, water condensation will occur."),
    ],
  },
  "wet-bulb": {
    title: "Wet-bulb temperature",
    formula: [
      "t* ≥ 0 °C:  W = ((2501 − 2.326 t*) W_{s}* − 1.006 (t − t*)) / (2501 + 1.86 t − 4.186 t*)",
      "t* < 0 °C:  W = ((2830 − 0.24 t*) W_{s}* − 1.006 (t − t*)) / (2830 + 1.86 t − 2.1 t*)",
      "solved for t*",
    ],
    where: ["t air temperature, °C", "t* wet-bulb temperature, °C", "W humidity ratio of the air", "W_{s}* saturation humidity ratio at t*"],
    text: [
      "The temperature a wetted thermometer settles at as water evaporates from it into this air. The drier the air, the further it falls below the air temperature; in saturated air the two are equal.",
      "The equations give W from t*, so PsychroMol finds t* by bisection between the dew point and the air temperature.",
      PSYCHROLIB_CHECK,
    ],
    citations: [
      cite("ashrae2017", "Ch. 1, Eq. 33 (t* ≥ 0 °C) and Eq. 35 (t* < 0 °C)"),
      cite("psychrolib", "GetTWetBulbFromHumRatio", "ASHRAE Handbook - Fundamentals (2017) ch. 1 eqn 33 and 35 solved for Tstar"),
      cite("bc2015", "pp. 5–6", "At 100% relative humidity, the wet and dry bulb temperatures are equal because no further evaporation is possible."),
    ],
  },
  "enthalpy": {
    title: "Specific enthalpy",
    formula: ["h = 1.006 t + W (2501 + 1.86 t)"],
    where: ["t air temperature, °C", "W humidity ratio, kg/kg", "h in kJ per kg of dry air"],
    text: [
      "The heat content of the air, counting both its temperature and the latent heat in its water vapour, from a zero at dry air and liquid water at 0 °C.",
    ],
    citations: [cite("ashrae2017", "Ch. 1, Eq. 30")],
  },
  "specific-volume": {
    title: "Specific volume",
    formula: ["v = 287.042 (t + 273.15)(1 + 1.607858 W) / p"],
    where: ["t air temperature, °C", "W humidity ratio, kg/kg", "p atmospheric pressure, Pa", "v in m³ per kg of dry air"],
    text: ["The volume taken up by the air that contains one kilogram of dry air."],
    citations: [cite("ashrae2017", "Ch. 1, Eq. 26")],
  },
  "density": {
    title: "Density",
    formula: ["ρ = (1 + W) / v"],
    where: ["W humidity ratio, kg/kg", "v specific volume, m³/kg"],
    text: ["Mass of moist air per cubic metre."],
    citations: [cite("ashrae2017", "Ch. 1, Eq. 11")],
  },
  "absolute-humidity": {
    title: "Absolute humidity",
    formula: ["d_{v} = M_{w} / V = W / v"],
    where: ["M_{w} mass of water vapour", "V volume of the air", "W humidity ratio, kg/kg", "v specific volume, m³/kg", "shown in g/m³ (× 1000)"],
    text: [
      "Grams of water vapour in each cubic metre of greenhouse air. ASHRAE defines it as the mass of water vapour over the volume of the sample; dividing the humidity ratio by the specific volume gives exactly that, because both are per kilogram of dry air.",
    ],
    citations: [cite("ashrae2017", "Ch. 1, definition of absolute humidity (water vapour density)"), cite("ashrae2017", "Ch. 1, Eq. 26 for v")],
  },
  "vpd": {
    title: "Vapour pressure deficit (VPD)",
    formula: ["VPD = p_{ws}(t) − p_{w} = p_{ws}(t) · (1 − RH/100)"],
    where: ["p_{ws}(t) saturation vapour pressure at the air temperature", "p_{w} vapour pressure of the air", "shown in kPa"],
    text: [
      "How far the air is from saturation at its own temperature: the atmospheric demand for water that drives transpiration.",
      "This is air VPD: it uses the air temperature. Leaf VPD would need the temperature of the leaves themselves, which the data source does not measure, so PsychroMol does not report it.",
    ],
    citations: [
      cite("shamshiri2018", "p. 290", "VPD is the difference between saturation vapour pressure (es) and the actual vapour pressure (ed)."),
      cite("bc2015", "p. 6", "Vapour Pressure Deficit - A measure of the atmospheric demand for water."),
      cite("shamshiri2018", "p. 292, VPD equation with the factor (1 − RH/100)"),
      cite("bc2015", "p. 6", "VPD’s for growing crops can only be calculated accurately when the surface temperature of the leaves is known."),
      SATURATION,
    ],
  },
  "thresholds": {
    title: "Temperature and humidity bands",
    text: [
      "These bands are yours to enter, with their source, for your crop and stage. PsychroMol ships no default, because no single level suits every crop.",
      "For orientation only: Shamshiri et al. (2018) note that greenhouse crops are mostly warm-season crops with optimal air temperatures between 17 and 27 °C, and that a relative humidity of 60–90 % is considered appropriate for most greenhouse tomato varieties.",
    ],
    citations: [
      cite("bc2015", "p. 3", "There is no one level of humidity that is good for all crops."),
      cite("shamshiri2018", "p. 289", "Greenhouse crops are mostly warm-season crops which are adapted to optimal air temperatures between 17-27°C, with the lower and upper marginal temperature of 10 and 35°C (Kittas et al., 2005)."),
      cite("shamshiri2018", "p. 290", "For most greenhouse tomato varieties, relative humidity range between 60-90% is considered appropriate by ASABE (2015) standards."),
    ],
  },
  "classification": {
    title: "LOW, OPTIMAL and HIGH",
    formula: ["value < minimum  → LOW", "minimum ≤ value ≤ maximum  → OPTIMAL", "value > maximum  → HIGH"],
    text: [
      "Temperature, relative humidity and VPD are each compared with their own band. The limits count as inside the band.",
      "Shamshiri et al. (2018) describe decision support that rates how close each of the three is to its optimum for the growth stage; PsychroMol uses only the optimal band, with no graded score.",
    ],
    citations: [cite("shamshiri2018", "pp. 294–295, microclimate evaluation with a decision support system")],
  },
  "rules": {
    title: "How a recommendation is chosen",
    text: [
      "Each rule names the state it needs for temperature, humidity and VPD (or any state). Every rule whose conditions all hold matches.",
      "The recommendation shown first is the matching rule with the worst severity; between equal severities, the lowest order number wins.",
      "Each rule carries its own source, shown with it.",
    ],
    citations: [],
  },
  "psychrometric-chart": {
    title: "Psychrometric chart",
    text: [
      "Temperature on the horizontal axis, humidity ratio on the vertical axis, drawn for the profile’s pressure.",
      "Every line comes from the equations behind the values: the saturation curve and relative-humidity curves from Eq. 5, 6, 12, 22 and 20; enthalpy lines from Eq. 30; wet-bulb lines from Eq. 33 and 35; specific-volume lines from Eq. 26.",
      "The shaded area is the profile’s temperature and humidity band, bounded above and below by real relative-humidity curves.",
    ],
    citations: [cite("ashrae2017", "Ch. 1, Eq. 5, 6, 12, 20, 22, 26, 30, 33 and 35")],
  },
  "mollier-chart": {
    title: "Mollier h–x diagram",
    formula: ["x axis: W (humidity ratio)", "y axis: h − 2501 · W"],
    where: ["h specific enthalpy (Eq. 30)", "2501 kJ/kg latent heat of vaporisation at 0 °C (Eq. 30)"],
    text: [
      "Mollier’s diagram for moist air plots enthalpy against humidity ratio. PsychroMol skews the enthalpy axis by 2501 · W so that the 0 °C isotherm runs horizontally and the other isotherms stay nearly flat; the lines of constant enthalpy then slope downward.",
      "The curves are the same equations as on the psychrometric chart, projected onto these axes.",
    ],
    citations: [cite("mollier1923", "the h–x diagram for moist air"), cite("ashrae2017", "Ch. 1, Eq. 30")],
  },
};
