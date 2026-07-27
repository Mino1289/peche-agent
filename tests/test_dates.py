"""Tests pour peche.dates."""

from datetime import date

import pytest

from peche.dates import parse_period_range, period_includes


@pytest.mark.parametrize(
    "text,expected_start,expected_end",
    [
        (
            "Période Du 1 er avril 2026 au 31 mars 2027",
            date(2026, 4, 1),
            date(2027, 3, 31),
        ),
        (
            "Du 15 mai 2026 au 10 septembre 2026 - Autres espèces",
            date(2026, 5, 15),
            date(2026, 9, 10),
        ),
        (
            "Du 20 décembre 2026 au 31 mars 2027",
            date(2026, 12, 20),
            date(2027, 3, 31),
        ),
        (
            "Du 1er fevrier 2026 au 28 fevrier 2026",
            date(2026, 2, 1),
            date(2026, 2, 28),
        ),
    ],
)
def test_parse_period_range(text, expected_start, expected_end):
    rng = parse_period_range(text)
    assert rng is not None
    start, end = rng
    assert start == expected_start
    assert end == expected_end


def test_parse_period_range_invalid():
    assert parse_period_range("") is None
    assert parse_period_range("pas une période") is None


def test_period_includes_inside():
    text = "Période Du 1 er avril 2026 au 31 mars 2027"
    assert period_includes(text, date(2026, 6, 15)) is True


def test_period_includes_outside():
    text = "Période Du 1 er avril 2026 au 31 mars 2027"
    assert period_includes(text, date(2025, 1, 1)) is False


def test_period_includes_unparseable_returns_true():
    assert period_includes("texte illisible", date(2026, 1, 1)) is True
