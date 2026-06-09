"""
Parametric Threaded Fasteners for Proteus
=========================================

Ported from bd_warehouse (Copyright 2024 Gumyr, Apache License 2.0).
Adapted to the Proteus base hierarchy via ``BasePart``.

Provides data-driven abstract bases for **Nut**, **Screw**, and **Washer**, plus
representative concrete classes and hole-cutout helpers.

Concrete classes landed
-----------------------
* ``HexNut`` — ISO 4032 / 4033 / 4035 hex nuts
* ``SocketHeadCapScrew`` — ISO 4762 / ASME B18.3 socket-head cap screws
* ``PlainWasher`` — ISO 7089 / 7091 / 7093 / 7094 plain washers
* ``HeatSetNut`` — heat-set insert nuts for thermoplastics (McMaster-Carr,
  Hilitchi, CNCKitchen, AE-SamZhihui)

Hole helpers
------------
* ``ClearanceHole`` — through-hole for screw/bolt clearance
* ``TapHole`` — pre-drilled hole sized for tapping
* ``ThreadedHole`` — clearance hole annotated with thread data
* ``InsertHole`` — hole sized for heat-set nut insertion

Deferred / missing infrastructure
----------------------------------
* **IsoThread** — helical thread geometry.  The upstream ``bd_warehouse.thread``
  module uses OCP helix sweeping and must be ported separately.  All fasteners
  default to ``simple=True`` which skips thread creation; passing
  ``simple=False`` raises ``NotImplementedError`` until the port is complete.
* **Additional concrete screw heads** — ButtonHead, CheeseHead, CounterSunk,
  HexHead, PanHead, SetScrew, etc.  The abstract ``Screw`` base supports them
  via ``head_profile`` / ``head_plan`` / ``head_recess`` hooks; only
  ``SocketHeadCapScrew`` is landed here.
* **Additional nut types** — DomedCapNut, HexNutWithFlange, SquareNut,
  UnchamferedHexagonNut, etc.
* **Additional washer types** — ChamferedWasher, CheeseHeadWasher,
  InternalToothLockWasher, etc.
* **Nominal screw length ranges** — parsed from CSV but not validated at
  construction time.
"""

from __future__ import annotations

import csv
import math
from abc import ABC, abstractmethod
from math import atan, cos, pi, radians, sin, sqrt, tan
from pathlib import Path
from typing import ClassVar, Literal

import build123d as bd
from build123d import (
    Align,
    Axis,
    BuildLine,
    BuildPart,
    BuildSketch,
    Color,
    Compound,
    Edge,
    Face,
    JernArc,
    Line,
    Location,
    LocationList,
    Locations,
    Mode,
    Part,
    Plane,
    PolarLine,
    PolarLocations,
    Polyline,
    Pos,
    Plane,
    PolarLine,
    PolarLocations,
    Polyline,
    Polygon,
    Pos,
    Rectangle,
    RegularPolygon,
    RigidJoint,
    RotationLike,
    Shell,
    Sketch,
    SlotOverall,
    Solid,
    SortBy,
    Spline,
    Vector,
    Wire,
    extrude,
    fillet,
    make_face,
    revolve,
    split,
)

from pydantic import Field

from proteus.common import BasePart

# ═══════════════════════════════════════════════════════════════════════
# Resolve data directory relative to this module
# ═══════════════════════════════════════════════════════════════════════

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _resolve_csv(filename: str) -> Path:
    p = _DATA_DIR / filename
    if not p.is_file():
        raise FileNotFoundError(f"Fastener data file not found: {p}")
    return p


# ═══════════════════════════════════════════════════════════════════════
# General-purpose utilities (ported from bd_warehouse)
# ═══════════════════════════════════════════════════════════════════════


def polygon_diagonal(width: float, num_sides: int = 6) -> float:
    """Distance across polygon diagonals given width across flats."""
    return width / cos(pi / num_sides)


def read_fastener_parameters_from_csv(filename: str) -> dict[str, dict[str, str]]:
    """Parse a CSV parameter file into a nested dict of strings.

    First column is the key; remaining columns are ``type:param`` pairs.
    """
    with _resolve_csv(filename).open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        column_headers = next(reader)
        parameters: dict[str, dict[str, str]] = {}
        for row in reader:
            if not row or not row[0].strip():
                continue
            row_data: dict[str, str] = {}
            for column, value in zip(column_headers[1:], row[1:]):
                row_data[column.strip()] = value.strip()
            parameters[row[0].strip()] = row_data
    return parameters


def decode_imperial_size(size: str) -> tuple[float, float]:
    """Extract major diameter and pitch from an imperial size string (e.g. ``"1/4-20"``)."""
    size_parts = size.split("-")
    if len(size_parts) != 2:
        raise ValueError(f"Imperial size {size} not in diameter-TPI format")
    diameter_str = size_parts[0]
    tpi = float(size_parts[1])
    if "/" in diameter_str:
        num, denom = diameter_str.split("/")
        diameter = float(num) / float(denom)
    elif "#" in diameter_str:
        number_gauge = float(diameter_str[1:])
        diameter = 0.06 + 0.013 * number_gauge
    else:
        diameter = float(diameter_str)
    pitch = 1 / tpi
    return (diameter, pitch)


def metric_str_to_float(measure: str) -> float | str:
    """Convert a metric measurement string to float or str, stripping trailing units.

    Returns the original string for non-numeric values (e.g., drill sizes like '#21').
    """
    measure = measure.strip()
    if not measure:
        return 0.0
    result: float | None = None
    for i, c in enumerate(measure):
        if not (c.isdigit() or c in (".", "-")):
            if i > 0:
                result = float(measure[:i])
            break
    if result is None:
        try:
            result = float(measure)
        except ValueError:
            return measure
    return result


def evaluate_parameter_dict_of_dict(
    measurements: dict[str, dict[str, str]],
    is_metric: bool = True,
) -> dict[str, dict[str, float]]:
    """Convert string values in a dict-of-dict structure to floats."""
    for size_key in measurements:
        for type_key, value in measurements[size_key].items():
            if is_metric:
                measurements[size_key][type_key] = (
                    metric_str_to_float(value) if value else 0.0
                )
            else:
                measurements[size_key][type_key] = (
                    imperial_str_to_float(value) if value else 0.0
                )
    return measurements  # type: ignore[return-value]


def evaluate_parameter_dict(
    measurements: dict[str, str],
    is_metric: bool = True,
) -> dict[str, float]:
    """Convert string values in a parameter dictionary to floats."""
    for key, value in measurements.items():
        if is_metric:
            measurements[key] = metric_str_to_float(value) if value else 0.0
        else:
            measurements[key] = imperial_str_to_float(value) if value else 0.0
    return measurements  # type: ignore[return-value]


def isolate_fastener_type(
    target_fastener: str, fastener_data: dict[str, dict[str, str]]
) -> dict[str, dict[str, str]]:
    """Split the fastener data ``type:value`` strings into per-type dictionaries."""
    result: dict[str, dict[str, str]] = {}
    for size, type_data in fastener_data.items():
        result[size] = {}
        for key, value in type_data.items():
            if ":" in key:
                ftype, param = key.split(":", 1)
                if ftype == target_fastener:
                    result[size][param] = value
    return result


def read_drill_sizes() -> dict[str, float]:
    """Read the drill size CSV and return ``{size_name: diameter_inches}``."""
    drill_sizes: dict[str, float] = {}
    with _resolve_csv("drill_sizes.csv").open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # header
        for row in reader:
            if row and row[0].strip():
                drill_sizes[row[0].strip()] = float(row[1].strip())
    return drill_sizes


def lookup_drill_diameters(drill_hole_sizes: dict) -> dict[str, dict[str, float]]:
    """Map drill size names to actual diameters for clearance/tap hole tables."""
    drill_hole_diameters: dict[str, dict[str, float]] = {}
    for size, fits in drill_hole_sizes.items():
        drill_hole_diameters[size] = {}
        for fit, drill_size in fits.items():
            try:
                drill_hole_diameters[size][fit] = float(drill_size)
            except ValueError:
                drill_hole_diameters[size][fit] = imperial_str_to_float(drill_size)
    return drill_hole_diameters


def lookup_nominal_screw_lengths() -> dict[str, list[float]]:
    """Return ``{fastener_type: [nominal_lengths, ...]}``."""
    nominal_screw_lengths: dict[str, list[float]] = {}
    with _resolve_csv("nominal_screw_lengths.csv").open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            if row and row[0].strip():
                nominal_screw_lengths[row[0].strip()] = [
                    float(v.strip()) for v in row[2].split(",") if v.strip()
                ]
    return nominal_screw_lengths


# -- imperial helpers --------------------------------------------------

