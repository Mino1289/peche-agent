"""Outils agent qui pilotent la carte (émettent des map_action)."""

from __future__ import annotations

from typing import Any

# Collecteur thread-local des actions carte pour le tour en cours.
# Rempli par les outils, vidé/consommé par loop.stream_chat.
_pending_actions: list[dict[str, Any]] = []
_current_map_state: dict[str, Any] | None = None


def set_current_map_state(state: dict[str, Any] | None) -> None:
    global _current_map_state
    _current_map_state = state


def current_map_state() -> dict[str, Any] | None:
    return _current_map_state


def drain_map_actions() -> list[dict[str, Any]]:
    actions = list(_pending_actions)
    _pending_actions.clear()
    return actions


def clear_map_actions() -> None:
    _pending_actions.clear()


def _emit(action: str, **payload: Any) -> dict[str, Any]:
    event = {"action": action, **payload}
    _pending_actions.append(event)
    return {"ok": True, "map_action": event}


def set_map_view(
    center: list[float] | None = None,
    zoom: float | None = None,
    bbox: list[float] | None = None,
) -> dict[str, Any]:
    """Centre / zoom / bbox de la carte."""
    payload: dict[str, Any] = {}
    if center is not None:
        if len(center) != 2:
            return {"error": "center doit être [lon, lat]"}
        payload["center"] = center
    if zoom is not None:
        payload["zoom"] = float(zoom)
    if bbox is not None:
        if len(bbox) != 4:
            return {"error": "bbox doit être [lon_min, lat_min, lon_max, lat_max]"}
        payload["bbox"] = bbox
    if not payload:
        return {"error": "Aucun paramètre fourni"}
    return _emit("set_view", **payload)


def toggle_layers(
    show: list[str] | None = None,
    hide: list[str] | None = None,
    opacity: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Affiche / masque des couches par id catalogue."""
    return _emit(
        "toggle_layers",
        show=show or [],
        hide=hide or [],
        opacity=opacity or {},
    )


def set_layer_filter(layer_id: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    """Applique un filtre attributaire / colorkey sur une couche."""
    if not layer_id:
        return {"error": "layer_id requis"}
    return _emit("set_layer_filter", layer_id=layer_id, filters=filters or {})


def filter_by_zone(zone_id: int | None = None, clear: bool = False) -> dict[str, Any]:
    """Clippe toutes les couches à une zone de pêche (numéro affiché ou id RegPec)."""
    if clear or zone_id is None:
        return _emit("filter_by_zone", zone_id=None, clear=True)
    from peche.reglements.zones import display_number, resolve_zone_ref

    zone = resolve_zone_ref(zone_id)
    payload: dict[str, Any] = {
        "zone_id": int(zone.value) if zone else int(zone_id),
        "no_zone": display_number(zone) if zone else int(zone_id),
        "zone_nom": zone.text if zone else None,
        "clear": False,
    }
    return _emit("filter_by_zone", **payload)


def highlight_features(
    layer_id: str,
    feature_ids: list[str | int] | None = None,
    geojson: dict | None = None,
) -> dict[str, Any]:
    """Surligne des features sur la carte."""
    return _emit(
        "highlight_features",
        layer_id=layer_id,
        feature_ids=feature_ids or [],
        geojson=geojson,
    )


def get_point_info(
    pin_number: int | None = None,
    lon: float | None = None,
    lat: float | None = None,
) -> dict[str, Any]:
    """Contexte géographique d'un point utilisateur (pin numéroté ou coords)."""
    from peche.spatial.point_context import get_point_context

    state = _current_map_state or {}
    pins = state.get("pins") or []
    if pin_number is not None:
        pin = next(
            (p for p in pins if int(p.get("n") or 0) == int(pin_number)),
            None,
        )
        if pin is None:
            return {
                "error": f"Point {pin_number} introuvable sur la carte.",
                "pins_available": [
                    {"n": p.get("n"), "label": p.get("label")} for p in pins
                ],
            }
        lon = float(pin["lon"])
        lat = float(pin["lat"])
        ctx = get_point_context(lon, lat)
        ctx["pin_number"] = pin_number
        ctx["label"] = pin.get("label")
        if pin.get("props"):
            ctx["cached_props"] = pin["props"]
        return ctx
    if lon is None or lat is None:
        return {
            "error": "Fournir pin_number ou lon+lat.",
            "pins_available": [
                {"n": p.get("n"), "label": p.get("label"), "lon": p.get("lon"), "lat": p.get("lat")}
                for p in pins
            ],
        }
    return get_point_context(float(lon), float(lat))
