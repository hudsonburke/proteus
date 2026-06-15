"""Parametric thread components adapted from bd_warehouse.

Provides general helical threads (``Thread``) and standardised thread forms:
``IsoThread``, ``TrapezoidalThread``, ``AcmeThread``, ``MetricTrapezoidalThread``,
and ``PlasticBottleThread``.  All classes produce build123d geometry and expose it
through the Proteus ``BasePart`` contract.
"""

from __future__ import annotations
from typing import ClassVar, Literal
import copy
import re
from math import copysign, radians, tan

import build123d as bd

from proteus.common import BasePart, convert

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_safe(value: str) -> bool:
    """Return True when *value* can be safely passed to :func:`eval`."""
    return len(value) <= 10 and all(c in "0123456789./ " for c in set(value))


def _imperial_str_to_float(measure: str) -> float:
    """Convert an imperial measurement (possibly a fraction) to a float in mm."""
    if _is_safe(measure):
        # The string is verified as safe before eval() is called.
        result = convert(eval(measure.strip().replace(" ", "+")), "in")  # noqa: S307
    else:
        result = convert(float(measure), "in")
    return result


EndFinish = Literal["raw", "square", "fade", "chamfer"]
Hand = Literal["right", "left"]

_VALID_FINISHES = {"raw", "square", "fade", "chamfer"}

# ---------------------------------------------------------------------------
# Thread  –  general helical thread
# ---------------------------------------------------------------------------