def is_safe(value: str) -> bool:
    """Evaluate if a string is a safe fractional number."""
    return len(value) <= 10 and all(c in "0123456789./ " for c in set(value))


def imperial_str_to_float(measure: str) -> float:
    """Convert an imperial measurement string (possibly a fraction) to float.

    Handles number/letter drill sizes by looking them up in drill_sizes.csv.
    """
    measure = measure.strip()
    if measure in ("–", "—", ""):
        return float("nan")

    # Handle drill sizes (e.g., "#51", "B")
    drill_sizes = read_drill_sizes()
    if measure in drill_sizes:
        return drill_sizes[measure]

    if "/" in measure:
        parts = measure.split()
        if len(parts) == 2 and is_safe(parts[0]) and is_safe(parts[1]):
            whole = float(parts[0])
            num, denom = parts[1].split("/")
            return whole + float(num) / float(denom)
        elif len(parts) == 1 and is_safe(measure):
            num, denom = measure.split("/")
            return float(num) / float(denom)
    return float(measure)


def select_by_size_fn(cls, size: str) -> dict:
    """Given a fastener size, return ``{class: [type, ...]}``."""
    type_dict: dict[str, list[str]] = {}
    for type_key in cls.fastener_data.get(size, {}):
        if ":" in type_key:
            ftype = type_key.split(":", 1)[0]
            type_dict.setdefault(ftype, []).append(type_key)
    return type_dict


def method_exists(obj, method: str) -> bool:
    """Check whether *obj* provides a callable *method* (not inherited from ABC)."""
    return hasattr(obj, method) and callable(getattr(obj, method))


# ═══════════════════════════════════════════════════════════════════════
# Recess helpers (ported from bd_warehouse)
# ═══════════════════════════════════════════════════════════════════════


def cross_recess(size: str) -> tuple[Face, float]:
    """Type H Cross / Phillips recess for screws.

    Returns ``(recess_face, depth)``.
    """
    recess_data_file = _resolve_csv("iso10664def.csv")
    raise NotImplementedError(
        "cross_recess (Phillips recess) not yet ported from bd_warehouse"
    )


def hex_recess(size: float) -> Face:
    """Hexagon recess for screws (Allen/hex key drive)."""
    with BuildSketch() as plan:
        RegularPolygon(size / 2, 6, major_radius=False)
    return plan.face()


def hexalobular_recess(size: str) -> tuple[Face, float]:
    """Hexalobular (Torx) recess for screws.

    Returns ``(recess_face, depth)``.
    """
    # Load ISO 10664 definition data
    torx_data: dict[str, dict[str, str]] = {}
    with _resolve_csv("iso10664def.csv").open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader)
        for row in reader:
            if row and row[0].strip():
                torx_data[row[0].strip()] = {
                    h: v.strip() for h, v in zip(headers[1:], row[1:])
                }
    try:
        data = torx_data[size]
    except KeyError:
        raise ValueError(f"Unknown Torx size: {size}")

    A = float(data["A"])
    B = float(data["B"])
    Re = float(data["Re"])

    with BuildSketch() as plan:
        with BuildLine():
            p1 = PolarLine((A / 2 - Re, 0), Re, 0)
            p2 = PolarLine(p1 @ 1, sqrt(3) * Re, 150)
            p3 = PolarLine(p2 @ 1, B - A + 2 * Re, 90)
            p4 = RadiusArc(p3 @ 1, p2 @ 0, -Re)
            p5 = RadiusArc(p4 @ 1, p1 @ 0, -Re)
        make_face()
        split(bisect_by=Plane.XZ)
        split(bisect_by=Plane.YZ)
    return (plan.sketch.face(), 0.6 * A)


def slot_recess(width: float, length: float) -> Face:
    """Slot (flat-blade) recess for screws."""
    return Face.make_rect(width, length)


def square_recess(size: str) -> tuple[Face, float]:
    """Robertson Square recess for screws.

    Returns ``(recess_face, depth)``.
    """
    depths = {"R0": 1.27, "R1": 2.31, "R2": 3.17, "R3": 4.77}
    square_sizes = {"R0": 1.27, "R1": 2.31, "R2": 3.17, "R3": 4.77, "R4": 5.38}
    m = square_sizes[size]
    return (Face.make_rect(m, m), depths[size])


# ═══════════════════════════════════════════════════════════════════════
# Shared helpers
# ═══════════════════════════════════════════════════════════════════════

def _parse_size(size: str) -> tuple[str, str, bool, float, float]:
    """Parse a size string like ``"M6-1"`` or ``"1/4-20"``.

    Returns ``(thread_size, length_size, is_metric, thread_diameter, thread_pitch)``.
    """
    size = size.strip()
    parts = size.split("-")
    if len(parts) < 2:
        raise ValueError(
            f"{size!r} invalid; expected size-pitch or size-TPI format"
        )
    thread_size = "-".join(parts[:2])
    length_size = parts[2] if len(parts) >= 3 else ""
    is_metric = thread_size.startswith("M")
    if is_metric:
        thread_diameter = float(parts[0][1:])
        thread_pitch = float(parts[1])
    else:
        thread_diameter, thread_pitch = decode_imperial_size(thread_size)
    return thread_size, length_size, is_metric, thread_diameter, thread_pitch


# ═══════════════════════════════════════════════════════════════════════
# Nut — abstract base
# ═══════════════════════════════════════════════════════════════════════


