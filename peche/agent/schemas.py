"""Schémas JSON des outils exposés au LLM.

Les outils sont **granulaires** : un appel par intention. Pas d'outil composite.
Le modèle doit choisir précisément ce qu'il appelle en fonction de la question
(météo seule / règlements seuls / hydro seule).
"""

from __future__ import annotations

from peche import tools

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "list_zones",
        "description": (
            "Liste les 34 zones de pêche du Québec avec leur saison et leur "
            "nombre de plans d'eau réglementés. À utiliser uniquement quand "
            "l'utilisateur demande la liste des zones."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "search_plans",
        "description": (
            "Recherche fuzzy d'un plan d'eau (lac, rivière, ruisseau...). "
            "À appeler dès qu'un nom de plan d'eau est mentionné. Renvoie "
            "`candidates` (jusqu'à 8, triés par score) et `groups` si "
            "plusieurs segments d'une même rivière (ex. Sainte-Marguerite "
            "a)…e)). Comprend Ste/Sainte, accents, tirets. Si plusieurs "
            "segments et requête non segmentée, lister tous les segments."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Nom (partiel) du plan d'eau.",
                },
                "zone_id": {
                    "type": "integer",
                    "description": "Optionnel — restreindre à une zone.",
                },
                "limit": {"type": "integer"},
                "group_segments": {
                    "type": "boolean",
                    "description": "Regrouper les segments d'une rivière (défaut true).",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_reglements",
        "description": (
            "Règlements (espèces, limites, longueurs, engins, périodes) pour "
            "une zone et optionnellement un plan d'eau. À appeler UNIQUEMENT "
            "quand l'utilisateur demande la réglementation. "
            "**Mettre `only_in_effect=true` par défaut** pour ne renvoyer que "
            "les périodes en vigueur à `date` (défaut = aujourd'hui). "
            "Mettre `false` seulement si l'utilisateur demande explicitement "
            "toutes les saisons."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "zone_id": {"type": "integer"},
                "plan_id": {
                    "type": "integer",
                    "description": "Issu de search_plans (optionnel).",
                },
                "only_in_effect": {
                    "type": "boolean",
                    "description": "Filtrer aux périodes incluant `date`.",
                },
                "date": {
                    "type": "string",
                    "description": "ISO YYYY-MM-DD ; défaut = aujourd'hui.",
                },
            },
            "required": ["zone_id"],
        },
    },
    {
        "name": "get_weather",
        "description": (
            "Météo live + courte prévision pour des coordonnées WGS84 "
            "arbitraires (GeoMet). À utiliser quand on a déjà des coords "
            "(ex. fournies par l'utilisateur). Sinon préférer "
            "`get_weather_at_plan`."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "lat": {"type": "number"},
                "lon": {"type": "number"},
            },
            "required": ["lat", "lon"],
        },
    },
    {
        "name": "get_weather_at_plan",
        "description": (
            "Météo live pour un plan d'eau identifié (résout les coordonnées). "
            "À appeler UNIQUEMENT quand l'utilisateur demande la météo / les "
            "conditions / la pluie / la température. Renvoie une erreur "
            "explicite si le plan n'est pas géolocalisé."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "integer"},
                "zone_id": {"type": "integer"},
            },
            "required": ["plan_id", "zone_id"],
        },
    },
    {
        "name": "get_weather_at_place",
        "description": (
            "Météo pour un nom de lieu **libre** (ville, village, secteur, "
            "rivière, point d'intérêt). Géocode via OpenStreetMap puis "
            "interroge GeoMet. À utiliser quand `search_plans` n'a pas de "
            "résultat ou quand l'utilisateur cite un endroit qui n'est pas "
            "un plan d'eau RegPec (ex. « Laterrière », « Chicoutimi »)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "place": {
                    "type": "string",
                    "description": "Nom du lieu à géocoder (FR ou EN).",
                },
            },
            "required": ["place"],
        },
    },
    {
        "name": "search_stations",
        "description": (
            "Recherche une station hydrométrique (Vigilance/CEHQ) par id, "
            "rivière ou description. **À utiliser quand l'utilisateur cite "
            "un nom de rivière** (ex. « rivière Chicoutimi », « rivière des "
            "Outaouais ») et que `search_plans` ne renvoie rien d'utile : "
            "ces rivières n'ont souvent pas de règle spécifique dans RegPec "
            "mais sont suivies par une station hydro."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Nom (partiel) de rivière, id de station, ou description.",
                },
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_hydromet",
        "description": (
            "Niveau / débit / état d'une station Vigilance précise (id de "
            "station). Pour les stations CEHQ, inclut aussi `history` : "
            "évolution sur ~7 jours (résumé journalier + tendance). Renvoie "
            "`urls.cehq`, `urls.cehq_tableau`, `urls.vigilance` — liens "
            "cliquables. Le `plan_eau` retourné est celui de la station — il "
            "peut différer du lac visé."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "station_id": {"type": "string"},
            },
            "required": ["station_id"],
        },
    },
    {
        "name": "get_iqbp",
        "description": (
            "Qualité d'eau IQBP (MELCC) pour une rivière ou station par "
            "numéro BQMA, nom (`hydronyme`) ou description. **Indice "
            "annuel** (mai-octobre, dernier snapshot disponible — pas du "
            "temps réel). À utiliser quand l'utilisateur demande la qualité "
            "de l'eau, la pollution, les coliformes, le phosphore, les "
            "nitrates, etc. Renvoie aussi `urls.atlas_eau` et "
            "`urls.donnees_quebec` cliquables."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_hydromet_for_waterbody",
        "description": (
            "Hydro pour un plan d'eau RegPec — **toutes** les stations "
            "matchées (ex. plusieurs barrages sur un lac). À préférer à "
            "`get_hydromet_at_plan` quand l'utilisateur demande le niveau "
            "ou le débit d'un lac / rivière identifié par `search_plans`. "
            "`metrics` : `level` (niveau seul, défaut), `flow` (débit), "
            "`both`. Ne mentionne pas le débit si `metrics=level`."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "integer"},
                "zone_id": {"type": "integer"},
                "metrics": {
                    "type": "string",
                    "enum": ["level", "flow", "both"],
                    "description": "Métrique demandée (défaut level).",
                },
                "include_history": {
                    "type": "boolean",
                    "description": "Inclure l'historique CEHQ ~7 jours.",
                },
            },
            "required": ["plan_id", "zone_id"],
        },
    },
    {
        "name": "get_hydromet_at_plan",
        "description": (
            "Hydro live pour un plan d'eau (station primaire seulement). "
            "Préférer `get_hydromet_for_waterbody` pour les lacs avec "
            "plusieurs stations. Si aucune station n'est à portée, retourne "
            "`error_no_station`."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "integer"},
                "zone_id": {"type": "integer"},
            },
            "required": ["plan_id", "zone_id"],
        },
    },
    {
        "name": "search_tide_stations",
        "description": (
            "Recherche une station marégraphique du SHC (Service hydrographique "
            "du Canada) par code à 5 chiffres ou par nom (ex. Rimouski, "
            "Pointe-au-Pic). À utiliser quand l'utilisateur cite un port / "
            "secteur côtier ou demande quelle station utiliser."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Code station ou nom (partiel).",
                },
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_tides",
        "description": (
            "Heures et hauteurs des **pleines et basses mers** (prédictions "
            "officielles IWLS/SHC). À appeler quand l'utilisateur demande les "
            "marées, l'heure de marée haute/basse, ou la hauteur d'eau au "
            "port. `station_code` = code 5 chiffres (issu de "
            "`search_tide_stations` ou de la question). Hauteurs en mètres "
            "(zéro des cartes). Inclure `urls.marees_gc_ca` dans la réponse."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "station_code": {
                    "type": "string",
                    "description": "Code SHC, ex. 03045.",
                },
                "days": {
                    "type": "integer",
                    "description": "Nombre de jours (1–31, défaut 7).",
                },
                "date": {
                    "type": "string",
                    "description": "Date de début YYYY-MM-DD (défaut = aujourd'hui).",
                },
            },
            "required": ["station_code"],
        },
    },
    {
        "name": "get_water_levels",
        "description": (
            "Niveau d'eau **actuel** : combine (1) Vigilance (QC, rivières) et "
            "(2) IWLS/SHC `wlo` (observations temps réel) quand disponible. "
            "À utiliser pour une question du type « hauteur/niveau d'eau "
            "maintenant à Chicoutimi sur la rivière Saguenay » afin de mettre "
            "en perspective le niveau observé (temps réel) avec, optionnellement, "
            "les horaires de marée (pleine/basse) si demandé. "
            "Ne pas confondre avec `get_tides` qui renvoie des prédictions "
            "d'extrema (pas le niveau instantané)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "include_tide_schedule": {"type": "boolean"},
                "tide_days": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_tides_at_place",
        "description": (
            "Marées pour un **lieu libre** (ville, secteur, embouchure). "
            "Géocode puis choisit la station SHC la plus proche (≤ 75 km). "
            "Si `error_no_tide_station`, le lieu est trop loin de la côte — "
            "l'annoncer clairement (pas de marée en eau intérieure)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "place": {"type": "string"},
                "days": {"type": "integer"},
                "date": {"type": "string"},
            },
            "required": ["place"],
        },
    },
    {
        "name": "get_tides_at_plan",
        "description": (
            "Marées pour un plan d'eau RegPec (coords du plan → station SHC "
            "la plus proche). À utiliser après `search_plans` quand l'utilisateur "
            "demande les marées pour un lac / rivière côtier identifié."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "integer"},
                "zone_id": {"type": "integer"},
                "days": {"type": "integer"},
                "date": {"type": "string"},
            },
            "required": ["plan_id", "zone_id"],
        },
    },
    {
        "name": "search_barrages",
        "description": (
            "Recherche un barrage dans le **répertoire CEHQ** (~6000 ouvrages) "
            "par nom, cours d'eau ou numéro (ex. Kénogami, Portage-des-Roches, "
            "X0000899). À utiliser pour identifier un ouvrage précis."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_barrages_at_plan",
        "description": (
            "Barrages du répertoire CEHQ à **≤10 km** d'un plan d'eau RegPec. "
            "À appeler quand l'utilisateur demande s'il y a un barrage, une "
            "retenue ou une structure près d'un lac/rivière identifié — "
            "utile pour repérer des zones où les poissons peuvent se "
            "concentrer (bord de barrage, déversoir, fosse d'aval). "
            "Ne pas confondre avec l'hydro Vigilance (`get_hydromet_*`)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "integer"},
                "zone_id": {"type": "integer"},
                "radius_km": {
                    "type": "number",
                    "description": "Rayon max 10 km (défaut 10).",
                },
            },
            "required": ["plan_id", "zone_id"],
        },
    },
    {
        "name": "get_barrages_at_place",
        "description": (
            "Barrages CEHQ à **≤10 km** d'un lieu libre (ville, secteur). "
            "Même usage que `get_barrages_at_plan` quand le lieu n'est pas "
            "encore résolu via `search_plans`."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "place": {"type": "string"},
                "radius_km": {
                    "type": "number",
                    "description": "Rayon max 10 km (défaut 10).",
                },
            },
            "required": ["place"],
        },
    },
    {
        "name": "get_map_context",
        "description": (
            "Contexte spatial d'un plan d'eau : match LCE, bassin hydrographique, "
            "segments DMS, espèces en vigueur. À appeler pour questions carte, "
            "localisation ou lien règlements ↔ milieu aquatique."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "zone_id": {"type": "integer"},
                "plan_id": {"type": "integer"},
                "bbox": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "[lon_min, lat_min, lon_max, lat_max] optionnel.",
                },
                "zoom": {"type": "integer", "description": "Niveau de zoom carte (défaut 11)."},
            },
            "required": ["zone_id", "plan_id"],
        },
    },
    {
        "name": "get_fishing_advice",
        "description": (
            "Conseils de pêche (leurres, techniques, profondeur, horaires) "
            "adaptés aux conditions. À appeler quand l'utilisateur demande "
            "des conseils techniques, le choix de leurres, la stratégie de "
            "pêche, etc. **Avant** d'appeler : collecte le contexte utile "
            "(météo, hydro, engins autorisés) si un lieu ou plan d'eau est "
            "mentionné ou déductible ; sinon appelle quand même avec l'espèce "
            "et la saison. Passe les données brutes dans `conditions`."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "species": {
                    "type": "string",
                    "description": "Espèce ciblée (ex. truite mouchetée).",
                },
                "question": {
                    "type": "string",
                    "description": "Question ou demande précise de l'utilisateur.",
                },
                "location": {
                    "type": "string",
                    "description": "Lieu, plan d'eau ou secteur (optionnel).",
                },
                "conditions": {
                    "type": "object",
                    "description": (
                        "Contexte structuré issu des outils déjà appelés : "
                        "clés suggérées `weather`, `hydromet`, `water_type` "
                        "(lac/rivière), `plan_nom`, `allowed_gear` (engins "
                        "RegPec), `notes`."
                    ),
                },
            },
            "required": ["species"],
        },
    },
    {
        "name": "set_map_view",
        "description": (
            "Centre / zoom / bbox de la carte interactive. "
            "center = [lon, lat], bbox = [lon_min, lat_min, lon_max, lat_max]."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "center": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "[lon, lat]",
                },
                "zoom": {"type": "number"},
                "bbox": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "[lon_min, lat_min, lon_max, lat_max]",
                },
            },
            "required": [],
        },
    },
    {
        "name": "toggle_layers",
        "description": (
            "Affiche (show) ou masque (hide) des couches par id catalogue "
            "(ex. lidar_pentes, vigilance_stations, zones_chasse, aq_reseau). "
            "opacity optionnel : {layer_id: 0..1}."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "show": {"type": "array", "items": {"type": "string"}},
                "hide": {"type": "array", "items": {"type": "string"}},
                "opacity": {"type": "object"},
            },
            "required": [],
        },
    },
    {
        "name": "set_layer_filter",
        "description": (
            "Filtre une couche. Ex. zones_chasse → filters={No_zone:'18'}; "
            "barrages_cehq → filters={categorie:['Petit barrage']}."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "layer_id": {"type": "string"},
                "filters": {"type": "object"},
            },
            "required": ["layer_id"],
        },
    },
    {
        "name": "filter_by_zone",
        "description": (
            "Clippe toutes les couches visibles à une zone de pêche RegPec "
            "(zone_id). clear=true pour retirer le filtre."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "zone_id": {"type": "integer"},
                "clear": {"type": "boolean"},
            },
            "required": [],
        },
    },
    {
        "name": "highlight_features",
        "description": "Surligne des features sur la carte (ids ou geojson).",
        "parameters": {
            "type": "object",
            "properties": {
                "layer_id": {"type": "string"},
                "feature_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "geojson": {"type": "object"},
            },
            "required": ["layer_id"],
        },
    },
    {
        "name": "get_point_info",
        "description": (
            "Contexte d'un point utilisateur sur la carte : zone de pêche, "
            "exception RegPec, lac/rivière (GRHQ), territoire faunique (TFS), "
            "chasse interdite. Utiliser pin_number (Point 1, Point 2…) depuis "
            "MapState.pins, ou lon+lat."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pin_number": {
                    "type": "integer",
                    "description": "Numéro du point (1, 2, 3…)",
                },
                "lon": {"type": "number"},
                "lat": {"type": "number"},
            },
            "required": [],
        },
    },
]


