"""Couches curées fishing-first — filtres, couleurs, légendes."""

from __future__ import annotations

from peche.catalog.models import FilterSpec, LayerDef

MFFP = "https://geoegl.msp.gouv.qc.ca/ws/mffpecofor.fcgi"
ENV_WSS = "https://geoegl.msp.gouv.qc.ca/apis/wss/environnement.fcgi"
SMARTFAUNE = "https://servicesvecto3.mern.gouv.qc.ca/geoserver/SmartFaunePub/ows"
HABITATS = "https://servicesvecto3.mern.gouv.qc.ca/geoserver/Habitats_Fauniques_Pub/ows"
FORET_PUB = "https://servicesvecto3.mern.gouv.qc.ca/geoserver/ForetOuvertePub/ows"
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
AQRESEAU = (
    "https://servicescarto.mrnf.gouv.qc.ca/pes/services/Territoire/"
    "AQreseauPlus_WMS/MapServer/WMSServer"
)

# WMS ArcGIS : noms GetCapabilities (niveaux 1–8, scale-dependent).
BASSINS_LAYERS = ",".join(
    [
        "Bassins_hydro._20k_et_50k_niveau_162427",
        "Bassins_hydro._20k_et_50k_niveau_219040",
        "Bassins_hydro._20k_et_50k_niveau_311657",
        "Bassins_hydro._20k_et_50k_niveau_440278",
        "Bassins_hydro._20k_et_50k_niveau_532895",
        "Bassins_hydro._20k_et_50k_niveau_655044",
        "Bassins_hydro._20k_et_50k_niveau_747661",
        "Bassins_hydro._20k_et_50k_niveau_810746",
    ]
)
BASSINS_LEGEND_LAYER = "Bassins_hydro._20k_et_50k_niveau_162427"

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
            source_type="wfs",
            url=SMARTFAUNE,
            layer_name="SmartFaunePub:TFS",
            curated=True,
            filter_spec=FilterSpec(kind="cql", attr="TYPE"),
            color="#a855f7",
            attribution="MFFP SmartFaune",
        ),
        LayerDef(
            id="chasse_interdite",
            title="Chasse interdite",
            group="faune",
            source_type="wfs",
            url=SMARTFAUNE,
            layer_name="SmartFaunePub:Chasse_Interdite",
            curated=True,
            filter_spec=FilterSpec(kind="cql"),
            color="#ef4444",
            attribution="MFFP SmartFaune",
        ),
        LayerDef(
            id="habitat_legal",
            title="Habitats fauniques légaux",
            group="faune",
            source_type="wfs",
            url=HABITATS,
            layer_name="Habitats_Fauniques_Pub:Habitat_legal",
            curated=True,
            filter_spec=FilterSpec(kind="cql"),
            color="#22c55e",
            attribution="MFFP",
        ),
        LayerDef(
            id="habitat_info",
            title="Habitats fauniques informationnels",
            group="faune",
            source_type="wfs",
            url=HABITATS,
            layer_name="Habitats_Fauniques_Pub:Habitat_informationnel",
            curated=True,
            filter_spec=FilterSpec(kind="cql"),
            color="#86efac",
            attribution="MFFP",
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
            title="Stations hydrométriques Vigilance",
            group="hydro_temps_reel",
            source_type="local",
            url="data/hydromet/stations.json",
            curated=True,
            filter_spec=FilterSpec(kind="none"),
            visible_default=True,
            color="#3b82f6",
            attribution="MSP Vigilance",
            extra={"etat_colors": True},
        ),
        LayerDef(
            id="barrages_cehq",
            title="Barrages CEHQ",
            group="hydro_temps_reel",
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
            extra={"geometry": "line"},
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
        # --- Hydrographie ---
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
            source_type="wms",
            url=THEMES,
            layer_name=BASSINS_LAYERS,
            curated=True,
            filter_spec=FilterSpec(kind="none"),
            legend_url=_legend(THEMES, BASSINS_LEGEND_LAYER),
            color="#94a3b8",
            attribution="MELCCFP",
            extra={"proxy": True},
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
            extra={"proxy": True},
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
