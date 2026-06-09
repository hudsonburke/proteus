"""Parametric involute spur gears.

Port of ``bd_warehouse.gear`` adapted to Proteus base classes.  All linear
dimensions are in mm; angles are in degrees.
"""

from __future__ import annotations

from math import acos, cos, degrees, radians, sin, tan

import build123d as bd
from OCP.StdFail import StdFail_NotDone

from ..common import BaseCurve, BasePart, BaseSketch


class InvoluteToothProfile(BaseCurve):
    """The outline of a single involute spur-gear tooth.

    Args:
        module: Ratio of the pitch diameter to the number of teeth, in mm.
        tooth_count: Number of teeth in the complete gear.
        pressure_angle: Angle between the line of action and the tangent to
            the pitch circle, in degrees.  Common values are 14.5° or 20°.
        root_fillet: Radius of the fillet at the tooth root, in mm.
            ``None`` disables the fillet.
        addendum: Radial distance from the pitch circle to the tooth tip,
            in mm.  Defaults to *module*.
        dedendum: Radial distance from the pitch circle to the tooth-space
            bottom, in mm.  Defaults to ``1.25 * module``.
        closed: When ``True``, close the tooth profile with a chord between
            the two root endpoints so the result is a closed wire.
    """

    module: float
    tooth_count: int
    pressure_angle: float
    root_fillet: float | None = None
    addendum: float | None = None
    dedendum: float | None = None
    closed: bool = False

    @property
    def pitch_radius(self) -> float:
        """Radius of the pitch circle."""
        return self.module * self.tooth_count / 2

    @property
    def base_radius(self) -> float:
        """Radius of the base circle."""
        return self.pitch_radius * cos(radians(self.pressure_angle))

    @property
    def addendum_radius(self) -> float:
        """Radius of the addendum (outer) circle."""
        add = self.addendum if self.addendum is not None else self.module
        return self.pitch_radius + add

    @property
    def root_radius(self) -> float:
        """Radius of the root (dedendum) circle."""
        ded = self.dedendum if self.dedendum is not None else 1.25 * self.module
        return self.pitch_radius - ded

    def _build_geometry(self) -> None:
        half_thick_angle = 90 / self.tooth_count
        half_pitch_angle = half_thick_angle + degrees(
            tan(radians(self.pressure_angle)) - radians(self.pressure_angle)
        )

        # Involute curve points
        involute_size = self.addendum_radius - self.base_radius
        pnts: list[tuple[float, float]] = []
        for i in range(11):
            r = self.base_radius + involute_size * i / 10
            α = acos(self.base_radius / r)
            involute = tan(α) - α
            rp = r * cos(involute)
            if rp > self.root_radius:
                pnts.append((rp, r * sin(involute)))

        with bd.BuildLine(
            bd.Plane.XY.rotated((0, 0, -half_pitch_angle))
        ) as tooth:
            l1 = bd.Spline(*pnts)
            l2 = bd.Line(pnts[0], (self.root_radius, 0))
            root = bd.RadiusArc(
                l2 @ 1,
                bd.Vector(self.root_radius, 0).rotate(
                    bd.Axis.Z, -2 * half_thick_angle
                ),
                self.root_radius,
            )
            top_land = bd.RadiusArc(
                l1 @ 1,
                bd.Vector(self.addendum_radius, 0),
                -self.addendum_radius,
            )
            if self.root_fillet is not None:
                try:
                    bd.fillet(
                        tooth.vertices().sort_by(bd.Axis.X)[1],
                        self.root_fillet,
                    )
                except StdFail_NotDone as err:
                    raise ValueError(
                        "Invalid root radius, try a smaller value"
                    ) from err
            bd.mirror(about=bd.Plane.XZ)

        if self.closed:
            close_edges = [
                bd.Edge.make_line(
                    tooth.vertices().sort_by(bd.Axis.Y)[-1].to_tuple(),
                    tooth.vertices().sort_by(bd.Axis.Y)[0].to_tuple(),
                )
            ]
        else:
            close_edges: list[bd.Edge] = []

        self.geom = bd.Wire(tooth.edges() + close_edges)


