import pint

from typing import Final

_ureg = pint.UnitRegistry[float]()

LENGTH_UNIT: Final[str] = "mm"
ANGLE_UNIT: Final[str] = "deg"
MASS_UNIT: Final[str] = "kg"
TIME_UNIT: Final[str] = "s"
FORCE_UNIT: Final[str] = "N"
TORQUE_UNIT: Final[str] = f"{FORCE_UNIT}*{LENGTH_UNIT}"
INERTIA_UNIT: Final[str] = f"{MASS_UNIT}*{LENGTH_UNIT}^2"
ACCELERATION_UNIT: Final[str] = f"{LENGTH_UNIT}/{TIME_UNIT}^2"


def convert(value: float, unit: str) -> float:
    """Convert a physical quantity to the CAD-native unit.

    Lengths → mm.  Angles → degrees.

    >>> convert(124, "in")
    3149.6
    >>> convert(1.57, "rad")
    89.95...
    >>> convert(90, "deg")
    90.0
    """
    q = _ureg.Quantity(value, unit)
    if q.check("[length]"):
        return q.to(_ureg.mm).magnitude
    if q.check("[angle]"):
        return q.to(_ureg.degrees).magnitude
    raise ValueError(f"Unsupported unit dimension: {q.dimensionality}")
