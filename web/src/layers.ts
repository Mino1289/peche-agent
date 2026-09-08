/** Construction des sources / couches OpenLayers depuis LayerDef. */

import TileLayer from "ol/layer/Tile";
import VectorLayer from "ol/layer/Vector";
import ImageLayer from "ol/layer/Image";
import XYZ from "ol/source/XYZ";
import TileWMS from "ol/source/TileWMS";
import ImageWMS from "ol/source/ImageWMS";
import VectorSource from "ol/source/Vector";
import ImageTile from "ol/ImageTile";
import LineString from "ol/geom/LineString";
import MultiLineString from "ol/geom/MultiLineString";
import MultiPolygon from "ol/geom/MultiPolygon";
import Polygon from "ol/geom/Polygon";
import {
  Circle as CircleStyle,
  Fill,
  Stroke,
  Style,
} from "ol/style";
import type { FeatureLike } from "ol/Feature";
import type BaseLayer from "ol/layer/Base";
import type { LayerDef } from "./types";

const OUTLINE_CACHE = "_outlineGeom";

/** Contour des zones de pêche (R=20 G=96 B=157). */
export const ZONES_PECHE_COLOR = "#14609d";

export function isOutlineLayer(def: LayerDef): boolean {
  return def.id === "zones_chasse" || Boolean(def.extra?.outline);
}

export function proxyUrl(absoluteUrl: string, useProxy: boolean): string {
  if (!useProxy) return absoluteUrl;
  return `/api/ogc?url=${encodeURIComponent(absoluteUrl)}`;
}

function needsProxy(def: LayerDef): boolean {
  if (def.extra?.proxy === false) return false;
  return Boolean(def.extra?.proxy ?? true);
}

