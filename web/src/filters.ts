/** Filtres client : clip zone + colorkey pente_cpl (image pré-filtrée). */

import type { Map as OlMap } from "ol";
import type Layer from "ol/layer/Layer";
import type { EventsKey } from "ol/events";
import type { Geometry, MultiPolygon, Polygon } from "ol/geom";
import GeoJSON from "ol/format/GeoJSON";
import Feature from "ol/Feature";
import { transformExtent } from "ol/proj";
import { unByKey } from "ol/Observable";
import ImageLayer from "ol/layer/Image";
import ImageWMS from "ol/source/ImageWMS";
import type { LayerDef } from "./types";

export const PENTE_COLORS: Record<string, [number, number, number]> = {
  A: [194, 254, 194],
  B: [2, 219, 0],
  C: [254, 246, 164],
  D: [249, 188, 103],
  E: [251, 103, 103],
  F: [254, 0, 0],
};

export type ZoneExpr =
  | { kind: "all" }
  | { kind: "list"; values: number[] };

/** Parse ``21,23,25-28`` or ``*``. Empty → all. */
export function parseZoneExpr(raw: string | null | undefined): ZoneExpr {
  const s = (raw ?? "").trim();
  if (!s || s === "*") return { kind: "all" };

  const values = new Set<number>();
  for (const token of s.split(",").map((t) => t.trim()).filter(Boolean)) {
    if (token === "*") return { kind: "all" };
    if (token.includes("-")) {
      const parts = token.split("-", 2);
      if (parts.length !== 2 || !parts[0].trim() || !parts[1].trim()) {
        throw new Error(`Plage invalide : ${token}`);
      }
      const a = Number(parts[0].trim());
      const b = Number(parts[1].trim());
      if (!Number.isFinite(a) || !Number.isFinite(b)) {
        throw new Error(`Plage invalide : ${token}`);
      }
      const lo = Math.min(a, b);
      const hi = Math.max(a, b);
      for (let n = lo; n <= hi; n++) values.add(n);
    } else {
      const n = Number(token);
      if (!Number.isFinite(n)) throw new Error(`Jeton invalide : ${token}`);
      values.add(n);
    }
  }
  if (!values.size) return { kind: "all" };
  return { kind: "list", values: [...values].sort((a, b) => a - b) };
}

export function zoneFilterActive(raw: string | null | undefined): boolean {
  const expr = parseZoneExpr(raw);
  return expr.kind === "list" && expr.values.length > 0;
}

export function zoneFilterParam(expr: ZoneExpr): string | null {
  if (expr.kind === "all") return null;
  return expr.values.join(",");
}

const COLOR_TOLERANCE = 22;

function colorMatches(
  r: number,
  g: number,
  b: number,
  target: [number, number, number],
): boolean {
  return (
    Math.abs(r - target[0]) <= COLOR_TOLERANCE &&
    Math.abs(g - target[1]) <= COLOR_TOLERANCE &&
    Math.abs(b - target[2]) <= COLOR_TOLERANCE
  );
}

function classForPixel(
  r: number,
  g: number,
  b: number,
  a: number,
): string | null {
  if (a < 10) return null;
  if (
    Math.abs(r - 130) <= COLOR_TOLERANCE &&
    Math.abs(g - 130) <= COLOR_TOLERANCE &&
    Math.abs(b - 130) <= COLOR_TOLERANCE
  ) {
    return null;
  }
  for (const [cls, rgb] of Object.entries(PENTE_COLORS)) {
    if (colorMatches(r, g, b, rgb)) return cls;
  }
  return null;
}

/** Filtre une image PNG WMS : classes non retenues → transparent. */
export function filterSlopeImage(
  img: HTMLImageElement | HTMLCanvasElement,
  allowedClasses: string[],
): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = img.width || (img as HTMLImageElement).naturalWidth;
  canvas.height = img.height || (img as HTMLImageElement).naturalHeight;
  const ctx = canvas.getContext("2d")!;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(img, 0, 0);
  const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
  const data = imageData.data;
  const allowed = new Set(allowedClasses);
  for (let i = 0; i < data.length; i += 4) {
    const cls = classForPixel(data[i], data[i + 1], data[i + 2], data[i + 3]);
    if (cls == null || !allowed.has(cls)) {
      data[i] = 0;
      data[i + 1] = 0;
      data[i + 2] = 0;
      data[i + 3] = 0;
    }
  }
  ctx.putImageData(imageData, 0, 0);
  return canvas;
}

/**
 * Remplace la source WMS de pente_cpl par une ImageWMS dont le
 * imageLoadFunction applique le filtre de classes (transparence réelle).
 */
export function applySlopeClassFilter(
  layer: Layer,
  allowedClasses: string[] | null,
  def?: LayerDef,
): void {
  const classes =
    !allowedClasses || allowedClasses.length === 0 || allowedClasses.length === 6
      ? null
      : allowedClasses;

  layer.set("slopeClasses", classes);

  // Rebuild ImageWMS with filtering loader
  const layerDef = (def || layer.get("layerDef")) as LayerDef | undefined;
  if (!layerDef || !(layer instanceof ImageLayer)) {
    // TileLayer fallback: recreate as ImageLayer is handled by map controller
    layer.changed();
    return;
  }

  const url = layerDef.url;
  const layerName = layerDef.layer_name || "pente_cpl";
  const source = new ImageWMS({
    url,
    params: {
      LAYERS: layerName,
      STYLES: "",
      VERSION: "1.3.0",
      FORMAT: "image/png",
      TRANSPARENT: true,
    },
    ratio: 1.2,
    crossOrigin: "anonymous",
    imageLoadFunction: (image, src) => {
      const img = new Image();
      img.crossOrigin = "anonymous";
      img.onload = () => {
        const allowed = layer.get("slopeClasses") as string[] | null;
        const el = image.getImage() as HTMLImageElement;
        if (!allowed) {
          el.src = src;
          return;
        }
        try {
          const filtered = filterSlopeImage(img, allowed);
          el.src = filtered.toDataURL("image/png");
        } catch {
          el.src = src;
        }
      };
      img.onerror = () => {
        (image.getImage() as HTMLImageElement).src = src;
      };
      img.src = src;
    },
  });
  layer.setSource(source);
}

