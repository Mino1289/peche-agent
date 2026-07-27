"""Outils métier appelables par l'agent.

Outils granulaires : un appel = une intention.

| Outil | Quand l'appeler |
|---|---|
| `list_zones` | l'utilisateur demande la liste des zones |
| `search_plans` | un nom de plan d'eau est mentionné — toujours en premier |
| `get_reglements` | l'utilisateur demande les **règlements** (espèces, limites, périodes) |
| `get_weather` | météo à des coordonnées arbitraires |
| `get_weather_at_plan` | météo pour un plan d'eau identifié (résout les coords) |
| `get_hydromet` | hydro pour un id de station précis |
| `get_hydromet_at_plan` | hydro pour le plan d'eau (résout la station matchée) |
| `get_fishing_advice` | conseils leurres / techniques (sous-agent expert) |
| `search_tide_stations` | recherche station marégraphique SHC |
| `get_tides` | heures et hauteurs des pleines et basses mers |
| `get_tides_at_place` | marées pour un lieu (géocodage + station proche) |
| `get_tides_at_plan` | marées pour un plan d'eau (station proche) |
| `get_water_levels` | **niveau actuel** : Vigilance + IWLS (temps réel) |
| `search_barrages` | répertoire CEHQ (~6000 barrages) |
| `get_barrages_at_plan` | barrages ≤10 km d'un plan d'eau |
| `get_barrages_at_place` | barrages ≤10 km d'un lieu |

Les retours live incluent toujours `observed_at` et `source`. Les retours
règlements incluent `as_of_date` quand un filtre temporel a été appliqué.
"""

from __future__ import annotations

import json
from datetime import date as _date_cls
from difflib import SequenceMatcher
from functools import lru_cache

from peche.matching.normalize import (
    expand_abbreviations,
    normalize_search_text,
    token_jaccard,
)

from peche.dates import period_includes, today
from peche.cehq import cehq_urls, fetch_cehq_history, is_cehq_station_id
from peche.hydromet import (
    STATIONS_PATH,
    get_live_station,
    search_stations_offline,
)
from peche.geocoding import geocode as _geocode
from peche.iqbp import search_iqbp as _search_iqbp
from peche.reglements.sync import DATA_DIR, INDEX_PATH, ZONES_DIR
from peche.reglements.zones import zone_by_id
from peche.tides import (
    get_tide_predictions as _get_tide_predictions,
    get_water_level_live as _get_water_level_live,
    nearest_tide_station as _nearest_tide_station,
    search_tide_stations as _search_tide_stations,
)
from peche.barrages import (
    DEFAULT_RADIUS_KM as _BARRAGE_RADIUS_KM,
    barrages_near_response as _barrages_near_response,
    search_barrages_offline as _search_barrages_offline,
)
from peche.weather import get_weather as _get_weather

LOCATIONS_DIR = DATA_DIR / "locations"
SEARCH_INDEX_PATH = DATA_DIR / "search_index.json"
MATCHES_DIR = DATA_DIR / "hydromet" / "matches"


# ---------- index / zones ----------


def _zone_error(zone_id: int) -> dict | None:
    """Erreur si `zone_id` absent du catalogue RegPec (34 zones)."""
    if zone_by_id(zone_id) is not None:
        return None
    return {
        "error": (
            f"zone_id {zone_id} inconnu (catalogue RegPec : 34 zones). "
            "Appeler list_zones pour les identifiants valides."
        )
    }


def list_zones() -> list[dict]:
    """Liste des zones avec saison en vigueur et nb de plans d'eau."""
    if not INDEX_PATH.exists():
        return []
    idx = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    out: list[dict] = []
    for z in idx.get("zones", []):
        zid = z["zone_id"]
        catalog = zone_by_id(zid)
        out.append(
            {
                "zone_id": zid,
                "zone_nom": z["zone_nom"],
                "zone_label": catalog.text if catalog else z["zone_nom"],
                "saison": z.get("saison", ""),
                "nb_plans_eau": z.get("nb_plans_eau", 0),
            }
        )
    return out


@lru_cache(maxsize=64)
def _load_zone(zone_id: int) -> dict:
    path = ZONES_DIR / f"{zone_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Zone {zone_id} introuvable ({path}).")
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=64)
def _load_locations(zone_id: int) -> list[dict]:
    path = LOCATIONS_DIR / f"{zone_id}.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("locations", [])


@lru_cache(maxsize=64)
def _load_match(zone_id: int) -> list[dict]:
    path = MATCHES_DIR / f"{zone_id}.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("matches", [])


