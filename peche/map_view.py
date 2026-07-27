"""Carte interactive (Folium) — hydro, barrages, marées, LCE, bassins, plan RegPec."""

from __future__ import annotations

import json
from typing import Any

from peche.barrages import load_barrages
from peche.hydromet import STATIONS_PATH, load_stations
from peche.reglements.sync import DATA_DIR
from peche.spatial.reg_link import get_match
from peche.spatial.viewport import features_in_bbox
from peche.tides import STATIONS_PATH as TIDE_STATIONS_PATH
from peche.tides import load_stations as load_tide_stations

LOCATIONS_DIR = DATA_DIR / "locations"

_PLAN_CONTEXT_TOOLS = frozenset(
    {
        "get_weather_at_plan",
        "get_hydromet_for_waterbody",
        "get_hydromet_at_plan",
        "get_barrages_at_plan",
        "get_tides_at_plan",
        "get_reglements",
        "get_map_context",
    }
)

_PLACE_CONTEXT_TOOLS = frozenset(
    {
        "get_weather_at_place",
        "get_barrages_at_place",
        "get_tides_at_place",
    }
)

_WEATHER_TOOLS = frozenset(
    {
        "get_weather",
        "get_weather_at_plan",
        "get_weather_at_place",
    }
)


def map_unavailable_reason() -> str | None:
    """Raison d'indisponibilité de la carte, ou None si OK."""
    try:
        import folium  # noqa: F401
    except ImportError:
        return (
            "Paquet `folium` absent dans l'interpréteur Python qui exécute "
            "Streamlit. Utiliser le venv du projet : "
            "`.venv/bin/python -m peche.ui` (ou reconstruire l'image Docker)."
        )
    if not STATIONS_PATH.exists():
        return (
            "Fichier `data/hydromet/stations.json` introuvable — lancer "
            "`python3 -m peche.hydromet sync-stations`."
        )
    return None


def _load_hydro_stations() -> list[dict]:
    if not STATIONS_PATH.exists():
        return []
    return [s for s in load_stations() if s.get("lat") is not None and s.get("lon") is not None]


def _load_tide_map_stations() -> list[dict]:
    if not TIDE_STATIONS_PATH.exists():
        return []
    return [
        s
        for s in load_tide_stations()
        if s.get("lat") is not None and s.get("lon") is not None
    ]


def _load_cehq_barrages() -> list[dict]:
    return [b for b in load_barrages() if b.get("lat") is not None and b.get("lon") is not None]


def map_layer_counts() -> dict[str, int]:
    from peche.lce import INDEX_PATH as LCE_INDEX

    lce_tiles = 0
    lce_features = 0
    if LCE_INDEX.exists():
        idx = json.loads(LCE_INDEX.read_text(encoding="utf-8"))
        lce_tiles = idx.get("nb_tiles", 0)
        lce_features = idx.get("nb_features", 0)
    return {
        "hydro": len(_load_hydro_stations()),
        "barrages": len(_load_cehq_barrages()),
        "tides": len(_load_tide_map_stations()),
        "lce": lce_features,
        "lce_tiles": lce_tiles,
    }


def _bbox_from_center(
    center: tuple[float, float],
    zoom: int,
) -> tuple[float, float, float, float]:
    """bbox approximatif (lon_min, lat_min, lon_max, lat_max) selon zoom."""
    lat, lon = center
    delta = max(0.05, 2.0 / (2 ** (zoom / 2)))
    return lon - delta, lat - delta, lon + delta, lat + delta


def _lce_popup(props: dict, reg_hint: str = "") -> str:
    nom = props.get("nom") or f"LCE #{props.get('id_lce', '?')}"
    lines = [f"<b>{nom}</b>", f"Type : {props.get('type', '—')}"]
    if props.get("profondeur_max_lac") is not None:
        lines.append(f"Profondeur max : {props['profondeur_max_lac']} m")
    if props.get("superficie_nette_lac") is not None:
        lines.append(f"Superficie : {props['superficie_nette_lac']} ha")
    if reg_hint:
        lines.append(f"<i>{reg_hint}</i>")
    return "<br>".join(lines)


