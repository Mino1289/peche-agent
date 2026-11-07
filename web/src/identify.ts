/** Overlay d’identification : cadre du popup + points ; le contenu vient de `featureKinds`. */

import Overlay from "ol/Overlay";
import type OlMap from "ol/Map";
import type { Coordinate } from "ol/coordinate";
import { toLonLat } from "ol/proj";
import type { MapPin } from "./types";
import { titleFr, uninvertName } from "./names";
import { escapeHtml } from "./regs";
import { t } from "./i18n";
import {
  featurePinKey,
  popupClass,
  popupHtml,
  titleFor,
  type IdentifyHit,
} from "./featureKinds";
import { dl, str } from "./featureKinds/html";
import { stripGeom } from "./featureKinds/kind";

const PINS_LAYER_ID = "__pins";
/** Espace entre le point carte et le bas du popup (ancré par le haut). */
const POPUP_GAP_PX = 14;

type IdentifyHandlers = {
  onToggleFeaturePin: (args: {
    label: string;
    layer: string;
    props: Record<string, unknown>;
    coordinate: Coordinate;
  }) => void;
  getFeaturePin: (
    layer: string,
    props: Record<string, unknown>,
    coordinate: Coordinate,
  ) => MapPin | null;
  onDeletePin: (id: string) => void;
  onShowDetail: (hit: IdentifyHit) => void;
};

export class IdentifyOverlay {
  private overlay: Overlay;
  private el: HTMLDivElement;
  private handlers: IdentifyHandlers;
  private last: IdentifyHit | null = null;
  private lastPinOpts: { loading?: boolean } | undefined;
  private resizeObserver: ResizeObserver;
  private pinToggleMeasureBtn: HTMLButtonElement | null = null;

  constructor(map: OlMap, handlers: IdentifyHandlers) {
    this.handlers = handlers;
    this.el = document.createElement("div");
    this.el.className = "identify-popup";
    this.el.addEventListener("click", (ev) => this.onClick(ev));
    this.overlay = new Overlay({
      element: this.el,
      autoPan: { animation: { duration: 250 } },
      // top-center + offset négatif : le haut du popup reste fixe quand la hauteur change
      positioning: "top-center",
      offset: [0, 0],
      stopEvent: true,
    });
    map.addOverlay(this.overlay);
    this.resizeObserver = new ResizeObserver(() => this.syncOverlayOffset());
    this.resizeObserver.observe(this.el);
  }

  private syncOverlayOffset(): void {
    if (!this.overlay.getPosition()) return;
    const apply = (): void => {
      if (!this.overlay.getPosition()) return;
      const h = this.el.offsetHeight;
      if (!h) return;
      this.overlay.setOffset([0, -(h + POPUP_GAP_PX)]);
    };
    requestAnimationFrame(() => {
      apply();
      queueMicrotask(apply);
    });
  }

  hide(): void {
    this.last = null;
    this.lastPinOpts = undefined;
    this.el.className = "identify-popup";
    this.el.innerHTML = "";
    this.overlay.setPosition(undefined);
  }

  refreshLocale(): void {
    if (!this.last) return;
    if (this.last.layerId === PINS_LAYER_ID) {
      this.renderPinPopup(this.last.props as MapPin, this.last.coordinate, this.lastPinOpts);
      return;
    }
    void this.showFeature(this.last);
  }

  refreshFeaturePinButton(): void {
    if (!this.last || this.last.layerId === PINS_LAYER_ID) return;
    const btn = this.el.querySelector<HTMLButtonElement>('[data-act="toggle-pin"]');
    if (!btn) return;
    const pinned = this.handlers.getFeaturePin(
      this.last.layerId,
      stripGeom(this.last.props),
      this.last.coordinate,
    );
    const m = t();
    btn.textContent = pinned ? m.removeFeaturePin : m.addPin;
    btn.classList.toggle("btn-danger", Boolean(pinned));
    btn.classList.toggle("btn-secondary", !pinned);
    this.applyPinToggleMinWidth(btn);
    this.syncOverlayOffset();
  }

