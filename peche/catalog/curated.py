"""Couches curées fishing-first — filtres, couleurs, légendes."""

from __future__ import annotations

from peche.catalog.models import FilterSpec, LayerDef

MFFP = "https://geoegl.msp.gouv.qc.ca/ws/mffpecofor.fcgi"
ENV_WSS = "https://geoegl.msp.gouv.qc.ca/apis/wss/environnement.fcgi"
SMARTFAUNE = "https://servicesvecto3.mern.gouv.qc.ca/geoserver/SmartFaunePub/ows"
FORET_PUB = "https://servicesvecto3.mern.gouv.qc.ca/geoserver/ForetOuvertePub/ows"
# (id stable envoyé par le client, valeur réelle de SmartFaunePub:TFS.DESCRIPTION)
TFS_TYPES = (
    ("pourvoirie", "Pourvoirie avec droits exclusifs"),
    ("zec_saumon", "ZEC pêche saumon"),
    ("zec", "ZEC"),
    ("petit_lac", "Petit lac aménagé"),
    ("reserve", "Réserve faunique"),
    ("aire_communautaire", "Aire faunique communautaire"),
    ("reserve_saumon", "Réserve faunique rivière à saumon"),
    ("entente_autochtone", "Entente particulière autochtone"),
    ("zec_sauvagine", "ZEC chasse sauvagine"),
)
THEMES = (
    "https://www.servicesgeo.enviroweb.gouv.qc.ca/donnees/services/Public/"
    "Themes_publics/MapServer/WMSServer"
)
MH = (
    "https://geo.environnement.gouv.qc.ca/donnees/services/Biodiversite/"
    "MH_potentiels/MapServer/WMSServer"
)
GRHQ_WMS = (
    "https://servicescarto.mrnf.gouv.qc.ca/pes/services/Territoire/"
    "GRHQ_WMS/MapServer/WMSServer"
)
STF_WMS = "https://servicescarto.mrnf.gouv.qc.ca/pes/services/Forets/STF_WMS/MapServer/WMSServer"
AQRESEAU = (
    "https://servicescarto.mrnf.gouv.qc.ca/pes/services/Territoire/"
    "AQreseauPlus_WMS/MapServer/WMSServer"
)

# Autoroute → nationale → régionale → collectrice → locale → autre.
AQ_ROADS = "56,57,58,59,48,49,50,51,41,42,43,33,34,35,36,21,22,23,17,18"
# Accès ressources + chemins multiusages (classes / carrossable).
AQ_FOREST = "27,28,86,85,74,75,71,72,77,78"

BARRAGE_CATEGORIES = [
    {"value": "Faible contenance", "label": "Faible contenance"},
    {"value": "Petit barrage", "label": "Petit barrage"},
    {"value": "Forte contenance", "label": "Forte contenance"},
    {"value": "Forte contenance (parent)", "label": "Forte contenance (parent)"},
    {"value": "Faible contenance (parent)", "label": "Faible contenance (parent)"},
    {"value": "Petit barrage (parent)", "label": "Petit barrage (parent)"},
]


def _legend(url: str, layer: str) -> str:
    # MapServer exige sld_version=1.1.0 pour GetLegendGraphic.
    return (
        f"{url}?version=1.3.0&service=WMS&request=GetLegendGraphic"
        f"&sld_version=1.1.0&layer={layer}&format=image/png&STYLE=default"
    )