def _find_location(zone_id: int, plan_id: int) -> dict | None:
    for loc in _load_locations(zone_id):
        if loc["id"] == plan_id:
            return loc
    return None


def _find_match(zone_id: int, plan_id: int) -> dict | None:
    for entry in _load_match(zone_id):
        if entry["plan_id"] == plan_id:
            return entry
    return None


# ---------- recherche fuzzy ----------


def _normalize(text: str) -> str:
    return normalize_search_text(text)


@lru_cache(maxsize=1)
def _load_search_index() -> list[dict]:
    if SEARCH_INDEX_PATH.exists():
        return json.loads(SEARCH_INDEX_PATH.read_text(encoding="utf-8")).get(
            "entries", []
        )
    entries: list[dict] = []
    for z in list_zones():
        zid = z["zone_id"]
        for loc in _load_locations(zid):
            entries.append(
                {
                    "plan_id": loc["id"],
                    "zone_id": zid,
                    "nom": loc.get("nom", ""),
                    "nom_brut": loc.get("nom_brut", loc.get("nom", "")),
                    "nom_search": loc.get("nom_search")
                    or normalize_search_text(loc.get("nom_brut", "")),
                    "segment_label": loc.get("segment_label"),
                    "river_base_name": loc.get("river_base_name", ""),
                    "aliases": loc.get("aliases") or [],
                    "lat": loc.get("lat"),
                    "lon": loc.get("lon"),
                }
            )
    return entries


def _score_plan_entry(query: str, entry: dict, zone_id: int | None) -> float:
    q_norm = normalize_search_text(expand_abbreviations(query))
    if not q_norm:
        return 0.0

    haystacks = [
        entry.get("nom_search") or "",
        normalize_search_text(entry.get("nom_brut", "")),
        normalize_search_text(entry.get("river_base_name", "")),
        *(entry.get("aliases") or []),
    ]
    best = 0.0
    for hay in haystacks:
        if not hay:
            continue
        if q_norm == hay:
            best = max(best, 1.0)
        elif q_norm in hay:
            best = max(best, 0.85 + 0.1 * (len(q_norm) / max(len(hay), 1)))
        else:
            best = max(best, SequenceMatcher(None, q_norm, hay).ratio())
            best = max(best, token_jaccard(query, hay) * 0.95)

    seg = entry.get("segment_label") or ""
    if seg and seg.rstrip(")") in q_norm:
        best = min(1.0, best + 0.08)

    if zone_id is not None and entry.get("zone_id") == zone_id:
        best = min(1.0, best + 0.05)
    return round(best, 3)


def _build_segment_groups(candidates: list[dict], index: list[dict]) -> list[dict]:
    """Regroupe les segments d'une même rivière (a)…e))."""
    by_key: dict[tuple[int, str], list[dict]] = {}
    index_by_id = {(e["zone_id"], e["plan_id"]): e for e in index}
    for c in candidates:
        entry = index_by_id.get((c["zone_id"], c["plan_id"]), {})
        base = entry.get("river_base_name") or c.get("nom", "")
        if not base:
            continue
        key = (c["zone_id"], normalize_search_text(base))
        by_key.setdefault(key, []).append(
            {
                "plan_id": c["plan_id"],
                "nom": c["nom"],
                "segment_label": entry.get("segment_label"),
                "score": c["score"],
            }
        )
    groups: list[dict] = []
    for (zid, _), segs in by_key.items():
        if len(segs) < 2:
            continue
        segs.sort(key=lambda s: s.get("segment_label") or "")
        base_name = index_by_id.get((zid, segs[0]["plan_id"]), {}).get(
            "river_base_name", segs[0]["nom"]
        )
        groups.append(
            {
                "zone_id": zid,
                "base_name": base_name,
                "segment_count": len(segs),
                "segments": segs,
            }
        )
    groups.sort(key=lambda g: max(s["score"] for s in g["segments"]), reverse=True)
    return groups