  showLoading(coord: Coordinate, title: string): void {
    const m = t();
    this.el.innerHTML = `
      <div class="identify-header">
        <h3>${escapeHtml(title)}</h3>
        <button type="button" class="identify-close" data-act="close" title="${escapeHtml(m.close)}">✕</button>
      </div>
      <div class="identify-body">${spinnerHtml()}</div>`;
    this.overlay.setPosition(coord);
    this.syncOverlayOffset();
  }

  async showFeature(hit: IdentifyHit): Promise<void> {
    this.last = hit;
    this.lastPinOpts = undefined;
    const title = titleFor(hit);
    this.showLoading(hit.coordinate, title);
    const body = await this.buildBody(hit);
    if (this.last !== hit) return;
    const [lon, lat] = toLonLat(hit.coordinate);
    const m = t();
    const extraClass = popupClass(hit.layerId);
    this.el.className = extraClass ? `identify-popup ${extraClass}` : "identify-popup";
    this.el.innerHTML = `
      <div class="identify-header">
        <h3>${escapeHtml(title)}</h3>
        <button type="button" class="identify-close" data-act="close" title="${escapeHtml(m.close)}">✕</button>
      </div>
      <div class="identify-body">${body}</div>
      <div class="identify-actions">
        <button type="button" class="btn-secondary" data-act="detail">${escapeHtml(m.viewDetail)}</button>
        ${this.featurePinButtonHtml(hit)}
        ${gmapsButton(lat, lon)}
      </div>`;
    this.overlay.setPosition(hit.coordinate);
    this.syncOverlayOffset();
  }

  showPin(
    pin: MapPin,
    coordinate: Coordinate,
    opts?: { loading?: boolean },
  ): void {
    this.last = {
      layerId: PINS_LAYER_ID,
      props: { ...pin },
      coordinate,
    };
    this.lastPinOpts = opts;
    this.renderPinPopup(pin, coordinate, opts);
  }

  refreshPin(pin: MapPin): void {
    if (!this.last || this.last.layerId !== PINS_LAYER_ID) return;
    const lastId = (this.last.props as MapPin).id;
    if (lastId !== pin.id) return;
    this.last.props = { ...pin };
    this.renderPinPopup(pin, this.last.coordinate);
  }

  private renderPinPopup(
    pin: MapPin,
    coordinate: Coordinate,
    opts?: { loading?: boolean },
  ): void {
    const m = t();
    const label = pin.label || coordsLabel(pin.lon, pin.lat);
    const ctx = (pin.props || {}) as Record<string, unknown>;
    const ctxHtml = opts?.loading ? spinnerHtml() : pinContextHtml(ctx);
    this.el.innerHTML = `
      <div class="identify-header">
        <h3>${escapeHtml(label)}</h3>
        <button type="button" class="identify-close" data-act="close" title="${escapeHtml(m.close)}">✕</button>
      </div>
      <div class="identify-body">
        <p>${fmt(pin.lat, 5)}° N · ${fmt(pin.lon, 5)}° O</p>
        ${ctxHtml}
        ${pin.source === "feature" && pin.layer ? `<p class="muted">${escapeHtml(m.fromLayer(pin.layer))}</p>` : ""}
      </div>
      <div class="identify-actions">
        ${exceptionDetailButton(ctx)}
        ${zoneRegsButton()}
        ${gmapsButton(pin.lat, pin.lon)}
        <button type="button" class="btn-danger" data-act="del-pin" data-pin="${escapeHtml(pin.id)}">${escapeHtml(m.removePin)}</button>
      </div>`;
    this.overlay.setPosition(coordinate);
    this.syncOverlayOffset();
  }

  private onClick(ev: Event): void {
    const btn = (ev.target as HTMLElement).closest("button") as HTMLButtonElement | null;
    if (!btn) return;
    const act = btn.dataset.act;
    if (act === "close") {
      this.hide();
    } else if (act === "detail" && this.last && this.last.layerId !== PINS_LAYER_ID) {
      this.handlers.onShowDetail(this.last);
    } else if (act === "toggle-pin" && this.last && this.last.layerId !== PINS_LAYER_ID) {
      this.handlers.onToggleFeaturePin({
        label: titleFor(this.last),
        layer: this.last.layerId,
        props: stripGeom(this.last.props),
        coordinate: this.last.coordinate,
      });
    } else if (act === "zone-regs" && this.last) {
      this.openZoneRegs(this.last);
    } else if (act === "exception-detail" && this.last) {
      this.openExceptionDetail(this.last);
    } else if (act === "del-pin") {
      const id = btn.dataset.pin;
      if (id) this.handlers.onDeletePin(id);
      this.hide();
    }
  }

