/** Contrôleur carte OpenLayers + MapState. */

import type { Catalog, LayerDef, LayerState, MapAction, MapPin, MapState, ToolEntry } from "./types";
import { createBasemapLayer, createOverlayLayer, styleForLayer, ZONES_PECHE_COLOR } from "./layers";
import {
  applySlopeClassFilter,
  attachClipToNewLayer,
  buildArcgisWhere,
  buildCql,
  clearZoneClip,
  extentToLonLatBbox,
  parseZoneExpr,
  setZoneClip,
  zoneFilterActive,
} from "./filters";
import { registerProjections } from "./projections";
import { IDENTIFY_LAYERS, IdentifyOverlay, type IdentifyHit } from "./identify";
import VectorLayer from "ol/layer/Vector";
import type BaseLayer from "ol/layer/Base";
import type Layer from "ol/layer/Layer";
import GeoJSON from "ol/format/GeoJSON";
import VectorSource from "ol/source/Vector";
import OlMap from "ol/Map";
import View from "ol/View";
import Overlay from "ol/Overlay";
import { boundingExtent } from "ol/extent";
import { defaults as defaultControls } from "ol/control";
import { fromLonLat, toLonLat } from "ol/proj";
import Feature from "ol/Feature";
import Point from "ol/geom/Point";
import { Circle as CircleStyle, Fill, Stroke, Style, Text } from "ol/style";

const QC_CENTER: [number, number] = [-73.0, 47.5];
const MAX_PINS = 20;
const PINS_LAYER_ID = "__pins";
const IDENTIFY_HIT = new Set([...IDENTIFY_LAYERS]);

function pinStyleFor(n: number): Style {
  return new Style({
    image: new CircleStyle({
      radius: 10,
      fill: new Fill({ color: "#f97316" }),
      stroke: new Stroke({ color: "#fff", width: 2 }),
    }),
    text: new Text({
      text: String(n),
      fill: new Fill({ color: "#fff" }),
      font: "bold 11px system-ui, sans-serif",
    }),
  });
}

/** Couches locales ponctuelles : chargement unique sans bbox. */
const POINT_LOCAL_LAYERS = new Set([
  "vigilance_stations",
  "marees_shc",
  "barrages_cehq",
]);

type FetchCache = {
  coverBbox: [number, number, number, number] | null;
  skipBbox: boolean;
  zoomBand: number;
  filterKey: string;
};

function expandBbox(
  bbox: [number, number, number, number],
  factor = 0.25,
): [number, number, number, number] {
  const w = bbox[2] - bbox[0];
  const h = bbox[3] - bbox[1];
  const padX = (w * factor) / 2;
  const padY = (h * factor) / 2;
  return [bbox[0] - padX, bbox[1] - padY, bbox[2] + padX, bbox[3] + padY];
}

function bboxContained(
  inner: [number, number, number, number],
  outer: [number, number, number, number],
): boolean {
  return (
    inner[0] >= outer[0] &&
    inner[1] >= outer[1] &&
    inner[2] <= outer[2] &&
    inner[3] <= outer[3]
  );
}

function zoomBand(zoom: number): number {
  return zoom < 9 ? 0 : 1;
}

function filterCacheKey(filters: Record<string, unknown>): string {
  return JSON.stringify(filters, Object.keys(filters).sort());
}

export class MapController {
  readonly map: OlMap;
  private catalog: Catalog | null = null;
  private layerIndex: Record<string, BaseLayer> = {};
  private defs: Record<string, LayerDef> = {};
  private highlightLayer: VectorLayer;
  private pinsLayer: VectorLayer;
  private pins: MapPin[] = [];
  private identify: IdentifyOverlay;
  private inflight: Record<string, AbortController> = {};
  private lastFetch: Record<string, FetchCache> = {};
  private zoneFitPending: Record<string, boolean> = {};
  private pinListEl: HTMLElement | null = null;
  private zoomHud: HTMLDivElement;
  private zoomListeners: Array<(z: number) => void> = [];
  private detailHandler: ((hit: IdentifyHit) => void) | null = null;

