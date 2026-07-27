"""Tests pour peche.reglements.zones."""

import pytest

from peche.reglements.zones import ZONES, zone_by_id


def test_zones_count():
    assert len(ZONES) == 34


def test_zone_by_id_known():
    z = zone_by_id(32)
    assert z is not None
    assert z.value == 32
    assert "28" in z.text


def test_zone_by_id_special_ids():
    assert zone_by_id(3063) is not None
    assert zone_by_id(2652) is not None
    assert zone_by_id(2653) is not None


def test_zone_by_id_unknown():
    assert zone_by_id(99999) is None


def test_zones_frozen():
    z = zone_by_id(1)
    assert z is not None
    with pytest.raises(AttributeError):
        z.value = 99  # type: ignore[misc]
