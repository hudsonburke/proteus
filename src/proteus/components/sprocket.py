"""Parametric chain sprockets.

Port of ``bd_warehouse.sprocket`` adapted to Proteus base classes.  All
linear dimensions are in mm.  Defaults correspond to standard bicycle chain
(1/2″ pitch, 5/16″ roller diameter).
"""

from __future__ import annotations

from math import cos, pi, radians, sqrt

import build123d as bd

from ..common import BasePart


class Sprocket(BasePart):
    """A parametric chain sprocket.

    Args:
        num_teeth: Number of teeth on the sprocket perimeter.
        chain_pitch: Distance between the centres of two adjacent rollers,
            in mm.  Defaults to 12.7 (1/2″).
        roller_diameter: Diameter of the chain rollers, in mm.
            Defaults to 7.9375 (5/16″).
        clearance: Additional gap between the chain rollers and the
            sprocket teeth, in mm.  Defaults to 0.
        thickness: Sprocket thickness, in mm.  Defaults to 2.1336
            (0.084″, typical for single-speed bicycle chain).
        bolt_circle_diameter: Diameter of the mounting bolt-hole pattern,
            in mm.  Defaults to 0 (no bolt holes).
        num_mount_bolts: Number of bolt holes.  Defaults to 0.
        mount_bolt_diameter: Diameter of each mounting bolt hole, in mm.
            Defaults to 0.
        bore_diameter: Diameter of the central bore, in mm.
            Defaults to 0 (no bore).
    """

    num_teeth: int
    chain_pitch: float = 12.7
    roller_diameter: float = 7.9375
    clearance: float = 0.0
    thickness: float = 2.1336
    bolt_circle_diameter: float = 0.0
    num_mount_bolts: int = 0
    mount_bolt_diameter: float = 0.0
    bore_diameter: float = 0.0

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def pitch_radius(self) -> float:
        """Radius of the circle formed by the chain-roller centres."""
        return Sprocket.sprocket_pitch_radius(self.num_teeth, self.chain_pitch)

    @property
    def outer_radius(self) -> float:
        """Radius from the sprocket centre to the tips of the teeth."""
        if self._flat_teeth:
            return self.pitch_radius + self.roller_diameter / 4
        return sqrt(
            self.pitch_radius**2 - (self.chain_pitch / 2) ** 2
        ) + sqrt(
            (self.chain_pitch - self.roller_diameter / 2) ** 2
            - (self.chain_pitch / 2) ** 2
        )

    @property
    def pitch_circumference(self) -> float:
        """Circumference of the sprocket at the pitch radius."""
        return Sprocket.sprocket_circumference(self.num_teeth, self.chain_pitch)

    @property
    def plan(self) -> bd.Face:
        """2D plan of the base sprocket (no cutouts)."""
        tooth_tip = Sprocket._make_tooth_outline(
            self.num_teeth, self.chain_pitch, self.roller_diameter, self.clearance
        )
        tooth_face = bd.Face(
            bd.Wire(
                tooth_tip.edges()
                + [
                    bd.Line((0, 0), tooth_tip @ 0),
                    bd.Line((0, 0), tooth_tip @ 1),
                ]
            )
        )
        if tooth_face.normal_at().Z == -1:
            tooth_face = -tooth_face
        return bd.Face() + bd.PolarLocations(0, self.num_teeth) * tooth_face

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def sprocket_pitch_radius(num_teeth: int, chain_pitch: float) -> float:
        """Calculate the pitch radius of a sprocket.

        Args:
            num_teeth: Number of teeth.
            chain_pitch: Distance between adjacent pins, in mm.
        """
        return sqrt(
            chain_pitch * chain_pitch / (2 * (1 - cos(2 * pi / num_teeth)))
        )

    @staticmethod
    def sprocket_circumference(num_teeth: int, chain_pitch: float) -> float:
        """Calculate the pitch circumference of a sprocket.

        Args:
            num_teeth: Number of teeth.
            chain_pitch: Distance between adjacent pins, in mm.
        """
        return (
            2
            * pi
            * sqrt(
                chain_pitch
                * chain_pitch
                / (2 * (1 - cos(2 * pi / num_teeth)))
            )
        )

    @staticmethod
    def _make_tooth_outline(
        num_teeth: int,
        chain_pitch: float,
        roller_diameter: float,
        clearance: float = 0.0,
    ) -> bd.Wire:
        """Create a Wire for a single sprocket tooth.

        Two tooth shapes are possible:

        * **"Spiky"** — rollers are large enough that no flat top section
          bridges the gap between roller slots (4 edges).
        * **"Flat"** — a circular flat section bridges the two roller
          slots (5 edges).
        """
        roller_rad = roller_diameter / 2 + clearance
        tooth_a_degrees = 360 / num_teeth
        pitch_rad = sqrt(
            chain_pitch**2 / (2 * (1 - cos(radians(tooth_a_degrees))))
        )
        outer_rad = pitch_rad + roller_rad / 2

        outer_circle = bd.CenterArc((0, 0), outer_rad, 0, 360)
        roller_circle = bd.CenterArc(
            bd.Vector(pitch_rad, 0).rotate(bd.Axis.Z, tooth_a_degrees / 2),
            roller_rad,
            0,
            360,
        )
        link_circle = bd.CenterArc(
            bd.Vector(pitch_rad, 0).rotate(bd.Axis.Z, -tooth_a_degrees / 2),
            chain_pitch - roller_rad,
            0,
            360,
        )

        roller_line_pnt = bd.Line(
            roller_circle.arc_center, link_circle.arc_center
        ) @ (roller_rad / chain_pitch)

        outer_pnt = (
            link_circle.find_intersection_points(outer_circle)
            .sort_by(bd.Axis.Y)[-1]
        )
        roller_start_pnt = (
            bd.PolarLine((0, 0), pitch_rad - roller_rad, tooth_a_degrees / 2)
            @ 1
        )

        arc1 = roller_circle.trim(roller_start_pnt, roller_line_pnt)

        if outer_pnt.Y > 0:  # "Flat" topped sprockets
            arc2 = link_circle.trim(roller_line_pnt, outer_pnt)
            arc3 = bd.RadiusArc(
                outer_pnt, (outer_pnt.X, -outer_pnt.Y), outer_rad
            )
            arc4 = arc2.mirror(bd.Plane.XZ)
            arc5 = arc1.mirror(bd.Plane.XZ)
            tooth_perimeter = bd.Wire([arc1, arc2, arc3, arc4, arc5])
        else:
            link_axis_pnt = (
                link_circle.intersect(bd.Axis.X).sort_by(bd.Axis.X)[-1]
            )
            arc2 = link_circle.trim(roller_line_pnt, link_axis_pnt)
            arc3 = arc2.mirror(bd.Plane.XZ)
            arc4 = arc1.mirror(bd.Plane.XZ)
            tooth_perimeter = bd.Wire([arc1, arc2, arc3, arc4])

        return tooth_perimeter

    # ------------------------------------------------------------------
    # Internal construction
    # ------------------------------------------------------------------

    def _build_geometry(self) -> None:
        # -- validate ---------------------------------------------------
        if self.roller_diameter >= self.chain_pitch:
            raise ValueError(
                f"roller_diameter {self.roller_diameter} is too large "
                f"for chain_pitch {self.chain_pitch}"
            )
        if not isinstance(self.num_teeth, int) or self.num_teeth <= 2:
            raise ValueError(
                f"num_teeth must be an integer greater than 2, "
                f"not {self.num_teeth}"
            )

        sprocket = self._make_sprocket()

        # Unwrap a single-element Compound when produced
        if isinstance(sprocket, bd.Compound):
            sprocket = sprocket.unwrap()

        self.geom = sprocket

    def _make_sprocket(self) -> bd.Compound:
        """Build the full sprocket solid (teeth, bolt holes, bore)."""
        tooth_tip = Sprocket._make_tooth_outline(
            self.num_teeth, self.chain_pitch, self.roller_diameter, self.clearance
        )

        # Record whether teeth are "flat" (5-edge outline) or "spiky"
        self._flat_teeth = len(tooth_tip.edges()) == 5

        tooth_face = bd.Pos(Z=-self.thickness / 2) * bd.Face(
            bd.Wire(
                tooth_tip.edges()
                + [
                    bd.Line((0, 0), tooth_tip @ 0),
                    bd.Line((0, 0), tooth_tip @ 1),
                ]
            )
        )
        tooth = bd.extrude(tooth_face, self.thickness, (0, 0, 1))

        if self._flat_teeth:
            tip_face = (
                tooth.faces()
                .filter_by(bd.GeomType.CYLINDER)
                .sort_by_distance((0, 0))[-1]
            )
            to_chamfer = tip_face.edges().filter_by(bd.GeomType.CIRCLE)
            tooth = bd.chamfer(
                to_chamfer,
                self.thickness * 0.25,
                self.thickness * 0.5,
                reference=tip_face,
            )

        sprocket = bd.Solid() + bd.PolarLocations(0, self.num_teeth) * tooth
        sprocket.orientation += (0, 0, 90)

        # Bolt holes
        if (
            self.bolt_circle_diameter != 0
            and self.num_mount_bolts != 0
            and self.mount_bolt_diameter != 0
        ):
            sprocket -= bd.PolarLocations(
                self.bolt_circle_diameter / 2, self.num_mount_bolts
            ) * bd.Cylinder(self.mount_bolt_diameter / 2, self.thickness)

        # Central bore
        if self.bore_diameter != 0:
            sprocket -= bd.Cylinder(self.bore_diameter / 2, self.thickness)

        return sprocket