function hexToRgba(hex: string, alpha: number): string {
  const h = hex.replace("#", "");
  const full =
    h.length === 3
      ? h
          .split("")
          .map((c) => c + c)
          .join("")
      : h;
  const n = parseInt(full, 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  return `rgba(${r},${g},${b},${alpha})`;
}

export const ETAT_COLORS: Record<string, string> = {
  normal: "#22c55e",
  surveillance: "#f59e0b",
  alerte: "#ef4444",
  inconnu: "#94a3b8",
};

function stripAccents(value: string): string {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

/** Mappe un libellé Vigilance (« État normal », « En surveillance », …) vers une clé couleur. */
export function etatColorKey(raw: unknown): keyof typeof ETAT_COLORS {
  if (raw == null || raw === "") return "inconnu";
  const key = stripAccents(String(raw).toLowerCase().trim());
  if (key.includes("alerte")) return "alerte";
  if (key.includes("surveillance")) return "surveillance";
  if (key.includes("normal")) return "normal";
  return "inconnu";
}

function etatColor(feature: FeatureLike, fallback: string): string {
  const raw = feature.get("etat");
  if (raw == null || raw === "") return fallback;
  return ETAT_COLORS[etatColorKey(raw)] || fallback;
}

const _pointStyles = new Map<string, Style>();
const _lineStyles = new Map<string, Style>();
const _polyStyles = new Map<string, Style>();
const _outlineStyles = new Map<string, Style>();

/** Contour extérieur seulement (comme RegPec) — pas de fill, pas les trous/lacs. */
function asOutlineGeom(feature: FeatureLike): LineString | MultiLineString | undefined {
  const cached = feature.get(OUTLINE_CACHE);
  if (cached instanceof MultiLineString || cached instanceof LineString) return cached;
  const g = feature.getGeometry();
  if (!g) return undefined;
  if (g instanceof LineString || g instanceof MultiLineString) return g;
  let rings: number[][][] = [];
  if (g instanceof Polygon) {
    const coords = g.getCoordinates();
    if (coords[0]) rings = [coords[0]];
  } else if (g instanceof MultiPolygon) {
    for (const poly of g.getCoordinates()) {
      if (poly[0]) rings.push(poly[0]);
    }
  } else {
    return undefined;
  }
  if (!rings.length) return undefined;
  const outline =
    rings.length === 1 ? new LineString(rings[0]) : new MultiLineString(rings);
  if (typeof (feature as { set?: unknown }).set === "function") {
    (feature as { set: (k: string, v: unknown, silent?: boolean) => void }).set(
      OUTLINE_CACHE,
      outline,
      true,
    );
  }
  return outline;
}

function cachedPointStyle(fill: string): Style {
  let s = _pointStyles.get(fill);
  if (!s) {
    s = new Style({
      image: new CircleStyle({
        radius: 6,
        fill: new Fill({ color: fill }),
        stroke: new Stroke({ color: "#fff", width: 1.5 }),
      }),
    });
    _pointStyles.set(fill, s);
  }
  return s;
}

function cachedLineStyle(color: string): Style {
  let s = _lineStyles.get(color);
  if (!s) {
    s = new Style({
      stroke: new Stroke({ color, width: 3, lineCap: "round" }),
    });
    _lineStyles.set(color, s);
  }
  return s;
}

function cachedPolyStyle(color: string): Style {
  let s = _polyStyles.get(color);
  if (!s) {
    s = new Style({
      fill: new Fill({ color: hexToRgba(color, 0.35) }),
      stroke: new Stroke({ color, width: 1.5 }),
    });
    _polyStyles.set(color, s);
  }
  return s;
}

function cachedOutlineStyle(color: string): Style {
  let s = _outlineStyles.get(color);
  if (!s) {
    s = new Style({
      geometry: asOutlineGeom,
      stroke: new Stroke({
        color,
        width: 2,
        lineJoin: "round",
        lineCap: "round",
      }),
    });
    _outlineStyles.set(color, s);
  }
  return s;
}

export function styleForLayer(def: LayerDef): (f: FeatureLike) => Style {
  const color = def.color || "#1d4ed8";
  const byEtat = Boolean(def.extra?.etat_colors) || def.id === "vigilance_stations";
  const outline = isOutlineLayer(def);
  return (feature) => {
    const g = feature.getGeometry()?.getType();
    const fill = byEtat ? etatColor(feature, "#94a3b8") : color;
    if (g === "Point" || g === "MultiPoint") {
      return cachedPointStyle(fill);
    }
    if (outline) return cachedOutlineStyle(color);
    if (g === "LineString" || g === "MultiLineString") {
      return cachedLineStyle(color);
    }
    return cachedPolyStyle(color);
  };
}

export function createBasemapLayer(def: LayerDef): BaseLayer {
  if (def.source_type === "xyz" || def.id === "fond_quebec" || def.id === "imagerie_continue") {
    return new TileLayer({
      source: new XYZ({
        url: def.url,
        crossOrigin: "anonymous",
        attributions: def.attribution || undefined,
        maxZoom: def.id === "imagerie_continue" ? 19 : 18,
      }),
      properties: { id: def.id, basemap: true },
      visible: def.visible_default !== false && def.id === "fond_quebec",
    });
  }
  if (def.source_type === "wmts") {
    // Fallback XYZ template if provided in url
    return new TileLayer({
      source: new XYZ({
        url: def.url.includes("{z}")
          ? def.url
          : "https://carto.msp.gouv.qc.ca/tms/1.0.0/carte_gouv_qc_public@EPSG_3857/{z}/{x}/{-y}.png",
        crossOrigin: "anonymous",
      }),
      properties: { id: def.id, basemap: true },
      visible: false,
    });
  }
  return new TileLayer({
    source: new XYZ({
      url: "https://carto.msp.gouv.qc.ca/tms/1.0.0/carte_gouv_qc_public@EPSG_3857/{z}/{x}/{-y}.png",
    }),
    properties: { id: def.id, basemap: true },
    visible: false,
  });
}

function makeTileWms(def: LayerDef, useProxy: boolean): TileLayer<TileWMS> {
  const params = {
    LAYERS: def.layer_name,
    TILED: true,
    VERSION: "1.3.0",
    FORMAT: "image/png",
    TRANSPARENT: true,
  };
  return new TileLayer({
    source: new TileWMS({
      url: def.url,
      params,
      crossOrigin: "anonymous",
      attributions: def.attribution || undefined,
      ...(useProxy
        ? {
            tileLoadFunction: (tile, src) => {
              const img = (tile as ImageTile).getImage() as HTMLImageElement;
              img.crossOrigin = "anonymous";
              img.src = `/api/ogc?url=${encodeURIComponent(src)}`;
            },
          }
        : {}),
    }),
    opacity: def.opacity ?? 1,
    visible: Boolean(def.visible_default),
    properties: { id: def.id, layerDef: def },
    minZoom: def.min_zoom ?? undefined,
    maxZoom: def.max_zoom ?? undefined,
  });
}

function makeImageWms(def: LayerDef, useProxy: boolean): ImageLayer<ImageWMS> {
  const layerName = def.layer_name || "";
  if (useProxy) {
    return new ImageLayer({
      source: new ImageWMS({
        url: "/api/ogc",
        params: {
          url: def.url,
          SERVICE: "WMS",
          VERSION: "1.3.0",
          REQUEST: "GetMap",
          LAYERS: layerName,
          STYLES: "",
          FORMAT: "image/png",
          TRANSPARENT: true,
        },
        ratio: 1,
        imageLoadFunction: (image, src) => {
          try {
            const u = new URL(src, window.location.origin);
            const target = u.searchParams.get("url") || def.url;
            u.searchParams.delete("url");
            const qs = u.searchParams.toString();
            const full = `${target}${target.includes("?") ? "&" : "?"}${qs}`;
            (image.getImage() as HTMLImageElement).src =
              `/api/ogc?url=${encodeURIComponent(full)}`;
          } catch {
            (image.getImage() as HTMLImageElement).src = src;
          }
        },
        crossOrigin: "anonymous",
        attributions: def.attribution || undefined,
      }),
      opacity: def.opacity ?? 1,
      visible: Boolean(def.visible_default),
      properties: { id: def.id, layerDef: def },
      minZoom: def.min_zoom ?? undefined,
      maxZoom: def.max_zoom ?? undefined,
    });
  }
  return new ImageLayer({
    source: new ImageWMS({
      url: def.url,
      params: {
        LAYERS: layerName,
        STYLES: "",
        VERSION: "1.3.0",
        FORMAT: "image/png",
        TRANSPARENT: true,
      },
      ratio: 1,
      crossOrigin: "anonymous",
      attributions: def.attribution || undefined,
    }),
    opacity: def.opacity ?? 1,
    visible: Boolean(def.visible_default),
    properties: { id: def.id, layerDef: def },
    minZoom: def.min_zoom ?? undefined,
    maxZoom: def.max_zoom ?? undefined,
  });
}

export function createOverlayLayer(def: LayerDef): BaseLayer {
  const visible = Boolean(def.visible_default);
  const props = { id: def.id, layerDef: def };

  if (def.source_type === "wms") {
    const useProxy = needsProxy(def);
    // pente_cpl : ImageWMS pour permettre le filtre colorkey (transparence)
    if (def.id === "pente_cpl" || def.filter_spec?.kind === "colorkey") {
      return makeImageWms(def, useProxy);
    }
    return makeTileWms(def, useProxy);
  }

  if (
    def.source_type === "wfs" ||
    def.source_type === "arcgis" ||
    def.source_type === "geojson" ||
    def.source_type === "local"
  ) {
    const source = new VectorSource();
    const outline = isOutlineLayer(def);
    const opacity = outline ? 1 : (def.opacity ?? 1);
    return new VectorLayer({
      source,
      style: styleForLayer(def),
      opacity,
      visible,
      properties: { ...props, dataSource: source },
      minZoom: def.min_zoom ?? undefined,
      maxZoom: def.max_zoom ?? undefined,
      // Contours seuls : redessiner au zoom pour rester nets (plus de raster VectorImage).
      updateWhileAnimating: outline,
      updateWhileInteracting: outline,
      renderBuffer: outline ? 180 : 100,
    });
  }

  return new VectorLayer({
    source: new VectorSource(),
    properties: props,
    visible: false,
  });
}

/** URL légende via proxy OGC. */
export function legendSrc(url: string | null | undefined): string | null {
  if (!url) return null;
  if (url.startsWith("/")) return url;
  return `/api/ogc?url=${encodeURIComponent(url)}`;
}
