"""Parametric pipes based on ASTM A312 / ASME B36 / ASTM B88 standards.

Ported from bd_warehouse to the Proteus base-class hierarchy.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import ClassVar, Literal

import build123d as bd

from proteus.common import BasePart, BaseSketch
from proteus.units import convert

# ── Type aliases ────────────────────────────────────────────────────────
Nps = Literal[
    "1/8", "1/4", "3/8", "1/2", "3/4", "1", "1 1/4", "1 1/2", "2",
    "2 1/2", "3", "4", "5", "6", "8", "10", "12", "14", "16", "18",
    "20", "22", "24", "30", "32", "34", "36", "42",
]
Identifier = Literal[
    "K", "L", "M", "STD", "XS", "XXS", "5S", "10", "10S", "20", "30",
    "40", "40S", "60", "80", "80S", "100", "120", "140", "160",
]
Material = Literal["abs", "copper", "iron", "pvc", "stainless", "steel"]

# ── Catalog ─────────────────────────────────────────────────────────────

_CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "pipe.csv"


def _load_pipe_catalog() -> dict[str, tuple[float, float]]:
    """Return {nps+material+identifier: (od_in, thickness_in)} from bundled CSV."""
    catalog: dict[str, tuple[float, float]] = {}
    with _CSV_PATH.open(newline="") as f:
        reader = csv.reader(f)
        next(reader, None)  # skip header
        for row in reader:
            if not row:
                continue
            nps, material, identifier, od, thickness = row
            catalog[nps + material + identifier] = (float(od), float(thickness))
    return catalog


_PIPE_DATA: dict[str, tuple[float, float]] = _load_pipe_catalog()

# ── Pipe section (2-D sketch) ──────────────────────────────────────────


class PipeSection(BaseSketch):
    """Cross-section of a standard pipe — two concentric circles.

    Args:
        nps: Nominal pipe size (e.g. ``"2"``, ``"3/4"``).
        material: Material type.
        identifier: Pipe schedule or type identifier (e.g. ``"40"``, ``"80S"``).
    """

    nps: str
    material: str
    identifier: str

    # Populated by _build_geometry.
    od: float = 0.0
    thickness: float = 0.0
    id: float = 0.0

    def _build_geometry(self) -> None:
        key = self.nps + self.material + self.identifier
        try:
            od_in, thickness_in = _PIPE_DATA[key]
        except KeyError:
            raise ValueError(
                f"No pipe data for nps={self.nps!r}, "
                f"material={self.material!r}, identifier={self.identifier!r}"
            ) from None

        self.od = convert(od_in, "in")
        self.thickness = convert(thickness_in, "in")
        self.id = self.od - 2 * self.thickness

        with bd.BuildSketch() as cross_section:
            bd.Circle(radius=self.od / 2)
            bd.Circle(radius=self.id / 2, mode=bd.Mode.SUBTRACT)

        self.geom = cross_section.sketch


# ── Pipe (3-D part) ────────────────────────────────────────────────────


class Pipe(BasePart):
    """Parametric pipe swept along a center-line path.

    Args:
        nps: Nominal pipe size.
        material: Material type.
        identifier: Pipe schedule or type identifier.
        path: Center-line as a single ``Edge``, a ``Wire``, or ``None`` to
              consume pending edges from the active ``BuildPart`` context.
    """

    nps: str
    material: str
    identifier: str
    path: object = None  # Edge, Wire, or None — processed in _build_geometry

    # Populated by _build_geometry.
    od: float = 0.0
    thickness: float = 0.0
    id: float = 0.0
    length: float = 0.0

    def _build_geometry(self) -> None:
        ctx: bd.BuildPart | None = bd.BuildPart._get_context()  # type: ignore[union-attr]

        path = self.path
        if path is None:
            if ctx is not None and ctx.pending_edges:
                path_edges = ctx.pending_edges
                ctx.pending_edges = []
            else:
                raise ValueError("A path must be provided")
        elif isinstance(path, bd.Wire):
            path_edges = path.edges()
        elif isinstance(path, bd.Edge):
            path_edges = [path]
        else:
            raise ValueError(f"Invalid path type: {type(path).__name__}")

        section = PipeSection(
            nps=self.nps,
            material=self.material,
            identifier=self.identifier,
        )
        self.od = section.od
        self.id = section.id
        self.thickness = section.thickness
        self.length = sum(p.length for p in path_edges)

        with bd.BuildPart() as pipe:
            for p in path_edges:
                bd.add(p)
                with bd.BuildSketch(bd.Plane(origin=p @ 0, z_dir=p % 0)):
                    bd.add(section.geom)
                bd.sweep()

        self.geom = pipe.part