def search_plans(
    query: str,
    zone_id: int | None = None,
    limit: int = 8,
    group_segments: bool = True,
) -> dict:
    """Recherche fuzzy d'un plan d'eau. Toujours appeler en premier quand un
    nom est mentionné. Retourne `candidates` et, si pertinent, `groups` de
    segments (ex. Rivière Sainte-Marguerite a)…e)).
    """
    if zone_id is not None:
        err = _zone_error(zone_id)
        if err:
            return {"candidates": [err], "groups": []}
    if not query.strip():
        return {"candidates": [], "groups": []}

    index = _load_search_index()
    pool = [e for e in index if e["zone_id"] == zone_id] if zone_id else index

    candidates: list[dict] = []
    for entry in pool:
        score = _score_plan_entry(query, entry, zone_id)
        if score < 0.35:
            continue
        candidates.append(
            {
                "plan_id": entry["plan_id"],
                "zone_id": entry["zone_id"],
                "nom": entry.get("nom") or entry.get("nom_brut", ""),
                "segment_label": entry.get("segment_label"),
                "river_base_name": entry.get("river_base_name"),
                "lat": entry.get("lat"),
                "lon": entry.get("lon"),
                "score": score,
            }
        )
    candidates.sort(key=lambda c: c["score"], reverse=True)
    top = candidates[:limit]

    out: dict = {"candidates": top, "groups": []}
    if group_segments and len(top) >= 2:
        groups = _build_segment_groups(top, index)
        if groups:
            out["groups"] = groups
            top_scores = [c["score"] for c in top[:2]]
            if len(top_scores) == 2 and abs(top_scores[0] - top_scores[1]) < 0.15:
                out["disambiguation_hint"] = (
                    "Plusieurs plans ou segments proches — préciser la zone "
                    "ou le segment (ex. « segment b) ») si nécessaire."
                )
    return out


# ---------- règlements ----------


def _filter_periodes(periodes: list[dict], day: _date_cls) -> list[dict]:
    return [p for p in periodes if period_includes(p.get("periode", ""), day)]


def _filter_segments(segments: list[dict], day: _date_cls) -> list[dict]:
    out = []
    for seg in segments:
        kept = _filter_periodes(seg.get("periodes", []), day)
        if kept:
            out.append({**seg, "periodes": kept})
    return out


def get_reglements(
    zone_id: int,
    plan_id: int | None = None,
    only_in_effect: bool = False,
    date: str | None = None,
) -> dict:
    """Règlements d'une zone (et d'un plan d'eau si fourni).

    Si `only_in_effect=True`, ne renvoie que les périodes qui couvrent la date
    `date` (ISO `YYYY-MM-DD`, défaut = aujourd'hui). À utiliser dès que
    l'utilisateur demande « ce qu'on peut pêcher aujourd'hui / cette semaine ».
    """
    err = _zone_error(zone_id)
    if err:
        return err
    try:
        z = _load_zone(zone_id)
    except FileNotFoundError:
        zone = zone_by_id(zone_id)
        label = zone.text if zone else str(zone_id)
        return {
            "error": (
                f"Données offline absentes pour {label} (zone_id={zone_id}). "
                "Lancer `python3 -m peche.reglements sync`."
            )
        }
    out: dict = {
        "zone_id": zone_id,
        "zone_nom": z["meta"]["zone_nom"],
        "saison": z["meta"].get("saison", ""),
        "saison_id": z["meta"].get("saison_id"),
        "fetched_at": z["meta"].get("fetched_at"),
        "source_url": z["meta"].get("source_url"),
        "filtre_en_vigueur": False,
        "as_of_date": None,
    }

    day: _date_cls | None = None
    if only_in_effect:
        if date:
            try:
                day = _date_cls.fromisoformat(date)
            except ValueError:
                return {"error": f"Date invalide '{date}', format attendu YYYY-MM-DD."}
        else:
            day = today()
        out["filtre_en_vigueur"] = True
        out["as_of_date"] = day.isoformat()

    regles_gen = z.get("regles_generales", [])
    if day is not None:
        regles_gen = _filter_segments(regles_gen, day)
    out["regles_generales"] = regles_gen

    if plan_id is not None:
        plan = next(
            (p for p in z.get("plans_eau", []) if p["id"] == plan_id),
            None,
        )
        if plan is None:
            out["plan_eau"] = {
                "error": f"Plan {plan_id} introuvable dans zone {zone_id}."
            }
        else:
            segs = plan.get("segments", [])
            if day is not None:
                segs = _filter_segments(segs, day)
            out["plan_eau"] = {
                "id": plan["id"],
                "nom": plan["nom"],
                "source_url": plan.get("source_url"),
                "segments": segs,
            }
    else:
        out["plan_eau"] = None
    return out


# ---------- live : météo ----------


def get_weather(lat: float, lon: float) -> dict:
    """Météo live à des coordonnées WGS84 arbitraires (GeoMet citypage)."""
    return _get_weather(lat, lon)