  constructor(target: HTMLElement) {
    registerProjections();
    this.highlightLayer = new VectorLayer({
      source: new VectorSource(),
      properties: { id: "__highlight", basemap: false },
      zIndex: 9999,
    });
    this.pinsLayer = new VectorLayer({
      source: new VectorSource(),
      style: (feature) => {
        const pinId = String(feature.get("pinId") || "");
        const pin = this.pins.find((p) => p.id === pinId);
        return pinStyleFor(pin?.n ?? 0);
      },
      properties: { id: PINS_LAYER_ID, basemap: false },
      zIndex: 10000,
    });
    this.map = new OlMap({
      target,
      controls: defaultControls({ zoom: true, rotate: false, attribution: true }),
      view: new View({
        center: fromLonLat(QC_CENTER),
        zoom: 6,
        maxZoom: 18,
      }),
      layers: [this.highlightLayer, this.pinsLayer],
    });
    this.identify = new IdentifyOverlay(this.map, {
      onAddPin: ({ label, layer, props, coordinate }) => {
        const [lon, lat] = toLonLat(coordinate);
        this.addPin({
          id: crypto.randomUUID(),
          lon,
          lat,
          label,
          source: "feature",
          layer,
          props,
        });
      },
      onDeletePin: (id) => this.removePin(id),
      onShowDetail: (hit) => this.detailHandler?.(hit),
    });
    this.zoomHud = document.createElement("div");
    this.zoomHud.className = "zoom-hud";
    this.zoomHud.title = "Niveau de zoom";
    target.appendChild(this.zoomHud);
    const syncZoom = () => {
      const z = this.getZoom();
      this.zoomHud.textContent = `z ${z.toFixed(1)}`;
      for (const cb of this.zoomListeners) cb(z);
    };
    this.map.getView().on("change:resolution", syncZoom);
    this.map.on("moveend", syncZoom);
    syncZoom();
    this.map.on("singleclick", (evt) => this.handleClick(evt));
  }

  setPinListEl(el: HTMLElement | null): void {
    this.pinListEl = el;
    this.renderPinList();
  }

  setDetailHandler(fn: (hit: IdentifyHit) => void): void {
    this.detailHandler = fn;
  }

  getZoom(): number {
    return this.map.getView().getZoom() ?? 0;
  }

  onZoomChange(cb: (z: number) => void): void {
    this.zoomListeners.push(cb);
  }

  private handleClick(evt: { pixel: number[]; coordinate: number[] }): void {
    const pixel = evt.pixel;
    const coordinate = evt.coordinate;

    const found: {
      pin: MapPin | null;
      feat: { layerId: string; props: Record<string, unknown> } | null;
    } = { pin: null, feat: null };

    this.map.forEachFeatureAtPixel(
      pixel,
      (feature, layer) => {
        const lid = layer?.get("id") as string | undefined;
        if (lid === PINS_LAYER_ID) {
          const id = String(feature.get("pinId") || "");
          found.pin = this.pins.find((p) => p.id === id) || null;
          return true;
        }
        if (lid && IDENTIFY_HIT.has(lid) && layer?.getVisible()) {
          const props = { ...(feature.getProperties() as Record<string, unknown>) };
          delete props.geometry;
          found.feat = { layerId: lid, props };
          return true;
        }
        return undefined;
      },
      {
        hitTolerance: 10,
        layerFilter: (layer) => {
          const lid = layer.get("id") as string | undefined;
          return lid === PINS_LAYER_ID || (Boolean(lid) && IDENTIFY_HIT.has(lid!));
        },
      },
    );

    if (found.pin) {
      void this.identify.showPin(found.pin, coordinate);
      return;
    }
    if (found.feat) {
      void this.identify.showFeature({
        layerId: found.feat.layerId,
        props: found.feat.props,
        coordinate,
      });
      return;
    }

    const [lon, lat] = toLonLat(coordinate);
    const n = this.pins.length + 1;
    this.addPin({
      id: crypto.randomUUID(),
      n,
      lon,
      lat,
      label: `Point ${n}`,
      source: "user",
    });
    const added = this.pins[this.pins.length - 1];
    if (added) {
      this.identify.showPin(added, coordinate, { loading: true });
      void this.enrichPin(added);
    }
  }

  private reindexPins(): void {
    this.pins.forEach((p, i) => {
      const n = i + 1;
      p.n = n;
      if (p.source === "user" && (!p.label || /^Point \d+$/.test(p.label))) {
        p.label = `Point ${n}`;
      }
    });
  }