class Thread(BasePart):
    """Helical thread.

    The most general thread class used to build all of the other threads.
    Creates right- or left-hand helical thread with the given root and apex
    radii.
    """

    apex_radius: float
    apex_width: float
    root_radius: float
    root_width: float
    pitch: float
    length: float
    apex_offset: float = 0.0
    interference: float = 0.2
    hand: Hand = "right"
    end_finishes: tuple[EndFinish, EndFinish] = ("raw", "raw")
    simple: bool = False

    # -- helpers called from _build_geometry ---------------------------------

    def _make_thread_loop(self, loop_height: float) -> bd.Solid:
        """Create one full or partial helical loop of thread.

        Args:
            loop_height: 0.0 < height <= 1.0 as a fraction of one pitch.
        """
        if not 0.0 < loop_height <= 1.0:
            raise ValueError(f"Invalid loop_height ({loop_height})")

        with bd.BuildPart() as thread_loop:
            with bd.BuildLine():
                thread_path_wire: bd.Wire = bd.Helix(
                    pitch=self.pitch,
                    height=loop_height * self.pitch,
                    radius=self.root_radius,
                    lefthand=not self._right_hand,
                )
            for i in range(11):
                u_value = i / 10
                with bd.BuildSketch(
                    bd.Plane(
                        thread_path_wire @ u_value,
                        x_dir=(0, 0, 1),
                        z_dir=thread_path_wire % u_value,
                    )
                ):
                    bd.add(self._thread_profile)
            bd.loft()

        loop = thread_loop.part.solids()[0]
        for i in range(2):
            bd.RigidJoint(str(i), loop, thread_path_wire.location_at(i))
        return loop

    def _make_fade_end(self, bottom: bool) -> bd.Solid:
        """Create a tapered tip that fades to almost nothing.

        Args:
            bottom: True for the bottom end, False for the top.
        """
        direction = -1 if bottom else 1
        height = min(self.pitch / 4, self.length / 2)
        with bd.BuildPart() as fade_tip:
            with bd.BuildLine():
                fade_path_wire: bd.Wire = bd.Helix(
                    pitch=self.pitch,
                    height=direction * height,
                    radius=self.root_radius,
                    lefthand=not self._right_hand,
                )
            for i in range(11):
                u_value = i / 10
                z_dir = fade_path_wire % u_value
                if bottom:
                    z_dir = z_dir.reverse()
                with bd.BuildSketch(
                    bd.Plane(
                        fade_path_wire @ u_value, x_dir=(0, 0, 1), z_dir=z_dir
                    )
                ):
                    bd.add(self._thread_profile)
                    bd.scale(by=(11 - i) / 11)
            bd.loft()

        tip = fade_tip.part.solids()[0]
        bd.RigidJoint(
            "0",
            tip,
            fade_path_wire.location_at(0)
            * bd.Location((0, 0, 0), (1, 0, 0), 180),
        )
        bd.RigidJoint("1", tip, fade_path_wire.location_at(0))
        return tip

    def _make_chamfer_shape(self) -> bd.Solid:
        """Create the shape that will intersect with the thread to chamfer ends."""
        inside_radius = min(self.apex_radius, self.root_radius)
        outside_radius = max(self.apex_radius, self.root_radius) + 0.001

        if self._external:
            chamfer_shape = bd.Solid.extrude(
                bd.Face(bd.Wire.make_circle(outside_radius)),
                (0, 0, self.length),
            )
        else:
            inside_radius -= 0.01
            chamfer_shape = bd.Solid.extrude(
                bd.Face(
                    bd.Wire.make_circle(2 * outside_radius),
                    [bd.Wire.make_circle(inside_radius)],
                ),
                (0, 0, self.length),
            )

        thickness = outside_radius - inside_radius
        for i in range(2):
            if self.end_finishes[i] == "chamfer":
                chamfer_edges = (
                    chamfer_shape.edges()
                    .group_by(bd.Axis.Z, reverse=i != 0)[0]
                    .sort_by(
                        bd.SortBy.RADIUS,
                        reverse=self.apex_radius > self.root_radius,
                    )[0:1]
                )
                chamfer_shape = chamfer_shape.chamfer(
                    thickness / 2, thickness / 2, chamfer_edges
                )
        return chamfer_shape

    # -- geometry ------------------------------------------------------------

    def _build_geometry(self) -> None:
        # Validate end finishes
        for finish in self.end_finishes:
            if finish not in _VALID_FINISHES:
                raise ValueError(
                    f"end_finishes invalid, must be tuple of {sorted(_VALID_FINISHES)}"
                )

        self._external: bool = self.apex_radius > self.root_radius
        self._right_hand: bool = self.hand == "right"

        tooth_height = abs(self.apex_radius - self.root_radius)
        self._thread_loops: float | None = None

        # Build the thread profile sketch
        with bd.BuildSketch(mode=bd.Mode.PRIVATE) as thread_face:
            height = self.apex_radius - self.root_radius
            overlap = -self.interference * copysign(1, height)
            with bd.BuildLine():
                if overlap == 0:
                    bd.Polyline(
                        (self.root_width / 2, 0),
                        (
                            self.apex_width / 2 + self.apex_offset,
                            height,
                        ),
                        (
                            -self.apex_width / 2 + self.apex_offset,
                            height,
                        ),
                        (-self.root_width / 2, 0),
                        close=True,
                    )
                else:
                    bd.Polyline(
                        (self.root_width / 2, overlap),
                        (self.root_width / 2, 0),
                        (
                            self.apex_width / 2 + self.apex_offset,
                            height,
                        ),
                        (
                            -self.apex_width / 2 + self.apex_offset,
                            height,
                        ),
                        (-self.root_width / 2, 0),
                        (-self.root_width / 2, overlap),
                        close=True,
                    )
                if not self._right_hand:
                    bd.mirror(about=bd.Plane.XZ, mode=bd.Mode.REPLACE)
            bd.make_face()
        self._thread_profile = thread_face.sketch_local.faces()[0]

        if self.simple:
            self.geom = bd.Compound()
            return

        # Create the base cylindrical thread
        number_faded_ends = self.end_finishes.count("fade")
        cylindrical_thread_length = self.length + self.pitch * (
            1 - 1 * number_faded_ends
        )
        self._thread_loops = cylindrical_thread_length / self.pitch

        if self.end_finishes[0] == "fade":
            cylindrical_thread_displacement = self.pitch / 2
        else:
            cylindrical_thread_displacement = -self.pitch / 2

        loops: list[bd.Solid] = []
        if self._thread_loops >= 1.0:
            full_loop = self._make_thread_loop(1.0)
            full_loop.label = "loop"
            loops = [copy.copy(full_loop) for _ in range(int(self._thread_loops))]
        if self._thread_loops % 1 > 0.0:
            last_loop = self._make_thread_loop(self._thread_loops % 1)
            last_loop.label = "partial"
            loops.append(last_loop)

        loops[0].locate(
            bd.Location((0, 0, cylindrical_thread_displacement))
        )
        for i in range(1, len(loops)):
            loops[i - 1].joints["1"].connect_to(loops[i].joints["0"])

        bd_object = bd.Compound(label="thread", children=loops)

        # Pre-compute chamfer shape if needed
        chamfer_shape: bd.Solid | None = None
        if self.end_finishes.count("chamfer") != 0:
            chamfer_shape = self._make_chamfer_shape()

        # Bottom end finish
        if self.end_finishes[0] == "fade":
            start_tip = self._make_fade_end(True)
            start_tip.label = "bottom_tip"
            loops[0].joints["0"].connect_to(start_tip.joints["0"])
            bd_object.children = list(bd_object.children) + [start_tip]
        elif self.end_finishes[0] in {"square", "chamfer"}:
            children = list(bd_object.children)
            bottom_loop = children.pop(0)
            label = bottom_loop.label
            if self.end_finishes[0] == "square":
                bottom_loop = bd.split(
                    bottom_loop, bisect_by=bd.Plane.XY, keep=bd.Keep.TOP
                )
            else:
                assert chamfer_shape is not None
                bottom_loop = bottom_loop.intersect(chamfer_shape)
                if isinstance(bottom_loop, list):
                    bottom_loop = bottom_loop[0]
            bottom_loop.label = label
            bd_object.children = [bottom_loop] + children

        # Top end finish
        if self.end_finishes[1] == "fade":
            end_tip = self._make_fade_end(False)
            end_tip.label = "top_tip"
            loops[-1].joints["1"].connect_to(end_tip.joints["1"])
            bd_object.children = list(bd_object.children) + [end_tip]
        elif self.end_finishes[1] in {"square", "chamfer"}:
            children = list(bd_object.children)
            top_loops: list[bd.Solid] = []
            last_square = False
            for _ in range(3):
                if not children:
                    continue
                top_loop = children.pop(-1)
                label = top_loop.label
                bbox = top_loop.bounding_box()
                if bbox.min.Z > self.length:
                    continue
                if self.end_finishes[1] == "square":
                    if bbox.max.Z < self.length:
                        last_square = True
                    else:
                        top_loop = bd.split(
                            top_loop,
                            bisect_by=bd.Plane.XY.offset(self.length),
                            keep=bd.Keep.BOTTOM,
                        )
                else:
                    assert chamfer_shape is not None
                    top_loop = top_loop.intersect(chamfer_shape)
                    if isinstance(top_loop, list):
                        top_loop = top_loop[0]
                if top_loop.volume != 0:
                    top_loop.label = label
                    top_loops.append(top_loop)
                if last_square:
                    break
            bd_object.children = children + top_loops

        self.geom = bd_object


