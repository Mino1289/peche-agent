"""Filtres à options : ids envoyés par le client → valeurs réelles, ids inconnus refusés."""

import pytest
from fastapi import HTTPException

from peche.api.routes import features

OPTIONS = [
    {"value": "zec", "label": "ZEC", "match": "ZEC"},
    {"value": "pourvoirie", "label": "Pourvoirie", "match": "Pourvoirie avec droits exclusifs"},
]


def test_option_matches_maps_ids_to_values():
    assert features._option_matches(OPTIONS, "pourvoirie,zec") == [
        "Pourvoirie avec droits exclusifs",
        "ZEC",
    ]
    assert features._option_matches(OPTIONS, "") is None


def test_option_matches_rejects_unknown_ids():
    with pytest.raises(HTTPException) as exc:
        features._option_matches(OPTIONS, "zec,'; DROP")
    assert exc.value.status_code == 400
