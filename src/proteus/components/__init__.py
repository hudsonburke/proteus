"""Component-level parametric CAD objects."""

from .fastener import (
    ClearanceHole,
    HeatSetNut,
    HexNut,
    InsertHole,
    Nut,
    PlainWasher,
    Screw,
    SocketHeadCapScrew,
    TapHole,
    ThreadedHole,
    Washer,
)
from .thread import (
    AcmeThread,
    IsoThread,
    MetricTrapezoidalThread,
    PlasticBottleThread,
    Thread,
    TrapezoidalThread,
)

__all__: list[str] = [
    "AcmeThread",
    "ClearanceHole",
    "HeatSetNut",
    "HexNut",
    "InsertHole",
    "IsoThread",
    "MetricTrapezoidalThread",
    "Nut",
    "PlainWasher",
    "PlasticBottleThread",
    "Screw",
    "SocketHeadCapScrew",
    "TapHole",
    "Thread",
    "ThreadedHole",
    "TrapezoidalThread",
    "Washer",
]
