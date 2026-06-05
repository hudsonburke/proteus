from __future__ import annotations

from typing import Annotated, ClassVar, Self, TYPE_CHECKING, TypeAlias, cast

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
    model_validator,
)

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


class BasePart(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(arbitrary_types_allowed=True)

    geom: bd.Part | None = Field(default=None, exclude=True)
    joints: dict[str, bd.Joint] = Field(default_factory=dict, exclude=True)

    def _build_geometry(self) -> None:
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _build_geometry()."
        )

    @model_validator(mode="after")
    def _finalize_geometry(self) -> Self:
        self._build_geometry()

        if self.geom is None:
            raise ValueError(
                f"{self.__class__.__name__}._build_geometry() did not set self.geom"
            )

        return self
