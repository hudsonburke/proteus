"""Bridge between melos subject data and proteus parametric parts.

This module adapts melos-core types (SegmentMeasurementSet, Transform)
into proteus part construction calls.  Melos operates in SI units (m, rad);
proteus operates in CAD-native units (mm, deg).  Conversion happens here,
at the boundary.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .units import convert

if TYPE_CHECKING:
    from melos.core.common.types import Transform as MelosTransform
    from melos.core.retarget.model import SegmentMeasurementSet
    from .components.cuff import Cuff


def build_cuff(
    measurements: SegmentMeasurementSet,
    segment_id: str,
    coverage: float = 0.75,
    wall_thickness: float = 3.0,
    padding_thickness: float = 2.0,
    width: float = 40.0,
    *,
    attachment_joints: dict[str, MelosTransform] | None = None,
) -> Cuff:
    """Build a Cuff from melos segment measurements.

    Parameters
    ----------
    measurements:
        A ``SegmentMeasurementSet`` from melos-core containing segment
        lengths in metres.
    segment_id:
        The segment to fit to (e.g. ``"left_shank"``).  Its measured length
        is used as the circumference from which the cuff radius is derived.
    coverage:
        Fraction of the limb circumference the cuff covers (0–1).  Passed
        through to ``Cuff``.
    wall_thickness:
        Shell wall thickness in **mm** (proteus-native).
    padding_thickness:
        Inner padding in **mm** (proteus-native).
    width:
        Axial height of the cuff along the limb, in **mm** (proteus-native).
    attachment_joints:
        Optional melos ``Transform`` frames (in metres) for the attachment
        sites.  These are converted to build123d ``RigidJoint`` locations in
        mm and applied to the returned cuff.

    Returns
    -------
    Cuff
        A fully constructed proteus ``Cuff`` part with geometry and joints
        in CAD-native units (mm/deg).
    """
    from .components.cuff import Cuff  # local import to avoid circular

    as_dict = measurements.as_dict()
    if segment_id not in as_dict:
        available = ", ".join(sorted(as_dict)) or "(none)"
        raise KeyError(
            f"Segment {segment_id!r} not found in measurements.  Available: {available}"
        )

    circumference_m = as_dict[segment_id]

    # Convert melos SI → proteus CAD-native
    circumference_mm = convert(circumference_m, "m")

    cuff = Cuff(
        limb_circumference=circumference_mm,
        width=width,
        coverage=coverage,
        wall_thickness=wall_thickness,
        padding_thickness=padding_thickness,
    )

    if attachment_joints:
        import build123d as bd

        for name, tfm in attachment_joints.items():
            tx, ty, tz = tfm.translation
            loc = bd.Location(
                bd.Plane(
                    origin=(convert(tx, "m"), convert(ty, "m"), convert(tz, "m")),
                )
            )
            cuff.joints[name] = bd.RigidJoint(name, cuff.geom, loc)

    return cuff