# ---------------------------------------------------------------------------
# IsoThread  –  ISO 60° metric thread
# ---------------------------------------------------------------------------


class IsoThread(BasePart):
    """ISO standard 60° metric thread.

    Both external and internal ISO standard threads.
    """

    major_diameter: float
    pitch: float
    length: float
    external: bool = True
    hand: Hand = "right"
    end_finishes: tuple[EndFinish, EndFinish] = ("fade", "square")
    interference: float = 0.2
    simple: bool = False

    thread_angle: float = 60.0

    # ------------------------------------------------------------------

    def _build_geometry(self) -> None:
        _validate_hand(self.hand)
        _validate_end_finishes(self.end_finishes)

        h_param = (self.pitch / 2) / tan(radians(self.thread_angle / 2))
        min_radius = (self.major_diameter - 2 * (5 / 8) * h_param) / 2

        if self.external:
            apex_radius = self.major_diameter / 2
            apex_width = self.pitch / 8
            root_radius = min_radius
            root_width = 3 * self.pitch / 4
        else:
            apex_radius = min_radius
            apex_width = self.pitch / 4
            root_radius = self.major_diameter / 2
            root_width = 7 * self.pitch / 8

        if self.simple:
            self.geom = bd.Compound()
            return

        inner = Thread(
            apex_radius=apex_radius,
            apex_width=apex_width,
            root_radius=root_radius,
            root_width=root_width,
            pitch=self.pitch,
            length=self.length,
            interference=self.interference,
            end_finishes=self.end_finishes,
            hand=self.hand,
            simple=False,
        )
        self.geom = bd.Compound(children=list(inner.geom.solids()))


