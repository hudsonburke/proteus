from __future__ import annotations

"""Simple examples of the Proteus base object hierarchy.

Run from the project root with:
    PYTHONPATH=src uv run python examples/base_objects.py
"""

import build123d as bd

from proteus import (
    BaseAssembly,
    BaseCurve,
    BaseObject,
    BasePart,
    BaseSketch,
    LengthMM,
    Quantity,
)


def mm(value: Quantity) -> float:
    """Convert a Pint quantity to a raw millimetre magnitude for build123d."""

    return value.to("mm").magnitude


class MaterialSpec(BaseObject):
    """Use BaseObject for validated models that do not directly build geometry."""

    name: str
    density_g_per_cm3: float


class MountingPlate(BasePart):
    """Use BasePart for standalone 3D components that assign ``self.geom``."""

    width: LengthMM = "40 mm"
    height: LengthMM = "20 mm"
    thickness: LengthMM = "6 mm"

    def _build_geometry(self) -> None:
        self.geom = bd.Box(mm(self.width), mm(self.height), mm(self.thickness))


class HolePattern(BaseSketch):
    """Use BaseSketch for reusable 2D profiles and cut patterns."""

    width: LengthMM = "40 mm"
    height: LengthMM = "20 mm"
    hole_spacing: LengthMM = "20 mm"
    hole_diameter: LengthMM = "5 mm"

    def _build_geometry(self) -> None:
        with bd.BuildSketch() as sketch:
            bd.Rectangle(mm(self.width), mm(self.height))
            with bd.Locations(
                (-mm(self.hole_spacing) / 2, 0),
                (mm(self.hole_spacing) / 2, 0),
            ):
                bd.Circle(mm(self.hole_diameter) / 2, mode=bd.Mode.SUBTRACT)
        self.geom = sketch.sketch


class ReferencePath(BaseCurve):
    """Use BaseCurve for standalone guide geometry such as edges and wires."""

    length: LengthMM = "60 mm"

    def _build_geometry(self) -> None:
        self.geom = bd.Edge.make_line((0, 0, 0), (mm(self.length), 0, 0))


class PlatePair(BaseAssembly):
    """Use BaseAssembly when the public object represents multiple child components."""

    spacing: LengthMM = "50 mm"
    plate_width: LengthMM = "40 mm"
    plate_height: LengthMM = "20 mm"
    plate_thickness: LengthMM = "6 mm"

    def _build_geometry(self) -> None:
        left_plate = MountingPlate(
            width=self.plate_width,
            height=self.plate_height,
            thickness=self.plate_thickness,
        )
        right_plate = MountingPlate(
            width=self.plate_width,
            height=self.plate_height,
            thickness=self.plate_thickness,
        )
        offset = mm(self.spacing) / 2

        self.children = [left_plate, right_plate]
        self.geom = bd.Compound(
            children=[
                left_plate.geom.moved(bd.Pos(Y=-offset)),
                right_plate.geom.moved(bd.Pos(Y=offset)),
            ]
        )


def main() -> None:
    material = MaterialSpec(name="6061-T6 Aluminum", density_g_per_cm3=2.70)
    plate = MountingPlate(width="60 mm", height="30 mm", thickness="8 mm")
    hole_pattern = HolePattern(width=plate.width, height=plate.height)
    path = ReferencePath(length="100 mm")
    assembly = PlatePair(spacing="70 mm")

    print("BaseObject ->", material.model_dump())
    print(
        "BasePart ->",
        type(plate.geom).__name__,
        tuple(round(value, 1) for value in plate.geom.bounding_box().size),
    )
    print(
        "BaseSketch ->",
        type(hole_pattern.geom).__name__,
        len(hole_pattern.geom.faces()),
        "face",
    )
    print("BaseCurve ->", type(path.geom).__name__, round(path.geom.length, 1), "mm")
    print(
        "BaseAssembly ->",
        type(assembly.geom).__name__,
        len(assembly.children),
        "children",
    )


if __name__ == "__main__":
    main()
