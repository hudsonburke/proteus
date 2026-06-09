from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Annotated, TYPE_CHECKING, TypeAlias, Any, cast

import build123d as bd
import pint
from pint.facets.plain import PlainQuantity
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    InstanceOf,
    PlainSerializer,
)


class BaseObject(BaseModel, ABC):
    """Common root for all Proteus parametric model types.

    Use this for shared validation, serialization, and quantity-backed inputs when a
    model does not yet need to commit to a specific build123d geometry kind.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)


class BaseGeometry(BaseObject, ABC):
    """Abstract base for models that own a concrete build123d geometry result.

    Subclasses implement ``_build_geometry()`` and must assign ``self.geom`` during
    ``model_post_init``. Use this when the object is expected to stand alone outside a
    builder context and may expose joints for later assembly.
    """

    geom: bd.Shape | None = Field(default=None, exclude=True)
    joints: dict[str, bd.Joint] = Field(default_factory=dict, exclude=True)

    @abstractmethod
    def _build_geometry(self) -> None:
        """Build the object geometry and assign it to ``self.geom``."""
        pass

    def _require_geometry(self) -> None:
        if self.geom is None:
            raise ValueError(
                f"{self.__class__.__name__}._build_geometry() did not set self.geom"
            )

    def model_post_init(self, __context: Any) -> None:
        self._build_geometry()
        self._require_geometry()


class BasePart(BaseGeometry, ABC):
    """Base class for standalone 3D parts and compound 3D objects.

    Use this for models that should behave like a single reusable physical component:
    bearings, screws, flanges, pipes, gears, sprockets, and similar solid or compound
    outputs.
    """

    geom: bd.Part | bd.Compound | None = Field(default=None, exclude=True)


class BaseAssembly(BaseGeometry, ABC):
    """Base class for multi-component assemblies composed from child geometry.

    Use this when the public object represents several coordinated parts with assembly
    joints, child placement, or aggregate compound output.
    """

    geom: bd.Compound | None = Field(default=None, exclude=True)
    children: list[BaseGeometry | bd.Shape] = Field(default_factory=list, exclude=True)


class BaseSketch(BaseGeometry, ABC):
    """Base class for standalone 2D sketches.

    Use this for reusable planar profiles and sections that are first-class design
    objects, not just intermediate construction geometry hidden inside a part builder.
    """

    geom: bd.Sketch | None = Field(default=None, exclude=True)


class BaseCurve(BaseGeometry, ABC):
    """Base class for standalone 1D curves, wires, and edges.

    Use this for reusable path or profile primitives such as tooth curves or guide
    geometry that should exist as first-class objects in the API.
    """

    geom: bd.Curve | bd.Wire | bd.Edge | None = Field(default=None, exclude=True)


ureg: pint.UnitRegistry[float] = pint.UnitRegistry()

Quantity: TypeAlias = PlainQuantity[float]
QuantityInput: TypeAlias = Quantity | str | float | int


def _quantity(value: str | float | int, unit: str | None = None) -> Quantity:
    return cast(Quantity, ureg.Quantity(value, unit))


def _to_unit(value: Quantity, unit: str) -> Quantity:
    return value.to(unit)  # pyright: ignore[reportUnknownMemberType]


def _dump_quantity(value: Quantity) -> str:
    return str(value)


def parse_quantity(value: object, default_unit: str) -> Quantity:
    if isinstance(value, bool):
        raise TypeError("Cannot parse bool into a physical quantity.")

    if isinstance(value, PlainQuantity):
        return _to_unit(cast(Quantity, value), default_unit)

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError("Cannot parse an empty quantity string.")

        try:
            return _to_unit(_quantity(stripped), default_unit)
        except pint.DimensionalityError:
            return _quantity(float(stripped), default_unit)

    if isinstance(value, int | float):
        return _quantity(float(value), default_unit)

    raise TypeError(f"Cannot parse {type(value)} into a physical quantity.")


def _parse_length_mm(value: object) -> Quantity:
    return parse_quantity(value, "mm")


def _parse_angle_deg(value: object) -> Quantity:
    return parse_quantity(value, "deg")


# Static type checkers model the accepted constructor/default inputs.
# Pydantic stores a Pint Quantity at runtime after the BeforeValidator runs.
if TYPE_CHECKING:
    LengthMM: TypeAlias = QuantityInput
    AngleDeg: TypeAlias = QuantityInput
else:
    LengthMM: TypeAlias = Annotated[
        InstanceOf[PlainQuantity],
        BeforeValidator(_parse_length_mm),
        PlainSerializer(_dump_quantity, return_type=str),
        Field(validate_default=True),
    ]
    AngleDeg: TypeAlias = Annotated[
        InstanceOf[PlainQuantity],
        BeforeValidator(_parse_angle_deg),
        PlainSerializer(_dump_quantity, return_type=str),
        Field(validate_default=True),
    ]