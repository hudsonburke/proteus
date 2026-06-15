"""Parametric bearings ported from bd_warehouse to the Proteus base hierarchy.

Provides an abstract Bearing base and concrete bearing classes:
  - SingleRowDeepGrooveBallBearing
  - SingleRowCappedDeepGrooveBallBearing
  - SingleRowTaperedRollerBearing
"""

from __future__ import annotations

import copy
import csv
import math
from abc import ABC, abstractmethod
from functools import cached_property
from pathlib import Path
from typing import ClassVar

import build123d as bd
from pydantic import Field

from ..common import BasePart, convert

# ---------------------------------------------------------------------------
# CSV parameter helpers
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Imperial number-size → diameter in inches
# Number drill sizes → diameter in inches
_NUMBER_DRILL_SIZES: dict[str, float] = {
    "#0000": 0.0210, "#000": 0.0340, "#00": 0.0470,
    "#0": 0.0600, "#1": 0.0730, "#2": 0.0860,
    "#3": 0.0990, "#4": 0.1120, "#5": 0.1250,
    "#6": 0.1380, "#7": 0.1510, "#8": 0.1640,
    "#9": 0.1770, "#10": 0.1900, "#11": 0.2030,
    "#12": 0.2160, "#13": 0.2210, "#14": 0.2280,
    "#15": 0.2340, "#16": 0.2460, "#17": 0.2570,
    "#18": 0.2650, "#19": 0.2720, "#20": 0.2770,
    "#21": 0.2820, "#22": 0.2870, "#23": 0.2900,
    "#24": 0.2950, "#25": 0.3020, "#26": 0.3070,
    "#27": 0.3160, "#28": 0.3230, "#29": 0.3300,
    "#30": 0.3360, "#31": 0.3440, "#32": 0.3540,
    "#33": 0.3620, "#34": 0.3680, "#35": 0.3770,
    "#36": 0.3840, "#37": 0.3970, "#38": 0.4040,
    "#39": 0.4100, "#40": 0.4200, "#41": 0.4280,
    "#42": 0.4360, "#43": 0.4380, "#44": 0.4440,
    "#45": 0.4530, "#46": 0.4600, "#47": 0.4680,
    "#48": 0.4760, "#49": 0.4840, "#50": 0.5000,
    "#51": 0.5160, "#52": 0.5310, "#53": 0.5460,
    "#54": 0.5630, "#55": 0.5780, "#56": 0.5940,
    "#57": 0.6090, "#58": 0.6250, "#59": 0.6410,
    "#60": 0.6560, "#61": 0.6720, "#62": 0.6880,
    "#63": 0.7030, "#64": 0.7190, "#65": 0.7340,
    "#66": 0.7500, "#67": 0.7660, "#68": 0.7810,
    "#69": 0.7970, "#70": 0.8120, "#71": 0.8280,
    "#72": 0.8440, "#73": 0.8590, "#74": 0.8750,
    "#75": 0.8910, "#76": 0.9060, "#77": 0.9220,
    "#78": 0.9380, "#79": 0.9530, "#80": 0.9690,
}

# Letter drill sizes → diameter in inches
_LETTER_DRILL_SIZES: dict[str, float] = {
    "A": 0.2340, "B": 0.2380, "C": 0.2420, "D": 0.2460,
    "E": 0.2500, "F": 0.2570, "G": 0.2610, "H": 0.2660,
    "I": 0.2720, "J": 0.2770, "K": 0.2810, "L": 0.2900,
    "M": 0.2950, "N": 0.3020, "O": 0.3160, "P": 0.3230,
    "Q": 0.3320, "R": 0.3390, "S": 0.3480, "T": 0.3580,
    "U": 0.3680, "V": 0.3770, "W": 0.3860, "X": 0.3970,
    "Y": 0.4040, "Z": 0.4130,
}

def _metric_str_to_float(s: str) -> float:
    """Safely evaluate a simple metric expression like '0.5' or '3 * 2'.

    Returns NaN for non-numeric placeholder values.
    """
    s = s.strip()
    if s in ("–", "—", ""):
        return float("nan")
    # Strip leading markers like '* ' used in designation fields
    if s.startswith("* "):
        s = s[2:]
    # Only eval strings that look like arithmetic / numeric expressions
    if all(c in "0123456789.+-*/() eE" for c in s):
        try:
            return float(eval(s))  # noqa: S307
        except Exception:
            return float("nan")
    return float("nan")