# ---------------------------------------------------------------------------
# TrapezoidalThread  –  base trapezoidal thread
# ---------------------------------------------------------------------------


class TrapezoidalThread(BasePart):
    """Trapezoidal thread base class.

    Trapezoidal thread forms are screw thread profiles with trapezoidal
    outlines, commonly used for leadscrews (power screws).  Can be used
    directly with arbitrary parameters, or through derived size-based
    classes like ``AcmeThread`` and ``MetricTrapezoidalThread``.
    """

    diameter: float
    pitch: float
    thread_angle: float
    length: float
    external: bool = True
    starts: int = 1
    hand: Hand = "right"
    end_finishes: tuple[EndFinish, EndFinish] = ("fade", "fade")
    interference: float = 0.2

    # ------------------------------------------------------------------

    def _build_geometry(self) -> None:
        _validate_hand(self.hand)
        _validate_end_finishes(self.end_finishes)

        lead = self.pitch * self.starts
        shoulder_width = (self.pitch / 2) * tan(
            radians(self.thread_angle / 2)
        )
        apex_width = (self.pitch / 2) - shoulder_width
        root_width = (self.pitch / 2) + shoulder_width

        if self.external:
            apex_radius = self.diameter / 2
            root_radius = self.diameter / 2 - self.pitch / 2
        else:
            apex_radius = self.diameter / 2 - self.pitch / 2
            root_radius = self.diameter / 2

        inner = Thread(
            apex_radius=apex_radius,
            apex_width=apex_width,
            root_radius=root_radius,
            root_width=root_width,
            pitch=lead,
            length=self.length,
            interference=self.interference,
            end_finishes=self.end_finishes,
            hand=self.hand,
        )

        self.geom = bd.Compound(
            children=[
                copy.copy(inner.geom).move(
                    bd.Rot(Z=i * (360 / self.starts))
                )
                for i in range(self.starts)
            ]
        )


# ---------------------------------------------------------------------------
# AcmeThread  –  ACME 29° imperial thread
# ---------------------------------------------------------------------------


class AcmeThread(BasePart):
    """ACME thread (29° trapezoidal, imperial sizes)."""

    _acme_pitch: ClassVar[dict[str, float]] = {
        "1/4": convert(1 / 16, "in"),
        "5/16": convert(1 / 14, "in"),
        "3/8": convert(1 / 12, "in"),
        "1/2": convert(1 / 10, "in"),
        "5/8": convert(1 / 8, "in"),
        "3/4": convert(1 / 6, "in"),
        "7/8": convert(1 / 6, "in"),
        "1": convert(1 / 5, "in"),
        "1 1/4": convert(1 / 5, "in"),
        "1 1/2": convert(1 / 4, "in"),
        "1 3/4": convert(1 / 4, "in"),
        "2": convert(1 / 4, "in"),
        "2 1/2": convert(1 / 3, "in"),
        "3": convert(1 / 2, "in"),
    }

    thread_angle: float = 29.0

    size: str
    length: float
    external: bool = True
    hand: Hand = "right"
    end_finishes: tuple[EndFinish, EndFinish] = ("fade", "fade")
    interference: float = 0.2

    @classmethod
    def sizes(cls) -> list[str]:
        """Return the list of available ACME thread size strings."""
        return list(cls._acme_pitch.keys())

    # ------------------------------------------------------------------

    def _build_geometry(self) -> None:
        diameter = _imperial_str_to_float(self.size)
        try:
            pitch = self._acme_pitch[self.size]
        except KeyError as exc:
            raise ValueError(
                f"Invalid screw size {self.size!r}; "
                f"valid sizes: {self.sizes()}"
            ) from exc

        inner = TrapezoidalThread(
            diameter=diameter,
            pitch=pitch,
            thread_angle=self.thread_angle,
            length=self.length,
            external=self.external,
            hand=self.hand,
            end_finishes=self.end_finishes,
            interference=self.interference,
        )
        self.geom = inner.geom