  private async enrichPin(pin: MapPin): Promise<void> {
    try {
      const resp = await fetch(
        `/api/point-context?lon=${encodeURIComponent(String(pin.lon))}&lat=${encodeURIComponent(String(pin.lat))}`,
      );
      if (!resp.ok) return;
      const ctx = (await resp.json()) as Record<string, unknown>;
      const props: Record<string, unknown> = { ...(pin.props || {}) };
      const fz = ctx.fishing_zone as Record<string, unknown> | undefined;
      if (fz?.zone_nom) props.zone_nom = fz.zone_nom;
      if (fz?.no_zone != null) props.no_zone = fz.no_zone;
      if (fz?.zone_id != null) props.zone_id = fz.zone_id;
      const exc = ctx.exception as Record<string, unknown> | undefined;
      if (exc?.nom) props.exception_nom = exc.nom;
      if (exc?.plan_id != null) props.exception_plan_id = exc.plan_id;
      const wb = ctx.waterbody as Record<string, unknown> | undefined;
      if (wb?.name) props.waterbody_name = wb.name;
      const tfs = ctx.tfs as Record<string, unknown> | undefined;
      if (tfs?.name) props.tfs_name = tfs.name;
      const hunt = ctx.hunting_forbidden as Record<string, unknown> | undefined;
      if (hunt?.name) props.hunting_forbidden_name = hunt.name;
      if (hunt?.kind) props.hunting_forbidden_kind = hunt.kind;
      pin.props = props;
      this.renderPinList();
      this.identify.refreshPin(pin);
    } catch {
      /* ignore */
    }
  }

  async loadCatalog(): Promise<Catalog> {
    const resp = await fetch("/api/catalog");
    const catalog = (await resp.json()) as Catalog;
    this.catalog = catalog;
    this.defs = {};

    for (const group of catalog.groups) {
      for (const def of group.layers) {
        if (def.id === "zones_chasse") def.color = ZONES_PECHE_COLOR;
      }
    }

    for (const b of catalog.basemaps) {
      this.defs[b.id] = b;
      const layer = createBasemapLayer(b);
      this.layerIndex[b.id] = layer;
      this.map.getLayers().insertAt(0, layer);
    }

    for (const group of catalog.groups) {
      for (const def of group.layers) {
        this.defs[def.id] = def;
        if (def.visible_default) {
          this.ensureLayer(def.id);
        }
      }
    }
    return catalog;
  }

  getCatalog(): Catalog | null {
    return this.catalog;
  }

  ensureLayer(id: string): BaseLayer | null {
    if (this.layerIndex[id]) return this.layerIndex[id];
    const def = this.defs[id];
    if (!def) return null;
    const layer = createOverlayLayer(def);
    this.layerIndex[id] = layer;
    this.map.addLayer(layer);
    attachClipToNewLayer(layer as Layer);
    if (layer.getVisible() && this.isVectorDef(def)) {
      void this.refreshVectorLayer(id);
    }
    return layer;
  }

  private isVectorDef(def: LayerDef): boolean {
    return (
      def.source_type === "wfs" ||
      def.source_type === "arcgis" ||
      def.source_type === "geojson" ||
      def.source_type === "local"
    );
  }

  private vectorDataSource(layer: Layer): VectorSource | null {
    const data = layer.get("dataSource") as VectorSource | undefined;
    if (data instanceof VectorSource) return data;
    const src = layer.getSource();
    if (src instanceof VectorSource) return src;
    return null;
  }

  setLayerVisible(id: string, visible: boolean): void {
    const layer = this.ensureLayer(id);
    layer?.setVisible(visible);
    if (visible) {
      void this.refreshVectorLayer(id);
      return;
    }
    delete this.lastFetch[id];
    const source = this.vectorDataSource(layer as Layer);
    if (source) source.clear();
  }

  setLayerOpacity(id: string, opacity: number): void {
    const layer = this.ensureLayer(id);
    layer?.setOpacity(opacity);
  }

  setLayerColor(id: string, color: string): void {
    const def = this.defs[id];
    const layer = this.ensureLayer(id);
    if (!def || !layer) return;
    def.color = color;
    layer.set("layerDef", def);
    if (typeof (layer as { setStyle?: unknown }).setStyle === "function") {
      (layer as VectorLayer).setStyle(styleForLayer(def));
    }
  }

