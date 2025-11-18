"""Tests for deterministic seeding."""
from __future__ import annotations

from datetime import datetime

import pytest

from app.utils.seeding import generate_deterministic_seed


def test_seed_deterministic_same_date_symbol():
    """Test that same date and symbol produce same seed."""
    seed1 = generate_deterministic_seed("2025-01-15", "BTCUSDT")
    seed2 = generate_deterministic_seed("2025-01-15", "BTCUSDT")
    assert seed1 == seed2


def test_seed_deterministic_different_date():
    """Test that different dates produce different seeds."""
    seed1 = generate_deterministic_seed("2025-01-15", "BTCUSDT")
    seed2 = generate_deterministic_seed("2025-01-16", "BTCUSDT")
    assert seed1 != seed2


def test_seed_deterministic_different_symbol():
    """Test that different symbols produce different seeds."""
    seed1 = generate_deterministic_seed("2025-01-15", "BTCUSDT")
    seed2 = generate_deterministic_seed("2025-01-15", "ETHUSDT")
    assert seed1 != seed2


def test_seed_with_datetime():
    """Test that datetime objects work correctly."""
    dt = datetime(2025, 1, 15)
    seed1 = generate_deterministic_seed(dt, "BTCUSDT")
    seed2 = generate_deterministic_seed("2025-01-15", "BTCUSDT")
    assert seed1 == seed2


def test_seed_integer_range():
    """Test that seed is within valid integer range."""
    seed = generate_deterministic_seed("2025-01-15", "BTCUSDT")
    assert isinstance(seed, int)
    assert 0 <= seed < 2**31


def test_seed_reproducibility():
    """Test that seed generation is reproducible across multiple calls."""
    seeds = [generate_deterministic_seed("2025-01-15", "BTCUSDT") for _ in range(10)]
    assert len(set(seeds)) == 1  # All seeds should be identical


def test_seed_case_insensitive_symbol():
    """Test that symbol case doesn't matter."""
    seed1 = generate_deterministic_seed("2025-01-15", "BTCUSDT")
    seed2 = generate_deterministic_seed("2025-01-15", "btcusdt")
    assert seed1 == seed2


def test_seed_date_formats():
    """Test that different date formats produce same seed."""
    seed1 = generate_deterministic_seed("2025-01-15", "BTCUSDT")
    seed2 = generate_deterministic_seed("20250115", "BTCUSDT")
    assert seed1 == seed2

