"""Parametric orthotic limb cuffs for exoskeleton attachment.

A cuff is a partial cylindrical shell that wraps around a limb segment.
It is sized from the limb circumference and can carry strap slots, padding,
and cable-guide attachment points.

All linear dimensions are in mm; angles in degrees (proteus CAD-native units).
Use ``Cuff.from_measurements()`` to construct directly from melos SI-unit data,
or use :func:`~proteus.fitting.build_cuff` as a convenience wrapper.
"""

from __future__ import annotations

from math import cos, pi, sin

import build123d as bd

from ..common import BasePart

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from melos.core.common.types import Transform as MelosTransform
    from melos.core.retarget.model import SegmentMeasurementSet


class Cuff(BasePart):
    """A partial cylindrical cuff that wraps around a limb segment.

    Parameters
    ----------
    limb_circumference:
        Circumference of the limb at the attachment site, in **mm**.
        The inner radius is derived as ``circumference / (2π)``.
    width:
        Axial height of the cuff along the limb, in **mm**.
    coverage:
        Fraction of the circumference covered (0–1).  ``0.75`` gives a
        270° open-back cuff.  Clamped to (0, 1].
    wall_thickness:
        Shell wall thickness in mm.
    padding_thickness:
        Clearance for inner padding in mm.  The inner surface of the shell
        is offset outward from the limb surface by this amount.
    """

    limb_circumference: float
    width: float = 40.0
    coverage: float = 0.75
    wall_thickness: float = 3.0
    padding_thickness: float = 2.0

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def limb_radius(self) -> float:
        """Limb radius derived from circumference, in mm."""
        return self.limb_circumference / (2 * pi)

    @property
    def inner_radius(self) -> float:
        """Inner shell radius (limb surface + padding), in mm."""
        return self.limb_radius + self.padding_thickness

    @property
    def outer_radius(self) -> float:
        """Outer shell radius, in mm."""
        return self.inner_radius + self.wall_thickness

    @property
    def arc_angle(self) -> float:
        """Coverage arc in degrees."""
        return self.coverage * 360.0

    # ------------------------------------------------------------------
    # Construction from melos subject data
    # ------------------------------------------------------------------

    @classmethod
    def from_measurements(
        cls,
        measurements: SegmentMeasurementSet,
        segment_id: str,
        coverage: float = 0.75,
        wall_thickness: float = 3.0,
        padding_thickness: float = 2.0,
        width: float = 40.0,
        *,
        attachment_joints: dict[str, MelosTransform] | None = None,
    ) -> Cuff:
        """Construct a cuff from melos segment measurements in SI units.

        Parameters
        ----------
        measurements:
            A ``SegmentMeasurementSet`` from melos-core.  Segment lengths
            are in **metres** and converted to mm internally.
        segment_id:
            Which segment to fit (e.g. ``"left_shank"``).
        coverage, wall_thickness, padding_thickness, width:
            Forwarded to the ``Cuff`` constructor (already in mm / fraction).
        attachment_joints:
            Optional melos ``Transform`` frames (in metres) mapped to
            build123d ``RigidJoint``s on the finished cuff.

        Returns
        -------
        Cuff
            A fully constructed cuff part.
        """
        from ..fitting import build_cuff

        return build_cuff(
            measurements,
            segment_id,
            coverage=coverage,
            wall_thickness=wall_thickness,
            padding_thickness=padding_thickness,
            width=width,
            attachment_joints=attachment_joints,
        )

    # ------------------------------------------------------------------
    # Internal geometry
    # ------------------------------------------------------------------

    def _build_geometry(self) -> None:
        r_in = self.inner_radius
        r_out = self.outer_radius
        a = self.arc_angle
        a_rad = a * pi / 180.0
        a_mid = a_rad / 2.0

        # Cross-section on the XZ plane:
        #   sketch x → global X, sketch y → global Z, extrude direction → global Y
        with bd.BuildSketch(bd.Plane.XZ) as section:
            with bd.BuildLine():
                # Inner arc: counterclockwise from θ=0 to θ=a
                p_in0 = bd.Vector(r_in, 0)
                p_in1 = bd.Vector(r_in * cos(a_rad), r_in * sin(a_rad))
                p_in_mid = bd.Vector(r_in * cos(a_mid), r_in * sin(a_mid))
                bd.ThreePointArc(p_in0, p_in_mid, p_in1)

                # Radial line at arc end: inner → outer
                p_out1 = bd.Vector(r_out * cos(a_rad), r_out * sin(a_rad))
                bd.Line(p_in1, p_out1)

                # Outer arc: clockwise from θ=a back to θ=0
                p_out0 = bd.Vector(r_out, 0)
                p_out_mid = bd.Vector(r_out * cos(a_mid), r_out * sin(a_mid))
                bd.ThreePointArc(p_out1, p_out_mid, p_out0)

                # Radial line at arc start: outer → inner (closes the profile)
                bd.Line(p_out0, p_in0)

            bd.make_face()

        self.geom = bd.extrude(section.sketch, amount=self.width)

        # Attachment joints at proximal and distal ends of the limb axis
        self.joints["limb_proximal"] = bd.RigidJoint(
            "limb_proximal", self.geom, bd.Location(bd.Plane.XY)
        )
        self.joints["limb_distal"] = bd.RigidJoint(
            "limb_distal", self.geom, bd.Location(bd.Plane.XY.offset(self.width))
        )
