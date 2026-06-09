"""Tests for pipe and flange components."""

from __future__ import annotations

import build123d as bd
import pytest
from proteus.components.flange import BlindFlange, Flange, SlipOnFlange
from proteus.components.pipe import Pipe, PipeSection


class TestPipeSection:
    """Test PipeSection class."""

    def test_creation(self):
        """Test basic pipe section creation."""
        section = PipeSection(
            nps="1/2",
            material="steel",
            identifier="40",
        )
        assert section.geom is not None
        assert len(section.geom.faces()) > 0

    def test_invalid_nps(self):
        """Test invalid NPS raises error."""
        with pytest.raises(ValueError):
            PipeSection(
                nps="invalid",
                material="stainless",
                identifier="10S",
            )

    def test_dimensions(self):
        """Test pipe dimensions are set."""
        section = PipeSection(
            nps="1/2",
            material="steel",
            identifier="40",
        )
        assert section.od > 0
        assert section.thickness > 0
        assert section.id > 0


class TestPipe:
    """Test Pipe class."""

    def test_creation_with_path(self):
        """Test basic pipe creation with a path."""
        path = bd.Edge.make_line((0, 0, 0), (100, 0, 0))
        pipe = Pipe(
            nps="1/2",
            material="steel",
            identifier="40",
            path=path,
        )
        assert pipe.geom is not None
        assert pipe.geom.volume > 0

    def test_no_path_raises(self):
        """Test that no path raises error."""
        with pytest.raises(ValueError):
            Pipe(
                nps="1/2",
                material="steel",
                identifier="40",
            )


class TestBlindFlange:
    """Test BlindFlange class."""

    def test_creation(self):
        """Test basic blind flange creation."""
        flange = BlindFlange(
            nps="1/2",
            flange_class="150",
        )
        assert flange.geom is not None
        assert flange.geom.volume > 0

    def test_joints(self):
        """Test joints exist."""
        flange = BlindFlange(
            nps="1/2",
            flange_class="150",
        )
        assert len(flange.joints) > 0


class TestSlipOnFlange:
    """Test SlipOnFlange class."""

    def test_creation(self):
        """Test basic slip-on flange creation."""
        flange = SlipOnFlange(
            nps="1/2",
            flange_class="150",
        )
        assert flange.geom is not None
        assert flange.geom.volume > 0

    def test_joints(self):
        """Test joints exist."""
        flange = SlipOnFlange(
            nps="1/2",
            flange_class="150",
        )
        assert len(flange.joints) > 0