class Nut(BasePart, ABC):
    """Parametric threaded nut — abstract base.

    Each concrete subclass supplies a ``fastener_data`` class attribute (a
    CSV-backed dict) and optionally overrides ``nut_profile``, ``nut_plan``,
    or ``countersink_profile``.

    Args:
        size: standard size, e.g. ``"M6-1"`` or ``"1/4-20"``.
        fastener_type: type identifier, e.g. ``"iso4032"``.
        hand: thread direction — ``"right"`` (default) or ``"left"``.
    """
    # ── Pydantic fields (required by __init__) ──────────────────────

    _nut_size: str = ""
    _thread_size: str = ""
    _length_size: str = ""
    _is_metric: bool = True
    _thread_diameter: float = 0.0
    _thread_pitch: float = 0.0
    _fastener_type: str = ""
    _hand: str = "right"
    _simple: bool = True
    socket_clearance: float = 6.0
    nut_data: dict = Field(default_factory=dict)
    hole_locations: list = Field(default_factory=list)
    label: str = ""
    color: object = None


    # ── class-level CSV-derived data ────────────────────────────────
    fastener_data: ClassVar[dict[str, dict[str, str]]]
    clearance_hole_drill_sizes: ClassVar[dict] = {}
    clearance_hole_data: ClassVar[dict] = {}
    tap_hole_drill_sizes: ClassVar[dict] = {}
    tap_hole_data: ClassVar[dict] = {}
    @classmethod
    def _load_hole_tables(cls) -> None:
        """One-time load of clearance / tap hole CSV tables (cached on the class)."""
        if not cls.clearance_hole_drill_sizes:
            cls.clearance_hole_drill_sizes = read_fastener_parameters_from_csv(
                "clearance_hole_sizes.csv"
            )
            cls.clearance_hole_data = lookup_drill_diameters(
                cls.clearance_hole_drill_sizes
            )
        if not cls.tap_hole_drill_sizes:
            cls.tap_hole_drill_sizes = read_fastener_parameters_from_csv(
                "tap_hole_sizes.csv"
            )
            cls.tap_hole_data = lookup_drill_diameters(cls.tap_hole_drill_sizes)

    # ── properties ───────────────────────────────────────────────────

    @property
    def tap_drill_sizes(self) -> dict[str, str]:
        """Drill size names for tapped holes (this thread size)."""
        try:
            return self.tap_hole_drill_sizes[self._thread_size]  # type: ignore[operator]
        except KeyError:
            raise ValueError(f"No tap hole data for size {self._thread_size}")

    @property
    def tap_hole_diameters(self) -> dict[str, float]:
        """Drill diameters for tapped holes (this thread size)."""
        try:
            return self.tap_hole_data[self._thread_size]  # type: ignore[operator]
        except KeyError:
            raise ValueError(f"No tap hole data for size {self._thread_size}")

    @property
    def clearance_drill_sizes(self) -> dict[str, str]:
        """Drill size names for clearance holes."""
        major = self._thread_size.split("-")[0]
        try:
            return self.clearance_hole_drill_sizes[major]
        except KeyError:
            raise ValueError(f"No clearance hole data for size {self._thread_size}")

    @property
    def clearance_hole_diameters(self) -> dict[str, float]:
        """Drill diameters for clearance holes."""
        major = self._thread_size.split("-")[0]
        try:
            return self.clearance_hole_data[major]
        except KeyError:
            raise ValueError(f"No clearance hole data for size {self._thread_size}")

    @property
    def info(self) -> str:
        return f"{self.nut_class}({self._fastener_type}): {self._thread_size}"

    @property
    def nut_class(self) -> str:
        return type(self).__name__

    @property
    def nut_thickness(self) -> float:
        return self.geom.bounding_box().max.Z if self.geom else 0.0

    @property
    def nut_diameter(self) -> float:
        if self.geom is None:
            return 0.0
        plan = self.nut_plan()
        verts = list(plan.vertices())
        if len(verts) < 3:
            return float(self.nut_data.get("s", 0))
        arc = Edge.make_three_point_arc(*verts[:3])
        return 2.0 * arc.radius

    def length_offset(self) -> float:
        return 0.0

    # ── class methods ────────────────────────────────────────────────

    @classmethod
    def select_by_size(cls, size: str) -> dict:
        return select_by_size_fn(cls, size)

    @classmethod
    def types(cls) -> set[str]:
        first_entry = next(iter(cls.fastener_data.values()), {})
        return {p.split(":")[0] for p in first_entry}

    @classmethod
    def sizes(cls, fastener_type: str) -> list[str]:
        return list(isolate_fastener_type(fastener_type, cls.fastener_data).keys())

    # ── abstract / overridable geometry hooks ────────────────────────

    @abstractmethod
    def nut_profile(self) -> Face:
        """Return a 2D half-profile of the nut (for revolution)."""
        ...

    @abstractmethod
    def nut_plan(self) -> Face:
        """Return a 2D plan (XY) of the nut (for extrusion/intersection)."""
        ...

    def countersink_profile(
        self, fit: Literal["Close", "Normal", "Loose"] = "Normal"
    ) -> Face:
        """Return a 2D profile for a countersink cutter."""
        return Nut.default_countersink_profile(self, fit)

    # ── defaults (used by HexNut and similar) ────────────────────────

    def default_nut_profile(self) -> Face:
        """Hex nut chamfered profile."""
        m = self.nut_data["m"]
        s = self.nut_data["s"]
        e = polygon_diagonal(s, 6)
        cs = (e - s) * tan(radians(15)) / 2
        with BuildSketch(Plane.XZ) as profile:
            Polygon(
                (0, 0),
                (s / 2, 0),
                (e / 2 - 0.001, cs),
                (e / 2 - 0.001, m - cs),
                (s / 2, m),
                (0, m),
                (0, 0),
                align=None,
            )
        return profile.sketch.face()

    def default_nut_plan(self) -> Face:
        """Regular hexagon plan."""
        with BuildSketch() as plan:
            RegularPolygon(self.nut_data["s"] / 2, 6, major_radius=False)
        return plan.face()

    def default_countersink_profile(
        self, fit: Literal["Close", "Normal", "Loose"] = "Normal"
    ) -> Face:
        """Simple rectangular countersink profile with socket clearance."""
        del fit
        m = self.nut_data["m"]
        s = self.nut_data["s"]
        width = polygon_diagonal(s, 6) + self.socket_clearance
        with BuildSketch(Plane.XZ) as profile:
            Rectangle(width / 2, m, align=Align.MIN)
        return profile.sketch.face()

    # ── construction ─────────────────────────────────────────────────

    def __init__(
        self,
        size: str = "",
        fastener_type: str = "",
        hand: Literal["right", "left"] = "right",
        simple: bool = True,
        nut_data: dict | None = None,
        hole_locations: list | None = None,
    ):
        self._load_hole_tables()

        _nut_size = size.strip()
        (
            _thread_size,
            _length_size,
            _is_metric,
            _thread_diameter,
            _thread_pitch,
        ) = _parse_size(_nut_size)

        if fastener_type not in self.types():
            raise ValueError(
                f"{fastener_type} invalid, must be one of {self.types()}"
            )

        if hand not in ("right", "left"):
            raise ValueError(f"{hand} invalid, must be one of 'right' or 'left'")

        # Resolve nut dimensions from CSV
        isolated = isolate_fastener_type(fastener_type, self.fastener_data)
        if _nut_size not in isolated:
            raise ValueError(
                f"{size!r} invalid, must be one of {self.sizes(fastener_type)}"
            )
        nut_data_computed = evaluate_parameter_dict(
            isolated[_nut_size], is_metric=_is_metric
        )

        super().__init__(
            nut_data=nut_data_computed if nut_data is None else nut_data,
            hole_locations=hole_locations if hole_locations is not None else [],
        )
        object.__setattr__(self, "_nut_size", _nut_size)
        object.__setattr__(self, "_thread_size", _thread_size)
        object.__setattr__(self, "_length_size", _length_size)
        object.__setattr__(self, "_is_metric", _is_metric)
        object.__setattr__(self, "_thread_diameter", _thread_diameter)
        object.__setattr__(self, "_thread_pitch", _thread_pitch)
        object.__setattr__(self, "_fastener_type", fastener_type)
        object.__setattr__(self, "_hand", hand)
        object.__setattr__(self, "_simple", simple)
        object.__setattr__(self, "socket_clearance", 6.0)
        self._build_geometry()

    def model_post_init(self, __context: object) -> None:
        """Override to skip auto-build — we call _build_geometry manually in __init__."""
        pass

    def _build_geometry(self) -> None:
        bd_object = self._make_nut()

        if isinstance(bd_object, Compound) and len(bd_object.solids()) == 1:
            self.geom = bd_object.solid()
        else:
            self.geom = bd_object

        # Tagging
        self.label = f"{self.__class__.__name__}({self._nut_size}, {self._fastener_type})"
        self.color = Color(0xC0C0C0)
        # Standard joints
        self.joints["a"] = RigidJoint("a", self.geom, Location())
        self.joints["b"] = RigidJoint("b", self.geom, Pos(Z=self.nut_thickness))


    def _make_nut(self) -> Solid | Compound:
        """Create nut geometry from profile + plan."""
        profile = self.nut_profile()
        max_nut_height = profile.bounding_box().max.Z
        nut_thread_height = self.nut_data["m"]

        nut = revolve(profile, Axis.Z)

        nut_blank = extrude(
            self.nut_plan(), max_nut_height, (0, 0, 1)
        ) - Solid.make_cylinder(self._thread_diameter / 2, nut_thread_height)

        nut = nut.intersect(nut_blank)
        if isinstance(nut, list):
            nut = nut[0]

        if method_exists(self.__class__, "flange_profile"):
            flange = revolve(
                split(
                    self.flange_profile(),  # type: ignore[attr-defined]
                    Plane.YZ.offset(self._thread_diameter / 2 + 0.1),
                ),
                Axis.Z,
            )
            nut = nut.fuse(flange)

        nut.label = "body"

        if not self._simple:
            raise NotImplementedError(
                "Helical thread generation (IsoThread) not yet ported to Proteus. "
                "Use simple=True or port bd_warehouse.thread first."
            )

        return nut


# ═══════════════════════════════════════════════════════════════════════
# HexNut
# ═══════════════════════════════════════════════════════════════════════


class HexNut(Nut):
    """Hex nut — ISO 4032 / 4033 / 4035.

    Args:
        size: e.g. ``"M6-1"``.
        fastener_type: one of ``"iso4032"``, ``"iso4033"``, ``"iso4035"``.
        hand: ``"right"`` (default) or ``"left"``.
        simple: omit thread geometry (default ``True``).
    """

    fastener_data: ClassVar[dict] = read_fastener_parameters_from_csv(
        "hex_nut_parameters.csv"
    )

    def __init__(
        self,
        size: str,
        fastener_type: Literal["iso4032", "iso4033", "iso4035"] = "iso4032",
        hand: Literal["right", "left"] = "right",
        simple: bool = True,
    ):
        super().__init__(size, fastener_type, hand, simple)

    nut_profile = Nut.default_nut_profile
    nut_plan = Nut.default_nut_plan
    countersink_profile = Nut.default_countersink_profile


# ═══════════════════════════════════════════════════════════════════════
# HeatSetNut
# ═══════════════════════════════════════════════════════════════════════