from peche.agent import map_tools as _map_tools

TOOLS = {
    "list_zones": lambda **_: tools.list_zones(),
    "search_plans": lambda **kw: tools.search_plans(**kw),
    "get_reglements": lambda **kw: tools.get_reglements(**kw),
    "get_weather": lambda **kw: tools.get_weather(**kw),
    "get_weather_at_plan": lambda **kw: tools.get_weather_at_plan(**kw),
    "get_weather_at_place": lambda **kw: tools.get_weather_at_place(**kw),
    "search_stations": lambda **kw: tools.search_stations(**kw),
    "get_hydromet": lambda **kw: tools.get_hydromet(**kw),
    "get_hydromet_for_waterbody": lambda **kw: tools.get_hydromet_for_waterbody(**kw),
    "get_hydromet_at_plan": lambda **kw: tools.get_hydromet_at_plan(**kw),
    "get_iqbp": lambda **kw: tools.get_iqbp(**kw),
    "search_tide_stations": lambda **kw: tools.search_tide_stations(**kw),
    "get_tides": lambda **kw: tools.get_tides(**kw),
    "get_tides_at_place": lambda **kw: tools.get_tides_at_place(**kw),
    "get_tides_at_plan": lambda **kw: tools.get_tides_at_plan(**kw),
    "get_water_levels": lambda **kw: tools.get_water_levels(**kw),
    "search_barrages": lambda **kw: tools.search_barrages(**kw),
    "get_barrages_at_plan": lambda **kw: tools.get_barrages_at_plan(**kw),
    "get_barrages_at_place": lambda **kw: tools.get_barrages_at_place(**kw),
    "get_fishing_advice": lambda **kw: tools.get_fishing_advice(**kw),
    "get_map_context": lambda **kw: tools.get_map_context(**kw),
    "set_map_view": lambda **kw: _map_tools.set_map_view(**kw),
    "toggle_layers": lambda **kw: _map_tools.toggle_layers(**kw),
    "set_layer_filter": lambda **kw: _map_tools.set_layer_filter(**kw),
    "filter_by_zone": lambda **kw: _map_tools.filter_by_zone(**kw),
    "highlight_features": lambda **kw: _map_tools.highlight_features(**kw),
    "get_point_info": lambda **kw: _map_tools.get_point_info(**kw),
}
