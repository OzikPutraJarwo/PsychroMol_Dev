"""Mollier h-x projection.

The psychrometric chart (ASHRAE convention) and the Mollier h-x diagram
(European convention) are **not two calculations**. They are two projections of
the same evaluated :class:`~psychromol.core.state.MoistAirState`:

=================  ==========================  ==========================
Diagram            abscissa                    ordinate
=================  ==========================  ==========================
Psychrometric      dry-bulb temperature ``t``  humidity ratio ``W``
Mollier h-x        humidity ratio ``x = W``    ``h - 2501 W``
=================  ==========================  ==========================

The ordinate skew is exactly the latent heat of vaporisation at 0 degC, which
is what makes the 0 degC isotherm horizontal and gives the Mollier chart its
characteristic shape. Because the skew is a pure coordinate transform of
quantities already in the state, switching chart mode in the interface
**re-projects; it never recomputes** (brief SS13). The current point, the
target zone and the historical trajectory all carry over unchanged.

This module therefore contains coordinate transforms only -- no thermodynamics.
"""

from __future__ import annotations

from dataclasses import dataclass

from .constants import CP_DRY_AIR, CP_WATER_VAPOUR, H_FG_0C
from .state import MoistAirState

__all__ = [
    "MollierPoint",
    "mollier_ordinate",
    "enthalpy_from_mollier_ordinate",
    "project",
    "project_values",
    "isotherm_ordinate",
]


@dataclass(frozen=True, slots=True)
class MollierPoint:
    """A state expressed in h-x chart coordinates.

    ``x`` is the humidity ratio in g/kg dry air (the axis label on a Mollier
    chart), ``y`` the skewed enthalpy ordinate in kJ/kg dry air. ``enthalpy``
    is carried alongside because the chart's isenthalp labels report the true
    enthalpy, not the skewed ordinate.
    """

    x: float
    y: float
    enthalpy: float
    temperature: float


def mollier_ordinate(enthalpy: float, humidity_ratio: float) -> float:
    """The skewed ordinate ``h - 2501 W`` [kJ/kg dry air].

    Subtracting ``H_FG_0C * W`` from the enthalpy is the Mollier skew. Note
    the result equals ``1.006 t + 1.86 W t``, i.e. the *sensible* part of the
    enthalpy -- which is the physical reason the 0 degC isotherm is flat.
    """
    return enthalpy - H_FG_0C * humidity_ratio


def enthalpy_from_mollier_ordinate(ordinate: float, humidity_ratio: float) -> float:
    """Invert :func:`mollier_ordinate`."""
    return ordinate + H_FG_0C * humidity_ratio


def isotherm_ordinate(temperature: float, humidity_ratio: float) -> float:
    """Ordinate of the constant-temperature line at ``W``.

    ``y = (1.006 + 1.86 W) t`` -- linear in ``W`` with slope ``1.86 t``, hence
    horizontal at ``t = 0``. Drawing isotherms from this closed form rather
    than by evaluating full states keeps the chart geometry cheap.
    """
    return (CP_DRY_AIR + CP_WATER_VAPOUR * humidity_ratio) * temperature


def project(state: MoistAirState) -> MollierPoint:
    """Re-project an evaluated state into h-x coordinates. No recomputation."""
    return MollierPoint(
        x=state.humidity_ratio * 1000.0,
        y=mollier_ordinate(state.enthalpy, state.humidity_ratio),
        enthalpy=state.enthalpy,
        temperature=state.temperature,
    )


def project_values(temperature: float, humidity_ratio: float) -> MollierPoint:
    """Project a bare ``(t, W)`` pair, for chart geometry.

    Uses Eq. (30) for the enthalpy directly rather than assembling a full
    state, because chart curves need thousands of points and none of the other
    state properties.
    """
    enthalpy = CP_DRY_AIR * temperature + humidity_ratio * (
        H_FG_0C + CP_WATER_VAPOUR * temperature
    )
    return MollierPoint(
        x=humidity_ratio * 1000.0,
        y=mollier_ordinate(enthalpy, humidity_ratio),
        enthalpy=enthalpy,
        temperature=temperature,
    )
