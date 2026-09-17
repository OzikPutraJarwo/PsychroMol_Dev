"""PsychroMol scientific core.

Dependency-free by design: this package imports nothing but the Python
standard library, so the psychrometric calculations can be reproduced and
audited without installing a web framework, a database driver or a plotting
library.

    >>> from psychromol.core import from_temperature_relative_humidity
    >>> state = from_temperature_relative_humidity(20.0, 50.0)
    >>> round(state.vpd_kpa, 4)
    1.1694

Scientific basis: ASHRAE Handbook -- Fundamentals (2017), Chapter 1. Each
relation names its equation number; see ``docs/psychrometric-methodology.md``.
"""

from .constants import STANDARD_PRESSURE_PA
from .mollier import MollierPoint, project, project_values
from .psychrometrics import PsychrometricRangeError, standard_atmospheric_pressure
from .state import (
    MoistAirState,
    from_temperature_dew_point,
    from_temperature_humidity_ratio,
    from_temperature_relative_humidity,
    from_temperature_wet_bulb,
)

__all__ = [
    "MoistAirState",
    "MollierPoint",
    "PsychrometricRangeError",
    "STANDARD_PRESSURE_PA",
    "from_temperature_relative_humidity",
    "from_temperature_dew_point",
    "from_temperature_wet_bulb",
    "from_temperature_humidity_ratio",
    "project",
    "project_values",
    "standard_atmospheric_pressure",
]
