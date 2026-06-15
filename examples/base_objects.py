from __future__ import annotations

import build123d as bd

from proteus import BaseAssembly, BaseCurve, BaseObject, BasePart, BaseSketch, convert

"""Simple examples of the Proteus base object hierarchy.

Run from the project root with:
    PYTHONPATH=src uv run python examples/base_objects.py
"""


class MaterialSpec(BaseObject):
    """Use BaseObject for validated models that do not directly build geometry."""

    name: str
    density_g_per_cm3: float


class MountingPlate(BasePart):
    """Use BasePart for standalone 3D components that assign ``self.geom``."""

    width: float = convert(40, "mm")
    height: float = convert(20, "mm")
    thickness: float = convert(6, "mm")

    def _build_geometry(self) -> None:
        self.geom = bd.Box(self.width, self.height, self.thickness)


class HolePattern(BaseSketch):
    """Use BaseSketch for reusable 2D profiles and cut patterns."""

    width: float = convert(40, "mm")
    height: float = convert(20, "mm")
    hole_spacing: float = convert(20, "mm")
    hole_diameter: float = convert(5, "mm")

    def _build_geometry(self) -> None:
        with bd.BuildSketch() as sketch:
            bd.Rectangle(self.width, self.height)
            with bd.Locations(
                (-self.hole_spacing / 2, 0),
                (self.hole_spacing / 2, 0),
            ):
                bd.Circle(self.hole_diameter / 2, mode=bd.Mode.SUBTRACT)
        self.geom = sketch.sketch


class ReferencePath(BaseCurve):
    """Use BaseCurve for standalone guide geometry such as edges and wires."""

    length: float = convert(60, "mm")

    def _build_geometry(self) -> None:
        self.geom = bd.Edge.make_line((0, 0, 0), (self.length, 0, 0))


class PlatePair(BaseAssembly):
    """Use BaseAssembly when the public object represents multiple child components."""

    spacing: float = convert(50, "mm")
    plate_width: float = convert(40, "mm")
    plate_height: float = convert(20, "mm")
    plate_thickness: float = convert(6, "mm")

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
        offset = self.spacing / 2

        self.children = [left_plate, right_plate]
        self.geom = bd.Compound(
            children=[
                left_plate.geom.moved(bd.Pos(Y=-offset)),
                right_plate.geom.moved(bd.Pos(Y=offset)),
            ]
        )


def main() -> None:
    material = MaterialSpec(name="6061-T6 Aluminum", density_g_per_cm3=2.70)
    plate = MountingPlate(
        width=convert(60, "mm"), height=convert(30, "mm"), thickness=convert(8, "mm")
    )
    hole_pattern = HolePattern(width=plate.width, height=plate.height)
    path = ReferencePath(length=convert(100, "mm"))
    assembly = PlatePair(spacing=convert(70, "mm"))

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