class HeatSetNut(Nut):
    """Heat-set insert nut for thermoplastics.

    Installed by heating and pressing into a pre-formed hole in plastic.
    Multiple manufacturers are supported via *fastener_type*.

    Args:
        size: e.g. ``"M5-0.8-Standard"``.
        fastener_type: ``"McMaster-Carr"`` (default), ``"Hilitchi"``,
            ``"CNCKitchen"``, or ``"AE-SamZhihui"``.
        hand: ``"right"`` (default) or ``"left"``.
        simple: omit thread geometry (default ``True``).

    Attributes:
        fill_factor: fraction of the insert hole filled by the nut.
    """

    fastener_data: ClassVar[dict] = read_fastener_parameters_from_csv(
        "heatset_nut_parameters.csv"
    )
    def __init__(
        self,
        size: str,
        fastener_type: Literal[
            "McMaster-Carr", "Hilitchi", "CNCKitchen", "AE-SamZhihui"
        ] = "McMaster-Carr",
        hand: Literal["right", "left"] = "right",
        simple: bool = True,
    ):
        self._load_hole_tables()

        _nut_size = size.strip()
        # HeatSet sizes include a length suffix: "M5-0.8-Standard"
        parts = _nut_size.split("-")
        thread_size = "-".join(parts[:2])
        (
            _thread_size,
            _length_size,
            _is_metric,
            _thread_diameter,
            _thread_pitch,
        ) = _parse_size(thread_size)

        if fastener_type not in self.types():
            raise ValueError(
                f"{fastener_type} invalid, must be one of {self.types()}"
            )

        if hand not in ("right", "left"):
            raise ValueError(f"{hand} invalid, must be one of 'right' or 'left'")

        # Resolve data — HeatSet keys use the full size (with length suffix)
        if _nut_size not in self.fastener_data:
            raise ValueError(
                f"{size!r} invalid, must be one of {list(self.fastener_data.keys())}"
            )
        raw = self.fastener_data[_nut_size]
        nut_data_raw: dict[str, str] = {}
        for key, value in raw.items():
            if key.startswith(fastener_type + ":"):
                param = key.split(":", 1)[1]
                nut_data_raw[param] = value
        nut_data = evaluate_parameter_dict(
            nut_data_raw, is_metric=_is_metric
        )

        BasePart.__init__(self, nut_data=nut_data)
        object.__setattr__(self, "_nut_size", _nut_size)
        object.__setattr__(self, "_thread_size", _thread_size)
        object.__setattr__(self, "_length_size", _length_size)
        object.__setattr__(self, "_is_metric", _is_metric)
        object.__setattr__(self, "_thread_diameter", _thread_diameter)
        object.__setattr__(self, "_thread_pitch", _thread_pitch)
        object.__setattr__(self, "_fastener_type", fastener_type)
        object.__setattr__(self, "_hand", hand)
        object.__setattr__(self, "_simple", simple)
        object.__setattr__(self, "socket_clearance", 6.0)
        self._build_geometry()

    def model_post_init(self, __context: object) -> None:
        """Override to skip auto-build — we call _build_geometry manually in __init__."""
        pass



    def _build_geometry(self) -> None:
        self.geom = self._make_nut()

    def nut_profile(self) -> Face:
        """Not used by HeatSetNut — stub to satisfy ABC."""
        pass  # pragma: no cover

    def nut_plan(self) -> Face:
        """Not used by HeatSetNut — stub to satisfy ABC."""
        pass  # pragma: no cover

    @staticmethod
    def knurled_cylinder_faces(
        diameter: float,
        bottom_hole_radius: float,
        top_hole_radius: float,
        height: float,
        knurl_depth: float,
        pitch: float,
        tip_count: int,
        hand: Literal["right", "left"] = "right",
    ) -> list[Face]:
        """Generate the Faces of a knurled cylinder.

        Used to build helical knurling for heat-set inserts.
        """
        lefthand = hand == "left"
        inside_edges = [
            Edge.make_helix(
                pitch, height, diameter / 2 - knurl_depth, lefthand=lefthand
            ).rotate(Axis.Z, i * 360 / tip_count)
            for i in range(tip_count)
        ]
        outside_edges = [
            Edge.make_helix(pitch, height, diameter / 2, lefthand=lefthand).rotate(
                Axis.Z, (i + 0.5) * 360 / tip_count
            )
            for i in range(tip_count)
        ]
        bottom_edges: list[Edge] = []
        top_edges: list[Edge] = []
        for i in range(tip_count):
            bottom_edges.append(
                Edge.make_line(
                    inside_edges[i].position_at(0), outside_edges[i].position_at(0)
                )
            )
            bottom_edges.append(
                Edge.make_line(
                    outside_edges[i].position_at(0),
                    inside_edges[(i + 1) % tip_count].position_at(0),
                )
            )
            top_edges.append(
                Edge.make_line(
                    inside_edges[i].position_at(1), outside_edges[i].position_at(1)
                )
            )
            top_edges.append(
                Edge.make_line(
                    outside_edges[i].position_at(1),
                    inside_edges[(i + 1) % tip_count].position_at(1),
                )
            )

        outside_faces: list[Face] = []
        for i in range(tip_count):
            outside_faces.append(
                Face.make_surface(
                    [
                        inside_edges[i],
                        outside_edges[i],
                        bottom_edges[2 * i],
                        top_edges[2 * i],
                    ]
                )
            )
            outside_faces.append(
                Face.make_surface(
                    [
                        outside_edges[i],
                        inside_edges[(i + 1) % tip_count],
                        bottom_edges[2 * i + 1],
                        top_edges[2 * i + 1],
                    ]
                )
            )

        bottom_face = Face(
            Wire(bottom_edges),
            [Wire(Edge.make_circle(bottom_hole_radius))],
        )
        top_face = Face(
            Wire(top_edges),
            [Wire(Edge.make_circle(top_hole_radius, Plane.XY.offset(height)))],
        )
        return [bottom_face, top_face] + outside_faces

    @property
    def fill_factor(self) -> float:
        """Fraction of the insert hole filled by the nut."""
        drill_sizes = read_drill_sizes()
        drill_key = self.nut_data.get("drill", 0)
        if isinstance(drill_key, str):
            hole_radius = drill_sizes.get(drill_key.strip(), 2.0) / 2
        else:
            hole_radius = float(drill_key) / 2
        heatset_volume = (
            self.geom.volume
            + self.nut_data["m"] * pi * (self._thread_diameter / 2) ** 2
        )
        hole_volume = self.nut_data["m"] * pi * hole_radius**2
        return heatset_volume / hole_volume if hole_volume else 0.0

    def _make_nut(self) -> Solid:
        """Build heat-set nut from Faces assembled into a Shell → Solid."""
        from build123d.objects_part import Cylinder as bdCylinder

        nut_base = bdCylinder(
            self.nut_data["dc"] / 2,
            0.11 * self.nut_data["m"],
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        ) + bdCylinder(
            0.425 * self.nut_data["dc"],
            0.24 * self.nut_data["m"],
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )
        base_bottom_face = (
            nut_base.faces()
            .sort_by(Axis.Z)[0]
            .make_holes([Wire(Edge.make_circle(self._thread_diameter / 2))])
        )
        base_outside_faces = nut_base.faces().sort_by(Axis.Z)[1:-1]

        lower_knurl_faces = HeatSetNut.knurled_cylinder_faces(
            self.nut_data["s"],
            0.425 * self.nut_data["dc"],
            0.425 * self.nut_data["dc"],
            height=0.33 * self.nut_data["m"],
            knurl_depth=0.1 * self.nut_data["s"],
            pitch=3 * self.nut_data["m"],
            tip_count=int(self.nut_data["knurls"]),
            hand="right",
        )
        lower_knurl_faces = [
            f.translate(Vector(0, 0, 0.24 * self.nut_data["m"]))
            for f in lower_knurl_faces
        ]

        nut_middle_face = Face.extrude(
            Edge.make_circle(
                0.425 * self.nut_data["dc"],
                Plane.XY.offset(0.57 * self.nut_data["m"]),
            ),
            (0, 0, 0.1 * self.nut_data["m"]),
        )

        upper_knurl_faces = HeatSetNut.knurled_cylinder_faces(
            self.nut_data["s"],
            0.425 * self.nut_data["dc"],
            self._thread_diameter / 2,
            height=0.33 * self.nut_data["m"],
            knurl_depth=0.1 * self.nut_data["s"],
            pitch=3 * self.nut_data["m"],
            tip_count=20,
            hand="left",
        )
        upper_knurl_faces = [
            f.translate(Vector(0, 0, 0.67 * self.nut_data["m"]))
            for f in upper_knurl_faces
        ]

        thread_hole_face = Face.extrude(
            Edge.make_circle(self._thread_diameter / 2),
            (0, 0, self.nut_data["m"]),
        )

        nut_shell = Shell(
            [base_bottom_face, nut_middle_face, thread_hole_face]
            + base_outside_faces
            + lower_knurl_faces
            + upper_knurl_faces
        )
        nut = Solid(nut_shell)
        nut.label = "body"

        if not self._simple:
            raise NotImplementedError(
                "Helical thread generation (IsoThread) not yet ported to Proteus."
            )
        return nut

    def countersink_profile(
        self, manufacturing_compensation: float = 0.0
    ) -> Face:
        """Profile for a cavity allowing the nut to be countersunk into plastic."""
        drill_sizes = read_drill_sizes()
        drill_key = self.nut_data.get("drill", 0)
        if isinstance(drill_key, str):
            hole_radius = (
                drill_sizes.get(drill_key.strip(), 2.0) / 2
                + manufacturing_compensation
            )
        else:
            hole_radius = float(drill_key) / 2 + manufacturing_compensation
        with BuildSketch(Plane.XZ) as profile:
            Rectangle(hole_radius, self.nut_data["m"], align=Align.MIN)
        return profile.sketch.face()