def get_weather_at_plan(plan_id: int, zone_id: int) -> dict:
    """Météo live pour un plan d'eau identifié — résout les coordonnées
    depuis `data/locations/`. Erreur explicite si lat/lon manquants.
    """
    loc = _find_location(zone_id, plan_id)
    if loc is None:
        return {"error": f"Plan {plan_id} introuvable dans zone {zone_id}."}
    if loc["lat"] is None or loc["lon"] is None:
        return {
            "plan_id": plan_id,
            "zone_id": zone_id,
            "plan_nom": loc["nom"],
            "error": "Coordonnées non disponibles pour ce plan d'eau.",
        }
    weather = get_weather(loc["lat"], loc["lon"])
    return {
        "plan_id": plan_id,
        "zone_id": zone_id,
        "plan_nom": loc["nom"],
        "plan_lat": loc["lat"],
        "plan_lon": loc["lon"],
        **weather,
    }


def get_weather_at_place(place: str) -> dict:
    """Météo pour un nom de lieu libre (ville, village, lac, rivière…).

    Utilise Nominatim (OpenStreetMap) pour résoudre `place` en coordonnées,
    puis interroge GeoMet (citypage). À utiliser quand `search_plans` ne
    trouve pas de plan d'eau correspondant — par exemple pour une
    municipalité (Laterrière), un toponyme générique (rivière Saguenay à
    Chicoutimi), un secteur, etc.

    Renvoie `error` si la résolution échoue ; renvoie `geocoded` même quand
    la météo est trouvée, pour que l'agent cite la ville/coords retenues.
    """
    if not place or not place.strip():
        return {"error": "Lieu vide."}
    try:
        candidates = _geocode(place)
    except Exception as exc:  # noqa: BLE001
        return {"place": place, "error": f"Géocodage indisponible : {exc}"}
    if not candidates:
        return {
            "place": place,
            "error": "Lieu introuvable dans Nominatim (OpenStreetMap).",
        }
    best = candidates[0]
    weather = get_weather(best["lat"], best["lon"])
    return {
        "place": place,
        "geocoded": {
            "lat": best["lat"],
            "lon": best["lon"],
            "display_name": best["display_name"],
            "type": best["type"],
            "category": best["category"],
        },
        "geocoder": "Nominatim (OpenStreetMap)",
        **weather,
    }


# ---------- live : hydro ----------


@lru_cache(maxsize=1)
def _load_stations_cache() -> list[dict]:
    if not STATIONS_PATH.exists():
        return []
    return json.loads(STATIONS_PATH.read_text(encoding="utf-8")).get("stations", [])


def search_stations(query: str, limit: int = 8) -> list[dict]:
    """Recherche une station hydrométrique (Vigilance) par id, rivière ou
    description. Utile quand l'utilisateur cite un nom de rivière qui n'a pas
    de règles spécifiques dans RegPec mais a une station hydro (ex. Rivière
    Chicoutimi → station 061004).
    """
    stations = _load_stations_cache()
    hits = search_stations_offline(query, stations, limit=limit)
    return [
        {
            "station_id": s["station"],
            "plan_eau": s["plan_eau"],
            "description": s["description"],
            "lat": s["lat"],
            "lon": s["lon"],
            "score": s.get("score", 0.0),
            "fournisseur": s.get("fournisseur", ""),
        }
        for s in hits
    ]


def _build_station_links(station: dict) -> dict[str, str]:
    """Construit les URLs cliquables (CEHQ + Vigilance) pour une station."""
    links: dict[str, str] = {}
    sid = str(station.get("station", ""))
    if is_cehq_station_id(sid, station.get("fournisseur_url")):
        links.update(cehq_urls(sid))
    elif station.get("fournisseur_url"):
        links["cehq"] = station["fournisseur_url"]
    if station.get("url_vigilance"):
        links["vigilance"] = station["url_vigilance"]
    return links


def get_hydromet(station_id: str) -> dict:
    """Niveau / débit / état d'une station Vigilance précise.

    Renvoie aussi `urls` (CEHQ tableau / graphique) et `history` (~7 jours
    CEHQ) quand la station est suivie par le CEHQ.
    """
    s = get_live_station(str(station_id))
    if s is None:
        return {
            "station_id": str(station_id),
            "error": "Station introuvable.",
            "source": "Vigilance WFS",
        }
    sid = s["station"]
    out = {
        "station_id": sid,
        "plan_eau": s["plan_eau"],
        "description": s["description"],
        "lat": s["lat"],
        "lon": s["lon"],
        "etat": s["etat"],
        "niveau_m": s["niveau_m"],
        "debit_m3s": s["debit_m3s"],
        "observed_at": s["observed_at"],
        "urls": _build_station_links(s),
        "source": "Vigilance WFS",
    }
    if is_cehq_station_id(sid, s.get("fournisseur_url")):
        history = fetch_cehq_history(sid)
        if history:
            out["history"] = history
    return out