def _add_geojson_layer(
    m: Any,
    features: list[dict],
    *,
    name: str,
    style: dict | None = None,
    show: bool = True,
) -> None:
    import folium

    if not features:
        return
    fg = folium.FeatureGroup(name=name, show=show)
    folium.GeoJson(
        {"type": "FeatureCollection", "features": features},
        style_function=lambda _x, st=style or {}: st,
    ).add_to(fg)
    fg.add_to(m)


def _add_lce_markers(m: Any, features: list[dict], *, show: bool = True) -> None:
    import folium

    if not features:
        return
    layer = folium.FeatureGroup(name="Lacs et rivières (LCE)", show=show)
    for feat in features:
        coords = feat.get("geometry", {}).get("coordinates")
        props = feat.get("properties") or {}
        if not coords:
            continue
        lon, lat = coords[0], coords[1]
        color = "#1565c0" if props.get("type") == "lac" else "#0d47a1"
        folium.CircleMarker(
            location=[lat, lon],
            radius=4,
            popup=folium.Popup(_lce_popup(props), max_width=280),
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.65,
        ).add_to(layer)
    layer.add_to(m)


def build_folium_map(
    *,
    center: tuple[float, float] | None = None,
    zoom: int = 7,
    hydro_stations: list[dict] | None = None,
    tide_stations: list[dict] | None = None,
    cehq_barrages: list[dict] | None = None,
    plan_pin: dict | None = None,
    weather: dict | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    lce_features: list[dict] | None = None,
    basin_features: list[dict] | None = None,
    segment_points: list[dict] | None = None,
    reg_summary: str | None = None,
    atlas_layers: dict[str, list[dict]] | None = None,
) -> Any:
    """Construit une carte Folium (retourne l'objet `folium.Map`)."""
    import folium
    from folium.plugins import MarkerCluster

    if center is None:
        if plan_pin and plan_pin.get("lat") is not None:
            center = (plan_pin["lat"], plan_pin["lon"])
        else:
            center = (48.5, -71.0)

    m = folium.Map(location=list(center), zoom_start=zoom, tiles="OpenStreetMap")

    if bbox is None and center is not None:
        bbox = _bbox_from_center(center, zoom)
    if lce_features is None and bbox is not None:
        lce_features = features_in_bbox("lce", bbox, zoom)
    if basin_features is None and bbox is not None:
        basin_features = features_in_bbox("bassins", bbox, zoom)

    if basin_features:
        _add_geojson_layer(
            m,
            basin_features,
            name="Bassins hydrographiques",
            style={
                "fillColor": "#4fc3f7",
                "color": "#0277bd",
                "weight": 1,
                "fillOpacity": 0.15,
            },
        )

    if lce_features:
        _add_lce_markers(m, lce_features)

    if atlas_layers:
        for layer_name, feats in atlas_layers.items():
            _add_lce_markers(m, feats, show=False) if layer_name == "rsvl" else None
            if layer_name != "rsvl":
                _add_geojson_layer(
                    m,
                    feats,
                    name=layer_name.upper(),
                    show=False,
                    style={"fillColor": "#81c784", "color": "#2e7d32", "weight": 1, "fillOpacity": 0.12},
                )

    hydro_layer = folium.FeatureGroup(name="Hydro CEHQ", show=True)
    barrage_layer = folium.FeatureGroup(name="Barrages CEHQ (répertoire)", show=True)
    tide_layer = folium.FeatureGroup(name="Marées SHC", show=True)

    hydro = hydro_stations if hydro_stations is not None else _load_hydro_stations()
    for s in hydro:
        lat, lon = s.get("lat"), s.get("lon")
        if lat is None or lon is None:
            continue
        popup = (
            f"<b>{s.get('station', '')}</b><br>"
            f"{s.get('plan_eau', '')}<br>"
            f"{s.get('description', '')}<br>"
            f"Niveau: {s.get('niveau_m', '—')} m<br>"
            f"Débit: {s.get('debit_m3s', '—')} m³/s"
        )
        folium.CircleMarker(
            location=[lat, lon],
            radius=5,
            popup=folium.Popup(popup, max_width=320),
            color="#1f77b4",
            fill=True,
            fill_color="#1f77b4",
            fill_opacity=0.7,
        ).add_to(hydro_layer)

    barrages = cehq_barrages if cehq_barrages is not None else _load_cehq_barrages()
    cluster = MarkerCluster(name="Barrages CEHQ")
    for b in barrages:
        lat, lon = b.get("lat"), b.get("lon")
        if lat is None or lon is None:
            continue
        nom = b.get("nom") or b.get("numero") or "Barrage"
        fiche = b.get("url_fiche") or ""
        popup = (
            f"<b>{nom}</b><br>"
            f"{b.get('numero', '')}<br>"
            f"{b.get('plan_eau', '')}<br>"
            f"{b.get('categorie', '')}<br>"
            f"{b.get('municipalite', '')}"
        )
        if fiche:
            popup += f'<br><a href="{fiche}" target="_blank">Répertoire CEHQ</a>'
        folium.CircleMarker(
            location=[lat, lon],
            radius=6,
            popup=folium.Popup(popup, max_width=320),
            color="#c0392b",
            fill=True,
            fill_color="#e74c3c",
            fill_opacity=0.85,
        ).add_to(cluster)
    cluster.add_to(barrage_layer)

    tides = tide_stations if tide_stations is not None else _load_tide_map_stations()
    for s in tides:
        lat, lon = s.get("lat"), s.get("lon")
        if lat is None or lon is None:
            continue
        popup = (
            f"<b>Marée {s.get('code', '')}</b><br>"
            f"{s.get('nom', '')}<br>"
            f"Type: {s.get('type', '—')}<br>"
            f"Opérationnelle: {'oui' if s.get('operating') else 'non'}"
        )
        folium.CircleMarker(
            location=[lat, lon],
            radius=6,
            popup=folium.Popup(popup, max_width=280),
            color="#6a1b9a",
            fill=True,
            fill_color="#9c27b0",
            fill_opacity=0.75,
        ).add_to(tide_layer)

    hydro_layer.add_to(m)
    barrage_layer.add_to(m)
    tide_layer.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)

    if segment_points:
        seg_layer = folium.FeatureGroup(name="Segments rivière (DMS)", show=True)
        for pt in segment_points:
            lat, lon = pt.get("lat"), pt.get("lon")
            if lat is None or lon is None:
                continue
            folium.CircleMarker(
                location=[lat, lon],
                radius=5,
                color="#e65100",
                fill=True,
                fill_color="#ff9800",
                fill_opacity=0.8,
                popup="Limite segment",
            ).add_to(seg_layer)
        seg_layer.add_to(m)

    if plan_pin and plan_pin.get("lat") is not None:
        popup_text = plan_pin.get("nom", "Plan d'eau")
        if reg_summary:
            popup_text = f"<b>{popup_text}</b><br>{reg_summary}"
        folium.CircleMarker(
            location=[plan_pin["lat"], plan_pin["lon"]],
            radius=10,
            popup=folium.Popup(popup_text, max_width=360),
            color="#2ca02c",
            fill=True,
            fill_color="#2ca02c",
            fill_opacity=0.85,
        ).add_to(m)
        if plan_pin.get("lce_match"):
            folium.Circle(
                location=[plan_pin["lat"], plan_pin["lon"]],
                radius=800,
                color="#2ca02c",
                fill=False,
                weight=2,
                opacity=0.5,
            ).add_to(m)

    if weather and weather.get("lat") is not None:
        cond = weather.get("conditions") or weather
        temp = cond.get("temperature_c") or cond.get("temp")
        folium.CircleMarker(
            location=[weather["lat"], weather["lon"]],
            radius=8,
            popup=f"Météo : {temp} °C" if temp is not None else "Météo",
            color="#ff7f0e",
            fill=True,
            fill_color="#ff7f0e",
            fill_opacity=0.85,
        ).add_to(m)

    return m