# ═══════════════════════════════════════════════════════════════════════
# Screw — abstract base
# ═══════════════════════════════════════════════════════════════════════


class Screw(BasePart, ABC):
    """Parametric screw / bolt — abstract base.

    Each concrete subclass supplies a ``fastener_data`` class attribute and
    overrides ``head_profile`` / ``head_plan`` / ``head_recess`` as needed.

    Args:
        size: e.g. ``"M6-1"`` or ``"1/4-20"``.
        length: distance from under-head to tip (mm).
        fastener_type: type identifier, e.g. ``"iso4762"``.
        hand: ``"right"`` (default) or ``"left"``.
        simple: if ``True`` (default), omit helical thread geometry.
    """
    # ── Pydantic fields (required by __init__) ──────────────────────
    _screw_size: str = ""
    _thread_size: str = ""
    _length_size: str = ""
    _is_metric: bool = True
    _thread_diameter: float = 0.0
    _thread_pitch: float = 0.0
    _fastener_type: str = ""
    _hand: str = "right"
    _simple: bool = True
    _length: float = 0.0
    _max_thread_length: float = 0.0
    _thread_length: float = 0.0
    _head_height: float = 0.0
    _head_diameter: float = 0.0
    socket_clearance: float = 6.0
    screw_data: dict = Field(default_factory=dict)
    hole_locations: list = Field(default_factory=list)
    label: str = ""
    color: object = None

    # ── class-level CSV-derived data ────────────────────────────────
    fastener_data: ClassVar[dict[str, dict[str, str]]]
    clearance_hole_drill_sizes: ClassVar[dict] = {}
    clearance_hole_data: ClassVar[dict] = {}
    tap_hole_drill_sizes: ClassVar[dict] = {}
    tap_hole_data: ClassVar[dict] = {}
    nominal_length_range: ClassVar[dict[str, list[float]]] = {}

    @classmethod
    def _load_hole_tables(cls) -> None:
        if not cls.clearance_hole_drill_sizes:
            cls.clearance_hole_drill_sizes = read_fastener_parameters_from_csv(
                "clearance_hole_sizes.csv"
            )
            cls.clearance_hole_data = lookup_drill_diameters(
                cls.clearance_hole_drill_sizes
            )
        if not cls.tap_hole_drill_sizes:
            cls.tap_hole_drill_sizes = read_fastener_parameters_from_csv(
                "tap_hole_sizes.csv"
            )
            cls.tap_hole_data = lookup_drill_diameters(cls.tap_hole_drill_sizes)
        if not cls.nominal_length_range:
            cls.nominal_length_range = lookup_nominal_screw_lengths()

    # ── properties ───────────────────────────────────────────────────

    @property
    def tap_drill_sizes(self) -> dict[str, str]:
        try:
            return self.tap_hole_drill_sizes[self._thread_size]  # type: ignore[operator]
        except KeyError:
            raise ValueError(f"No tap hole data for size {self._thread_size}")

    @property
    def tap_hole_diameters(self) -> dict[str, float]:
        try:
            return self.tap_hole_data[self._thread_size]  # type: ignore[operator]
        except KeyError:
            raise ValueError(f"No tap hole data for size {self._thread_size}")

    @property
    def clearance_drill_sizes(self) -> dict[str, str]:
        major = self._thread_size.split("-")[0]
        try:
            return self.clearance_hole_drill_sizes[major]
        except KeyError:
            raise ValueError(f"No clearance hole data for size {self._thread_size}")

    @property
    def clearance_hole_diameters(self) -> dict[str, float]:
        major = self._thread_size.split("-")[0]
        try:
            return self.clearance_hole_data[major]
        except KeyError:
            raise ValueError(f"No clearance hole data for size {self._thread_size}")

    @property
    def info(self) -> str:
        return (
            f"{self.screw_class}({self._fastener_type}): "
            f"{self._thread_size}x{self._length}"
            f"{' left hand thread' if self._hand == 'left' else ''}"
        )

    @property
    def screw_class(self) -> str:
        return type(self).__name__

    @property
    def nominal_lengths(self) -> list[float] | None:
        try:
            range_min = self.screw_data["short"]
        except KeyError:
            range_min = None
        try:
            range_max = self.screw_data["long"]
        except KeyError:
            range_max = None
        if (
            range_min is None
            or range_max is None
            or self._fastener_type not in Screw.nominal_length_range
        ):
            return None
        return [
            s
            for s in Screw.nominal_length_range[self._fastener_type]
            if range_min <= s <= range_max
        ]

    # ── class methods ────────────────────────────────────────────────

    @classmethod
    def select_by_size(cls, size: str) -> dict:
        return select_by_size_fn(cls, size)

    @classmethod
    def types(cls) -> set[str]:
        first_entry = next(iter(cls.fastener_data.values()), {})
        return {p.split(":")[0] for p in first_entry}

    @classmethod
    def sizes(cls, fastener_type: str) -> list[str]:
        return list(isolate_fastener_type(fastener_type, cls.fastener_data).keys())

    # ── geometry hooks ───────────────────────────────────────────────

    def length_offset(self) -> float:
        """Override to include head height in length (e.g. countersunk heads)."""
        return 0.0

    def min_hole_depth(self, counter_sunk: bool = True) -> float:
        cs_profile = self.countersink_profile("Loose")
        if cs_profile is None:
            return 0.0
        head_offset = cs_profile.vertices().sort_by(Axis.Z)[-1].Z
        if counter_sunk:
            return self._length + head_offset - self.length_offset()
        return self._length - self.length_offset()

    @abstractmethod
    def countersink_profile(
        self, fit: Literal["Close", "Normal", "Loose"] = "Normal"
    ) -> Face | None:
        """Return a 2D profile for countersink cutout (or None)."""
        ...

    # ── defaults ─────────────────────────────────────────────────────

    def default_head_recess(self) -> tuple[Face, float, float]:
        """Auto-detect recess from screw_data: slot, hex, Phillips, Torx, or Robertson."""
        recess_plan: Face | None = None
        recess_depth: float = 0.0
        recess_taper: float = 0.0

        try:
            dk = self.screw_data["dk"]
            n = self.screw_data["n"]
            t = self.screw_data["t"]
            recess_plan = slot_recess(dk, n)
            recess_depth = t
            recess_taper = 0.0
        except KeyError:
            pass

        try:
            s = self.screw_data["s"]
            t2 = self.screw_data["t"]
            recess_plan = hex_recess(s)
            recess_depth = t2
            recess_taper = 0.0
        except KeyError:
            pass

        try:
            recess = str(self.screw_data["recess"]).upper()
            if recess.startswith("PH"):
                recess_plan, recess_depth = cross_recess(recess)
                recess_taper = 20.0
            elif recess.startswith("T"):
                recess_plan, recess_depth = hexalobular_recess(recess)
                recess_taper = 5.0
            elif recess.startswith("R"):
                recess_plan, recess_depth = square_recess(recess)
                recess_taper = 0.0
        except KeyError:
            pass

        if recess_plan is None:
            raise ValueError(
                f"Recess data missing from screw_data: {self.screw_data}"
            )
        return (recess_plan, recess_depth, recess_taper)

    def default_countersink_profile(
        self, fit: Literal["Close", "Normal", "Loose"] = "Normal"
    ) -> Face:
        try:
            clearance_hole_diameter = self.clearance_hole_diameters[fit]
        except KeyError:
            raise ValueError(
                f"{fit} invalid, "
                f"must be one of {list(self.clearance_hole_diameters.keys())}"
            )
        width = (
            clearance_hole_diameter
            - self._thread_diameter
            + self.screw_data["dk"]
        )
        with BuildSketch(Plane.XZ) as profile:
            Rectangle(width / 2, self.screw_data["k"], align=Align.MIN)
        return profile.sketch.face()

    # ── construction ─────────────────────────────────────────────────

    def __init__(
        self,
        size: str,
        length: float,
        fastener_type: str,
        hand: Literal["right", "left"] = "right",
        simple: bool = True,
        socket_clearance: float = 6.0,
    ):
        self._load_hole_tables()

        _screw_size = size.strip()
        (
            _thread_size,
            _length_size,
            _is_metric,
            _thread_diameter,
            _thread_pitch,
        ) = _parse_size(_screw_size)

        _length = float(length)

        if fastener_type not in self.types():
            raise ValueError(
                f"{fastener_type} invalid, must be one of {self.types()}"
            )

        if hand not in ("right", "left"):
            raise ValueError(f"{hand} invalid, must be one of 'right' or 'left'")

        isolated = isolate_fastener_type(fastener_type, self.fastener_data)
        if _thread_size not in isolated:
            raise ValueError(
                f"{size!r} invalid, must be one of {self.sizes(fastener_type)}"
            )
        screw_data = evaluate_parameter_dict(
            isolated[_thread_size], is_metric=_is_metric
        )

        length_offset = self.length_offset()
        if length_offset >= _length:
            raise ValueError(
                f"Screw length {_length} is <= countersunk head {length_offset}"
            )
        _max_thread_length = _length - length_offset
        _thread_length = _length - length_offset

        super().__init__(
            screw_data=screw_data,
            hole_locations=[],
        )
        object.__setattr__(self, "_screw_size", _screw_size)
        object.__setattr__(self, "_thread_size", _thread_size)
        object.__setattr__(self, "_length_size", _length_size)
        object.__setattr__(self, "_is_metric", _is_metric)
        object.__setattr__(self, "_thread_diameter", _thread_diameter)
        object.__setattr__(self, "_thread_pitch", _thread_pitch)
        object.__setattr__(self, "_length", _length)
        object.__setattr__(self, "_fastener_type", fastener_type)
        object.__setattr__(self, "_hand", hand)
        object.__setattr__(self, "_simple", simple)
        object.__setattr__(self, "socket_clearance", socket_clearance)
        object.__setattr__(self, "_max_thread_length", _max_thread_length)
        object.__setattr__(self, "_thread_length", _thread_length)
        self._build_geometry()

    def model_post_init(self, __context: object) -> None:
        """Override to skip auto-build — we call _build_geometry manually in __init__."""
        pass


    def _build_geometry(self) -> None:
        head = self._make_head()

        if head is None:
            self._head_height = 0.0
            self._head_diameter = 0.0
            ends = ("fade", "fade")
        else:
            head_bb = head.bounding_box()
            self._head_height = head_bb.max.Z
            self._head_diameter = 2 * max(head_bb.max.X, head_bb.max.Y)
            ends = ("fade", "raw")
            head = head.translate((0, 0, -self.length_offset()))

        # Shank
        shank = Solid.make_cylinder(
            self._thread_diameter / 2,
            self._thread_length,
            Plane.XY.offset(-self._length),
        )

        if method_exists(self.__class__, "custom_make"):
            screw = self.custom_make()  # type: ignore[attr-defined]
        elif head is not None:
            screw = head.fuse(shank)
            if hasattr(screw, '__iter__'):  # Handle ShapeList from failed boolean
                screw = next(iter(screw))
        else:
            screw = shank

        if isinstance(screw, Compound):
            screw = screw.unwrap(fully=True)
        screw.label = "body"

        if not self._simple:
            raise NotImplementedError(
                "Helical thread generation (IsoThread) not yet ported to Proteus. "
                "Use simple=True."
            )

        self.geom = screw
        self.label = (
            f"{self.__class__.__name__}"
            f"({self._screw_size}, {self._length:0.2f}, {self._fastener_type})"
        )
        self.color = Color(0xC0C0C0)
        self.joints["a"] = RigidJoint("a", self.geom, Location())

    def _make_head(self) -> Solid | None:
        """Create screw head from class-defined profile / plan / recess."""
        has_profile = method_exists(self.__class__, "head_profile")
        has_plan = method_exists(self.__class__, "head_plan")
        has_recess = method_exists(self.__class__, "head_recess")
        has_flange = method_exists(self.__class__, "flange_profile")

        head: Solid | None = None

        if has_profile:
            profile = self.head_profile()  # type: ignore[attr-defined]
            profile_bbox = profile.bounding_box()
            max_head_height = profile_bbox.size.Z
            max_head_radius = profile_bbox.max.X
            min_head_height = profile_bbox.min.Z
            head = revolve(profile)

        if has_plan:
            head_plan = self.head_plan()  # type: ignore[attr-defined]
        else:
            head_plan = Face.make_rect(
                3 * (max_head_radius if has_profile else 5),
                3 * (max_head_radius if has_profile else 5),
                Plane.XY.offset(min_head_height if has_profile else 0),
            )

        if head is None:
            return None

        if has_recess:
            recess_plan, recess_depth, recess_taper = self.head_recess()  # type: ignore[attr-defined]
            recess = Solid.extrude_taper(
                recess_plan,
                (0, 0, -recess_depth),
                taper=recess_taper,
            ).translate((0, 0, max_head_height))
            head_blank = (
                extrude(head_plan, max_head_height, (0, 0, 1)) - recess
            )
            head = head.intersect(head_blank)
        elif has_plan:
            head_blank = extrude(head_plan, max_head_height)
            head = head.intersect(head_blank)

        if isinstance(head, list):
            head = head[0]

        if has_flange:
            head = head.fuse(revolve(self.flange_profile()))  # type: ignore[attr-defined]

        return head