class SpurGearPlan(BaseSketch):
    """The 2D face profile of an involute spur gear.

    Args:
        module: Ratio of the pitch diameter to the number of teeth, in mm.
        tooth_count: Number of teeth.
        pressure_angle: Pressure angle in degrees (commonly 14.5° or 20°).
        root_fillet: Root fillet radius in mm, or ``None`` to omit.
        addendum: Addendum in mm, or ``None`` to use *module*.
        dedendum: Dedendum in mm, or ``None`` to use ``1.25 * module``.
    """

    module: float
    tooth_count: int
    pressure_angle: float
    root_fillet: float | None = None
    addendum: float | None = None
    dedendum: float | None = None

    @property
    def pitch_radius(self) -> float:
        """Radius of the pitch circle."""
        return self.module * self.tooth_count / 2

    @property
    def base_radius(self) -> float:
        """Radius of the base circle."""
        return self.pitch_radius * cos(radians(self.pressure_angle))

    @property
    def addendum_radius(self) -> float:
        """Radius of the addendum (outer) circle."""
        add = self.addendum if self.addendum is not None else self.module
        return self.pitch_radius + add

    @property
    def root_radius(self) -> float:
        """Radius of the root (dedendum) circle."""
        ded = self.dedendum if self.dedendum is not None else 1.25 * self.module
        return self.pitch_radius - ded

    def _build_geometry(self) -> None:
        if self.base_radius < self.root_radius:
            raise ValueError(
                "Invalid configuration, try changing the pressure angle"
            )

        gear_tooth = InvoluteToothProfile(
            module=self.module,
            tooth_count=self.tooth_count,
            pressure_angle=self.pressure_angle,
            root_fillet=self.root_fillet,
            addendum=self.addendum,
            dedendum=self.dedendum,
        )
        tooth_wire = gear_tooth.geom
        gear_teeth = bd.PolarLocations(0, self.tooth_count) * tooth_wire
        gear_wire = bd.Wire(
            [e for tooth in gear_teeth for e in tooth.edges()]
        )
        gear_face = bd.Face(gear_wire)
        if gear_face.normal_at().Z < 0:
            gear_face = -gear_face
        with bd.BuildSketch() as sketch:
            bd.add(gear_face)
        self.geom = sketch.sketch


class SpurGear(BasePart):
    """The 3D solid model of an involute spur gear.

    Args:
        module: Ratio of the pitch diameter to the number of teeth, in mm.
        tooth_count: Number of teeth.
        pressure_angle: Pressure angle in degrees (commonly 14.5° or 20°).
        thickness: Gear face width (thickness along the axis), in mm.
        root_fillet: Root fillet radius in mm, or ``None`` to omit.
        addendum: Addendum in mm, or ``None`` to use *module*.
        dedendum: Dedendum in mm, or ``None`` to use ``1.25 * module``.
    """

    module: float
    tooth_count: int
    pressure_angle: float
    thickness: float
    root_fillet: float | None = None
    addendum: float | None = None
    dedendum: float | None = None

    @property
    def pitch_radius(self) -> float:
        """Radius of the pitch circle."""
        return self.module * self.tooth_count / 2

    @property
    def base_radius(self) -> float:
        """Radius of the base circle."""
        return self.pitch_radius * cos(radians(self.pressure_angle))

    @property
    def addendum_radius(self) -> float:
        """Radius of the addendum (outer) circle."""
        add = self.addendum if self.addendum is not None else self.module
        return self.pitch_radius + add

    @property
    def root_radius(self) -> float:
        """Radius of the root (dedendum) circle."""
        ded = self.dedendum if self.dedendum is not None else 1.25 * self.module
        return self.pitch_radius - ded

    def _build_geometry(self) -> None:
        gear_plan = SpurGearPlan(
            module=self.module,
            tooth_count=self.tooth_count,
            pressure_angle=self.pressure_angle,
            root_fillet=self.root_fillet,
            addendum=self.addendum,
            dedendum=self.dedendum,
        )
        self.geom = bd.extrude(gear_plan.geom, amount=self.thickness)