  async setLayerFilters(
    id: string,
    filters: Record<string, unknown>,
    opts?: { show?: boolean },
  ): Promise<void> {
    const def = this.defs[id];
    const layer = this.ensureLayer(id);
    if (!def || !layer) return;
    layer.set("filters", filters);
    if (opts?.show) layer.setVisible(true);

    if (def.filter_spec?.kind === "colorkey" || id === "pente_cpl") {
      const classes =
        (filters.classes as string[]) || (filters.value as string[]) || null;
      applySlopeClassFilter(layer as Layer, classes, def);
      return;
    }

    if (this.isVectorDef(def) && layer.getVisible()) {
      delete this.lastFetch[id];
      if (zoneFilterActive(String(filters.No_zone ?? filters.no_zone ?? ""))) {
        this.zoneFitPending[id] = true;
      }
      await this.refreshVectorLayer(id);
    }
  }

  async refreshVectorLayer(id: string, opts?: { fitZone?: boolean }): Promise<void> {
    const def = this.defs[id];
    const layer = this.layerIndex[id] as Layer | undefined;
    if (!def || !layer) return;
    if (!layer.getVisible()) return;
    const source = this.vectorDataSource(layer);
    if (!source) return;

    const zoom = this.map.getView().getZoom() || 0;
    if (def.min_zoom != null && zoom < def.min_zoom) {
      source.clear();
      return;
    }
    if (def.max_zoom != null && zoom > def.max_zoom) {
      source.clear();
      return;
    }

    const extent = this.map.getView().calculateExtent(this.map.getSize());
    const bbox = extentToLonLatBbox(extent);
    const filters = (layer.get("filters") as Record<string, unknown>) || {};
    const zoneQ =
      filters.No_zone ?? filters.no_zone ?? filters.zone_id ?? null;
    const zoneActive =
      zoneQ != null && String(zoneQ).trim() !== "" && zoneFilterActive(String(zoneQ));
    const skipBbox =
      (id === "zones_chasse" || id === "plans_regpec") && zoneActive;
    const zBand = zoomBand(zoom);
    const fKey = filterCacheKey(filters);
    const isPointLayer = POINT_LOCAL_LAYERS.has(id);

    const prev = this.lastFetch[id];
    if (prev && source.getFeatures().length > 0) {
      if (isPointLayer && prev.skipBbox) return;
      if (skipBbox && prev.skipBbox && prev.filterKey === fKey) return;
      if (
        !skipBbox &&
        !isPointLayer &&
        prev.coverBbox &&
        prev.zoomBand === zBand &&
        prev.filterKey === fKey &&
        bboxContained(bbox, prev.coverBbox)
      ) {
        return;
      }
    }

    const limit = isPointLayer
      ? 10000
      : zoom < 9
        ? 500
        : zoom < 12
          ? 1500
          : 3000;
    const params = new URLSearchParams({
      layer: id,
      limit: String(limit),
      zoom: String(Math.round(zoom)),
    });
    if (!skipBbox && !isPointLayer) {
      const cover = expandBbox(bbox);
      params.set("bbox", cover.join(","));
    }

    const kind = def.filter_spec?.kind;
    if (kind === "cql") {
      const cql = buildCql(def.filter_spec?.attr, filters);
      if (cql) params.set("filter", cql);
    } else if (kind === "arcgis") {
      const where = buildArcgisWhere(def.filter_spec?.attr, filters);
      if (where) params.set("filter", where);
    } else if (kind === "local" || def.source_type === "local") {
      if (zoneQ != null && String(zoneQ).trim() !== "") {
        params.set("no_zone", String(zoneQ));
      }
      const cat = filters.categorie ?? filters[def.filter_spec?.attr || ""];
      if (Array.isArray(cat) && cat.length) {
        const allOpts = def.filter_spec?.options?.map((o) => o.value) || [];
        if (!(allOpts.length && cat.length === allOpts.length)) {
          params.set("categorie", cat.map(String).join(","));
        }
      } else if (typeof cat === "string" && cat) {
        params.set("categorie", cat);
      }
      const etat = filters.etat;
      if (Array.isArray(etat) && etat.length) {
        const allOpts = def.filter_spec?.options?.map((o) => o.value) || [];
        if (!(allOpts.length && etat.length === allOpts.length)) {
          params.set("etat", etat.map(String).join(","));
        }
      } else if (filters.etat != null && filters.etat !== "") {
        params.set("etat", String(filters.etat));
      }
    }

    this.inflight[id]?.abort();
    const ac = new AbortController();
    this.inflight[id] = ac;

    try {
      const resp = await fetch(`/api/features?${params}`, { signal: ac.signal });
      if (!resp.ok) return;
      const geojson = await resp.json();
      const format = new GeoJSON();
      const features = format.readFeatures(geojson, {
        dataProjection: "EPSG:4326",
        featureProjection: this.map.getView().getProjection(),
      });
      source.clear();
      source.addFeatures(features);
      this.lastFetch[id] = {
        coverBbox: skipBbox || isPointLayer ? null : expandBbox(bbox),
        skipBbox: skipBbox || isPointLayer,
        zoomBand: zBand,
        filterKey: fKey,
      };
      const shouldFit =
        (opts?.fitZone || this.zoneFitPending[id]) && zoneActive && features.length > 0;
      if (shouldFit) {
        delete this.zoneFitPending[id];
        const extent = source.getExtent();
        if (extent && extent.every(Number.isFinite)) {
          this.map.getView().fit(extent, {
            padding: [48, 48, 48, 48],
            maxZoom: id === "zones_chasse" ? 10 : 12,
            duration: 400,
          });
        }
      }
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
    } finally {
      if (this.inflight[id] === ac) delete this.inflight[id];
    }
  }

