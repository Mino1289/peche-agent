"""Tests point_context — géométrie et résolution zone."""

from peche.spatial.point_context import (
    _point_in_geometry,
    get_point_context,
    hunting_forbidden_label,
    parse_grhq_toponyme,
)


def test_point_in_geometry_point():
    geom = {"type": "Point", "coordinates": [-71.2, 46.5]}
    assert _point_in_geometry(-71.2, 46.5, geom)
    assert not _point_in_geometry(-72.0, 46.5, geom)


def test_point_in_polygon():
    ring = [[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]
    geom = {"type": "Polygon", "coordinates": [ring]}
    assert _point_in_geometry(1, 1, geom)
    assert not _point_in_geometry(5, 5, geom)


def test_hunting_forbidden_label_toponyme():
    props = {
        "TOPONYME": "Réserve écologique du Grand-Lac-Salé",
        "DESIGNOM": "Réserve écologique",
        "NOM": "Grand-Lac-Salé",
    }
    name, kind = hunting_forbidden_label(props)
    assert name == "Réserve écologique du Grand-Lac-Salé"
    assert kind == "Réserve écologique"


def test_hunting_forbidden_label_compose():
    props = {
        "DESIGNOM": "Parc national",
        "ARTICLE": "du",
        "NOM": "Mont-Tremblant",
    }
    name, kind = hunting_forbidden_label(props)
    assert name == "Parc national du Mont-Tremblant"
    assert kind == "Parc national"


def test_parse_grhq_toponyme():
    sample = (
        "@Surface [2.5M - 750K] Unité_découpage_hydrographique;Type;Pérennité;"
        "Indicateur_isolé;Superficie_ha;Largeur_moyenne_calculée;Longueur_moyenne_calculée;"
        "Producteur;Source_données;Méthode_production_données;Toponyme;Précision_planimétrique;"
        "Date_mise_à_jour;Date_source_données;Numéro_séquence;Shape; "
        "05AM;Lac;Permanent;Non isolé;351,003476;2966;5284;MERN;Orthophotographie;"
        "Stéréorestitution photographique;Lac Saint-Charles;6;20160510;20010509;13043;Polygone;"
    )
    assert parse_grhq_toponyme(sample) == "Lac Saint-Charles"


def test_custom_layer_in_point_context(monkeypatch):
    from peche.spatial import point_context as mod

    monkeypatch.setattr(mod, "fishing_zone_at_point", lambda _lon, _lat: None)
    monkeypatch.setattr(mod, "plans_geojson", lambda *_a, **_k: {"features": []})
    monkeypatch.setattr(mod, "_waterbody_name_at_point", lambda _lon, _lat: (None, None))
    monkeypatch.setattr(mod, "_wfs_point_query", lambda *_a, **_k: [])
    monkeypatch.setattr(
        mod,
        "overlay_at_custom_layer",
        lambda **_kw: {
            "layer_id": "custom:test",
            "title": "Ma couche",
            "rows": [{"label": "Nom", "value": "Test"}],
        },
    )

    out = get_point_context(
        -71.0,
        46.0,
        custom_layers=[
            {
                "id": "custom:test",
                "title": "Ma couche",
                "url": "https://example.invalid/wfs",
                "layer_name": "layer",
                "source_type": "wfs",
            }
        ],
    )
    overlays = out.get("layer_overlays") or []
    assert len(overlays) == 1
    assert overlays[0]["title"] == "Ma couche"


def test_downsample_curve_keeps_first_and_spaced():
    from datetime import datetime, timezone

    from peche.tides import _downsample_curve

    pts = [
        {"eventDate": "2026-01-01T00:00:00Z", "value": 1.0},
        {"eventDate": "2026-01-01T00:05:00Z", "value": 1.1},
        {"eventDate": "2026-01-01T00:20:00Z", "value": 1.2},
    ]
    out = _downsample_curve(pts, step_minutes=15)
    assert len(out) == 2
    assert out[0]["value"] == 1.0
    assert out[1]["value"] == 1.2