# ═══════════════════════════════════════════════════════════════════════
# SocketHeadCapScrew
# ═══════════════════════════════════════════════════════════════════════


class SocketHeadCapScrew(Screw):
    """Socket-head cap screw — ISO 4762 / ASME B18.3.

    Args:
        size: e.g. ``"M6-1"``.
        length: screw length under head (mm).
        fastener_type: ``"iso4762"`` (default) or ``"asme_b18.3"``.
        hand: ``"right"`` (default) or ``"left"``.
        simple: omit thread geometry (default ``True``).
    """

    fastener_data: ClassVar[dict] = read_fastener_parameters_from_csv(
        "socket_head_cap_parameters.csv"
    )

    def __init__(
        self,
        size: str,
        length: float,
        fastener_type: Literal["iso4762", "asme_b18.3"] = "iso4762",
        hand: Literal["right", "left"] = "right",
        simple: bool = True,
    ):
        super().__init__(size, length, fastener_type, hand, simple)

    def head_profile(self) -> Face:
        dk = self.screw_data["dk"]
        k = self.screw_data["k"]
        with BuildSketch(Plane.XZ) as profile:
            Rectangle(dk / 2, k, align=Align.MIN)
            fillet(
                profile.vertices().group_by(Axis.Y)[-1].sort_by(Axis.X)[-1],
                k * 0.075,
            )
        return profile.sketch.face()

    head_recess = Screw.default_head_recess
    countersink_profile = Screw.default_countersink_profile


# ═══════════════════════════════════════════════════════════════════════
# Washer — abstract base
# ═══════════════════════════════════════════════════════════════════════