# ---------- qualité de l'eau (IQBP) ----------


def get_iqbp(query: str, limit: int = 5) -> list[dict]:
    """Indice IQBP (qualité d'eau MELCC) pour une rivière ou une station.

    Cherche par numéro BQMA, nom de rivière (`hydronyme`) ou description.
    L'IQBP est un indice annuel agrégé (mai-octobre) ; chaque résultat
    correspond au snapshot le plus récent disponible pour la station.
    """
    return _search_iqbp(query, limit=limit)


# ---------- marées (IWLS / SHC) ----------


def search_tide_stations(query: str, limit: int = 8) -> list[dict]:
    """Recherche une station de marées (code ou nom) — région Québec (SHC)."""
    return _search_tide_stations(query, limit=limit)


def get_tides(
    station_code: str,
    days: int = 7,
    date: str | None = None,
) -> dict:
    """Pleines et basses mers pour une station SHC (code 5 chiffres, ex. 03045).

    Hauteurs en mètres (zéro des cartes). `date` = début de fenêtre YYYY-MM-DD.
    """
    return _get_tide_predictions(station_code, days=days, start_date=date)


def get_tides_at_place(place: str, days: int = 7, date: str | None = None) -> dict:
    """Marées pour un lieu libre : géocodage OSM puis station SHC la plus proche."""
    if not place or not place.strip():
        return {"error": "Lieu vide."}
    place_norm = _normalize(place)
    try:
        candidates = _geocode(place)
    except Exception as exc:  # noqa: BLE001
        return {"place": place, "error": f"Géocodage indisponible : {exc}"}
    if not candidates:
        return {
            "place": place,
            "error": "Lieu introuvable dans Nominatim (OpenStreetMap).",
        }
    best = candidates[0]

    # Heuristique: certains libellés géocodés (ex. « Saguenay ») peuvent
    # pointer vers un arrondissement voisin (La Baie / Port-Alfred) alors que
    # l'utilisateur a demandé explicitement « Chicoutimi ».
    if "chicoutimi" in place_norm:
        near = {"station_code": "03480", "station_nom": "Chicoutimi"}
    else:
        near = _nearest_tide_station(best["lat"], best["lon"])
    if near is None:
        return {
            "place": place,
            "geocoded": {
                "lat": best["lat"],
                "lon": best["lon"],
                "display_name": best["display_name"],
            },
            "error_no_tide_station": (
                "Aucune station de marées SHC à moins de 75 km — "
                "les prédictions ne s'appliquent qu'aux eaux côtières / estuaire."
            ),
        }
    tides = get_tides(near["station_code"], days=days, date=date)
    return {
        "place": place,
        "geocoded": {
            "lat": best["lat"],
            "lon": best["lon"],
            "display_name": best["display_name"],
        },
        "matched_station": near,
        **tides,
    }