def render_map_streamlit(
    *,
    center: tuple[float, float] | None = None,
    zoom: int = 7,
    plan_pin: dict | None = None,
    weather: dict | None = None,
    height: int = 480,
    bbox: tuple[float, float, float, float] | None = None,
    segment_points: list[dict] | None = None,
    reg_summary: str | None = None,
) -> dict | None:
    """Affiche la carte dans Streamlit ; retourne bounds/zoom si disponibles."""
    import streamlit as st

    m = build_folium_map(
        center=center,
        zoom=zoom,
        plan_pin=plan_pin,
        weather=weather,
        bbox=bbox,
        segment_points=segment_points,
        reg_summary=reg_summary,
    )
    try:
        from streamlit_folium import st_folium

        return st_folium(
            m,
            width=None,
            height=height,
            returned_objects=["bounds", "last_clicked"],
        )
    except ImportError:
        pass

    hydro = _load_hydro_stations()
    tides = _load_tide_map_stations()
    barrages = _load_cehq_barrages()
    rows = [
        {
            "lat": s["lat"],
            "lon": s["lon"],
            "label": s.get("plan_eau") or s.get("station"),
            "layer": "hydro",
        }
        for s in hydro
    ]
    rows.extend(
        {
            "lat": s["lat"],
            "lon": s["lon"],
            "label": s.get("nom") or s.get("code"),
            "layer": "tide",
        }
        for s in tides
    )
    rows.extend(
        {
            "lat": b["lat"],
            "lon": b["lon"],
            "label": b.get("nom") or b.get("numero"),
            "layer": "barrage",
        }
        for b in barrages
    )
    if plan_pin and plan_pin.get("lat") is not None:
        rows.append(
            {
                "lat": plan_pin["lat"],
                "lon": plan_pin["lon"],
                "label": plan_pin.get("nom", "Plan"),
                "layer": "plan",
            }
        )
    if rows:
        import pandas as pd

        st.map(pd.DataFrame(rows), latitude="lat", longitude="lon", size=20)
        st.caption(
            f"{len(rows)} points (repli `st.map`). "
            "Installer `streamlit-folium` pour la carte interactive complète."
        )
    else:
        st.caption("Aucune station à afficher.")
    return None


