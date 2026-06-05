from pydantic import BaseModel, Field
import build123d as bd
from abc import ABC, abstractmethod
from typing import Any


class BasePart(BaseModel, ABC):
    model_config = {"arbitrary_types_allowed": True}

    geom: bd.Part | None = Field(default=None, exclude=True)
    joints: dict[str, bd.Joint] = Field(default_factory=dict, exclude=True)

    @abstractmethod
    def _build_geometry(self):
        pass

    def model_post_init(self, context: Any) -> None:
        self._build_geometry()

        if self.geom is None:
            raise ValueError(
                "{self.__class__.__name__}._build_geometry() did not set self.geom"
            )