  private openZoneRegs(hit: IdentifyHit): void {
    const pin = pinFromHit(hit);
    if (!pin) return;
    const ctx = pinContext(pin);
    this.handlers.onShowDetail({
      layerId: "zone",
      props: {
        zone_id: ctx.zone_id,
        zone_nom: ctx.zone_nom,
        no_zone: ctx.no_zone,
        lon: pin.lon,
        lat: pin.lat,
      },
      coordinate: hit.coordinate,
    });
  }

  private openExceptionDetail(hit: IdentifyHit): void {
    const pin = pinFromHit(hit);
    if (!pin) return;
    const ctx = pinContext(pin);
    const planId = ctx.exception_plan_id;
    const zoneId = ctx.exception_zone_id ?? ctx.zone_id;
    if (planId == null || zoneId == null) return;
    this.handlers.onShowDetail({
      layerId: "plans_regpec",
      props: {
        plan_id: planId,
        zone_id: zoneId,
        no_zone: ctx.exception_no_zone ?? ctx.no_zone,
        zone_nom: ctx.exception_zone_nom ?? ctx.zone_nom,
        nom: ctx.exception_nom ?? ctx.waterbody_name,
        lon: pin.lon,
        lat: pin.lat,
      },
      coordinate: hit.coordinate,
    });
  }

  private async buildBody(hit: IdentifyHit): Promise<string> {
    try {
      return await popupHtml(hit);
    } catch (err) {
      return `<p class="identify-error">${escapeHtml(String(err))}</p>`;
    }
  }

  private featurePinButtonHtml(hit: IdentifyHit): string {
    const m = t();
    const pinned = Boolean(
      this.handlers.getFeaturePin(hit.layerId, stripGeom(hit.props), hit.coordinate),
    );
    const label = pinned ? m.removeFeaturePin : m.addPin;
    const cls = pinned ? "btn-danger" : "btn-secondary";
    const minW = this.pinToggleMinWidthPx();
    return `<button type="button" class="${cls}" data-act="toggle-pin" style="min-width:${minW}px">${escapeHtml(label)}</button>`;
  }

  private pinToggleMinWidthPx(): number {
    const m = t();
    const probe =
      this.pinToggleMeasureBtn ??
      (() => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "btn-secondary identify-actions-measure";
        b.setAttribute("aria-hidden", "true");
        b.tabIndex = -1;
        Object.assign(b.style, {
          position: "fixed",
          left: "-9999px",
          visibility: "hidden",
          pointerEvents: "none",
        });
        document.body.appendChild(b);
        this.pinToggleMeasureBtn = b;
        return b;
      })();
    probe.className = "btn-secondary identify-actions-measure";
    let max = 0;
    for (const label of [m.addPin, m.removeFeaturePin]) {
      probe.textContent = label;
      max = Math.max(max, probe.offsetWidth);
    }
    return max;
  }

  private applyPinToggleMinWidth(btn: HTMLButtonElement): void {
    btn.style.minWidth = `${this.pinToggleMinWidthPx()}px`;
  }
}

export function pinMatchesFeature(
  pin: MapPin,
  layer: string,
  props: Record<string, unknown>,
  lon: number,
  lat: number,
): boolean {
  if (pin.source !== "feature" || pin.layer !== layer) return false;
  const key = featurePinKey(layer, props, lon, lat);
  if (!key) return false;
  const stored = pin.props?.feature_key;
  if (typeof stored === "string") return stored === key;
  return featurePinKey(layer, pin.props || {}, pin.lon, pin.lat) === key;
}

function gmapsButton(lat: number, lon: number): string {
  const url = `https://www.google.com/maps?q=${lat},${lon}`;
  return `<a class="btn-secondary gmaps-link" href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(t().showOnGmaps)}</a>`;
}

function zoneRegsButton(): string {
  return `<button type="button" class="btn-secondary" data-act="zone-regs">${escapeHtml(t().zoneRegs)}</button>`;
}

