"""Tests for thread components."""

from __future__ import annotations

import pytest
from proteus.components.thread import (
    AcmeThread,
    IsoThread,
    MetricTrapezoidalThread,
    PlasticBottleThread,
    Thread,
    TrapezoidalThread,
)


class TestThread:
    """Test the base Thread class."""

    def test_iso_thread_creation(self):
        """Test basic IsoThread creation."""
        thread = IsoThread(
            major_diameter=10,
            pitch=1.5,
            length=20,
        )
        assert thread.geom is not None
        assert thread.geom.volume > 0

    def test_trapezoidal_thread_creation(self):
        """Test basic TrapezoidalThread creation."""
        thread = TrapezoidalThread(
            diameter=10,
            pitch=2,
            thread_angle=30,
            length=20,
        )
        assert thread.geom is not None
        assert thread.geom.volume > 0

    def test_acme_thread_creation(self):
        """Test basic AcmeThread creation."""
        thread = AcmeThread(
            size="1/4",
            length=20,
        )
        assert thread.geom is not None
        assert thread.geom.volume > 0

    def test_metric_trapezoidal_thread_creation(self):
        """Test basic MetricTrapezoidalThread creation."""
        thread = MetricTrapezoidalThread(
            size="10x2",
            length=20,
        )
        assert thread.geom is not None
        assert thread.geom.volume > 0

    def test_plastic_bottle_thread_creation(self):
        """Test basic PlasticBottleThread creation."""
        thread = PlasticBottleThread(
            size="M28SP444",
            length=10,
        )
        assert thread.geom is not None
        assert thread.geom.volume > 0

    def test_thread_end_finishes(self):
        """Test thread creation with different end finishes."""
        for finish in ["raw", "fade", "square", "chamfer"]:
            thread = IsoThread(
                major_diameter=10,
                pitch=1.5,
                length=20,
                end_finishes=(finish, finish),
            )
            assert thread.geom is not None
            assert thread.geom.volume > 0

    def test_thread_hand(self):
        """Test left and right hand threads."""
        for hand in ["right", "left"]:
            thread = IsoThread(
                major_diameter=10,
                pitch=1.5,
                length=20,
                hand=hand,
            )
            assert thread.geom is not None

    def test_invalid_hand(self):
        """Test invalid hand raises error."""
        with pytest.raises(ValueError):
            IsoThread(
                major_diameter=10,
                pitch=1.5,
                length=20,
                hand="invalid",
            )

    def test_invalid_end_finish(self):
        """Test invalid end finish raises error."""
        with pytest.raises(ValueError):
            IsoThread(
                major_diameter=10,
                pitch=1.5,
                length=20,
                end_finishes=("invalid", "raw"),
            )