  async applyZoneFilter(layerId: string, raw: string): Promise<string | null> {
    const q = raw.trim();
    if (!q) {
      await this.setLayerFilters(layerId, {});
      return null;
    }
    try {
      parseZoneExpr(q);
    } catch (err) {
      return String(err);
    }
    const filters: Record<string, unknown> = {
      No_zone: q,
      no_zone: q,
      zone_id: q,
    };
    this.zoneFitPending[layerId] = true;
    await this.setLayerFilters(layerId, filters, { show: true });
    return null;
  }

  /** @deprecated Utiliser applyZoneFilter */
  async searchFishingZone(raw: string): Promise<string | null> {
    return this.applyZoneFilter("zones_chasse", raw);
  }

  async setZoneFilter(zoneId: number | null): Promise<void> {
    await setZoneClip(this.map, zoneId);
  }

  addPin(pin: MapPin): void {
    if (this.pins.length >= MAX_PINS) this.pins.shift();
    if (pin.n == null) pin.n = this.pins.length + 1;
    this.pins.push(pin);
    this.reindexPins();
    this.syncPinsLayer();
    this.renderPinList();
  }

  removePin(id: string): void {
    this.pins = this.pins.filter((p) => p.id !== id);
    this.reindexPins();
    this.syncPinsLayer();
    this.renderPinList();
  }

  setPins(pins: MapPin[]): void {
    this.pins = pins.slice(0, MAX_PINS);
    this.reindexPins();
    this.syncPinsLayer();
    this.renderPinList();
  }

  private syncPinsLayer(): void {
    const src = this.pinsLayer.getSource()!;
    src.clear();
    for (const pin of this.pins) {
      const f = new Feature({
        geometry: new Point(fromLonLat([pin.lon, pin.lat])),
        pinId: pin.id,
      });
      src.addFeature(f);
    }
  }

  private renderPinList(): void {
    const el = this.pinListEl;
    if (!el) return;
    if (!this.pins.length) {
      el.hidden = true;
      el.innerHTML = "";
      return;
    }
    el.hidden = false;
    el.innerHTML = `<div class="pin-list-header">Points <span class="badge">${this.pins.length}</span></div>`;
    for (const pin of this.pins) {
      const row = document.createElement("div");
      row.className = "pin-row";
      const label = pin.label || `${pin.lat.toFixed(3)}, ${pin.lon.toFixed(3)}`;
      row.innerHTML = `<button type="button" class="pin-goto">${escapeHtml(label)}</button>
        <button type="button" class="pin-del" title="Retirer">×</button>`;
      row.querySelector(".pin-goto")!.addEventListener("click", () => {
        this.map.getView().animate({
          center: fromLonLat([pin.lon, pin.lat]),
          zoom: Math.max(this.map.getView().getZoom() || 8, 11),
          duration: 300,
        });
        this.identify.showPin(pin, fromLonLat([pin.lon, pin.lat]));
      });
      row.querySelector(".pin-del")!.addEventListener("click", () => this.removePin(pin.id));
      el.appendChild(row);
    }
  }