type ClipListener = {
  layer: Layer;
  keys: EventsKey[];
};

const clipState: {
  geometry: Geometry | null;
  listeners: ClipListener[];
} = { geometry: null, listeners: [] };

/** zoneRef = numéro affiché (28) ou zone_id RegPec. */
export async function setZoneClip(
  map: OlMap,
  zoneRef: number | null,
): Promise<void> {
  clearZoneClip(map);
  if (zoneRef == null) return;

  const resp = await fetch(`/api/zones/${zoneRef}/geometry`);
  if (!resp.ok) return;
  const featJson = await resp.json();
  const format = new GeoJSON();
  const olFeat = format.readFeature(featJson, {
    dataProjection: "EPSG:4326",
    featureProjection: map.getView().getProjection(),
  });
  const feature = Array.isArray(olFeat) ? olFeat[0] : olFeat;
  if (!(feature instanceof Feature)) return;
  const geom = feature.getGeometry();
  if (!geom) return;
  const extent = geom.getExtent();
  const size = Math.max(extent[2] - extent[0], extent[3] - extent[1], 1);
  const simplified = geom.simplify(size / 400);
  clipState.geometry = simplified;

  map.getLayers().forEach((layer) => {
    if (layer.get("basemap")) return;
    if (!layer.getVisible()) return;
    attachClip(layer as Layer, simplified);
  });
  map.render();
}

function attachClip(layer: Layer, geom: Geometry): void {
  if (clipState.listeners.some((l) => l.layer === layer)) return;

  const pre = (event: {
    context?: CanvasRenderingContext2D | WebGLRenderingContext;
    frameState?: { coordinateToPixelTransform: number[] };
  }) => {
    const ctx = event.context;
    if (!ctx || !("save" in ctx) || !clipState.geometry || !event.frameState) return;
    const c2d = ctx as CanvasRenderingContext2D;
    c2d.save();
    try {
      const px = event.frameState.coordinateToPixelTransform;
      c2d.beginPath();
      const type = geom.getType();
      let rings: number[][][] = [];
      if (type === "Polygon") {
        rings = (geom as Polygon).getCoordinates();
      } else if (type === "MultiPolygon") {
        for (const poly of (geom as MultiPolygon).getCoordinates()) {
          rings.push(...poly);
        }
      }
      for (const ring of rings) {
        ring.forEach((coord, i) => {
          const x = coord[0] * px[0] + coord[1] * px[2] + px[4];
          const y = coord[0] * px[1] + coord[1] * px[3] + px[5];
          if (i === 0) c2d.moveTo(x, y);
          else c2d.lineTo(x, y);
        });
        c2d.closePath();
      }
      c2d.clip();
    } catch {
      /* ignore */
    }
  };

  const post = (event: {
    context?: CanvasRenderingContext2D | WebGLRenderingContext;
  }) => {
    const ctx = event.context;
    if (ctx && "restore" in ctx) (ctx as CanvasRenderingContext2D).restore();
  };

  const k1 = (layer as unknown as { on: (t: string, fn: unknown) => EventsKey }).on(
    "prerender",
    pre,
  );
  const k2 = (layer as unknown as { on: (t: string, fn: unknown) => EventsKey }).on(
    "postrender",
    post,
  );
  clipState.listeners.push({ layer, keys: [k1, k2] });
}

export function clearZoneClip(map: OlMap): void {
  for (const { keys } of clipState.listeners) {
    unByKey(keys);
  }
  clipState.listeners = [];
  clipState.geometry = null;
  map.render();
}

export function attachClipToNewLayer(layer: Layer): void {
  if (!clipState.geometry || !layer.getVisible()) return;
  attachClip(layer, clipState.geometry);
}

export function buildCql(
  attr: string | undefined | null,
  filters: Record<string, unknown>,
): string | null {
  if (!attr) {
    if (typeof filters.cql === "string") return filters.cql;
    return null;
  }
  const val = filters[attr] ?? filters.value ?? filters.classes;
  if (val == null || val === "") return null;
  if (Array.isArray(val)) {
    if (!val.length) return null;
    const quoted = val
      .map((v) => `'${String(v).replace(/'/g, "''")}'`)
      .join(",");
    return `${attr} IN (${quoted})`;
  }
  return `${attr}='${String(val).replace(/'/g, "''")}'`;
}

export function buildArcgisWhere(
  attr: string | undefined | null,
  filters: Record<string, unknown>,
): string | null {
  if (typeof filters.where === "string") return filters.where;
  if (!attr) return null;
  const val = filters[attr] ?? filters.value;
  if (val == null || val === "") return null;
  if (Array.isArray(val)) {
    const quoted = val
      .map((v) => `'${String(v).replace(/'/g, "''")}'`)
      .join(",");
    return `${attr} IN (${quoted})`;
  }
  if (typeof val === "number") return `${attr}=${val}`;
  return `${attr}='${String(val).replace(/'/g, "''")}'`;
}

export function extentToLonLatBbox(
  extent: number[],
): [number, number, number, number] {
  const e = transformExtent(extent, "EPSG:3857", "EPSG:4326");
  return [e[0], e[1], e[2], e[3]];
}
