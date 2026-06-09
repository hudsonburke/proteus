"""Tests for bearing components."""

from __future__ import annotations

from proteus.components.bearing import (
    Bearing,
    SingleRowCappedDeepGrooveBallBearing,
    SingleRowDeepGrooveBallBearing,
    SingleRowTaperedRollerBearing,
)


class TestSingleRowDeepGrooveBallBearing:
    """Test SingleRowDeepGrooveBallBearing class."""

    def test_creation(self):
        """Test basic bearing creation."""
        bearing = SingleRowDeepGrooveBallBearing(
            size="M8-22-7",
            bearing_type="SKT",
        )
        assert bearing.geom is not None
        assert bearing.geom.volume > 0

    def test_properties(self):
        """Test bearing properties."""
        bearing = SingleRowDeepGrooveBallBearing(
            size="M8-22-7",
            bearing_type="SKT",
        )
        assert bearing.roller_diameter > 0
        assert bearing.bore_diameter > 0

    def test_bounding_box(self):
        """Test bounding box size."""
        bearing = SingleRowDeepGrooveBallBearing(
            size="M8-22-7",
            bearing_type="SKT",
        )
        bbox = bearing.geom.bounding_box()
        assert bbox.size.X > 0
        assert bbox.size.Y > 0
        assert bbox.size.Z > 0

    def test_info(self):
        """Test info property."""
        bearing = SingleRowDeepGrooveBallBearing(
            size="M8-22-7",
            bearing_type="SKT",
        )
        assert len(bearing.info) > 2

    def test_clearance_hole_diameters(self):
        """Test clearance hole diameters property."""
        bearing = SingleRowDeepGrooveBallBearing(
            size="M8-22-7",
            bearing_type="SKT",
        )
        assert len(bearing.clearance_hole_diameters) > 0


class TestSingleRowCappedDeepGrooveBallBearing:
    """Test SingleRowCappedDeepGrooveBallBearing class."""

    def test_creation(self):
        """Test basic capped bearing creation."""
        bearing = SingleRowCappedDeepGrooveBallBearing(
            size="M8-22-7",
            bearing_type="SKT",
        )
        assert bearing.geom is not None
        assert bearing.geom.volume > 0

    def test_capped(self):
        """Test that capped bearings have caps."""
        bearing = SingleRowCappedDeepGrooveBallBearing(
            size="M8-22-7",
            bearing_type="SKT",
        )
        assert bearing.capped is True


class TestSingleRowTaperedRollerBearing:
    """Test SingleRowTaperedRollerBearing class."""

    def test_creation(self):
        """Test basic tapered roller bearing creation."""
        bearing = SingleRowTaperedRollerBearing(
            size="M15-42-14.25",
            bearing_type="SKT",
        )
        assert bearing.geom is not None
        assert bearing.geom.volume > 0

    def test_roller_diameter(self):
        """Test roller diameter."""
        bearing = SingleRowTaperedRollerBearing(
            size="M15-42-14.25",
            bearing_type="SKT",
        )
        assert bearing.roller_diameter > 0

    def test_bore_diameter(self):
        """Test bore diameter."""
        bearing = SingleRowTaperedRollerBearing(
            size="M15-42-14.25",
            bearing_type="SKT",
        )
        assert bearing.bore_diameter > 0

    def test_bounding_box(self):
        """Test bounding box size."""
        bearing = SingleRowTaperedRollerBearing(
            size="M15-42-14.25",
            bearing_type="SKT",
        )
        bbox = bearing.geom.bounding_box()
        assert bbox.size.X > 0
        assert bbox.size.Y > 0
        assert bbox.size.Z > 0