# ---------------------------------------------------------------------------
# MetricTrapezoidalThread  –  ISO 2904 metric trapezoidal thread
# ---------------------------------------------------------------------------


class MetricTrapezoidalThread(BasePart):
    """ISO 2904 metric trapezoidal thread (30° thread angle)."""

    standard_sizes: ClassVar[list[str]] = [
        "8x1.5", "9x1.5", "9x2", "10x1.5", "10x2", "11x2", "11x3",
        "12x2", "12x3", "14x2", "14x3", "16x2", "16x3", "16x4", "18x2",
        "18x3", "18x4", "20x2", "20x3", "20x4", "22x3", "22x5", "22x8",
        "24x3", "24x5", "24x8", "26x3", "26x5", "26x8", "28x3", "28x5",
        "28x8", "30x3", "30x6", "30x10", "32x3", "32x6", "32x10", "34x3",
        "34x6", "34x10", "36x3", "36x6", "36x10", "38x3", "38x7", "38x10",
        "40x3", "40x7", "40x10", "42x3", "42x7", "42x10", "44x3", "44x7",
        "44x12", "46x3", "46x8", "46x12", "48x3", "48x8", "48x12", "50x3",
        "50x8", "50x12", "52x3", "52x8", "52x12", "55x3", "55x9", "55x14",
        "60x3", "60x9", "60x14", "65x4", "65x10", "65x16", "70x4", "70x10",
        "70x16", "75x4", "75x10", "75x16", "80x4", "80x10", "80x16", "85x4",
        "85x12", "85x18", "90x4", "90x12", "90x18", "95x4", "95x12",
        "95x18", "100x4", "100x12", "100x20", "105x4", "105x12", "105x20",
        "110x4", "110x12", "110x20", "115x6", "115x12", "115x14",
        "115x22", "120x6", "120x12", "120x14", "120x22", "125x6",
        "125x12", "125x14", "125x22", "130x6", "130x12", "130x14",
        "130x22", "135x6", "135x12", "135x14", "135x24", "140x6",
        "140x12", "140x14", "140x24", "145x6", "145x12", "145x14",
        "145x24", "150x6", "150x12", "150x16", "150x24", "155x6",
        "155x12", "155x16", "155x24", "160x6", "160x12", "160x16",
        "160x28", "165x6", "165x12", "165x16", "165x28", "170x6",
        "170x12", "170x16", "170x28", "175x8", "175x12", "175x16",
        "175x28", "180x8", "180x12", "180x18", "180x28", "185x8",
        "185x12", "185x18", "185x24", "185x32", "190x8", "190x12",
        "190x18", "190x24", "190x32", "195x8", "195x12", "195x18",
        "195x24", "195x32", "200x8", "200x12", "200x18", "200x24",
        "200x32", "205x4", "210x4", "210x8", "210x12", "210x20",
        "210x24", "210x36", "215x4", "220x4", "220x8", "220x12",
        "220x20", "220x24", "220x36", "230x4", "230x8", "230x12",
        "230x20", "230x24", "230x36", "235x4", "240x4", "240x8",
        "240x12", "240x20", "240x22", "240x24", "240x36", "250x4",
        "250x12", "250x22", "250x24", "250x40", "260x4", "260x12",
        "260x20", "260x22", "260x24", "260x40", "270x12", "270x24",
        "270x40", "275x4", "280x4", "280x12", "280x24", "280x40",
        "290x4", "290x12", "290x24", "290x44", "295x4", "300x4",
        "300x12", "300x24", "300x44", "310x5", "315x5",
    ]

    thread_angle: float = 30.0

    size: str
    length: float
    external: bool = True
    hand: Hand = "right"
    end_finishes: tuple[EndFinish, EndFinish] = ("fade", "fade")
    interference: float = 0.2

    @classmethod
    def sizes(cls) -> list[str]:
        """Return the list of standard metric trapezoidal thread size strings."""
        return list(cls.standard_sizes)

    # ------------------------------------------------------------------

    def _build_geometry(self) -> None:
        if self.size not in self.standard_sizes:
            raise ValueError(
                f"size invalid, must be one of {self.standard_sizes}"
            )
        diameter_str, pitch_str = self.size.split("x")
        diameter = float(diameter_str)
        pitch = float(pitch_str)

        inner = TrapezoidalThread(
            diameter=diameter,
            pitch=pitch,
            thread_angle=self.thread_angle,
            length=self.length,
            external=self.external,
            hand=self.hand,
            end_finishes=self.end_finishes,
            interference=self.interference,
        )
        self.geom = inner.geom