class Washer(BasePart, ABC):
    """Parametric washer — abstract base.

    Each concrete subclass supplies a ``fastener_data`` class attribute and
    overrides ``washer_profile``.

    Args:
        size: e.g. ``"M6"`` (nominal thread size).
        fastener_type: type identifier, e.g. ``"iso7089"``.

    Raises:
        ValueError: invalid *fastener_type* or *size*.
    """
    # ── Pydantic fields (required by __init__) ──────────────────────
    _washer_size: str = ""
    _thread_size: str = ""
    _is_metric: bool = True
    _thread_diameter: float = 0.0
    _fastener_type: str = ""
    washer_data: dict = Field(default_factory=dict)
    hole_locations: list = Field(default_factory=list)
    label: str = ""
    color: object = None

    # ── class-level CSV-derived data ────────────────────────────────
    fastener_data: ClassVar[dict[str, dict[str, str]]]
    clearance_hole_drill_sizes: ClassVar[dict] = {}
    clearance_hole_data: ClassVar[dict] = {}
    @classmethod
    def _load_hole_tables(cls) -> None:
        if not cls.clearance_hole_drill_sizes:
            cls.clearance_hole_drill_sizes = read_fastener_parameters_from_csv(
                "clearance_hole_sizes.csv"
            )
            cls.clearance_hole_data = lookup_drill_diameters(
                cls.clearance_hole_drill_sizes
            )

    @property
    def clearance_hole_diameters(self) -> dict[str, float]:
        major = self._thread_size.split("-")[0]
        try:
            return self.clearance_hole_data[major]
        except KeyError:
            raise ValueError(f"No clearance hole data for size {self._thread_size}")

    @property
    def info(self) -> str:
        return f"{self.washer_class}({self._fastener_type}): {self._thread_size}"

    @property
    def washer_class(self) -> str:
        return type(self).__name__

    @property
    def washer_thickness(self) -> float:
        if self.geom is None:
            return 0.0
        return self.geom.bounding_box().size.Z

    @property
    def washer_diameter(self) -> float:
        if self.geom is None:
            return 0.0
        radii = [
            (Vector(0, 0, v.Z) - Vector(v)).length for v in self.geom.vertices()
        ]
        return 2.0 * max(radii)

    @classmethod
    def types(cls) -> set[str]:
        first_entry = next(iter(cls.fastener_data.values()), {})
        return {p.split(":")[0] for p in first_entry}

    @classmethod
    def sizes(cls, fastener_type: str) -> list[str]:
        return list(isolate_fastener_type(fastener_type, cls.fastener_data).keys())

    @classmethod
    def select_by_size(cls, size: str) -> dict:
        return select_by_size_fn(cls, size)

    @abstractmethod
    def washer_profile(self) -> Face:
        """Return a 2D half-profile of the washer (for revolution)."""
        ...

    def countersink_profile(
        self, fit: Literal["Close", "Normal", "Loose"] = "Normal"
    ) -> Face:
        return Washer.default_countersink_profile(self, fit)

    # ── defaults ─────────────────────────────────────────────────────

    def default_washer_profile(self) -> Face:
        d1 = self.washer_data["d1"]
        d2 = self.washer_data["d2"]
        h = self.washer_data["h"]
        with BuildSketch(Plane.XZ) as profile:
            with Locations((d1 / 2, 0)):
                Rectangle((d2 - d1) / 2, h, align=Align.MIN)
        return profile.sketch.face()

    def default_countersink_profile(
        self, fit: Literal["Close", "Normal", "Loose"] = "Normal"
    ) -> Face:
        try:
            clearance_hole_diameter = self.clearance_hole_diameters[fit]
        except KeyError:
            raise ValueError(
                f"{fit} invalid, "
                f"must be one of {list(self.clearance_hole_diameters.keys())}"
            )
        gap = clearance_hole_diameter - self._thread_diameter
        d2 = self.washer_data["d2"]
        h = self.washer_data["h"]
        with BuildSketch(Plane.XZ) as profile:
            Rectangle(d2 / 2 + gap, h, align=Align.MIN)
        return profile.sketch.face()

    # ── construction ─────────────────────────────────────────────────

    def __init__(
        self,
        size: str,
        fastener_type: str,
    ):
        self._load_hole_tables()

        _washer_size = size.strip()
        _thread_size = size.strip()
        _is_metric = _thread_size.startswith("M")

        if _is_metric:
            _thread_diameter = float(size[1:])
        else:
            _thread_diameter = imperial_str_to_float(size)

        if fastener_type not in self.types():
            raise ValueError(
                f"{fastener_type} invalid, must be one of {self.types()}"
            )

        isolated = isolate_fastener_type(fastener_type, self.fastener_data)
        if _thread_size not in isolated:
            raise ValueError(
                f"{size!r} invalid, must be one of {self.sizes(fastener_type)}"
            )
        washer_data = evaluate_parameter_dict(
            isolated[_thread_size], is_metric=_is_metric
        )

        super().__init__(
            washer_data=washer_data,
            hole_locations=[],
        )
        object.__setattr__(self, "_washer_size", _washer_size)
        object.__setattr__(self, "_thread_size", _thread_size)
        object.__setattr__(self, "_is_metric", _is_metric)
        object.__setattr__(self, "_thread_diameter", _thread_diameter)
        object.__setattr__(self, "_fastener_type", fastener_type)
        self._build_geometry()

    def model_post_init(self, __context: object) -> None:
        """Override to skip auto-build — we call _build_geometry manually in __init__."""
        pass

    def _build_geometry(self) -> None:
        washer = revolve(self.washer_profile()).solid()
        self.geom = washer
        self.label = (
            f"{self.__class__.__name__}({self._washer_size}, {self._fastener_type})"
        )
        self.color = Color(0xC0C0C0)
        self.joints["a"] = RigidJoint("a", self.geom, Location())
        self.joints["b"] = RigidJoint("b", self.geom, Pos(Z=self.washer_thickness))

# ═══════════════════════════════════════════════════════════════════════
# PlainWasher
# ═══════════════════════════════════════════════════════════════════════


class PlainWasher(Washer):
    """Plain (flat) washer — ISO 7089 / 7091 / 7093 / 7094.

    Args:
        size: e.g. ``"M6"``.
        fastener_type: one of ``"iso7089"``, ``"iso7091"``, ``"iso7093"``, ``"iso7094"``.
    """

    fastener_data: ClassVar[dict] = read_fastener_parameters_from_csv(
        "plain_washer_parameters.csv"
    )

    def __init__(
        self,
        size: str,
        fastener_type: Literal[
            "iso7089", "iso7091", "iso7093", "iso7094"
        ] = "iso7089",
    ):
        super().__init__(size, fastener_type)

    washer_profile = Washer.default_washer_profile
    countersink_profile = Washer.default_countersink_profile


# ═══════════════════════════════════════════════════════════════════════
# Shared hole-builder helper
# ═══════════════════════════════════════════════════════════════════════


def _make_fastener_hole(
    hole_diameters: dict[str, float],
    fastener: Nut | Screw,
    countersink_profile: Face | None,
    depth: float,
    fit: Literal["Close", "Normal", "Loose"] | None = None,
    material: Literal["Soft", "Hard"] | None = None,
    counter_sunk: bool = True,
    captive_nut: bool = False,
    threaded_hole: bool = False,
) -> Part:
    """Build a counterbore/clearance/tap/threaded hole solid for a fastener.

    The result is a ``Part`` intended for boolean subtraction from a parent body.
    """
    bore_direction = Vector(0, 0, -1)
    origin = Vector(0, 0, 0)

    head_offset = 0.0
    countersink_cutter: Solid | None = None

    if captive_nut:
        clearance = fastener.clearance_hole_diameters[fit] - getattr(
            fastener, "_thread_diameter", 0
        )
        head_offset = (
            countersink_profile.vertices().sort_by(Axis.Z)[-1].Z
            if countersink_profile
            else 0.0
        )
        from build123d.objects_sketch import RectangleRounded

        nd = fastener.nut_diameter
        fillet_radius = nd / 4
        rect_width = nd + clearance
        rect_height = nd * math.sin(math.pi / 3) + clearance
        with BuildPart(mode=Mode.PRIVATE) as csk_builder:
            with BuildSketch():
                RectangleRounded(rect_width, rect_height, fillet_radius)
            extrude(amount=-head_offset)
        countersink_cutter = csk_builder.part

    elif counter_sunk and countersink_profile is not None:
        head_offset = countersink_profile.vertices().sort_by(Axis.Z)[-1].Z
        countersink_cutter = revolve(
            countersink_profile, mode=Mode.PRIVATE
        ).moved(Pos(0, 0, -head_offset))

    if threaded_hole:
        hole_radius = fastener._thread_diameter / 2
    else:
        key = fit if material is None else material
        try:
            hole_radius = hole_diameters[key] / 2
        except KeyError:
            raise ValueError(
                f"{key} invalid, must be one of {list(hole_diameters.keys())}"
            )

    shank_hole = Solid.make_cylinder(
        radius=hole_radius,
        height=depth,
        plane=Plane(origin, z_dir=bore_direction),
    )

    if counter_sunk and countersink_cutter is not None:
        fastener_hole = countersink_cutter.fuse(shank_hole)
    else:
        fastener_hole = shank_hole

    # Drill tip cone
    csk_angle = 180.0 - 82.0
    h = hole_radius / math.tan(math.radians(csk_angle / 2.0))
    drill_tip = Solid.make_cone(
        hole_radius,
        0.0,
        h,
        plane=Plane(bore_direction * depth, z_dir=bore_direction),
    )
    fastener_hole = fastener_hole.fuse(drill_tip)

    return fastener_hole


# ═══════════════════════════════════════════════════════════════════════
# ClearanceHole
# ═══════════════════════════════════════════════════════════════════════


