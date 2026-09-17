# Reference data — NOT experimental data

Files in this directory exist **solely to verify the psychrometric engine**.
None of them is a greenhouse measurement, and none of them may be cited as
experimental evidence.

| File | Origin | Role |
|---|---|---|
| `external-tool-benchmark.csv` | Point export from the researcher's earlier browser tool `psychrometric-mollier`, which uses the Magnus / Alduchov–Eskridge saturation formulation | Independent cross-check of the ASHRAE engine (`tests/test_external_benchmark.py`) |

The Magnus form differs from ASHRAE Eq. (6) by up to ~0.4 % over 0–50 °C. The
test tolerances are sized to that difference and to the file's printed
precision, and are justified in the test docstring. Agreement confirms the two
implementations share the same physics; it does not validate either to its last
digit. The authoritative validation is against the ASHRAE tables, ASHRAE's
worked Example 1 and `psychrolib` — see `tests/test_psychrometrics.py`.
