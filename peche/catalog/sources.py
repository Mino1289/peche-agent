"""Endpoints OGC publics (catalogue Forêt ouverte + Atlas de l'eau + Vigilance)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ServiceKind = Literal["wms", "wmts", "wfs", "arcgis", "xyz"]


@dataclass(frozen=True)
class OgcSource:
    id: str
    title: str
    kind: ServiceKind
    url: str
    group: str
    """Groupe catalogue par défaut pour les couches découvertes."""
    wfs_url: str | None = None
    """URL WFS associée (GeoServer / MapServer)."""
    proxy: bool = True
    """Passer par /api/ogc (CORS)."""


# Basemaps Forêt ouverte
BASEMAP_SOURCES: list[OgcSource] = [
    OgcSource(
        id="fond_quebec",
        title="Fond Québec",
        kind="xyz",
        url="https://carto.msp.gouv.qc.ca/tms/1.0.0/carte_gouv_qc_public@EPSG_3857/{z}/{x}/{-y}.png",
        group="basemaps",
        proxy=False,
    ),
    OgcSource(
        id="imagerie_continue",
        title="Imagerie aérienne du gouvernement du Québec",
        kind="wmts",
        url=(
            "https://servicesmatriciels.mern.gouv.qc.ca/erdas-iws/ogc/wmts/"
            "Imagerie_Continue/Imagerie_GQ/default/"
            "GoogleMapsCompatibleExt2:epsg:3857/{z}/{y}/{x}.jpg"
        ),
        group="basemaps",
        proxy=False,
    ),
]

# Services WMS/WFS — Forêt ouverte + faune + hydrographie
WMS_SOURCES: list[OgcSource] = [
    OgcSource(
        id="environnement_wss",
        title="Hydrographie (GRHQ)",
        kind="wms",
        url="https://geoegl.msp.gouv.qc.ca/apis/wss/environnement.fcgi",
        group="hydrographie",
        proxy=True,
    ),
    OgcSource(
        id="aleas",
        title="Aléas (feux, restrictions)",
        kind="wms",
        url="https://geoegl.msp.gouv.qc.ca/apis/wss/aleas.fcgi",
        group="perturbations",
        proxy=True,
    ),
    OgcSource(
        id="stf_wms",
        title="STF — territoires forestiers",
        kind="wms",
        url="https://servicescarto.mrnf.gouv.qc.ca/pes/services/Forets/STF_WMS/MapServer/WMSServer",
        group="territoire",
        proxy=True,
    ),
    OgcSource(
        id="sda_wms",
        title="Découpages administratifs",
        kind="wms",
        url="https://servicescarto.mrnf.gouv.qc.ca/pes/services/Territoire/SDA_WMS/MapServer/WmsServer",
        group="territoire",
        proxy=True,
    ),
    OgcSource(
        id="grhq_wms",
        title="GRHQ détaillée (MRNF)",
        kind="wms",
        url=(
            "https://servicescarto.mrnf.gouv.qc.ca/pes/services/Territoire/"
            "GRHQ_WMS/MapServer/WMSServer"
        ),
        group="hydrographie",
        proxy=True,
    ),
    OgcSource(
        id="aqreseau",
        title="Réseau routier (AQréseau+)",
        kind="wms",
        url="https://servicescarto.mrnf.gouv.qc.ca/pes/services/Territoire/AQreseauPlus_WMS/MapServer/WMSServer",
        group="territoire",
        proxy=True,
    ),
    OgcSource(
        id="tbe_wms",
        title="TBE — tordeuse des bourgeons de l'épinette",
        kind="wms",
        url="https://servicescarto.mrnf.gouv.qc.ca/pes/services/Forets/DPF_WMS_TBE/MapServer/WMSServer",
        group="perturbations",
        proxy=True,
    ),
    OgcSource(
        id="cptaq",
        title="Zones agricoles (CPTAQ)",
        kind="wms",
        url="https://carto.cptaq.gouv.qc.ca/cgi-bin/cptaq",
        group="territoire",
        proxy=True,
    ),
    OgcSource(
        id="aires_protegees",
        title="Aires protégées (MELCCFP)",
        kind="wms",
        url="https://geo.environnement.gouv.qc.ca/donnees/services/Biodiversite/Aires_protegees/MapServer/WMSServer",
        group="biodiversite",
        proxy=True,
    ),
    OgcSource(
        id="milieux_humides",
        title="Milieux humides potentiels",
        kind="wms",
        url="https://geo.environnement.gouv.qc.ca/donnees/services/Biodiversite/MH_potentiels/MapServer/WMSServer",
        group="hydrographie",
        proxy=True,
    ),
    OgcSource(
        id="themes_publics",
        title="Thèmes publics (bassins, inondables)",
        kind="wms",
        url="https://www.servicesgeo.enviroweb.gouv.qc.ca/donnees/services/Public/Themes_publics/MapServer/WMSServer",
        group="hydrographie",
        proxy=True,
    ),
]

# GeoServer WFS/WMS faune
GEOSERVER_SOURCES: list[OgcSource] = [
    OgcSource(
        id="smartfaune",
        title="Faune (SmartFaune)",
        kind="wfs",
        url="https://servicesvecto3.mern.gouv.qc.ca/geoserver/SmartFaunePub/ows",
        group="faune",
        wfs_url="https://servicesvecto3.mern.gouv.qc.ca/geoserver/SmartFaunePub/ows",
        proxy=True,
    ),
    OgcSource(
        id="foretouverte_pub",
        title="Forêt ouverte (pub)",
        kind="wfs",
        url="https://servicesvecto3.mern.gouv.qc.ca/geoserver/ForetOuvertePub/ows",
        group="faune",
        wfs_url="https://servicesvecto3.mern.gouv.qc.ca/geoserver/ForetOuvertePub/ows",
        proxy=True,
    ),
    OgcSource(
        id="habitats_fauniques",
        title="Habitats fauniques",
        kind="wfs",
        url="https://servicesvecto3.mern.gouv.qc.ca/geoserver/Habitats_Fauniques_Pub/ows",
        group="faune",
        wfs_url="https://servicesvecto3.mern.gouv.qc.ca/geoserver/Habitats_Fauniques_Pub/ows",
        proxy=True,
    ),
]

# Atlas de l'eau — ArcGIS REST MapServers
ARCGIS_EAU_BASE = "https://geo.environnement.gouv.qc.ca/donnees/rest/services/Eau"
ARCGIS_EAU_SERVICES: list[str] = [
    "AD_CE_BV_Lacs",
    "Aire_prot_prlv_eau",
    "Bacteriologie_fleuve",
    "Benthos",
    "Cadre_reg_MHyd_OPI",
    "Guide_poisson",
    "IQBP",
    "IQBR",
    "Pesticides_eau_surface",
    "PrelevEauAutorises",
    "Registre_OPI",
    "Secteurs_travaux_ZIZM",
    "Zones_gestion_integree_eau",
]


def arcgis_sources() -> list[OgcSource]:
    return [
        OgcSource(
            id=f"eau_{name.lower()}",
            title=f"Atlas de l'eau — {name}",
            kind="arcgis",
            url=f"{ARCGIS_EAU_BASE}/{name}/MapServer",
            group="qualite_eau",
            proxy=True,
        )
        for name in ARCGIS_EAU_SERVICES
    ]


def all_harvest_sources() -> list[OgcSource]:
    # Catalogue UI curated-only : pas de dump GetCapabilities
    # (WMS_SOURCES / GEOSERVER_SOURCES restent comme référence d'endpoints).
    return list(BASEMAP_SOURCES)
