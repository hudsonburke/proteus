"""Component-level parametric CAD objects."""

from .cuff import Cuff
from .bearing import (
    Bearing,
    SingleRowCappedDeepGrooveBallBearing,
    SingleRowDeepGrooveBallBearing,
    SingleRowTaperedRollerBearing,
)
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
from .flange import BlindFlange, Flange, SlipOnFlange
from .gear import InvoluteToothProfile, SpurGear, SpurGearPlan
from .pipe import Pipe, PipeSection
from .sprocket import Sprocket
from .thread import (
    AcmeThread,
    IsoThread,
    MetricTrapezoidalThread,
    PlasticBottleThread,
    Thread,
    TrapezoidalThread,
)

__all__: list[str] = [
    "Cuff",
    "AcmeThread",
    "Bearing",
    "BlindFlange",
    "ClearanceHole",
    "Flange",
    "HeatSetNut",
    "HexNut",
    "InsertHole",
    "InvoluteToothProfile",
    "IsoThread",
    "MetricTrapezoidalThread",
    "Nut",
    "Pipe",
    "PipeSection",
    "PlainWasher",
    "PlasticBottleThread",
    "Screw",
    "SingleRowCappedDeepGrooveBallBearing",
    "SingleRowDeepGrooveBallBearing",
    "SingleRowTaperedRollerBearing",
    "SlipOnFlange",
    "SocketHeadCapScrew",
    "SpurGear",
    "SpurGearPlan",
    "Sprocket",
    "TapHole",
    "Thread",
    "ThreadedHole",
    "TrapezoidalThread",
    "Washer",
]