def curated_layers() -> list[LayerDef]:
    layers: list[LayerDef] = [
        # --- Réglementation pêche ---
        # Même géométrie que « zones de chasse » ; No_zone = numéro affiché (28).
        LayerDef(
            id="zones_chasse",
            title="Zones de pêche",
            group="reglementation",
            source_type="local",
            url="data/spatial/zones_peche.geojson",
            curated=True,
            filter_spec=FilterSpec(
                kind="local",
                attr="No_zone",
                multi=False,
            ),
            visible_default=True,
            opacity=1.0,
            color="#14609d",
            attribution="MFFP SmartFaune / RegPec",
            extra={"outline": True},
        ),
        LayerDef(
            id="plans_regpec",
            title="Plans d'eau réglementés",
            group="reglementation",
            source_type="local",
            url="data/locations",
            curated=True,
            filter_spec=FilterSpec(kind="local", attr="zone_id"),
            min_zoom=8,
            visible_default=True,
            color="#f59e0b",
            attribution="RegPec — Plans d'eau exceptions (carte interactive)",
        ),
        # --- Faune ---
        LayerDef(
            id="tfs",
            title="Territoires fauniques structurés (ZEC, pourvoiries…)",
            group="faune",
            source_type="local",
            url="data/spatial/tfs.geojson",  # snapshot : python3 -m peche.spatial tfs-sync
            curated=True,
            filter_spec=FilterSpec(
                kind="local",
                attr="DESCRIPTION",
                options=[{"value": vid, "label": desc, "match": desc} for vid, desc in TFS_TYPES],
            ),
            color="#16a34a",
            attribution="MFFP SmartFaune",
        ),
        LayerDef(
            id="chasse_interdite",
            title="Chasse/Pêche interdite",
            group="faune",
            source_type="wfs",
            url=SMARTFAUNE,
            layer_name="SmartFaunePub:Chasse_Interdite",
            curated=True,
            filter_spec=FilterSpec(kind="cql"),
            color="#ef4444",
            attribution="MFFP SmartFaune",
            extra={"no_color": True},
        ),
        LayerDef(
            id="stations_lavage",
            title="Stations de nettoyage d'embarcations",
            group="faune",
            source_type="wfs",
            url=FORET_PUB,
            layer_name="ForetOuvertePub:stations_lavages_qc",
            curated=True,
            filter_spec=FilterSpec(kind="cql"),
            color="#06b6d4",
            attribution="MFFP",
        ),
        # --- Hydro temps réel ---
        LayerDef(
            id="vigilance_stations",
            title="Stations hydrométriques (Vigilance / Hydro-Québec)",
            group="hydro_temps_reel",
            source_type="local",
            url="data/hydromet/stations.json",
            curated=True,
            filter_spec=FilterSpec(kind="none"),
            visible_default=True,
            color="#3b82f6",
            attribution="MSP Vigilance; données ouvertes Hydro-Québec",
            extra={"etat_colors": True},
        ),
        LayerDef(
            id="marees_shc",
            title="Stations marégraphiques SHC",
            group="hydro_temps_reel",
            source_type="local",
            url="data/tides/stations.json",
            curated=True,
            filter_spec=FilterSpec(kind="local"),
            color="#6366f1",
            attribution="SHC / IWLS",
        ),
        LayerDef(
            id="meteo_eccc",
            title="Météo ECCC (villes GeoMet, Québec)",
            group="hydro_temps_reel",
            source_type="local",
            url="data/weather/cities.json",
            curated=True,
            filter_spec=FilterSpec(kind="local"),
            color="#fb7185",
            attribution="Environnement et Changement climatique Canada — GeoMet",
            extra={"proxy": False},
        ),
        # --- Hydrographie ---
        LayerDef(
            id="barrages_cehq",
            title="Barrages CEHQ",
            group="hydrographie",
            source_type="local",
            url="data/barrages/barrages.json",
            curated=True,
            filter_spec=FilterSpec(
                kind="local",
                attr="categorie",
                options=BARRAGE_CATEGORIES,
                multi=True,
            ),
            min_zoom=9,
            color="#9a3412",
            attribution="CEHQ",
        ),
        LayerDef(
            id="grhq_lin_perm",
            title="GRHQ — réseau linéaire permanent",
            group="hydrographie",
            source_type="wms",
            url=ENV_WSS,
            layer_name="GRHQ_RES_LIN_PERM",
            curated=True,
            filter_spec=FilterSpec(kind="none"),
            legend_url=_legend(ENV_WSS, "GRHQ_RES_LIN_PERM"),
            min_zoom=8,
            color="#2563eb",
            attribution="MELCCFP GRHQ",
            extra={"proxy": True},
        ),
        LayerDef(
            id="grhq_surf",
            title="GRHQ — surfaces d'eau",
            group="hydrographie",
            source_type="wms",
            url=ENV_WSS,
            layer_name="GRHQ_RES_SURF",
            curated=True,
            filter_spec=FilterSpec(kind="none"),
            legend_url=_legend(ENV_WSS, "GRHQ_RES_SURF"),
            min_zoom=8,
            color="#38bdf8",
            attribution="MELCCFP GRHQ",
            extra={"proxy": True},
        ),
        LayerDef(
            id="grhq_flow",
            title="GRHQ — sens d'écoulement",
            group="hydrographie",
            source_type="wms",
            url=GRHQ_WMS,
            layer_name="22",
            curated=True,
            filter_spec=FilterSpec(kind="none"),
            legend_url=_legend(GRHQ_WMS, "22"),
            min_zoom=12,
            color="#1d4ed8",
            attribution="MRNF GRHQ",
            extra={"proxy": True},
        ),
        LayerDef(
            id="hydrolidar_lits",
            title="Lit d'écoulement potentiel LiDAR",
            group="hydrographie",
            source_type="wms",
            url=MFFP,
            layer_name="hydrolidar_lits",
            curated=True,
            filter_spec=FilterSpec(kind="none"),
            legend_url=_legend(MFFP, "hydrolidar_lits"),
            min_zoom=12,
            color="#7c3aed",
            attribution="MFFP LiDAR",
            extra={"proxy": True},
        ),
        LayerDef(
            id="milieux_humides",
            title="Milieux humides potentiels",
            group="hydrographie",
            source_type="wms",
            url=MH,
            layer_name="Milieux_humides_potentiels11904",
            curated=True,
            filter_spec=FilterSpec(kind="none"),
            legend_url=_legend(MH, "Milieux_humides_potentiels11904"),
            color="#14b8a6",
            attribution="MELCCFP",
            extra={"proxy": True},
        ),
        LayerDef(
            id="bassins_wms",
            title="Bassins hydrographiques",
            group="hydrographie",
            source_type="local",
            url="data/spatial/bassins",  # snapshot : python3 -m peche.bassins sync
            curated=True,
            filter_spec=FilterSpec(
                kind="local",
                attr="niveau",
                options=[{"value": str(n), "label": f"Niveau {n}"} for n in range(1, 9)],
                multi=True,
            ),
            color="#94a3b8",
            attribution="MELCCFP",
        ),
        # --- LiDAR ---
        LayerDef(
            id="lidar_pentes",
            title="Pente LiDAR (dégradé continu)",
            group="lidar",
            source_type="wms",
            url=MFFP,
            layer_name="lidar_pentes",
            curated=True,
            filter_spec=FilterSpec(kind="none"),
            legend_url=_legend(MFFP, "lidar_pentes"),
            min_zoom=11,
            color="#fb923c",
            attribution="MFFP LiDAR",
            extra={"proxy": True, "no_color": True},
        ),
        LayerDef(
            id="lidar_courbes_1m",
            title="Courbe de niveau lidar 1 m",
            group="lidar",
            source_type="wms",
            url=MFFP,
            layer_name="courbes_niveau_1m",
            curated=True,
            filter_spec=FilterSpec(kind="none"),
            legend_url=_legend(MFFP, "courbes_niveau_1m"),
            min_zoom=15,
            color="#a78bfa",
            attribution="MFFP LiDAR",
            extra={
                "proxy": True,
                "dataset_url": (
                    "https://www.donneesquebec.ca/recherche/dataset/"
                    "produits-derives-de-base-du-lidar"
                ),
            },
        ),
        LayerDef(
            id="lidar_courbes_10m",
            title="Courbe de niveau lidar 10 m",
            group="lidar",
            source_type="wms",
            url=MFFP,
            layer_name="courbes_niveau_10m",
            curated=True,
            filter_spec=FilterSpec(kind="none"),
            legend_url=_legend(MFFP, "courbes_niveau_10m"),
            min_zoom=11,
            color="#8b5cf6",
            attribution="MFFP LiDAR",
            extra={
                "proxy": True,
                "dataset_url": (
                    "https://www.donneesquebec.ca/recherche/dataset/"
                    "produits-derives-de-base-du-lidar"
                ),
            },
        ),
        # --- Territoire (AQréseau+ ; WMS RQTT pas encore en ligne) ---
        LayerDef(
            id="aq_reseau",
            title="Réseau routier (AQréseau+)",
            group="territoire",
            source_type="wms",
            url=AQRESEAU,
            layer_name=AQ_ROADS,
            curated=True,
            filter_spec=FilterSpec(kind="none"),
            legend_url=_legend(AQRESEAU, "56"),
            min_zoom=8,
            color="#64748b",
            attribution="MRNF Adresses Québec",
            extra={"proxy": True},
        ),
        LayerDef(
            id="aq_forestier",
            title="Chemins forestiers / multiusages",
            group="territoire",
            source_type="wms",
            url=AQRESEAU,
            layer_name=AQ_FOREST,
            curated=True,
            filter_spec=FilterSpec(kind="none"),
            legend_url=_legend(AQRESEAU, "86"),
            min_zoom=9,
            color="#a16207",
            attribution="MRNF Adresses Québec",
            extra={"proxy": True},
        ),
        # STF (WMS) : sous-couche « Propriété privée ».
        LayerDef(
            id="stf_propriete_privee",
            title="Propriété privée",
            group="territoire",
            source_type="wms",
            url=STF_WMS,
            layer_name="Propriété_privée40726",
            curated=True,
            filter_spec=FilterSpec(kind="none"),
            legend_url=_legend(STF_WMS, "Propriété_privée40726"),
            min_zoom=9,
            opacity=0.5,
            color="#0f766e",
            attribution="MRNF STF",
            extra={"proxy": True},
        ),
    ]
    return layers


GROUP_TITLES: dict[str, str] = {
    "reglementation": "Réglementation pêche",
    "faune": "Faune",
    "hydro_temps_reel": "Hydro temps réel",
    "hydrographie": "Hydrographie",
    "lidar": "LiDAR",
    "territoire": "Territoire",
    "basemaps": "Fonds de carte",
}


def curated_ids() -> list[str]:
    return [layer.id for layer in curated_layers()]
