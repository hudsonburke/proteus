"""Parametric pipe flanges based on ASME B16.5.

Ported from bd_warehouse to the Proteus base-class hierarchy.
"""
from __future__ import annotations

from math import atan2, degrees
from typing import Literal

import build123d as bd

from proteus.common import BasePart
from proteus.components.pipe import Nps as PipeNps

# ── Helpers ─────────────────────────────────────────────────────────────


def _is_safe(value: str) -> bool:
    """Check whether *value* is a fractional string safe for ``eval()``."""
    return len(value) <= 10 and all(c in "0123456789./ " for c in set(value))


def _imperial_str_to_float(measure: str) -> float:
    """Convert an imperial measurement string (possibly a fraction) to mm."""
    if _is_safe(measure):
        result = eval(measure.strip().replace(" ", "+")) * bd.IN  # noqa: S307
    else:
        result = float(measure) * bd.IN
    return result


def _as_float(value: object) -> float:
    """Coerce a table value to float; raises on ``"…"`` / ``"Note (X)"``."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip().replace(" ", "")
        if stripped in ("…", ""):
            raise ValueError("Missing data placeholder encountered")
        try:
            return float(stripped)
        except ValueError:
            raise ValueError(f"Cannot convert {value!r} to float") from None
    raise TypeError(f"Unexpected table value type: {type(value)}")


# ── Data tables (ASME B16.5) ───────────────────────────────────────────

# Nominal pipe size → nominal diameter (mm)
NPS_TO_DN: dict[str, int] = {
    "1/2": 15, "3/4": 20, "1": 25, "1 1/4": 32, "1 1/2": 40,
    "2": 50, "2 1/2": 65, "3": 80, "4": 100, "5": 125,
    "6": 150, "8": 200, "10": 250, "12": 300, "14": 350,
    "16": 400, "18": 450, "20": 500, "22": 550, "24": 600,
}

# ASME B16.5 Table 7 — Templates for Drilling, Class 150
# [O, W, d (imperial str), n, bolt_dia (imperial str), …]
_DRILLING_150: dict[str, list] = {
    "1/2": [90, 60.3, "5/8", 4, "1/2", 55, "…", 50],
    "3/4": [100, 69.9, "5/8", 4, "1/2", 65, "…", 50],
    "1": [110, 79.4, "5/8", 4, "1/2", 65, 75, 55],
    "1 1/4": [115, 88.9, "5/8", 4, "1/2", 70, 85, 55],
    "1 1/2": [125, 98.4, "5/8", 4, "1/2", 70, 85, 65],
    "2": [150, 120.7, "3/4", 4, "5/8", 85, 95, 70],
    "2 1/2": [180, 139.7, "3/4", 4, "5/8", 90, 100, 75],
    "3": [190, 152.4, "3/4", 4, "5/8", 90, 100, 75],
    "3 1/2": [215, 177.8, "3/4", 8, "5/8", 90, 100, 75],
    "4": [230, 190.5, "3/4", 8, "5/8", 90, 100, 75],
    "5": [255, 215.9, "7/8", 8, "3/4", 95, 110, 85],
    "6": [280, 241.3, "7/8", 8, "3/4", 100, 115, 85],
    "8": [345, 298.5, "7/8", 8, "3/4", 110, 120, 90],
    "10": [405, 362.0, "1", 12, "7/8", 115, 125, 100],
    "12": [485, 431.8, "1", 12, "7/8", 120, 135, 100],
    "14": [535, 476.3, "1 1/8", 12, "1", 135, 145, 115],
    "16": [595, 539.8, "1 1/8", 16, "1", 135, 145, 115],
    "18": [635, 577.9, "1 1/4", 16, "1 1/8", 145, 160, 125],
    "20": [700, 635.0, "1 1/4", 20, "1 1/8", 160, 170, 140],
    "22": [750, 692.2, "1 3/8", 20, "1 1/4", 170, 185, 150],
    "24": [815, 749.3, "1 3/8", 20, "1 1/4", 170, 185, 150],
}

# ASME B16.5 Table 9 — Templates for Drilling, Class 300
_DRILLING_300: dict[str, list] = {
    "1/2": [95, 66.7, "5/8", 4, "1/2", 65, 75, 55],
    "3/4": [115, 82.6, "3/4", 4, "5/8", 75, 90, 65],
    "1": [125, 88.9, "3/4", 4, "5/8", 75, 90, 65],
    "1 1/4": [135, 98.4, "3/4", 4, "5/8", 85, 95, 70],
    "1 1/2": [155, 114.3, "7/8", 4, "3/4", 90, 100, 75],
    "2": [165, 127.0, "3/4", 8, "5/8", 90, 100, 75],
    "2 1/2": [190, 149.2, "7/8", 8, "3/4", 100, 115, 85],
    "3": [210, 168.3, "7/8", 8, "3/4", 110, 120, 90],
    "3 1/2": [230, 184.2, "7/8", 8, "3/4", 110, 125, 95],
    "4": [255, 200.0, "7/8", 8, "3/4", 115, 125, 95],
    "5": [280, 235.0, "7/8", 8, "3/4", 120, 135, 110],
    "6": [320, 269.9, "7/8", 12, "3/4", 120, 140, 110],
    "8": [380, 330.2, "1", 12, "7/8", 140, 150, 120],
    "10": [445, 387.4, "1 1/8", 16, "1", 160, 170, 140],
    "12": [520, 450.8, "1 1/4", 16, "1 1/8", 170, 185, 145],
    "14": [585, 514.4, "1 1/4", 20, "1 1/8", 180, 190, 160],
    "16": [650, 571.5, "1 3/8", 20, "1 1/4", 190, 205, 165],
    "18": [710, 628.6, "1 3/8", 24, "1 1/4", 195, 210, 170],
    "20": [775, 685.8, "1 3/8", 24, "1 1/4", 205, 220, 185],
    "22": [840, 743.0, "1 5/8", 24, "1 1/2", 230, 255, 205],
    "24": [915, 812.8, "1 5/8", 24, "1 1/2", 230, 255, 205],
}

# ASME B16.5 Table 8 — Dimensions of Class 150 Flanges
# fmt: off
_FLANGE_DATA_150: dict[str, list] = {
    "1/2": [90, 9.6, 11.2, 30, 21.3, 14, 16, 46, 16, 22.2, 22.9, 15.8, 3, 10],
    "3/4": [100, 11.2, 12.7, 38, 26.7, 14, 16, 51, 16, 27.7, 28.2, 20.9, 3, 11],
    "1": [110, 12.7, 14.3, 49, 33.4, 16, 17, 54, 17, 34.5, 34.9, 26.6, 3, 13],
    "1 1/4": [115, 14.3, 15.9, 59, 42.2, 19, 21, 56, 21, 43.2, 43.7, 35.1, 5, 14],
    "1 1/2": [125, 15.9, 17.5, 65, 48.3, 21, 22, 60, 22, 49.5, 50.0, 40.9, 6, 16],
    "2": [150, 17.5, 19.1, 78, 60.3, 24, 25, 62, 25, 61.9, 62.5, 52.5, 8, 17],
    "2 1/2": [180, 20.7, 22.3, 90, 73.0, 27, 29, 68, 29, 74.6, 75.4, 62.7, 8, 19],
    "3": [190, 22.3, 23.9, 108, 88.9, 29, 30, 68, 30, 90.7, 91.4, 77.9, 10, 21],
    "3 1/2": [215, 22.3, 23.9, 122, 101.6, 30, 32, 70, 32, 103.4, 104.1, 90.1, 10, "…"],
    "4": [230, 22.3, 23.9, 135, 114.3, 32, 33, 75, 33, 116.1, 116.8, 102.3, 11, "…"],
    "5": [255, 22.3, 23.9, 164, 141.3, 35, 36, 87, 36, 143.8, 144.4, 128.2, 11, "…"],
    "6": [280, 23.9, 25.4, 192, 168.3, 38, 40, 87, 40, 170.7, 171.4, 154.1, 13, "…"],
    "8": [345, 27.0, 28.6, 246, 219.1, 43, 44, 100, 44, 221.5, 222.2, 202.7, 13, "…"],
    "10": [405, 28.6, 30.2, 305, 273.0, 48, 49, 100, 49, 276.2, 277.4, 254.6, 13, "…"],
    "12": [485, 30.2, 31.8, 365, 323.8, 54, 56, 113, 56, 327.0, 328.2, 304.8, 13, "…"],
    "14": [535, 33.4, 35.0, 400, 355.6, 56, 79, 125, 57, 359.2, 360.2, "Note (8)", 13, "…"],
    "16": [595, 35.0, 36.6, 457, 406.4, 62, 87, 125, 64, 410.5, 411.2, "Note (8)", 13, "…"],
    "18": [635, 38.1, 39.7, 505, 457.0, 67, 97, 138, 68, 461.8, 462.3, "Note (8)", 13, "…"],
    "20": [700, 41.3, 42.9, 559, 508.0, 71, 103, 143, 73, 513.1, 514.4, "Note (8)", 13, "…"],
    "22": [750, 44.5, 46.1, 610, 558.8, 78, 108, 148, "…", 564.4, 565.2, "Note (8)", 13, "…"],
    "24": [815, 46.1, 47.7, 663, 610.0, 81, 111, 151, 83, 616.0, 616.0, "Note (8)", 13, "…"],
}
# fmt: on

# ASME B16.5 Table 10 — Dimensions of Class 300 Flanges
# fmt: off
_FLANGE_DATA_300: dict[str, list] = {
    "1/2": [95, 12.7, 14.3, 38, 21.3, 21, 22, 51, 16, 22.2, 22.9, 15.8, 3, 23.6, 10],
    "3/4": [115, 14.3, 15.9, 48, 26.7, 24, 25, 56, 16, 27.7, 28.2, 20.9, 3, 29.0, 11],
    "1": [125, 15.9, 17.5, 54, 33.4, 25, 27, 60, 18, 34.5, 34.9, 26.6, 3, 35.8, 13],
    "1 1/4": [135, 17.5, 19.1, 64, 42.2, 25, 27, 64, 21, 43.2, 43.7, 35.1, 5, 44.4, 14],
    "1 1/2": [155, 19.1, 20.7, 70, 48.3, 29, 30, 67, 23, 49.5, 50.0, 40.9, 6, 50.3, 16],
    "2": [165, 20.7, 22.3, 84, 60.3, 32, 33, 68, 29, 61.9, 62.5, 52.5, 8, 63.5, 17],
    "2 1/2": [190, 23.9, 25.4, 100, 73.0, 37, 38, 75, 32, 74.6, 75.4, 62.7, 8, 76.2, 19],
    "3": [210, 27.0, 28.6, 117, 88.9, 41, 43, 78, 32, 90.7, 91.4, 77.9, 10, 92.2, 21],
    "3 1/2": [230, 28.6, 30.2, 133, 101.6, 43, 44, 79, 37, 103.4, 104.1, 90.1, 10, 104.9, "…"],
    "4": [255, 30.2, 31.8, 146, 114.3, 46, 48, 84, 37, 116.1, 116.8, 102.3, 11, 117.6, "…"],
    "5": [280, 33.4, 35.0, 178, 141.3, 49, 51, 97, 43, 143.8, 144.4, 128.2, 11, 144.4, "…"],
    "6": [320, 35.0, 36.6, 206, 168.3, 51, 52, 97, 47, 170.7, 171.4, 154.1, 13, 171.4, "…"],
    "8": [380, 39.7, 41.3, 260, 219.1, 60, 62, 110, 51, 221.5, 222.2, 202.7, 13, 222.2, "…"],
    "10": [445, 46.1, 47.7, 321, 273.0, 65, 95, 116, 56, 276.2, 277.4, 254.6, 13, 276.2, "…"],
    "12": [520, 49.3, 50.8, 375, 323.8, 71, 102, 129, 61, 327.0, 328.2, 304.8, 13, 328.6, "…"],
    "14": [585, 52.4, 54.0, 425, 355.6, 75, 111, 141, 64, 359.2, 360.2, "Note (7)", 13, 360.4, "…"],
    "16": [650, 55.6, 57.2, 483, 406.4, 81, 121, 144, 69, 410.5, 411.2, "Note (7)", 13, 411.2, "…"],
    "18": [710, 58.8, 60.4, 533, 457.0, 87, 130, 157, 70, 461.8, 462.3, "Note (7)", 13, 462.0, "…"],
    "20": [775, 62.0, 63.5, 587, 508.0, 94, 140, 160, 74, 513.1, 514.4, "Note (7)", 13, 512.8, "…"],
    "22": [840, 65.1, 66.7, 640, 558.8, 100, 145, 164, "…", 564.4, 565.2, "Note (7)", 13, "…", "…"],
    "24": [915, 68.3, 69.9, 702, 610.0, 105, 152, 167, 83, 616.0, 616.0, "Note (7)", 13, 614.4, "…"],
}
# fmt: on

# Ring joint facings — Class 150
# [groove#, P, E, F, R, K, distance_between_flanges]
_RING_JOINT_150: dict[str, list] = {
    "1": [15, 47.63, 6.35, 8.74, 0.8, 63.5, 4],
    "1 1/4": [17, 57.15, 6.35, 8.74, 0.8, 73, 4],
    "1 1/2": [19, 65.07, 6.35, 8.74, 0.8, 82.5, 4],
    "2": [22, 82.55, 6.35, 8.74, 0.8, 102, 4],
    "2 1/2": [25, 101.6, 6.35, 8.74, 0.8, 121, 4],
    "3": [29, 114.3, 6.35, 8.74, 0.8, 133, 4],
    "3 1/2": [33, 131.78, 6.35, 8.74, 0.8, 154, 4],
    "4": [36, 149.23, 6.35, 8.74, 0.8, 171, 4],
    "5": [40, 171.45, 6.35, 8.74, 0.8, 194, 4],
    "6": [43, 193.68, 6.35, 8.74, 0.8, 219, 4],
    "8": [48, 247.65, 6.35, 8.74, 0.8, 273, 4],
    "10": [52, 304.8, 6.35, 8.74, 0.8, 330, 4],
    "12": [56, 381, 6.35, 8.74, 0.8, 406, 4],
    "14": [59, 396.88, 6.35, 8.74, 0.8, 425, 3],
    "16": [64, 454.03, 6.35, 8.74, 0.8, 483, 3],
    "18": [68, 517.53, 6.35, 8.74, 0.8, 546, 3],
    "20": [72, 558.8, 6.35, 8.74, 0.8, 597, 3],
    "22": [80, 615.95, 6.35, 8.74, 0.8, 648, 3],
    "24": [76, 673.1, 6.35, 8.74, 0.8, 711, 3],
}

# Ring joint facings — Class 300
_RING_JOINT_300: dict[str, list] = {
    "1/2": [11, 34.14, 5.54, 7.14, 0.8, 51, 3],
    "3/4": [13, 42.88, 6.35, 8.74, 0.8, 63.5, 4],
    "1": [16, 50.8, 6.35, 8.74, 0.8, 70, 4],
    "1 1/4": [18, 60.33, 6.35, 8.74, 0.8, 79.5, 4],
    "1 1/2": [20, 68.27, 6.35, 8.74, 0.8, 90.5, 4],
    "2": [23, 82.55, 7.92, 11.91, 0.8, 108, 6],
    "2 1/2": [26, 101.6, 7.92, 11.91, 0.8, 127, 6],
    "3": [31, 123.83, 7.92, 11.91, 0.8, 146, 6],
    "3 1/2": [34, 131.78, 7.92, 11.91, 0.8, 159, 6],
    "4": [37, 149.23, 7.92, 11.91, 0.8, 175, 6],
    "5": [41, 180.98, 7.92, 11.91, 0.8, 210, 6],
    "6": [45, 211.12, 7.92, 11.91, 0.8, 241, 6],
    "8": [49, 269.88, 7.92, 11.91, 0.8, 302, 6],
    "10": [53, 323.85, 7.92, 11.91, 0.8, 356, 6],
    "12": [57, 381, 7.92, 11.91, 0.8, 413, 6],
    "14": [61, 419.1, 7.92, 11.91, 0.8, 457, 6],
    "16": [65, 469.9, 7.92, 11.91, 0.8, 508, 6],
    "18": [69, 533.4, 7.92, 11.91, 0.8, 575, 6],
    "20": [73, 584.2, 9.53, 13.49, 1.5, 635, 6],
    "22": [81, 635, 11.13, 15.09, 1.5, 686, 6],
    "24": [77, 692.15, 11.13, 16.66, 1.5, 749, 6],
}

# ── Type aliases ────────────────────────────────────────────────────────

Nps = Literal[
    "1/2", "3/4", "1", "1 1/4", "1 1/2", "2", "2 1/2", "3", "4",
    "5", "6", "8", "10", "12", "14", "16", "18", "20", "22", "24",
]
FaceType = Literal[
    "Flat", "Raised", "Ring", "Tongue", "Groove", "Male", "Female",
]
FlangeClass = Literal[150, 300, 400, 600, 900, 1500, 2500]

# ── Flange base class ──────────────────────────────────────────────────


class Flange(BasePart):
    """Abstract base for ASME B16.5 flanges.

    Subclasses implement ``_build_geometry()`` by constructing a 2-D
    profile sketch and calling ``_revolve_with_bolts()``.
    """

    nps: str
    flange_class: int
    face_type: str | None = "Raised"

    # Populated by _build_geometry.
    od: float = 0.0
    thickness: float = 0.0
    id: float = 0.0

    @staticmethod
    def _validate(nps: str, flange_class: int, face_type: str | None) -> None:
        """Raise ``ValueError`` for invalid input combinations."""
        valid_nps = Nps.__args__  # type: ignore[union-attr]
        if nps not in valid_nps:
            raise ValueError(f"Invalid nps {nps!r}; valid: {valid_nps}")
        valid_cls = FlangeClass.__args__  # type: ignore[union-attr]
        if flange_class not in valid_cls:
            raise ValueError(f"Invalid flange_class {flange_class}; valid: {valid_cls}")
        if face_type is not None:
            valid_face = FaceType.__args__  # type: ignore[union-attr]
            if face_type not in valid_face:
                raise ValueError(f"Invalid face_type {face_type!r}; valid: {valid_face}")

    @staticmethod
    def _lookup_data(
        nps: str, flange_class: int, face_type: str | None
    ) -> tuple[list, list]:
        """Return ``(flange_data, drilling_data)`` for *nps* / *class*."""
        if flange_class == 150:
            fdata = _FLANGE_DATA_150[nps]
            bdata = _DRILLING_150[nps]
        elif flange_class == 300:
            fdata = _FLANGE_DATA_300[nps]
            bdata = _DRILLING_300[nps]
        else:
            raise ValueError(f"Unsupported flange class: {flange_class}")
        return fdata, bdata

    @staticmethod
    def _face_section(
        nps: str,
        flange_class: int,
        face_type: str | None,
        face_thickness: float | None = None,
        flange_data: list | None = None,
    ) -> tuple[bd.Sketch | None, float]:
        """Build the face-profile sketch and return ``(sketch, height)``.

        Returns ``(None, 0.0)`` for flat / no-face-type flanges.
        """
        if flange_class not in (150, 300):
            raise ValueError(f"Face section unsupported for class {flange_class}")

        # Resolve the raised-face diameter K and ring-joint parameters.
        ring_table = _RING_JOINT_150 if flange_class == 150 else _RING_JOINT_300
        if nps in ring_table:
            ring_data = ring_table[nps]
            P, E_ring, F, R_groove, K_ring = (_as_float(v) for v in ring_data[1:6])
            K = K_ring
        else:
            # Ring joint data not available for this NPS — fall back to
            # flange data column 2 (raised-face diameter) for Raised/Groove.
            if face_type == "Ring":
                raise ValueError(
                    f"Ring joint facing not available for NPS {nps!r} class {flange_class}"
                )
            if flange_data is not None:
                K = _as_float(flange_data[2])
            else:
                raise ValueError(
                    f"No face data for NPS {nps!r} class {flange_class} — "
                    f"pass *flange_data* or use a larger NPS"
                )
            P = E_ring = F = R_groove = 0.0  # unused for non-Ring faces

        if face_thickness is not None:
            E = face_thickness
        elif face_type is None or face_type == "Flat":
            E = 0.0
        elif face_type == "Raised":
            E = 2.0 if flange_class <= 300 else 7.0
        elif face_type == "Ring":
            E = E_ring
        else:
            raise ValueError(f"Unsupported face_type: {face_type!r}")

        if face_type in (None, "Flat") or E == 0.0:
            return None, 0.0

        with bd.BuildSketch() as face_builder:
            if face_type in ("Raised", "Ring", "Groove"):
                bd.Rectangle(K, E, align=(bd.Align.CENTER, bd.Align.MIN))
            if face_type == "Ring":
                with bd.BuildSketch(bd.Plane.XZ, mode=bd.Mode.SUBTRACT) as groove:
                    with bd.Locations((P / 2, 0)):
                        bd.Trapezoid(F, E, 90 - 23)
                    bd.fillet(
                        groove.vertices().group_by(bd.Axis.Y)[-1], R_groove
                    )
            face_section = face_builder.sketch
            height = face_section.bounding_box().max.Y
            return face_section, height
    @staticmethod
    def _revolve_with_bolts(
        profile_sketch: bd.Sketch,
        bcd: float,
        bolt_hole_count: int,
        bolt_hole_diameter: float,
    ) -> bd.Part:
        """Revolve *profile_sketch* and add bolt holes; return the Part."""
        with bd.BuildPart() as builder:
            with bd.BuildSketch(bd.Plane.XZ):
                bd.add(profile_sketch)
                bd.split(bisect_by=bd.Plane.YZ)
            bd.revolve()
            with bd.PolarLocations(bcd / 2, bolt_hole_count):
                bd.Hole(bolt_hole_diameter / 2)
        return builder.part


# ── Blind flange ───────────────────────────────────────────────────────


class BlindFlange(Flange):
    """Blind flange — a solid disk used to close off a pipe end.

    Args:
        nps: Nominal pipe size.
        flange_class: Pressure class (150, 300, …).
        face_type: Flange face type (default ``"Raised"``).
    """

    nps: str
    flange_class: int
    face_type: str = "Raised"

    def _build_geometry(self) -> None:
        Flange._validate(self.nps, self.flange_class, self.face_type)
        fdata, bdata = Flange._lookup_data(
            self.nps, self.flange_class, self.face_type
        )

        O = _as_float(fdata[0])
        tf = _as_float(fdata[1])
        B = _as_float(fdata[9])
        W = _as_float(bdata[1])
        d_imp = str(bdata[2])
        n = int(bdata[3])
        d = _imperial_str_to_float(d_imp)

        face_profile, face_thickness = Flange._face_section(
            self.nps, self.flange_class, self.face_type, flange_data=fdata
        )

        self.od = O
        self.thickness = tf + face_thickness

        with bd.BuildSketch(bd.Plane.XZ) as flange_profile:
            with bd.Locations((0, face_thickness)):
                bd.Rectangle(O, tf, align=(bd.Align.CENTER, bd.Align.MIN))
            bd.fillet(
                flange_profile.vertices().group_by(bd.Axis.Y)[-1], tf / 4
            )
            if face_profile is not None:
                bd.add(face_profile)
            bd.Rectangle(
                B,
                face_thickness,
                align=(bd.Align.CENTER, bd.Align.MIN),
                mode=bd.Mode.SUBTRACT,
            )

        self.geom = Flange._revolve_with_bolts(
            flange_profile.sketch, W, n, d
        )
        self.joints["face"] = bd.RigidJoint(
            "face", self.geom, bd.Location(bd.Plane.YX)
        )


# ── Slip-on flange ────────────────────────────────────────────────────


class SlipOnFlange(Flange):
    """Slip-on flange — slides over pipe and is welded in place.

    Args:
        nps: Nominal pipe size.
        flange_class: Pressure class (150, 300, …).
        face_type: Flange face type (default ``"Raised"``).
    """

    nps: str
    flange_class: int
    face_type: str = "Raised"

    def _build_geometry(self) -> None:
        Flange._validate(self.nps, self.flange_class, self.face_type)
        fdata, bdata = Flange._lookup_data(
            self.nps, self.flange_class, self.face_type
        )

        O = _as_float(fdata[0])
        tf = _as_float(fdata[1])
        X = _as_float(fdata[3])
        Y = _as_float(fdata[5])
        B = _as_float(fdata[9])
        W = _as_float(bdata[1])
        d_imp = str(bdata[2])
        n = int(bdata[3])
        d = _imperial_str_to_float(d_imp)

        face_profile, face_thickness = Flange._face_section(
            self.nps, self.flange_class, self.face_type, flange_data=fdata
        )

        self.od = O
        self.id = B
        self.thickness = Y + face_thickness

        with bd.BuildSketch(bd.Plane.XZ) as flange_profile:
            with bd.Locations((0, face_thickness)):
                bd.Rectangle(X, Y, align=(bd.Align.CENTER, bd.Align.MIN))
                bd.Rectangle(O, tf, align=(bd.Align.CENTER, bd.Align.MIN))
            vertices = [
                v
                for v in flange_profile.vertices().group_by(bd.Axis.Y)[-1]
                + flange_profile.vertices().group_by(bd.Axis.Y)[-2]
            ]
            bd.fillet(vertices, (Y - tf) / 4)
            if face_profile is not None:
                bd.add(face_profile)
            bd.Rectangle(
                B,
                Y + face_thickness,
                align=(bd.Align.CENTER, bd.Align.MIN),
                mode=bd.Mode.SUBTRACT,
            )

        self.geom = Flange._revolve_with_bolts(
            flange_profile.sketch, W, n, d
        )
        self.joints["pipe"] = bd.RigidJoint(
            "pipe", self.geom, bd.Location(bd.Plane.YX.offset(-(1 / 16) * bd.IN))
        )
        self.joints["face"] = bd.RigidJoint(
            "face", self.geom, bd.Location(bd.Plane.XY)
        )