# ---------------------------------------------------------------------------
# PlasticBottleThread  –  ASTM D2911
# ---------------------------------------------------------------------------


class PlasticBottleThread(BasePart):
    """ASTM D2911 plastic bottle thread.

    L Style — All-Purpose Thread (trapezoidal, 30° shoulders).
    M Style — Modified Buttress Thread (asymmetric 10° / 40-50° shoulders).
    """

    # -- class-level lookup tables -------------------------------------------

    _l_style_thread_dimensions: ClassVar[dict[int, tuple[float, float]]] = {
        4: (3.18, 1.57),
        5: (3.05, 1.52),
        6: (2.39, 1.19),
        8: (2.13, 1.07),
        12: (1.14, 0.76),
    }
    _m_style_thread_dimensions: ClassVar[dict[int, tuple[float, float]]] = {
        4: (3.18, 1.57),
        5: (3.05, 1.52),
        6: (2.39, 1.19),
        8: (2.13, 1.07),
        12: (1.29, 0.76),
    }

    _thread_angles: ClassVar[dict[str, tuple[float, float]]] = {
        "L100": (30, 30), "M100": (10, 40),
        "L103": (30, 30), "M103": (10, 40),
        "L110": (30, 30), "M110": (10, 50),
        "L200": (30, 30), "M200": (10, 40),
        "L400": (30, 30), "M400": (10, 45),
        "L410": (30, 30), "M410": (10, 45),
        "L415": (30, 30), "M415": (10, 45),
        "L425": (30, 30), "M425": (10, 45),
        "L444": (30, 30), "M444": (10, 45),
    }

    _finish_data: ClassVar[dict[int, tuple[float, list[int]]]] = {
        100: (1.125, [22, 24, 28, 30, 33, 35, 38]),
        103: (1.125, [26]),
        110: (1.125, [28]),
        200: (1.5, [24, 28]),
        400: (
            1.0,
            [
                18, 20, 22, 24, 28, 30, 33, 35, 38, 40, 43, 45, 48, 51,
                53, 58, 60, 63, 66, 70, 75, 77, 83, 89, 100, 110, 120,
            ],
        ),
        410: (1.5, [18, 20, 22, 24, 28]),
        415: (2.0, [13, 15, 18, 20, 22, 24, 28, 30, 33]),
        425: (2.0, [13, 15]),
        444: (
            1.125,
            [
                24, 28, 30, 33, 35, 38, 40, 43, 45, 48, 51, 53, 58, 60,
                63, 66, 70, 75, 77, 83,
            ],
        ),
    }

    _thread_dimensions: ClassVar[dict[int, tuple[float, float, int]]] = {
        13: (13.06, 12.75, 12),
        15: (14.76, 14.45, 12),
        18: (17.88, 17.47, 8),
        20: (19.89, 19.48, 8),
        22: (21.89, 21.49, 8),
        24: (23.88, 23.47, 8),
        26: (25.63, 25.12, 8),
        28: (27.64, 27.13, 6),
        30: (28.62, 28.12, 6),
        33: (32.13, 31.52, 6),
        35: (34.64, 34.04, 6),
        38: (37.49, 36.88, 6),
        40: (40.13, 39.37, 6),
        43: (42.01, 41.25, 6),
        45: (44.20, 43.43, 6),
        48: (47.50, 46.74, 6),
        51: (49.99, 49.10, 6),
        53: (52.50, 51.61, 6),
        58: (56.49, 55.60, 6),
        60: (59.49, 58.60, 6),
        63: (62.51, 61.62, 6),
        66: (65.51, 64.62, 6),
        70: (69.49, 68.60, 6),
        75: (73.99, 73.10, 6),
        77: (77.09, 76.20, 6),
        83: (83.01, 82.12, 5),
        89: (89.18, 88.29, 5),
        100: (100.00, 99.11, 5),
        110: (110.01, 109.12, 5),
        120: (119.99, 119.10, 5),
    }

    # -- fields --------------------------------------------------------------

    size: str
    external: bool = True
    hand: Hand = "right"
    interference: float = 0.2
    manufacturing_compensation: float = 0.0

    # ------------------------------------------------------------------

    def _build_geometry(self) -> None:
        _validate_hand(self.hand)

        size_match = re.match(r"([LM])(\d+)SP(\d+)", self.size)
        if not size_match:
            raise ValueError(
                "size invalid, must match "
                "[L|M][diameter(mm)]SP[100|103|110|200|400|410|415:425|444]"
            )

        style: str = size_match.group(1)
        diameter: int = int(size_match.group(2))
        finish: int = int(size_match.group(3))

        if finish not in self._finish_data:
            raise ValueError(
                f"finish ({finish}) invalid, must be one of "
                f"{list(self._finish_data.keys())}"
            )
        if diameter not in self._finish_data[finish][1]:
            raise ValueError(
                f"diameter ({diameter}) invalid, must be one of "
                f"{self._finish_data[finish][1]}"
            )

        diameter_max, diameter_min, tpi = self._thread_dimensions[diameter]

        if style == "L":
            root_width, thread_height = self._l_style_thread_dimensions[tpi]
        else:
            root_width, thread_height = self._m_style_thread_dimensions[tpi]

        if self.external:
            apex_radius = diameter_min / 2 - self.manufacturing_compensation
            root_radius = (
                diameter_min / 2
                - thread_height
                - self.manufacturing_compensation
            )
        else:
            root_radius = diameter_max / 2 + self.manufacturing_compensation
            apex_radius = (
                diameter_max / 2
                - thread_height
                + self.manufacturing_compensation
            )

        thread_angles = self._thread_angles[style + str(finish)]
        shoulders = [
            thread_height * tan(radians(a)) for a in thread_angles
        ]
        apex_width = root_width - sum(shoulders)
        apex_offset = (
            shoulders[0] + apex_width / 2 - root_width / 2
        )
        if not self.external:
            apex_offset = -apex_offset

        pitch = convert(1, "in") / tpi
        length = (self._finish_data[finish][0] + 0.75) * pitch

        inner = Thread(
            apex_radius=apex_radius,
            apex_width=apex_width,
            root_radius=root_radius,
            root_width=root_width,
            pitch=pitch,
            length=length,
            apex_offset=apex_offset,
            interference=self.interference,
            hand=self.hand,
            end_finishes=("fade", "fade"),
        )
        self.geom = inner.geom


# ---------------------------------------------------------------------------
# Shared validation helpers
# ---------------------------------------------------------------------------


def _validate_hand(hand: str) -> None:
    if hand not in {"right", "left"}:
        raise ValueError(
            f"hand must be one of 'right' or 'left', not {hand!r}"
        )


def _validate_end_finishes(finishes: tuple[str, str]) -> None:
    for finish in finishes:
        if finish not in _VALID_FINISHES:
            raise ValueError(
                f"end_finishes invalid, must be tuple of "
                f"{sorted(_VALID_FINISHES)}"
            )