class ClearanceHole(BasePart):
    """Clearance through-hole for a screw or bolt.

    Args:
        fastener: a ``Nut`` or ``Screw`` instance defining thread dimensions.
        fit: ``"Close"``, ``"Normal"`` (default), or ``"Loose"``.
        depth: hole depth; ``None`` (default) means through-part
            (requires a build123d ``BuildPart`` context).
        counter_sunk: include countersink recess (default ``True``).
        captive_nut: create a rectangular filleted recess for captive nuts
            (default ``False``).
    """
    # ── Pydantic fields ─────────────────────────────────────────────
    _fastener: Nut | Screw = None  # type: ignore[assignment]
    _fit: str = "Normal"
    _depth: float | None = None
    _counter_sunk: bool = True
    _captive_nut: bool = False
    hole_depth: float = 0.0
    label: str = ""
    color: object = None

    def __init__(
        self,
        fastener: Nut | Screw,
        fit: Literal["Close", "Normal", "Loose"] = "Normal",
        depth: float | None = None,
        counter_sunk: bool = True,
        captive_nut: bool = False,
    ):
        if isinstance(fastener, HeatSetNut):
            raise ValueError(
                "ClearanceHole doesn't accept HeatSetNut — use InsertHole instead"
            )
        if captive_nut and not isinstance(fastener, (HexNut,)):
            raise ValueError("Only HexNut (and similar) can be captive")

        # Resolve depth
        if depth is not None:
            hole_depth = depth
        else:
            # When no BuildPart context, default to 10 × thread diameter
            hole_depth = 10 * getattr(fastener, "_thread_diameter", 5.0)

        super().__init__(hole_depth=hole_depth)
        object.__setattr__(self, "_fastener", fastener)
        object.__setattr__(self, "_fit", fit)
        object.__setattr__(self, "_depth", depth)
        object.__setattr__(self, "_counter_sunk", counter_sunk)
        object.__setattr__(self, "_captive_nut", captive_nut)
        self._build_geometry()

    def model_post_init(self, __context: object) -> None:
        """Override to skip auto-build — we call _build_geometry manually in __init__."""
        pass

    def _build_geometry(self) -> None:
        cs_profile = self._fastener.countersink_profile(self._fit)  # type: ignore[call-arg]
        hole_part = _make_fastener_hole(
            hole_diameters=self._fastener.clearance_hole_diameters,
            fastener=self._fastener,
            countersink_profile=cs_profile,
            depth=self.hole_depth,
            fit=self._fit,
            counter_sunk=self._counter_sunk,
            captive_nut=self._captive_nut,
        )
        self.geom = hole_part
        self.label = f"ClearanceHole({self._fastener.info})"


# ═══════════════════════════════════════════════════════════════════════
# TapHole
# ═══════════════════════════════════════════════════════════════════════


class TapHole(BasePart):
    """Pre-drilled hole sized for subsequent thread tapping.

    Args:
        fastener: a ``Nut`` or ``Screw`` instance.
        material: ``"Soft"`` (default) or ``"Hard"`` — determines tap drill size.
        fit: clearance fit for countersunk head — ``"Normal"`` default.
        depth: hole depth; ``None`` = through-part.
        counter_sunk: include countersink recess (default ``True``).
    """
    # ── Pydantic fields ─────────────────────────────────────────────
    _fastener: Nut | Screw = None  # type: ignore[assignment]
    _material: str = "Soft"
    _fit: str = "Normal"
    _depth: float | None = None
    _counter_sunk: bool = True
    hole_depth: float = 0.0
    label: str = ""
    color: object = None
    def __init__(
        self,
        fastener: Nut | Screw,
        material: Literal["Soft", "Hard"] = "Soft",
        fit: Literal["Close", "Normal", "Loose"] = "Normal",
        depth: float | None = None,
        counter_sunk: bool = True,
    ):
        if isinstance(fastener, HeatSetNut):
            raise ValueError(
                "TapHole doesn't accept HeatSetNut — use InsertHole instead"
            )

        if depth is not None:
            hole_depth = depth
        else:
            hole_depth = 10 * getattr(fastener, "_thread_diameter", 5.0)

        super().__init__(hole_depth=hole_depth)
        object.__setattr__(self, "_fastener", fastener)
        object.__setattr__(self, "_material", material)
        object.__setattr__(self, "_fit", fit)
        object.__setattr__(self, "_depth", depth)
        object.__setattr__(self, "_counter_sunk", counter_sunk)
        self._build_geometry()

    def model_post_init(self, __context: object) -> None:
        """Override to skip auto-build — we call _build_geometry manually in __init__."""
        pass

    def _build_geometry(self) -> None:
        cs_profile = self._fastener.countersink_profile(self._fit)  # type: ignore[call-arg]
        hole_part = _make_fastener_hole(
            hole_diameters=self._fastener.tap_hole_diameters,
            fastener=self._fastener,
            countersink_profile=cs_profile,
            depth=self.hole_depth,
            fit=self._fit,
            material=self._material,
            counter_sunk=self._counter_sunk,
        )
        self.geom = hole_part
        self.label = f"TapHole({self._fastener.info})"

class ThreadedHole(BasePart):
    """Clearance hole annotated for threaded insert.

    The hole is sized as a clearance hole; thread geometry is deferred
    (see ``IsoThread`` port note in module docstring).

    Args:
        fastener: a ``Nut`` or ``Screw`` instance.
        material: ``"Soft"`` (default) or ``"Hard"``.
        fit: ``"Normal"`` default.
        depth: hole depth; ``None`` = through-part.
        counter_sunk: include countersink recess (default ``True``).
        simple: if ``True`` (default), skip thread annotation.
    """
    # ── Pydantic fields ─────────────────────────────────────────────
    _fastener: Nut | Screw = None  # type: ignore[assignment]
    _material: str = "Soft"
    _fit: str = "Normal"
    _depth: float | None = None
    _counter_sunk: bool = True

    _simple: bool = True
    hole_depth: float = 0.0
    label: str = ""
    color: object = None


    def __init__(
        self,
        fastener: Nut | Screw,
        material: Literal["Soft", "Hard"] = "Soft",
        fit: Literal["Close", "Normal", "Loose"] = "Normal",
        depth: float | None = None,
        counter_sunk: bool = True,
        simple: bool = True,
    ):
        if isinstance(fastener, HeatSetNut):
            raise ValueError(
                "ThreadedHole doesn't accept HeatSetNut — use InsertHole instead"
            )

        if depth is not None:
            hole_depth = depth
        else:
            hole_depth = 10 * getattr(fastener, "_thread_diameter", 5.0)

        super().__init__(hole_depth=hole_depth)
        object.__setattr__(self, "_fastener", fastener)
        object.__setattr__(self, "_material", material)
        object.__setattr__(self, "_fit", fit)
        object.__setattr__(self, "_depth", depth)
        object.__setattr__(self, "_counter_sunk", counter_sunk)
        object.__setattr__(self, "_simple", simple)
        self._build_geometry()

    def model_post_init(self, __context: object) -> None:
        """Override to skip auto-build — we call _build_geometry manually in __init__."""
        pass

    def _build_geometry(self) -> None:
        cs_profile = self._fastener.countersink_profile(self._fit)  # type: ignore[call-arg]
        hole_part = _make_fastener_hole(
            hole_diameters=self._fastener.clearance_hole_diameters,
            fastener=self._fastener,
            countersink_profile=cs_profile,
            depth=self.hole_depth,
            fit=self._fit,
            material=self._material,
            counter_sunk=self._counter_sunk,
            threaded_hole=True,
        )
        if not self._simple:
            raise NotImplementedError(
                "ThreadedHole with simple=False requires IsoThread port."
            )
        self.geom = hole_part
        self.label = f"ThreadedHole({self._fastener.info})"


# ═══════════════════════════════════════════════════════════════════════
# InsertHole
# ═══════════════════════════════════════════════════════════════════════


class InsertHole(BasePart):
    """Hole sized for heat-set nut insertion.

    Args:
        fastener: a ``HeatSetNut`` instance.
        fit: ``"Close"``, ``"Normal"`` (default), or ``"Loose"``.
        depth: hole depth; ``None`` = through-part.
        manufacturing_compensation: radial compensation for 3D printer
            over-extrusion (mm, default 0.0).
    """
    # ── Pydantic fields ─────────────────────────────────────────────
    _fastener: HeatSetNut = None  # type: ignore[assignment]
    _fit: str = "Normal"
    _depth: float | None = None
    _manufacturing_compensation: float = 0.0

    hole_depth: float = 0.0
    label: str = ""
    color: object = None
    def __init__(
        self,
        fastener: HeatSetNut,
        fit: Literal["Close", "Normal", "Loose"] = "Normal",
        depth: float | None = None,
        manufacturing_compensation: float = 0.0,
    ):
        if depth is not None:
            hole_depth = depth
        else:
            hole_depth = 10 * getattr(fastener, "_thread_diameter", 5.0)

        super().__init__(hole_depth=hole_depth)
        object.__setattr__(self, "_fastener", fastener)
        object.__setattr__(self, "_fit", fit)
        object.__setattr__(self, "_depth", depth)
        object.__setattr__(self, "_manufacturing_compensation", manufacturing_compensation)
        self._build_geometry()

    def model_post_init(self, __context: object) -> None:
        """Override to skip auto-build — we call _build_geometry manually in __init__."""
        pass

    def _build_geometry(self) -> None:
        cs_profile = self._fastener.countersink_profile(
            self._manufacturing_compensation
        )
        hole_part = _make_fastener_hole(
            hole_diameters=self._fastener.clearance_hole_diameters,
            fastener=self._fastener,
            countersink_profile=cs_profile,
            depth=self.hole_depth,
            fit=self._fit,
        )
        self.geom = hole_part
        self.label = f"InsertHole({self._fastener.info})"
