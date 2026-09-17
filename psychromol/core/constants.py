"""Physical constants for moist-air psychrometrics.

Every constant is taken from ASHRAE Handbook -- Fundamentals (2017),
Chapter 1 "Psychrometrics", and names the equation it appears in. They are
defined exactly once in this project; no other module may redefine them
(brief SS61: no duplicated formulas).

Base units in this package
--------------------------
temperature      degree Celsius        [degC]
pressure         pascal                [Pa]
humidity ratio   kg water / kg dry air [kg/kg_da]
enthalpy         kilojoule / kg dry air[kJ/kg_da]
specific volume  cubic metre / kg d.a. [m3/kg_da]

Pascal is the internal pressure unit because ASHRAE's saturation correlations
are written in Pa. The API and the user interface work in kPa; conversion
happens explicitly, in ``units.py``, at the boundary -- never implicitly.
"""

from __future__ import annotations

#: Ratio of molecular masses, M_water / M_dry_air = 18.015268 / 28.966.
#: ASHRAE Fundamentals 2017, Ch. 1, used throughout Eq. (20)-(24).
MW_RATIO: float = 0.621945

#: Reciprocal of MW_RATIO as printed in ASHRAE Eq. (26).
SPECIFIC_VOLUME_W_COEFF: float = 1.607858

#: Specific gas constant of dry air [J/(kg*K)]. ASHRAE prints
#: 0.287042 kJ/(kg*K) in Eq. (26); this package works in Pa, hence J.
R_DRY_AIR: float = 287.042

#: Specific heat of dry air [kJ/(kg*K)] -- ASHRAE Eq. (30).
CP_DRY_AIR: float = 1.006

#: Specific heat of water vapour [kJ/(kg*K)] -- ASHRAE Eq. (30).
CP_WATER_VAPOUR: float = 1.86

#: Specific heat of liquid water [kJ/(kg*K)] -- ASHRAE Eq. (33).
CP_LIQUID_WATER: float = 4.186

#: Specific heat of ice [kJ/(kg*K)] -- ASHRAE Eq. (34).
CP_ICE: float = 2.1

#: Latent heat of vaporisation of water at 0 degC [kJ/kg] -- ASHRAE Eq. (30).
H_FG_0C: float = 2501.0

#: Latent heat of sublimation of ice at 0 degC [kJ/kg] -- ASHRAE Eq. (34).
H_IG_0C: float = 2830.0

#: 0 degC expressed in kelvin.
ZERO_CELSIUS_IN_KELVIN: float = 273.15

#: Standard atmospheric pressure at sea level [Pa] -- ASHRAE Eq. (3) at Z = 0.
#: A DEFAULT ONLY. Every relation that depends on pressure takes it as an
#: argument; nothing in this package assumes sea level.
STANDARD_PRESSURE_PA: float = 101325.0

#: Validity range of the Hyland-Wexler correlations, ASHRAE Eq. (5) and (6).
#: Inputs outside this range are rejected rather than extrapolated.
MIN_TEMPERATURE_C: float = -100.0
MAX_TEMPERATURE_C: float = 200.0

#: Physically admissible total pressure [Pa]. The lower bound is roughly the
#: standard atmosphere at 11 km; the upper bound leaves room for a pressurised
#: chamber. Outside this, an input is a unit mistake, not a measurement.
MIN_PRESSURE_PA: float = 20000.0
MAX_PRESSURE_PA: float = 200000.0
