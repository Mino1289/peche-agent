"""Tests discover / validate couches custom."""

from peche.catalog.discover import _crs_ok, validate_custom_layer
from peche.catalog.harvest import harvest_source
from peche.catalog.sources import WMS_SOURCES

_WMS_CAPS = (
    b'<?xml version="1.0"?>'
    b'<WMS_Capabilities><Capability>'
    b"<Layer><Name>TestLayer</Name><Title>Test</Title></Layer>"
    b"</Capability></WMS_Capabilities>"
)


def test_warm_capabilities_cache(monkeypatch):
    from peche.catalog import discover as mod

    calls: list[str] = []

    class _Src:
        id = "x"

        kind = "wms"

    def fake_sources():
        return [_Src()]

    def fake_harvest(source, *, cache_dir):  # noqa: ANN001, ARG001
        calls.append(source.id)
        return []

    monkeypatch.setattr(mod, "discover_sources", fake_sources)
    monkeypatch.setattr(mod, "harvest_source", fake_harvest)
    assert mod.warm_capabilities_cache() == 1
    assert calls == ["x"]


def test_harvest_source_reads_caps_cache(tmp_path, monkeypatch):
    import importlib

    harvest_mod = importlib.import_module("peche.catalog.harvest")

    src = WMS_SOURCES[0]
    calls: list[str] = []

    def fake_fetch(url: str) -> bytes:
        calls.append(url)
        return _WMS_CAPS

    monkeypatch.setattr(harvest_mod, "_fetch", fake_fetch)
    assert harvest_source(src, cache_dir=tmp_path)
    assert len(calls) == 1
    assert harvest_source(src, cache_dir=tmp_path)
    assert len(calls) == 1


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