def _reg_summary_short(zone_id: int, plan_id: int) -> str:
    try:
        from peche.tools import get_reglements

        reg = get_reglements(zone_id, plan_id, only_in_effect=True)
        if reg.get("error"):
            return ""
        especes: list[str] = []
        for block in reg.get("reglements") or []:
            for per in block.get("periodes") or []:
                for esp in per.get("especes") or []:
                    name = esp.get("espece")
                    if name and name not in especes:
                        especes.append(name)
        if not especes:
            return "Règlements : voir onglet Chat"
        shown = ", ".join(especes[:6])
        if len(especes) > 6:
            shown += f" (+{len(especes) - 6})"
        return f"Espèces en vigueur : {shown}"
    except Exception:
        return ""


def _iter_tool_entries(messages: list[dict]):
    for msg in reversed(messages):
        if msg.get("role") != "assistant":
            continue
        for entry in reversed(msg.get("tools") or []):
            if entry.get("result_pending"):
                continue
            yield entry


def _coords_from_result(result: dict) -> tuple[float, float] | None:
    lat = result.get("lat") or result.get("plan_lat")
    lon = result.get("lon") or result.get("plan_lon")
    if lat is not None and lon is not None:
        return float(lat), float(lon)
    geo = result.get("geocoded")
    if isinstance(geo, dict) and geo.get("lat") is not None and geo.get("lon") is not None:
        return float(geo["lat"]), float(geo["lon"])
    return None


def _plan_ref_from_entry(entry: dict) -> tuple[int, int, str | None] | None:
    name = entry.get("name")
    result = entry.get("result")
    args = entry.get("args") or {}

    if name == "search_plans" and isinstance(result, dict):
        for cand in result.get("candidates") or []:
            pid, zid = cand.get("plan_id"), cand.get("zone_id")
            if pid is not None and zid is not None:
                return int(zid), int(pid), cand.get("nom")
        return None

    if name not in _PLAN_CONTEXT_TOOLS:
        return None

    if isinstance(result, dict):
        pid = result.get("plan_id")
        zid = result.get("zone_id")
        if pid is not None and zid is not None:
            label = result.get("plan_nom") or result.get("label")
            return int(zid), int(pid), label

    pid = args.get("plan_id")
    zid = args.get("zone_id")
    if pid is not None and zid is not None:
        return int(zid), int(pid), None
    return None