def get_water_levels(
    query: str,
    *,
    include_tide_schedule: bool = False,
    tide_days: int = 2,
) -> dict:
    """Niveau d'eau actuel : croise Vigilance (QC) et IWLS wlo (SHC).

    À utiliser pour « hauteur / niveau d'eau **maintenant** » sur une rivière
    ou un estuaire (ex. Chicoutimi, Saguenay). Les prédictions de marée
    (`get_tides`) ne remplacent pas le niveau observé.

    `query` : nom de rivière, ville, secteur ou id de station.
    `include_tide_schedule` : ajoute les horaires pleine/basse (sans les
    présenter comme niveau actuel).
    """
    if not query or not query.strip():
        return {"error": "Requête vide."}

    q = query.strip()
    # `search_stations` est volontairement permissif (utile en mode interactif),
    # mais ici la requête peut contenir beaucoup de mots (« hauteur eau ... »)
    # et polluer les résultats. On réduit donc à un "noyau" sémantique.
    q_norm = _normalize(q)
    core = None
    for kw in ("saguenay", "chicoutimi", "st-laurent", "saint-laurent"):
        if kw in q_norm:
            core = kw
            break
    core = core or q

    # On privilégie les stations dont `plan_eau` / `description` matchent
    # le mieux le texte utilisateur (sinon on peut ramasser des homonymes).
    vigilance_hits = search_stations(core, limit=8)
    vigilance_hits.sort(key=lambda s: float(s.get("score", 0.0)), reverse=True)
    vigilance_live: list[dict] = []
    for hit in vigilance_hits:
        try:
            live = get_hydromet(hit["station_id"])
        except Exception as exc:  # noqa: BLE001
            # Vigilance WFS peut être indisponible; on ne veut pas casser l'outil
            # si IWLS (SHC) est disponible.
            live = {"error": f"Vigilance indisponible: {exc}"}
        if "error" not in live:
            niveau_m = live.get("niveau_m")
            if isinstance(niveau_m, (int, float)):
                niveau_m = round(float(niveau_m), 2)
            vigilance_live.append(
                {
                    "station_id": live["station_id"],
                    "plan_eau": live.get("plan_eau"),
                    "description": live.get("description"),
                    "niveau_m": niveau_m,
                    "debit_m3s": live.get("debit_m3s"),
                    "etat": live.get("etat"),
                    "observed_at": live.get("observed_at"),
                    "urls": live.get("urls"),
                    "source": live.get("source"),
                    "score": hit.get("score"),
                }
            )
        if len(vigilance_live) >= 3:
            break

    iwls_live: dict | None = None
    shc_codes: list[str] = []
    for v in vigilance_live:
        sid = str(v.get("station_id", ""))
        if len(sid) == 5 and sid.isdigit():
            shc_codes.append(sid)
    # Si l'utilisateur cite explicitement un lieu, on priorise ce code.
    # (Ex. « Chicoutimi » → station SHC 03480 quand disponible.)
    if shc_codes:
        preferred = None
        if "chicoutimi" in q_norm and "03480" in shc_codes:
            preferred = "03480"
        if preferred:
            shc_codes = [preferred] + [c for c in shc_codes if c != preferred]
    if not shc_codes:
        for hit in _search_tide_stations(q, limit=2):
            shc_codes.append(hit["station_code"])
    for code in shc_codes:
        live = _get_water_level_live(code)
        if "error" not in live:
            if isinstance(live.get("niveau_m"), (int, float)):
                live["niveau_m"] = round(float(live["niveau_m"]), 2)
            iwls_live = live
            break
        if iwls_live is None:
            if isinstance(live.get("niveau_m"), (int, float)):
                live["niveau_m"] = round(float(live["niveau_m"]), 2)
            iwls_live = live

    marees: dict | None = None
    if include_tide_schedule and shc_codes:
        marees = get_tides(shc_codes[0], days=tide_days)

    out: dict = {
        "query": q,
        "vigilance": vigilance_live,
        "iwls": iwls_live,
        "note": (
            "Niveau actuel = Vigilance et/ou IWLS wlo (observations). "
            "Les hauteurs dans « marees » sont des prédictions de pleines/basses "
            "mers, pas le niveau instantané."
        ),
    }
    if not vigilance_live and (iwls_live is None or iwls_live.get("error")):
        out["error"] = (
            "Aucune station Vigilance ni observation IWLS trouvée pour cette requête."
        )
    if marees is not None:
        out["marees_horaires"] = marees
    return out


def get_tides_at_plan(
    plan_id: int,
    zone_id: int,
    days: int = 7,
    date: str | None = None,
) -> dict:
    """Marées pour un plan d'eau — station SHC la plus proche (≤ 75 km)."""
    loc = _find_location(zone_id, plan_id)
    if loc is None:
        return {"error": f"Plan {plan_id} introuvable dans zone {zone_id}."}
    if loc["lat"] is None or loc["lon"] is None:
        return {
            "plan_id": plan_id,
            "zone_id": zone_id,
            "plan_nom": loc["nom"],
            "error": "Coordonnées non disponibles pour ce plan d'eau.",
        }
    near = _nearest_tide_station(loc["lat"], loc["lon"])
    if near is None:
        return {
            "plan_id": plan_id,
            "zone_id": zone_id,
            "plan_nom": loc["nom"],
            "plan_lat": loc["lat"],
            "plan_lon": loc["lon"],
            "error_no_tide_station": (
                "Aucune station de marées SHC à moins de 75 km — "
                "ce plan est probablement en eau intérieure (pas de marée mesurable)."
            ),
        }
    tides = get_tides(near["station_code"], days=days, date=date)
    return {
        "plan_id": plan_id,
        "zone_id": zone_id,
        "plan_nom": loc["nom"],
        "plan_lat": loc["lat"],
        "plan_lon": loc["lon"],
        "matched_station": near,
        **tides,
    }


def get_fishing_advice(
    species: str,
    *,
    question: str | None = None,
    location: str | None = None,
    conditions: dict | None = None,
) -> dict:
    """Conseils de pêche (leurres, techniques) via le sous-agent expert.

    `conditions` regroupe le contexte déjà collecté (météo, hydro, engins
    autorisés, type d'eau, etc.) — l'agent principal doit le remplir après
    les appels pertinents.
    """
    from peche.agent.fishing_expert import advise

    advice = advise(
        species,
        question=question,
        location=location,
        conditions=conditions,
    )
    return {
        "species": species,
        "location": location,
        "advice": advice,
        "source": "fishing_expert",
    }


