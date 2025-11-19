from datetime import date, datetime

import pytest

from app.utils.seeding import generate_deterministic_seed


@pytest.mark.parametrize(
    "input_date",
    [
        datetime(2025, 11, 19, 12, 0),
        date(2025, 11, 19),
        "2025-11-19",
        "20251119",
    ],
)
def test_generate_deterministic_seed_accepts_multiple_inputs(input_date):
    seed = generate_deterministic_seed(input_date, "BTCUSDT")

    assert isinstance(seed, int)
    assert seed >= 0


def test_generate_deterministic_seed_is_deterministic_for_same_inputs():
    first = generate_deterministic_seed("2025-11-19", "ETHUSDT")
    second = generate_deterministic_seed(date(2025, 11, 19), "ETHUSDT")

    assert first == second


def test_generate_deterministic_seed_varies_with_input_changes():
    base_seed = generate_deterministic_seed("2025-11-19", "BTCUSDT")
    different_date = generate_deterministic_seed("2025-11-20", "BTCUSDT")
    different_symbol = generate_deterministic_seed("2025-11-19", "ETHUSDT")

    assert base_seed != different_date
    assert base_seed != different_symbol


def test_generate_deterministic_seed_rejects_invalid_date_string():
    with pytest.raises(ValueError):
        generate_deterministic_seed("invalid-date", "BTCUSDT")

