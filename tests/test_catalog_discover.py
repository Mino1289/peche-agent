"""Tests discover / validate couches custom."""

from peche.catalog.discover import _crs_ok, validate_custom_layer


def test_crs_ok_accepts_common():
    assert _crs_ok(["EPSG:3857"])
    assert _crs_ok(["EPSG:4326"])
    assert _crs_ok(["CRS:84"])
    assert not _crs_ok(["EPSG:2154"])


def test_validate_requires_fields():
    out = validate_custom_layer(url="", layer_name="x")
    assert not out["ok"]


def test_validate_layer_not_found(monkeypatch):
    from peche.catalog import discover as mod

    monkeypatch.setattr(
        mod,
        "_layers_for_source",
        lambda _src: [],
    )
    out = validate_custom_layer(
        url="https://geoegl.msp.gouv.qc.ca/apis/wss/environnement.fcgi",
        layer_name="CoucheInexistante",
        source_type="wms",
    )
    assert not out["ok"]
    assert "introuvable" in out["error"].lower()


def test_validate_layer_found(monkeypatch, tmp_path):
    from peche.catalog import discover as mod
    from peche.catalog.models import LayerDef

    layer = LayerDef(
        id="env:Sols",
        title="Sols",
        group="hydrographie",
        source_type="wms",
        url="https://geoegl.msp.gouv.qc.ca/apis/wss/environnement.fcgi",
        layer_name="Sols",
    )
    monkeypatch.setattr(mod, "_layers_for_source", lambda _src: [layer])

    caps = tmp_path / "environnement_wss_wms.xml"
    caps.write_bytes(
        b'<?xml version="1.0"?><WMS_Capabilities>'
        b"<Capability><Layer><Name>Sols</Name>"
        b"<CRS>EPSG:3857</CRS><CRS>EPSG:4326</CRS></Layer></Capability>"
        b"</WMS_Capabilities>"
    )
    monkeypatch.setattr(mod, "CAPS_CACHE_DIR", tmp_path)

    out = validate_custom_layer(
        url=layer.url,
        layer_name="Sols",
        source_type="wms",
    )
    assert out["ok"]
    assert out["layer"]["layer_name"] == "Sols"