def _match_station_list(match: dict) -> list[dict]:
    """Liste des stations pré-matchées (schéma multi ou legacy)."""
    if match.get("stations"):
        return list(match["stations"])
    legacy = match.get("station")
    if legacy:
        return [legacy]
    return []


def _filter_stations_by_metrics(
    stations: list[dict], metrics: str
) -> list[dict]:
    if metrics == "both":
        return stations
    if metrics == "flow":
        return [s for s in stations if s.get("role") in ("flow", "both", None)]
    # level (défaut) : stations de niveau ; garde « both » si seule option geo
    level_stations = [s for s in stations if s.get("role") in ("level", "both", None)]
    return level_stations or stations


def get_hydromet_for_waterbody(
    plan_id: int,
    zone_id: int,
    metrics: str = "level",
    include_history: bool = True,
) -> dict:
    """Hydro pour un plan d'eau — toutes les stations matchées (nom + geo).

    `metrics` : `level` (niveau seul, défaut), `flow` (débit), `both`.
    Retourne une entrée par station avec live (+ history CEHQ si demandé).
    """
    if metrics not in ("level", "flow", "both"):
        metrics = "level"

    match = _find_match(zone_id, plan_id)
    if match is None:
        return {
            "plan_id": plan_id,
            "zone_id": zone_id,
            "error": "Aucun matching offline pour ce plan (coords manquantes ?).",
        }

    plan_nom = match.get("plan_nom", "")
    station_meta = _filter_stations_by_metrics(_match_station_list(match), metrics)
    if not station_meta:
        return {
            "plan_id": plan_id,
            "zone_id": zone_id,
            "plan_nom": plan_nom,
            "requested_metrics": metrics,
            "error_no_station": "Aucune station hydro à moins de 25 km.",
        }

    stations_out: list[dict] = []
    for meta in station_meta:
        sid = meta.get("id") or meta.get("station")
        if not sid:
            continue
        live = get_hydromet(str(sid))
        if "error" in live:
            stations_out.append(
                {
                    "station_id": str(sid),
                    "description": meta.get("description", ""),
                    "plan_eau": meta.get("plan_eau", ""),
                    "distance_km": meta.get("distance_km"),
                    "match_reason": meta.get("match_reason", "geo"),
                    "role": meta.get("role"),
                    "error": live["error"],
                }
            )
            continue
        entry: dict = {
            "station_id": live["station_id"],
            "description": live.get("description") or meta.get("description", ""),
            "plan_eau": live.get("plan_eau") or meta.get("plan_eau", ""),
            "distance_km": meta.get("distance_km"),
            "match_reason": meta.get("match_reason", "geo"),
            "role": meta.get("role"),
            "niveau_m": live.get("niveau_m"),
            "debit_m3s": live.get("debit_m3s"),
            "etat": live.get("etat"),
            "observed_at": live.get("observed_at"),
            "urls": live.get("urls"),
            "source": live.get("source"),
        }
        if include_history and live.get("history"):
            entry["history"] = live["history"]
        stations_out.append(entry)

    primary_id = match.get("primary_station_id") or (
        station_meta[0].get("id") or station_meta[0].get("station")
    )
    return {
        "plan_id": plan_id,
        "zone_id": zone_id,
        "plan_nom": plan_nom,
        "requested_metrics": metrics,
        "primary_station_id": primary_id,
        "stations": stations_out,
        "station_count": len(stations_out),
    }


def get_hydromet_at_plan(plan_id: int, zone_id: int) -> dict:
    """Hydro live pour un plan d'eau — station primaire (rétrocompat).

    Préférer `get_hydromet_for_waterbody` pour obtenir toutes les stations.
    """
    match = _find_match(zone_id, plan_id)
    if match is None:
        return {
            "plan_id": plan_id,
            "zone_id": zone_id,
            "error": "Aucun matching offline pour ce plan (coords manquantes ?).",
        }
    station_meta = _match_station_list(match)
    if not station_meta:
        return {
            "plan_id": plan_id,
            "zone_id": zone_id,
            "plan_nom": match.get("plan_nom", ""),
            "error_no_station": "Aucune station hydro à moins de 25 km.",
        }
    station = station_meta[0]
    sid = station.get("id") or station.get("station")
    live = get_hydromet(str(sid))
    if "error" in live:
        return {**live, "plan_id": plan_id, "zone_id": zone_id}
    return {
        "plan_id": plan_id,
        "zone_id": zone_id,
        "plan_nom": match.get("plan_nom", ""),
        "distance_km": station.get("distance_km"),
        "matched_station_plan_eau": station.get("plan_eau"),
        **live,
    }