def _weather_from_entry(entry: dict) -> dict | None:
    name = entry.get("name")
    if name not in _WEATHER_TOOLS:
        return None
    result = entry.get("result")
    args = entry.get("args") or {}
    if not isinstance(result, dict) or result.get("error"):
        return None

    coords = _coords_from_result(result)
    if name == "get_weather" and coords is None:
        alat, alon = args.get("lat"), args.get("lon")
        if alat is not None and alon is not None:
            coords = float(alat), float(alon)
    if coords is None:
        return None

    lat, lon = coords
    return {"lat": lat, "lon": lon, "conditions": result}


def _place_from_entry(entry: dict) -> tuple[float, float, str] | None:
    name = entry.get("name")
    if name not in _PLACE_CONTEXT_TOOLS:
        return None
    result = entry.get("result")
    args = entry.get("args") or {}
    if not isinstance(result, dict) or result.get("error"):
        return None

    coords = _coords_from_result(result)
    if coords is None:
        return None

    label = (
        result.get("place")
        or result.get("plan_nom")
        or result.get("label")
        or args.get("place")
        or "Lieu"
    )
    return coords[0], coords[1], str(label)


def map_context_from_messages(
    messages: list[dict],
    *,
    fetch_weather: bool = True,
) -> dict:
    """Déduit le contexte carte depuis l'historique chat (pin, météo, centre)."""
    plan_ref: tuple[int, int, str | None] | None = None
    weather: dict | None = None
    place: tuple[float, float, str] | None = None

    for entry in _iter_tool_entries(messages):
        if plan_ref is None:
            plan_ref = _plan_ref_from_entry(entry)
        if weather is None:
            weather = _weather_from_entry(entry)
        if place is None:
            place = _place_from_entry(entry)

    plan_pin = None
    label = None
    center = None
    zoom = 7

    segment_points: list[dict] = []
    reg_summary: str | None = None
    lce_match = None

    if plan_ref is not None:
        zid, pid, ref_label = plan_ref
        plan_pin = find_plan_pin(zid, pid)
        spatial = get_match(zid, pid)
        if spatial:
            segment_points = spatial.get("segment_points") or []
            lce_match = spatial.get("lce")
        if plan_pin:
            label = plan_pin.get("nom") or ref_label
            center = (plan_pin["lat"], plan_pin["lon"])
            zoom = 11
            if lce_match:
                plan_pin["lce_match"] = lce_match
            reg_summary = _reg_summary_short(zid, pid)
        elif ref_label:
            label = ref_label
    elif place is not None:
        lat, lon, plabel = place
        label = plabel
        center = (lat, lon)
        zoom = 11

    if (
        weather is None
        and fetch_weather
        and plan_pin
        and plan_pin.get("lat") is not None
    ):
        from peche.weather import get_weather

        w = get_weather(plan_pin["lat"], plan_pin["lon"])
        if not w.get("error"):
            weather = {
                "lat": plan_pin["lat"],
                "lon": plan_pin["lon"],
                "conditions": w,
            }

    bbox = _bbox_from_center(center, zoom) if center else None

    return {
        "plan_pin": plan_pin,
        "weather": weather,
        "center": center,
        "zoom": zoom,
        "label": label,
        "bbox": bbox,
        "segment_points": segment_points,
        "reg_summary": reg_summary,
        "lce_match": lce_match,
    }


def find_plan_pin(zone_id: int, plan_id: int) -> dict | None:
    path = LOCATIONS_DIR / f"{zone_id}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    for loc in data.get("locations", []):
        if loc["id"] == plan_id and loc.get("lat") is not None:
            return {
                "nom": loc.get("nom"),
                "lat": loc["lat"],
                "lon": loc["lon"],
                "zone_id": zone_id,
                "plan_id": plan_id,
            }
    return None
