"""Cross-check against an export from an independent psychrometric tool.

``data/reference/external-tool-benchmark.csv`` is a point export produced by a
third-party psychrometric chart application (the researcher's earlier
browser-based tool, ``psychrometric-mollier``). It is used here as a fourth,
fully independent verification source -- independent in the strong sense that
it was computed by different code, by a different formulation, at a different
time.

**What the tolerances mean.** That tool evaluates saturation vapour pressure
with the Magnus / Alduchov-Eskridge form
``p_ws = 610.94 exp(17.625 t / (t + 243.04))``, which departs from ASHRAE
Eq. (6) by up to roughly 0.4 % over 0..50 degC, and it prints only 4-6
significant figures. The tolerances below are therefore sized to *that tool's*
accuracy, not to this engine's. Agreement at this level confirms that the two
implementations agree on the physics; it does not and cannot confirm the last
digit of either.

The file is a **reference dataset, not experimental greenhouse data**, and is
labelled as such in ``data/reference/README.md``.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from psychromol.core import state as st
from psychromol.core.constants import STANDARD_PRESSURE_PA

BENCHMARK_FILE = (
    Path(__file__).resolve().parents[1] / "data" / "reference" / "external-tool-benchmark.csv"
)

COLUMN_HUMIDITY_RATIO = "W (kg/kg')"

def _load_benchmark() -> list[dict[str, str]]:
    if not BENCHMARK_FILE.exists():
        pytest.skip(f"benchmark file missing: {BENCHMARK_FILE}")
    with BENCHMARK_FILE.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))

BENCHMARK_ROWS = _load_benchmark()

@pytest.mark.parametrize(
    "row", BENCHMARK_ROWS, ids=[f"{r['Tdb (°C)']}C/{r['RH (%)']}%" for r in BENCHMARK_ROWS]
)
def test_engine_agrees_with_independent_tool(row):
    temperature = float(row["Tdb (°C)"])
    relative_humidity = float(row["RH (%)"])
    state = st.from_temperature_relative_humidity(
        temperature, relative_humidity, STANDARD_PRESSURE_PA
    )

    # Humidity ratio: 5e-5 kg/kg absolute covers the Magnus-vs-ASHRAE gap
    assert state.humidity_ratio == pytest.approx(
        float(row[COLUMN_HUMIDITY_RATIO]), abs=5e-5
    )
    assert state.wet_bulb == pytest.approx(float(row["Twb (°C)"]), abs=0.05)
    assert state.dew_point == pytest.approx(float(row["Tdp (°C)"]), abs=0.05)
    assert state.enthalpy == pytest.approx(float(row["h (kJ/kg)"]), abs=0.15)
    assert state.specific_volume == pytest.approx(float(row["v (m³/kg)"]), abs=5e-4)
    assert state.density == pytest.approx(float(row["ρ (kg/m³)"]), abs=5e-4)
    assert state.absolute_humidity == pytest.approx(float(row["AH (g/m³)"]), abs=0.1)

def test_benchmark_file_is_not_empty():
    assert len(BENCHMARK_ROWS) >= 5