def search_barrages(query: str, limit: int = 8) -> list[dict]:
    """Recherche dans le répertoire CEHQ des barrages (nom, cours d'eau, numéro)."""
    return _search_barrages_offline(query, limit=limit)


def get_barrages_at_plan(
    plan_id: int,
    zone_id: int,
    radius_km: float = _BARRAGE_RADIUS_KM,
) -> dict:
    """Barrages CEHQ à ≤10 km d'un plan d'eau RegPec."""
    zerr = _zone_error(zone_id)
    if zerr:
        return zerr
    loc = _find_location(zone_id, plan_id)
    if loc is None:
        return {"error": f"Plan {plan_id} introuvable dans zone {zone_id}."}
    if loc.get("lat") is None or loc.get("lon") is None:
        return {
            "plan_id": plan_id,
            "zone_id": zone_id,
            "plan_nom": loc.get("nom"),
            "error": "Coordonnées non disponibles pour ce plan d'eau.",
        }
    return _barrages_near_response(
        lat=float(loc["lat"]),
        lon=float(loc["lon"]),
        label=loc.get("nom") or "plan",
        radius_km=radius_km,
        extra={
            "plan_id": plan_id,
            "zone_id": zone_id,
            "plan_nom": loc.get("nom"),
        },
    )


def get_barrages_at_place(place: str, radius_km: float = _BARRAGE_RADIUS_KM) -> dict:
    """Barrages CEHQ à ≤10 km d'un lieu libre (géocodage)."""
    hits = _geocode(place, limit=1)
    if not hits:
        return {"place": place, "error": f"Lieu introuvable : {place!r}."}
    best = hits[0]
    if best.get("lat") is None or best.get("lon") is None:
        return {"place": place, "error": "Géocodage sans coordonnées."}
    return _barrages_near_response(
        lat=float(best["lat"]),
        lon=float(best["lon"]),
        label=best.get("label") or place,
        radius_km=radius_km,
        extra={"place": place, "geocoded_label": best.get("label")},
    )


def get_map_context(
    zone_id: int,
    plan_id: int,
    *,
    bbox: list[float] | None = None,
    zoom: int = 11,
) -> dict:
    """Contexte spatial pour la carte : LCE, bassin, segments DMS, règlements."""
    from peche.spatial.reg_link import get_match
    from peche.spatial.viewport import basin_level_for_zoom, features_in_bbox, layers_for_zoom

    zerr = _zone_error(zone_id)
    if zerr:
        return zerr
    loc = _find_location(zone_id, plan_id)
    if loc is None:
        return {"error": f"Plan {plan_id} introuvable dans zone {zone_id}."}

    lat, lon = loc.get("lat"), loc.get("lon")
    if bbox is None and lat is not None and lon is not None:
        delta = max(0.05, 2.0 / (2 ** (zoom / 2)))
        bbox = [lon - delta, lat - delta, lon + delta, lat + delta]
    query_bbox = tuple(bbox) if bbox and len(bbox) == 4 else (0, 0, 0, 0)

    spatial = get_match(zone_id, plan_id) or {}
    lce_near = features_in_bbox("lce", query_bbox, zoom) if query_bbox != (0, 0, 0, 0) else []
    basins_near = (
        features_in_bbox("bassins", query_bbox, zoom) if query_bbox != (0, 0, 0, 0) else []
    )

    reg = get_reglements(zone_id, plan_id, only_in_effect=True)
    reg_especes: list[str] = []
    if not reg.get("error"):
        for block in reg.get("reglements") or []:
            for per in block.get("periodes") or []:
                for esp in per.get("especes") or []:
                    name = esp.get("espece")
                    if name and name not in reg_especes:
                        reg_especes.append(name)

    return {
        "zone_id": zone_id,
        "plan_id": plan_id,
        "plan_nom": loc.get("nom"),
        "plan_lat": lat,
        "plan_lon": lon,
        "lce_match": spatial.get("lce"),
        "segment_points": spatial.get("segment_points") or [],
        "lce_in_viewport": len(lce_near),
        "basins_in_viewport": len(basins_near),
        "basin_level": basin_level_for_zoom(zoom),
        "active_layers": layers_for_zoom(zoom),
        "reg_especes_en_vigueur": reg_especes[:12],
        "bbox": bbox,
        "zoom": zoom,
    }
