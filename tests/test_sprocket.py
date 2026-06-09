"""Tests for sprocket components."""

from __future__ import annotations

import pytest
from proteus.components.sprocket import Sprocket


class TestSprocket:
    """Test Sprocket class."""

    def test_creation(self):
        """Test basic sprocket creation."""
        sprocket = Sprocket(
            num_teeth=32,
            bolt_circle_diameter=104,
            num_mount_bolts=4,
            mount_bolt_diameter=8,
            bore_diameter=80,
        )
        assert sprocket.geom is not None
        assert sprocket.geom.volume > 0

    def test_properties(self):
        """Test sprocket properties."""
        sprocket = Sprocket(
            num_teeth=32,
            bolt_circle_diameter=104,
            num_mount_bolts=4,
            mount_bolt_diameter=8,
            bore_diameter=80,
        )
        assert sprocket.pitch_radius > 0
        assert sprocket.outer_radius > 0
        assert sprocket.pitch_circumference > 0

    def test_invalid_teeth_count(self):
        """Test invalid teeth count raises error."""
        with pytest.raises(ValueError):
            Sprocket(
                num_teeth=2,
                chain_pitch=12.7,
                roller_diameter=7.9375,
            )

    def test_invalid_chain(self):
        """Test invalid chain parameters raise error."""
        with pytest.raises(ValueError):
            Sprocket(
                num_teeth=32,
                chain_pitch=4,
                roller_diameter=5,
            )

    def test_flat_sprocket(self):
        """Test flat sprocket creation."""
        sprocket = Sprocket(
            num_teeth=32,
            bolt_circle_diameter=104,
            num_mount_bolts=4,
            mount_bolt_diameter=8,
            bore_diameter=80,
        )
        assert sprocket.geom is not None
        assert sprocket.geom.volume > 0

    def test_spiky_sprocket(self):
        """Test spiky sprocket creation."""
        sprocket = Sprocket(
            num_teeth=16,
            chain_pitch=12.7,
            roller_diameter=7.9375,
        )
        assert sprocket.geom is not None
        assert sprocket.geom.volume > 0