  getMapState(): MapState {
    const view = this.map.getView();
    const center3857 = view.getCenter() || fromLonLat(QC_CENTER);
    const [lon, lat] = toLonLat(center3857);
    const extent = view.calculateExtent(this.map.getSize());
    const bbox = extentToLonLatBbox(extent);
    const layers: LayerState[] = [];
    let basemap = "fond_quebec";
    for (const id of Object.keys(this.layerIndex)) {
      const layer = this.layerIndex[id];
      if (layer.get("basemap")) {
        if (layer.getVisible()) basemap = id;
        continue;
      }
      if (!layer.getVisible() && !layer.get("filters")) continue;
      layers.push({
        id,
        visible: layer.getVisible(),
        opacity: layer.getOpacity(),
        filters: (layer.get("filters") as Record<string, unknown>) || undefined,
      });
    }
    const zoneId = this.map.get("zoneFilterId") as number | undefined;
    return {
      center: [lon, lat],
      zoom: view.getZoom() || 6,
      bbox,
      basemap,
      layers,
      zoneFilter: zoneId != null ? { zoneId } : undefined,
      pins: this.pins.length ? this.pins.map((p) => ({ ...p })) : undefined,
    };
  }

  async applyMapState(
    state: MapState,
    opts?: { skipView?: boolean },
  ): Promise<void> {
    if (!opts?.skipView) {
      if (state.center) {
        this.map.getView().setCenter(fromLonLat(state.center));
      }
      if (state.zoom != null) this.map.getView().setZoom(state.zoom);
    }

    for (const id of Object.keys(this.layerIndex)) {
      const layer = this.layerIndex[id];
      if (layer.get("basemap")) {
        layer.setVisible(id === state.basemap);
      }
    }

    for (const id of Object.keys(this.layerIndex)) {
      const layer = this.layerIndex[id];
      if (!layer.get("basemap")) layer.setVisible(false);
    }
    for (const ls of state.layers || []) {
      this.setLayerVisible(ls.id, ls.visible);
      this.setLayerOpacity(ls.id, ls.opacity ?? 1);
      if (ls.filters) await this.setLayerFilters(ls.id, ls.filters);
    }

    const zid = state.zoneFilter?.zoneId ?? null;
    this.map.set("zoneFilterId", zid);
    await this.setZoneFilter(zid);
    this.setPins(state.pins || []);
  }

  async restoreMapStateFromChat(
    state: MapState,
    msg: { tools?: ToolEntry[]; map_state?: MapState },
  ): Promise<void> {
    window.dispatchEvent(new CustomEvent("peche:show-map"));
    await new Promise<void>((resolve) => {
      requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
    });
    this.map.updateSize();
    await this.applyMapState(state, { skipView: true });
    const targets = extractFocusTargets(msg);
    if (targets.length) {
      this.focusLocations(targets);
      return;
    }
    if (state.center) {
      this.map.getView().animate({
        center: fromLonLat(state.center),
        zoom: state.zoom ?? this.map.getView().getZoom() ?? 8,
        duration: 400,
      });
    }
  }

  focusLocations(points: { lon: number; lat: number }[]): void {
    if (!points.length) return;
    if (points.length === 1) {
      this.map.getView().animate({
        center: fromLonLat([points[0].lon, points[0].lat]),
        zoom: Math.max(this.map.getView().getZoom() || 8, 12.5),
        duration: 400,
      });
    } else {
      const extent = boundingExtent(points.map((p) => fromLonLat([p.lon, p.lat])));
      this.map.getView().fit(extent, {
        padding: [60, 60, 60, 60],
        maxZoom: 13,
        duration: 400,
      });
    }
    for (const p of points) this.showRipple(p.lon, p.lat);
  }

  async focusZone(zoneRef: number): Promise<void> {
    const resp = await fetch(`/api/zones/${zoneRef}/geometry`);
    if (!resp.ok) return;
    const featJson = await resp.json();
    const format = new GeoJSON();
    const olFeat = format.readFeature(featJson, {
      dataProjection: "EPSG:4326",
      featureProjection: this.map.getView().getProjection(),
    });
    const feature = Array.isArray(olFeat) ? olFeat[0] : olFeat;
    if (!(feature instanceof Feature)) return;
    const geom = feature.getGeometry();
    if (!geom) return;
    const extent = geom.getExtent();
    if (!extent.every(Number.isFinite)) return;
    this.map.getView().fit(extent, {
      padding: [48, 48, 48, 48],
      maxZoom: 10,
      duration: 400,
    });
  }

