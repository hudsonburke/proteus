"""Tests for gear components."""

from __future__ import annotations

import pytest
import build123d as bd

from proteus.components.gear import InvoluteToothProfile, SpurGear, SpurGearPlan


class TestInvoluteToothProfile:
    """Test InvoluteToothProfile class."""

    def test_creation(self):
        """Test basic tooth profile creation."""
        profile = InvoluteToothProfile(
            module=1,
            tooth_count=14,
            pressure_angle=14.5,
        )
        assert profile.geom is not None
        assert len(profile.geom.edges()) > 0

    def test_radii(self):
        """Test calculated radii."""
        profile = InvoluteToothProfile(
            module=1,
            tooth_count=14,
            pressure_angle=14.5,
        )
        assert profile.pitch_radius > 0
        assert profile.base_radius > 0
        assert profile.addendum_radius > 0
        assert profile.root_radius > 0

    def test_pitch_radius(self):
        """Test pitch radius calculation."""
        module = 1
        tooth_count = 14
        profile = InvoluteToothProfile(
            module=module,
            tooth_count=tooth_count,
            pressure_angle=14.5,
        )
        assert profile.pitch_radius == pytest.approx(module * tooth_count / 2, abs=1e-5)


class TestSpurGearPlan:
    """Test SpurGearPlan class."""

    def test_creation(self):

        """Test basic gear plan creation."""
        plan = SpurGearPlan(
            module=1,
            tooth_count=14,
            pressure_angle=14.5,
            root_fillet=0.5,
        )
        assert plan.geom is not None
        assert len(plan.geom.faces()) > 0

    def test_face_normal(self):

        """Test face normal points up."""
        plan = SpurGearPlan(
            module=1,
            tooth_count=14,
            pressure_angle=14.5,
            root_fillet=0.5,
        )
        # The gear plan should be in the XY plane
        face = plan.geom.faces()[0]
        normal = face.normal_at()
        assert normal.Z == pytest.approx(1.0, abs=1e-5)


class TestSpurGear:
    """Test SpurGear class."""

    def test_creation(self):

        """Test basic gear creation."""
        gear = SpurGear(
            module=2,
            tooth_count=12,
            pressure_angle=14.5,
            root_fillet=0.5,
            thickness=5,
        )
        assert gear.geom is not None
        assert gear.geom.volume > 0

    def test_bounding_box(self):

        """Test bounding box size."""
        module = 2
        tooth_count = 12
        thickness = 5
        gear = SpurGear(
            module=module,
            tooth_count=tooth_count,
            pressure_angle=14.5,
            root_fillet=0.5,
            thickness=thickness,
        )
        addendum_radius = module * tooth_count / 2 + module
        bbox = gear.geom.bounding_box()
        assert bbox.size.X == pytest.approx(2 * addendum_radius, abs=1e-5)
        assert bbox.size.Y == pytest.approx(2 * addendum_radius, abs=1e-5)
        assert bbox.size.Z == pytest.approx(thickness, abs=1e-5)