def _imperial_str_to_float(s: str) -> float:
    """Convert an imperial size string to a float in mm.

    Parses fractions and known drill/number sizes and returns values converted
    to the CAD-native unit (mm).
    """
    s = s.strip()
    if s in ("–", "—", ""):
        return float("nan")
    if s.startswith("#"):
        return convert(_NUMBER_DRILL_SIZES.get(s, float("nan")), "in")
    if s in _LETTER_DRILL_SIZES:
        return convert(_LETTER_DRILL_SIZES[s], "in")
    parts = s.replace('"', "").split()
    total = 0.0
    for p in parts:
        if "/" in p:
            n, d = p.split("/")
            total += float(n) / float(d)
        else:
            total += float(p)
    return convert(total, "in")

def _read_csv(filename: str) -> dict[str, dict[str, str]]:
    """Read a parameter CSV and return {Size: {TYPE:param: value, ...}}."""
    with (_DATA_DIR / filename).open(newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        params: dict[str, dict[str, str]] = {}
        for row in reader:
            key = row[fieldnames[0]]
            row.pop(fieldnames[0], None)
            params[key] = {k.strip(): v.strip() for k, v in row.items()}
    return params


def _isolate_type(
    target: str, data: dict[str, dict[str, str]]
) -> dict[str, dict[str, str]]:
    """Extract rows for *target* type, stripping the type prefix from keys."""
    result: dict[str, dict[str, str]] = {}
    for size, params in data.items():
        dims: dict[str, str] = {}
        for key, val in params.items():
            if ":" not in key:
                continue
            prefix, dim = key.split(":", 1)
            if prefix == target and val != "":
                dims[dim] = val
        if dims:
            result[size] = dims
    return result


def _evaluate_params(
    params: dict[str, str], *, is_metric: bool = True
) -> dict[str, float]:
    """Convert string parameter values to floats."""
    converter = _metric_str_to_float if is_metric else _imperial_str_to_float
    return {k: converter(v) for k, v in params.items()}


def _lookup_drill_diameters(
    drill_hole_sizes: dict[str, dict[str, str]]
) -> dict[str, dict[str, float]]:
    """Map drill size names to actual diameters for clearance/tap hole tables."""
    drill_hole_diameters: dict[str, dict[str, float]] = {}
    for size, fits in drill_hole_sizes.items():
        drill_hole_diameters[size] = {}
        for fit, drill_size in fits.items():
            if fit == "Size":
                continue
            try:
                drill_hole_diameters[size][fit] = float(drill_size)
            except ValueError:
                drill_hole_diameters[size][fit] = _imperial_str_to_float(drill_size)
    return drill_hole_diameters


# ---------------------------------------------------------------------------
# Abstract Bearing base
# ---------------------------------------------------------------------------


class Bearing(BasePart, ABC):
    """Parametric bearing base class.

    Concrete subclasses must set ``bearing_data`` (a dict from CSV) and
    implement the abstract geometry methods (or alias them to a default).
    """

    # --- class-level data (set by subclasses) ---
    bearing_data: ClassVar[dict[str, dict[str, str]]] = {}

    # --- Pydantic fields ---
    size: str = Field(..., description="Bearing size e.g. 'M8-22-7'")
    bearing_type: str = Field(default="SKT", description="Type identifier")

    # --- Initialization via _build_geometry (called by model_post_init) ---

    def _build_geometry(self) -> None:
        """Parse parameters, build geometry, assign self.geom."""
        parsed = _isolate_type(self.bearing_type, self.bearing_data)
        if self.size not in parsed:
            raise ValueError(
                f"Size {self.size!r} not found for type {self.bearing_type!r}"
            )
        self._bearing_dict = _evaluate_params(
            parsed[self.size],
            is_metric=self.size.startswith("M"),
        )
        self.geom = self._make_bearing()

    # ------------------------------------------------------------------
    # Dimension properties
    # ------------------------------------------------------------------

    @property
    def bearing_dict(self) -> dict[str, float]:
        """Evaluated parameter dict for this bearing."""
        return self._bearing_dict

    @property
    def bore_diameter(self) -> float:
        """Diameter of central hole."""
        return self.bearing_dict["d"]

    @property
    def outer_diameter(self) -> float:
        """Bearing outer diameter."""
        return self.bearing_dict["D"]

    @property
    def thickness(self) -> float:
        """Bearing thickness / width."""
        return self.bearing_dict.get("T", self.bearing_dict.get("B", 0.0))

    @cached_property
    def roller_diameter(self) -> float:
        """Derived class may override; default is computed from d1/D1."""
        d1 = self.bearing_dict.get("d1")
        D1 = self.bearing_dict.get("D1")
        if d1 is not None and D1 is not None:
            return 0.625 * (D1 - d1)
        return float("nan")

    @cached_property
    def race_center_radius(self) -> float:
        """Default roller race center radius."""
        d1 = self.bearing_dict.get("d1")
        D1 = self.bearing_dict.get("D1")
        if d1 is not None and D1 is not None:
            return (D1 + d1) / 4.0
        return float("nan")

    @property
    def roller_count(self) -> int:
        return int(1.8 * math.pi * self.race_center_radius / self.roller_diameter)

    def method_exists(self, method: str) -> bool:
        """Return True if the derived class defines *method*."""
        return hasattr(self.__class__, method) and callable(
            getattr(self.__class__, method, None)
        )

    @property
    def info(self) -> str:
        """Return identifying information."""
        return f"{self.bearing_class}({self.bearing_type}): {self.size}"

    @property
    def bearing_class(self) -> str:
        """Name of the derived class that created this bearing."""
        return type(self).__name__

    @property
    def clearance_hole_diameters(self) -> dict[str, float]:
        """Drill diameters for clearance holes (Close, Normal, Loose fits)."""
        sizes = _read_csv("clearance_hole_sizes.csv")
        data = _lookup_drill_diameters(sizes)
        size_prefix = self.size.split("-")[0]
        try:
            return data[size_prefix]
        except KeyError as e:
            raise ValueError(
                f"No clearance hole data for size {self.bore_diameter}"
            ) from e

    @property
    def capped(self) -> bool:
        """Return True if this bearing type has caps/shields."""
        return self.method_exists("_make_cap") and type(self)._make_cap is not Bearing._make_cap

    # ------------------------------------------------------------------
    # Abstract geometry sections — subclasses must provide
    # ------------------------------------------------------------------

    @abstractmethod
    def _inner_race_section(self) -> bd.Face:
        """2D profile of the inner race (in XZ plane)."""
        ...

    @abstractmethod
    def _outer_race_section(self) -> bd.Face:
        """2D profile of the outer race (in XZ plane)."""
        ...

    @abstractmethod
    def _roller(self) -> bd.Solid:
        """A single rolling element."""
        ...

    @abstractmethod
    def _countersink_profile(self) -> bd.Face:
        """Profile of a countersink cutter for this bearing."""
        ...

    # ------------------------------------------------------------------
    # Default implementations usable by simple subclasses
    # ------------------------------------------------------------------

    def _default_inner_race_section(self) -> bd.Face:
        d1 = self.bearing_dict["d1"]
        d = self.bearing_dict["d"]
        B = self.bearing_dict["B"]
        r12 = self.bearing_dict["r12"]
        with bd.BuildSketch(bd.Plane.XZ) as section:
            with bd.Locations(((d1 + d) / 4, 0)):
                bd.RectangleRounded((d1 - d) / 2, B, r12)
        return section.sketch.face()

    def _default_outer_race_section(self) -> bd.Face:
        D1 = self.bearing_dict["D1"]
        D = self.bearing_dict["D"]
        B = self.bearing_dict["B"]
        r12 = self.bearing_dict["r12"]
        with bd.BuildSketch(bd.Plane.XZ) as section:
            with bd.Locations(((D1 + D) / 4, 0)):
                bd.RectangleRounded((D - D1) / 2, B, r12)
        return section.sketch.face()

    def _default_roller(self) -> bd.Solid:
        r = bd.Solid.make_sphere(self.roller_diameter / 2)
        r.color = bd.Color(0x909090)
        return r

    def _default_countersink_profile(self, interference: float = 0.0) -> bd.Face:
        D = self.bearing_dict["D"]
        B = self.bearing_dict["B"]
        with bd.BuildSketch(bd.Plane.XZ) as profile:
            bd.Rectangle(D / 2 - interference, B, align=bd.Align.MIN)
        return profile.sketch.face()

    def _default_cap(self) -> bd.Solid:
        D1 = self.bearing_dict["D1"]
        d1 = self.bearing_dict["d1"]
        B = self.bearing_dict["B"]
        with bd.BuildPart() as cap:
            with bd.BuildSketch(bd.Plane.XY.offset(B * 0.42)):
                bd.Circle(D1 / 2)
                bd.Circle(d1 / 2, mode=bd.Mode.SUBTRACT)
            bd.extrude(amount=B * 0.05)
        s = cap.solid()
        s.color = bd.Color(0x030303)
        return s

    # ------------------------------------------------------------------
    # Assembly
    # ------------------------------------------------------------------

    def _make_bearing(self) -> bd.Compound:
        """Create the full bearing compound from race sections and rollers."""
        outer_race = bd.revolve(self._outer_race_section(), bd.Axis.Z)
        outer_race.color = bd.Color(0xC0C0C0)
        outer_race.label = "OuterRace"

        inner_race = bd.revolve(self._inner_race_section(), bd.Axis.Z)
        inner_race.color = bd.Color(0xC0C0C0)
        inner_race.label = "InnerRace"

        pieces: list[bd.Shape] = [outer_race, inner_race]

        if self._has_cap():
            cap = self._make_cap()
            cap.label = "Cap"
            pieces.append(cap)
            pieces.append(copy.copy(cap).mirror(bd.Plane.XY))
        else:
            roller = self._roller()
            roller.label = "Roller"
            locs = bd.PolarLocations(
                self.race_center_radius, self.roller_count
            ).locations
            pieces.extend(
                [locs[0] * roller]
                + [loc * copy.copy(roller) for loc in locs[1:]]
            )
        bearing = bd.Compound(children=pieces)
        bearing.color = bd.Color(0xC0C0C0)
        return bearing

    def _has_cap(self) -> bool:
        """Return True if the subclass defines its own cap."""
        return type(self)._make_cap is not Bearing._make_cap

    def _make_cap(self) -> bd.Solid:
        """Create a cap/shield; override in capped bearings."""
        return self._default_cap()

    # ------------------------------------------------------------------
    # Type query helpers
    # ------------------------------------------------------------------

    @classmethod
    def types(cls) -> set[str]:
        """Return the set of bearing type keys in the class data."""
        if not cls.bearing_data:
            return set()
        first = next(iter(cls.bearing_data.values()))
        return {k.split(":")[0] for k in first}

    @classmethod
    def sizes(cls, bearing_type: str) -> list[str]:
        """Return sizes available for a given type."""
        return list(_isolate_type(bearing_type, cls.bearing_data).keys())


# ===================================================================
# Concrete bearings
# ===================================================================


class SingleRowDeepGrooveBallBearing(Bearing):
    """Single Row Deep Groove Ball Bearing.

    The most widely used bearing type — versatile, non-separable, suitable
    for high speeds and robust in operation.
    """

    bearing_data: ClassVar = _read_csv(
        "single_row_deep_groove_ball_bearing_parameters.csv"
    )

    _inner_race_section = Bearing._default_inner_race_section
    _outer_race_section = Bearing._default_outer_race_section
    _roller = Bearing._default_roller
    _countersink_profile = Bearing._default_countersink_profile


class SingleRowCappedDeepGrooveBallBearing(Bearing):
    """Single Row Capped Deep Groove Ball Bearing.

    Deep groove ball bearings capped with seals or shields on both sides.
    """

    bearing_data: ClassVar = _read_csv(
        "single_row_capped_deep_groove_ball_bearing_parameters.csv"
    )

    _inner_race_section = Bearing._default_inner_race_section
    _outer_race_section = Bearing._default_outer_race_section
    _roller = Bearing._default_roller
    _countersink_profile = Bearing._default_countersink_profile

    def _make_cap(self) -> bd.Solid:
        return self._default_cap()


class SingleRowTaperedRollerBearing(Bearing):
    """Tapered Roller Bearing.

    Tapered inner and outer ring raceways with tapered rollers. Designed
    for combined radial and axial loads. Separable — inner ring with roller
    and cage assembly (cone) can be mounted separately from the outer ring (cup).
    """

    bearing_data: ClassVar = _read_csv(
        "single_row_tapered_roller_bearing_parameters.csv"
    )

    # ------------------------------------------------------------------
    # Overrides
    # ------------------------------------------------------------------

    @cached_property
    def roller_diameter(self) -> float:
        """Diameter of the larger end of the roller (with cage clearance)."""
        _ = self._roller_obj
        return max(self._roller_diameters) * 1.25

    @cached_property
    def roller_count(self) -> int:
        return math.floor(
            self._race_center_radius * 2 * math.pi / self.roller_diameter
        )

    @cached_property
    def race_center_radius(self) -> float:
        _ = self._roller_obj
        return self._race_center_radius

    @cached_property
    def contact_angle(self) -> float:
        """Angle of the outer raceway in degrees."""
        e = self.bearing_dict["e"]
        return math.degrees(math.atan(e))

    def _inner_race_section(self) -> bd.Face:
        d = self.bearing_dict["d"]
        da = self.bearing_dict["da"]
        B = self.bearing_dict["B"]
        T = self.bearing_dict["T"]
        r12 = self.bearing_dict["r12"]
        inner_raceway_angle = self.contact_angle / 1.5

        with bd.BuildSketch(
            bd.Plane((0, 0, T - B / 2), x_dir=(1, 0, 0), z_dir=(0, -1, 0))
        ) as section:
            with bd.BuildLine() as bl:
                l1 = bd.Polyline((da / 2 - r12, -B), (d / 2, -B), (d / 2, 0))
                l2 = bd.PolarLine(
                    l1 @ 0,
                    B,
                    90 - inner_raceway_angle,
                    length_mode=bd.LengthMode.VERTICAL,
                )
                bd.Line(l1 @ 1, l2 @ 1)
            bd.make_face()
            bd.fillet(section.vertices().group_by(bd.Axis.X)[0], r12)

            # Slot around the inner race to capture the rollers
            outside_edge = section.edges().sort_by(bd.Edge.length)[-1]
            bd.add(
                bd.sweep(
                    outside_edge.trim(0.075, 0.925),
                    bd.Edge.make_line(
                        outside_edge.position_at(0.5),
                        outside_edge.position_at(0.5)
                        + outside_edge.tangent_at(0.5).rotate(bd.Axis.Z, 90)
                        * r12
                        / 2,
                    ),
                ),
                mode=bd.Mode.SUBTRACT,
            )
        return section.sketch.face()

    def _outer_race_section(self) -> bd.Face:
        B = self.bearing_dict["B"]
        C = self.bearing_dict["C"]
        D = self.bearing_dict["D"]
        T = self.bearing_dict["T"]
        r34 = self.bearing_dict["r34"]

        with bd.BuildSketch(
            bd.Plane((0, 0, -B / 2), x_dir=(1, 0, 0), z_dir=(0, -1, 0))
        ) as section:
            with bd.BuildLine() as bl:
                l1 = bd.Polyline(
                    (D / 2, 0),
                    (D / 2, C),
                    (D / 2 - r34 * 1.5, C),
                )
                l2 = bd.PolarLine(
                    l1 @ 1,
                    C,
                    direction=bd.Vector(0, -1).rotate(
                        bd.Axis.Z, -self.contact_angle
                    ),
                    length_mode=bd.LengthMode.VERTICAL,
                )
                bd.Line(l2 @ 1, l1 @ 0)
            bd.make_face()
            bd.fillet(section.vertices().group_by(bd.Axis.X)[-1], r34)
        return section.sketch.face()

    def _roller(self) -> bd.Solid:
        return self._roller_obj

    @cached_property
    def _roller_obj(self) -> bd.Solid:
        """Build the tapered roller solid, caching side-effect outputs."""
        GAP = 0.05
        inner_section = self._inner_race_section()
        outer_section = self._outer_race_section()

        inner_edge = (
            inner_section.edges()
            .filter_by(bd.Axis.Z, reverse=True)
            .sort_by(bd.Edge.length)[-1]
        )
        outer_edge = outer_section.edges().sort_by(bd.Axis.X)[0]

        roller_inner_edge = inner_edge.trim(GAP, 1 - GAP)
        c_inner_a = bd.Axis(inner_edge)
        c_outer_a = bd.Axis(outer_edge)
        r_axis = bd.Axis(
            c_inner_a.intersect(c_outer_a),
            (c_inner_a.direction + c_outer_a.direction * -1) / 2,
        )

        roller_non_planar_face = bd.Face.revolve(roller_inner_edge, 360, r_axis)
        roller_circles = roller_non_planar_face.edges().filter_by(
            bd.GeomType.CIRCLE
        )
        roller_ends = [bd.Face(bd.Wire(e)) for e in roller_circles]
        roller_solid = bd.Solid(bd.Shell(roller_ends + [roller_non_planar_face]))

        self._roller_diameters = [2 * e.radius for e in roller_circles]
        self._cage_edge_raw = bd.section(roller_solid, bd.Plane.XZ).intersect(
            bd.Axis(
                r_axis.position
                + bd.Vector(0.3 * min(self._roller_diameters), 0, 0),
                r_axis.direction,
            )
        )
        self._cage_edge = (
            self._cage_edge_raw[0]
            if isinstance(self._cage_edge_raw, list)
            else self._cage_edge_raw
        )
        self._race_center_radius = (
            roller_solid.faces().sort_by(bd.Axis.Z)[-1].center().X
        )

        roller_solid.position -= (self._race_center_radius, 0, 0)
        roller_solid.color = bd.Color(0x909090)
        return roller_solid

    def _countersink_profile(self) -> bd.Face:
        return self._default_countersink_profile()

    def _make_cage(self) -> bd.Compound:
        """Cage holding the rollers together with the cone."""
        roller_solid = self._roller_obj
        roller_hole_cutter = bd.offset(
            roller_solid, convert(0.25, "mm"), kind=bd.Kind.INTERSECTION
        ).move(bd.Pos(X=self._race_center_radius))

        roller_max_r = (
            roller_solid.faces()
            .filter_by(bd.GeomType.PLANE)
            .sort_by(bd.Face.area)[0]
            .edge()
            .radius
        )
        cage_side: bd.Edge = bd.Pos(X=roller_max_r / 4) * bd.Edge.make_line(
            self._cage_edge @ -0.1, self._cage_edge @ 1.1
        )

        bottom = (
            1
            if self._cage_edge.position_at(0).Y
            < self._cage_edge.position_at(1).Y
            else 0
        )
        hook_sign = -1 if bottom == 0 else 1
        hook = bd.JernArc(
            cage_side @ bottom,
            (cage_side % bottom) * hook_sign,
            convert(3, "mm"),
            80,
        )
        cage_profile = bd.Wire([cage_side, hook])
        cage_surface = bd.Shell.revolve(cage_profile, 360, bd.Axis.Z)
        cage_surface -= (
            bd.PolarLocations(0, self.roller_count) * roller_hole_cutter
        )
        cage = bd.Solid.thicken(cage_surface, convert(0.5, "mm"))
        cage.color = bd.Color(0x909090)
        return cage

    # ------------------------------------------------------------------
    # Override _make_bearing to include the cage
    # ------------------------------------------------------------------

    def _make_bearing(self) -> bd.Compound:
        outer_race = bd.revolve(self._outer_race_section(), bd.Axis.Z)
        outer_race.color = bd.Color(0xC0C0C0)
        outer_race.label = "OuterRace"

        inner_race = bd.revolve(self._inner_race_section(), bd.Axis.Z)
        inner_race.color = bd.Color(0xC0C0C0)
        inner_race.label = "InnerRace"

        pieces: list[bd.Shape] = [outer_race, inner_race]

        roller = self._roller_obj
        roller.label = "Roller"
        locs = bd.PolarLocations(
            self.race_center_radius, self.roller_count
        ).locations
        pieces.extend(
            [locs[0] * roller] + [loc * copy.copy(roller) for loc in locs[1:]]
        )

        cage = self._make_cage()
        cage.label = "Cage"
        pieces.append(cage)

        bearing = bd.Compound(children=pieces)
        bearing.color = bd.Color(0xC0C0C0)
        return bearing