function exceptionDetailButton(ctx: Record<string, unknown>): string {
  if (ctx.exception_plan_id == null) return "";
  const m = t();
  return `<button type="button" class="btn-secondary" data-act="exception-detail" title="${escapeHtml(m.viewDetail)}">＋ ${escapeHtml(m.viewDetail)}</button>`;
}

function pinFromHit(hit: IdentifyHit): MapPin | null {
  if (hit.layerId !== PINS_LAYER_ID) return null;
  return hit.props as MapPin;
}

function pinContext(pin: MapPin): Record<string, unknown> {
  return (pin.props || {}) as Record<string, unknown>;
}

function pinContextHtml(ctx: Record<string, unknown>): string {
  const m = t();
  const rows: [string, string][] = [];
  const zone = str(ctx.zone_nom || ctx.fishing_zone);
  if (zone) rows.push([m.fishingZone, zone]);
  const exception = str(ctx.exception_nom);
  if (exception) {
    rows.push([m.exception, uninvertName(exception)]);
  }
  const water = str(ctx.waterbody_name);
  if (water) rows.push([m.waterbody, uninvertName(water)]);
  const tfs = str(ctx.tfs_name);
  if (tfs) rows.push([m.wildlifeTerritory, tfs]);
  const hunt = str(ctx.hunting_forbidden_name);
  if (hunt) rows.push([m.huntingForbidden, uninvertName(hunt)]);
  let html = "";
  if (exception) {
    html += `<p><span class="badge exception-badge">${escapeHtml(m.regulatoryException)}</span></p>`;
  }
  if (rows.length) {
    html += dl(rows);
  } else {
    html += `<p class="muted">${escapeHtml(m.userPin)}</p>`;
  }
  html += layerOverlaysHtml(ctx.layer_overlays);
  html += speciesPreviewHtml(ctx.species);
  return html;
}

function layerOverlaysHtml(raw: unknown): string {
  if (!Array.isArray(raw) || !raw.length) return "";
  const blocks: string[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const overlay = item as Record<string, unknown>;
    const title = titleFr(str(overlay.title || overlay.layer_id));
    const rows = overlay.rows;
    if (!title || !Array.isArray(rows) || !rows.length) continue;
    const inner = rows
      .map((row) => {
        if (!row || typeof row !== "object") return "";
        const r = row as Record<string, unknown>;
        const label = str(r.label);
        const value = str(r.value);
        if (!label || !value) return "";
        return `<div class="identify-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
      })
      .join("");
    if (inner) {
      blocks.push(
        `<section class="identify-overlay-block"><h4>${escapeHtml(title)}</h4><div class="identify-dl">${inner}</div></section>`,
      );
    }
  }
  return blocks.join("");
}

function speciesPreviewHtml(raw: unknown): string {
  if (!Array.isArray(raw) || !raw.length) return "";
  const m = t();
  const items = raw
    .slice(0, 8)
    .map((sp) => {
      if (!sp || typeof sp !== "object") return "";
      const s = sp as Record<string, unknown>;
      const name = str(s.nom_commun);
      if (!name) return "";
      const latin = str(s.nom_latin);
      const statut = str(s.statut);
      const meta = [latin, statut].filter(Boolean).join(" · ");
      return `<li><strong>${escapeHtml(name)}</strong>${meta ? ` <span class="muted">${escapeHtml(meta)}</span>` : ""}</li>`;
    })
    .filter(Boolean);
  if (!items.length) return "";
  return `<section class="identify-species-block"><h4>${escapeHtml(m.speciesGuide)}</h4><ul class="identify-species-list">${items.join("")}</ul><p class="muted">${escapeHtml(m.speciesGuideDisclaimer)}</p></section>`;
}

function spinnerHtml(): string {
  const m = t();
  return `<div class="identify-spinner-wrap" role="status" aria-label="${escapeHtml(m.loadingAria)}"><span class="identify-spinner"></span></div>`;
}

function fmt(n: number, digits: number): string {
  return n.toFixed(digits);
}

function coordsLabel(lon: number, lat: number): string {
  return `${lat.toFixed(4)}, ${lon.toFixed(4)}`;
}
