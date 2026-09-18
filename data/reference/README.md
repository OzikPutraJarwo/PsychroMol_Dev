# Reference data — NOT experimental data

Files in this directory exist **solely to verify the psychrometric engine**.
None of them is a greenhouse measurement, and none of them may be cited as
experimental evidence.

| File | Origin | Role |
|---|---|---|
| `psychrolib-grid.json` | 102 points generated once with PsychroLib 2.5.0 (SI), an independent implementation of the same ASHRAE chapter | Cross-check of every property in `tests/js/psychro.test.mjs` and `scripts/verify_engine.mjs` |
| `external-tool-benchmark.csv` | Point export from the researcher's earlier browser tool `psychrometric-mollier`, which uses the Magnus / Alduchov–Eskridge saturation formulation | Independent cross-check of the ASHRAE engine |

`psychrolib-grid.json` covers −10…50 °C × 5…100 % RH at 101.325 kPa, plus
25 °C / 70 % at 85, 95 and 105 kPa, and stores humidity ratio, dew point, wet
bulb, enthalpy, specific volume, density and VPD for each point. It is a
**file**, not a dependency: PsychroLib is never imported at runtime or by the
test suite. Its header records the library version and the functions used, so
it can be regenerated. Reference: Meyer, D. and Thevenard, D. (2019).
PsychroLib: a library of psychrometric functions to calculate thermodynamic
properties of air. *Journal of Open Source Software*, 4(33), 1137.
<https://doi.org/10.21105/joss.01137>

The Magnus form in the CSV differs from ASHRAE Eq. (6) by up to ~0.4 % over
0–50 °C. The test tolerances are sized to that difference and to the file's
printed precision. Agreement confirms the two implementations share the same
physics; it does not validate either to its last digit. The authoritative
validation is against the ASHRAE tables and ASHRAE's worked Example 1 — see
`tests/js/psychro.test.mjs` and `docs/psychrometric-methodology.md`.