  private showRipple(lon: number, lat: number): void {
    const el = document.createElement("div");
    el.className = "map-ripple";
    el.innerHTML = "<span></span><span></span><span></span>";
    const overlay = new Overlay({
      element: el,
      positioning: "center-center",
      stopEvent: false,
    });
    this.map.addOverlay(overlay);
    overlay.setPosition(fromLonLat([lon, lat]));
    window.setTimeout(() => this.map.removeOverlay(overlay), 1200);
  }

  async applyMapAction(event: MapAction): Promise<void> {
    const action = event.action;
    if (action === "set_view") {
      if (Array.isArray(event.center) && event.center.length === 2) {
        this.map
          .getView()
          .setCenter(fromLonLat(event.center as [number, number]));
      }
      if (typeof event.zoom === "number") {
        this.map.getView().setZoom(event.zoom);
      }
      if (Array.isArray(event.bbox) && event.bbox.length === 4) {
        const b = event.bbox as number[];
        const extent = [
          ...fromLonLat([b[0], b[1]]),
          ...fromLonLat([b[2], b[3]]),
        ];
        this.map.getView().fit(extent as [number, number, number, number], {
          padding: [40, 40, 40, 40],
          maxZoom: 14,
          duration: 400,
        });
      }
    } else if (action === "toggle_layers") {
      for (const id of (event.show as string[]) || []) {
        this.setLayerVisible(id, true);
      }
      for (const id of (event.hide as string[]) || []) {
        this.setLayerVisible(id, false);
      }
      const opacity = (event.opacity as Record<string, number>) || {};
      for (const [id, op] of Object.entries(opacity)) {
        this.setLayerOpacity(id, op);
      }
    } else if (action === "set_layer_filter") {
      const lid = String(event.layer_id || "");
      await this.setLayerFilters(
        lid,
        (event.filters as Record<string, unknown>) || {},
        { show: true },
      );
    } else if (action === "filter_by_zone") {
      if (event.clear) {
        this.map.set("zoneFilterId", null);
        await this.setZoneFilter(null);
        await this.setLayerFilters("zones_chasse", {});
      } else {
        const zid = Number(event.no_zone ?? event.zone_id);
        this.map.set("zoneFilterId", zid);
        await this.setZoneFilter(zid);
        if (event.no_zone != null) {
          await this.applyZoneFilter("zones_chasse", String(event.no_zone));
        }
      }
    } else if (action === "highlight_features") {
      const src = this.highlightLayer.getSource()!;
      src.clear();
      if (event.geojson) {
        const feats = new GeoJSON().readFeatures(event.geojson as object, {
          dataProjection: "EPSG:4326",
          featureProjection: this.map.getView().getProjection(),
        });
        src.addFeatures(feats);
      }
    }
  }

  destroy(): void {
    clearZoneClip(this.map);
    this.map.setTarget(undefined);
  }
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

const HYDRO_FOCUS_TOOLS = new Set([
  "get_hydromet",
  "get_hydromet_at_plan",
  "get_hydromet_for_waterbody",
  "get_tides",
  "get_tides_at_place",
  "get_tides_at_plan",
  "get_water_levels",
]);

function extractFocusTargets(msg: {
  tools?: ToolEntry[];
  map_state?: MapState;
}): { lon: number; lat: number }[] {
  const out: { lon: number; lat: number }[] = [];
  const seen = new Set<string>();

  const push = (lon: unknown, lat: unknown) => {
    const lo = Number(lon);
    const la = Number(lat);
    if (!Number.isFinite(lo) || !Number.isFinite(la)) return;
    const key = `${lo.toFixed(5)},${la.toFixed(5)}`;
    if (seen.has(key)) return;
    seen.add(key);
    out.push({ lon: lo, lat: la });
  };

  const walk = (node: unknown, depth = 0): void => {
    if (node == null || depth > 8) return;
    if (Array.isArray(node)) {
      for (const item of node) walk(item, depth + 1);
      return;
    }
    if (typeof node !== "object") return;
    const rec = node as Record<string, unknown>;
    if ("lon" in rec && "lat" in rec) push(rec.lon, rec.lat);
    if ("longitude" in rec && "latitude" in rec) push(rec.longitude, rec.latitude);
    for (const v of Object.values(rec)) walk(v, depth + 1);
  };

  for (const tool of msg.tools || []) {
    if (!HYDRO_FOCUS_TOOLS.has(tool.name)) continue;
    walk(tool.result);
  }

  if (!out.length) {
    for (const pin of msg.map_state?.pins || []) {
      push(pin.lon, pin.lat);
    }
  }
  return out;
}
