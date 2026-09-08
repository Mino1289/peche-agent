/** Overlay d’identification d’entités + fiches live (hydro / marées / plan). */

import Overlay from "ol/Overlay";
import type OlMap from "ol/Map";
import type { Coordinate } from "ol/coordinate";
import { toLonLat } from "ol/proj";
import type { MapPin } from "./types";
import { uninvertName } from "./names";
import { escapeHtml } from "./regs";

export const IDENTIFY_LAYERS = new Set([
  "barrages_cehq",
  "vigilance_stations",
  "marees_shc",
  "plans_regpec",
]);

const PINS_LAYER_ID = "__pins";

export type IdentifyHit = {
  layerId: string;
  props: Record<string, unknown>;
  coordinate: Coordinate;
};

type IdentifyHandlers = {
  onAddPin: (args: {
    label: string;
    layer: string;
    props: Record<string, unknown>;
    coordinate: Coordinate;
  }) => void;
  onDeletePin: (id: string) => void;
  onShowDetail: (hit: IdentifyHit) => void;
};

export class IdentifyOverlay {
  private overlay: Overlay;
  private el: HTMLDivElement;
  private handlers: IdentifyHandlers;
  private last: IdentifyHit | null = null;

  constructor(map: OlMap, handlers: IdentifyHandlers) {
    this.handlers = handlers;
    this.el = document.createElement("div");
    this.el.className = "identify-popup";
    this.el.addEventListener("click", (ev) => this.onClick(ev));
    this.overlay = new Overlay({
      element: this.el,
      autoPan: { animation: { duration: 250 } },
      positioning: "bottom-center",
      offset: [0, -14],
      stopEvent: true,
    });
    map.addOverlay(this.overlay);
  }

  hide(): void {
    this.last = null;
    this.el.innerHTML = "";
    this.overlay.setPosition(undefined);
  }

  showLoading(coord: Coordinate, title: string): void {
    this.el.innerHTML = `
      <div class="identify-header">
        <h3>${escapeHtml(title)}</h3>
        <button type="button" class="identify-close" data-act="close" title="Fermer">✕</button>
      </div>
      <div class="identify-body">${spinnerHtml()}</div>`;
    this.overlay.setPosition(coord);
  }

  async showFeature(hit: IdentifyHit): Promise<void> {
    this.last = hit;
    const title = titleFor(hit);
    this.showLoading(hit.coordinate, title);
    const body = await this.buildBody(hit);
    if (this.last !== hit) return;
    const [lon, lat] = toLonLat(hit.coordinate);
    this.el.innerHTML = `
      <div class="identify-header">
        <h3>${escapeHtml(title)}</h3>
        <button type="button" class="identify-close" data-act="close" title="Fermer">✕</button>
      </div>
      <div class="identify-body">${body}</div>
      <div class="identify-actions">
        <button type="button" class="btn-secondary" data-act="detail">Voir en détail</button>
        <button type="button" class="btn-secondary" data-act="add-pin">Ajouter en point</button>
        ${gmapsButton(lat, lon)}
      </div>`;
    this.overlay.setPosition(hit.coordinate);
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
    const label = pin.label || coordsLabel(pin.lon, pin.lat);
    const ctx = (pin.props || {}) as Record<string, unknown>;
    const ctxHtml = opts?.loading ? spinnerHtml() : pinContextHtml(ctx);
    this.el.innerHTML = `
      <div class="identify-header">
        <h3>${escapeHtml(label)}</h3>
        <button type="button" class="identify-close" data-act="close" title="Fermer">✕</button>
      </div>
      <div class="identify-body">
        <p>${fmt(pin.lat, 5)}° N · ${fmt(pin.lon, 5)}° O</p>
        ${ctxHtml}
        ${pin.source === "feature" && pin.layer ? `<p class="muted">Issu de ${escapeHtml(pin.layer)}</p>` : ""}
      </div>
      <div class="identify-actions">
        ${zoneRegsButton()}
        ${gmapsButton(pin.lat, pin.lon)}
        <button type="button" class="btn-danger" data-act="del-pin" data-pin="${escapeHtml(pin.id)}">Retirer</button>
      </div>`;
    this.overlay.setPosition(coordinate);
  }

  private onClick(ev: Event): void {
    const btn = (ev.target as HTMLElement).closest("button") as HTMLButtonElement | null;
    if (!btn) return;
    const act = btn.dataset.act;
    if (act === "close") {
      this.hide();
    } else if (act === "detail" && this.last && this.last.layerId !== PINS_LAYER_ID) {
      this.handlers.onShowDetail(this.last);
    } else if (act === "add-pin" && this.last && this.last.layerId !== PINS_LAYER_ID) {
      this.handlers.onAddPin({
        label: titleFor(this.last),
        layer: this.last.layerId,
        props: stripGeom(this.last.props),
        coordinate: this.last.coordinate,
      });
    } else if (act === "zone-regs" && this.last) {
      this.openZoneRegs(this.last);
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

  private async buildBody(hit: IdentifyHit): Promise<string> {
    const p = hit.props;
    try {
      if (hit.layerId === "barrages_cehq") return barrageHtml(p);
      if (hit.layerId === "vigilance_stations") return await hydrometHtml(p);
      if (hit.layerId === "marees_shc") return await tidesHtml(p);
      if (hit.layerId === "plans_regpec") return planPopupHtml(p);
    } catch (err) {
      return `<p class="identify-error">${escapeHtml(String(err))}</p>`;
    }
    return `<pre class="identify-raw">${escapeHtml(JSON.stringify(stripGeom(p), null, 2).slice(0, 800))}</pre>`;
  }
}

export function titleFor(hit: IdentifyHit): string {
  const p = hit.props;
  if (hit.layerId === "barrages_cehq") {
    return uninvertName(String(p.nom || p.name || `Barrage ${p.numero || ""}`.trim()));
  }
  if (hit.layerId === "vigilance_stations") {
    return String(p.description || p.plan_eau || p.station || "Station hydrométrique");
  }
  if (hit.layerId === "marees_shc") {
    return String(p.nom || p.officialName || p.name || p.code || "Station de marée");
  }
  if (hit.layerId === "plans_regpec") {
    return uninvertName(String(p.nom || p.name || `Plan ${p.plan_id || ""}`));
  }
  if (hit.layerId === "zone") {
    const z = zoneLabelFromProps(p);
    return z ? `Réglementation — ${z}` : "Réglementation de zone";
  }
  return uninvertName(String(p.nom || p.name || hit.layerId));
}

export function zoneLabelFromProps(p: Record<string, unknown>): string {
  if (p.zone_nom) return String(p.zone_nom);
  if (p.no_zone != null && p.no_zone !== "") return `Zone ${p.no_zone}`;
  if (p.zone_id != null && p.zone_id !== "") return `Zone (id ${p.zone_id})`;
  return "";
}

function gmapsButton(lat: number, lon: number): string {
  const url = `https://www.google.com/maps?q=${lat},${lon}`;
  return `<a class="btn-secondary gmaps-link" href="${escapeHtml(url)}" target="_blank" rel="noopener">Afficher sur Google Maps</a>`;
}

function zoneRegsButton(): string {
  return `<button type="button" class="btn-secondary" data-act="zone-regs">Voir la réglementation de la zone</button>`;
}

function pinFromHit(hit: IdentifyHit): MapPin | null {
  if (hit.layerId !== PINS_LAYER_ID) return null;
  return hit.props as MapPin;
}

function pinContext(pin: MapPin): Record<string, unknown> {
  return (pin.props || {}) as Record<string, unknown>;
}

function pinContextHtml(ctx: Record<string, unknown>): string {
  const rows: [string, string][] = [];
  const zone = str(ctx.zone_nom || ctx.fishing_zone);
  if (zone) rows.push(["Zone de pêche", zone]);
  const exception = str(ctx.exception_nom);
  if (exception) rows.push(["Exception", uninvertName(exception)]);
  const water = str(ctx.waterbody_name);
  if (water) rows.push(["Plan d'eau", uninvertName(water)]);
  const tfs = str(ctx.tfs_name);
  if (tfs) rows.push(["Territoire faunique", tfs]);
  const hunt = str(ctx.hunting_forbidden_name);
  if (hunt) rows.push(["Chasse interdite", uninvertName(hunt)]);
  if (!rows.length) {
    return `<p class="muted">Point utilisateur</p>`;
  }
  return dl(rows);
}

function spinnerHtml(): string {
  return `<div class="identify-spinner-wrap" role="status" aria-label="Chargement"><span class="identify-spinner"></span></div>`;
}

function barrageHtml(p: Record<string, unknown>): string {
  const rows: [string, string][] = [
    ["Nom", uninvertName(str(p.nom || p.name))],
    ["N°", str(p.numero)],
    ["Catégorie", str(p.categorie)],
    ["Plan d'eau", uninvertName(str(p.plan_eau))],
    ["Municipalité", str(p.municipalite)],
    ["MRC", str(p.mrc)],
  ];
  let html = dl(rows);
  const url = str(p.url_fiche);
  if (url) {
    html += `<p><a href="${escapeHtml(url)}" target="_blank" rel="noopener">Fiche CEHQ</a></p>`;
  }
  return html;
}

async function hydrometHtml(p: Record<string, unknown>): Promise<string> {
  const sid = str(p.station || p.station_id || p.id);
  const cached = dl([
    ["Station", sid],
    ["Plan d'eau", uninvertName(str(p.plan_eau))],
    ["État (cache)", str(p.etat)],
  ]);
  if (!sid) return cached;
  const resp = await fetch(`/api/hydromet/${encodeURIComponent(sid)}`);
  if (!resp.ok) {
    return `${cached}<p class="identify-error">Mesures live indisponibles (${resp.status})</p>`;
  }
  const live = (await resp.json()) as Record<string, unknown>;
  if (live.error) {
    return `${cached}<p class="identify-error">${escapeHtml(String(live.error))}</p>`;
  }
  return (
    dl([
      ["Station", str(live.station_id || sid)],
      ["Plan d'eau", uninvertName(str(live.plan_eau || p.plan_eau))],
      ["État", str(live.etat)],
      ["Niveau", live.niveau_m != null ? `${live.niveau_m} m` : "—"],
      ["Débit", live.debit_m3s != null ? `${live.debit_m3s} m³/s` : "—"],
      ["Observé", str(live.observed_at)],
    ]) + linksHtml(live.urls as Record<string, string> | undefined)
  );
}

async function tidesHtml(p: Record<string, unknown>): Promise<string> {
  const code = str(p.code || p.station_code || p.id);
  const nom = str(p.nom || p.officialName || p.name);
  if (!code) {
    return dl([["Nom", nom]]);
  }
  const resp = await fetch(`/api/tides/${encodeURIComponent(code)}?days=2`);
  if (!resp.ok) {
    return `<p class="identify-error">Marées indisponibles (${resp.status})</p>`;
  }
  const live = (await resp.json()) as Record<string, unknown>;
  if (live.error && live.niveau_m == null) {
    return `<p class="identify-error">${escapeHtml(String(live.error))}</p>`;
  }
  const latest =
    live.niveau_m != null
      ? `<p>Niveau observé : <strong>${escapeHtml(String(live.niveau_m))} m</strong>${
          live.observed_at
            ? ` <span class="muted">(${escapeHtml(String(live.observed_at))})</span>`
            : ""
        }</p>`
      : "";
  const lignes =
    (live.table as { lignes?: Record<string, unknown>[] } | undefined)?.lignes || [];
  let table = "";
  if (lignes.length) {
    table = `<table class="identify-table"><thead><tr><th>Jour</th><th>Basse</th><th>Haute</th></tr></thead><tbody>`;
    for (const row of lignes.slice(0, 4)) {
      table += `<tr><td>${escapeHtml(str(row.jour))}</td><td>${escapeHtml(
        str(row.maree_basse_1 || row["marée_basse_1"]),
      )}</td><td>${escapeHtml(
        str(row.maree_haute_1 || row["marée_haute_1"]),
      )}</td></tr>`;
    }
    table += `</tbody></table>`;
  }
  return (
    dl([
      ["Nom", str(nom || live.station_nom)],
      ["Code", code],
    ]) +
    latest +
    table +
    linksHtml(live.urls as Record<string, string> | undefined)
  );
}

/** Popup léger : pas de règlements (réservés au panneau détail). */
function planPopupHtml(p: Record<string, unknown>): string {
  const nom = uninvertName(str(p.nom || p.name));
  const zone = zoneLabelFromProps(p);
  const planId = str(p.plan_id);
  const typeEndro = str(p.type_endro);
  let html = `<p><span class="badge exception-badge">Exception réglementaire</span></p>`;
  if (nom) html += `<p><strong>${escapeHtml(nom)}</strong></p>`;
  const meta: string[] = [];
  if (planId) meta.push(`Plan ${planId}`);
  if (zone) meta.push(zone);
  if (typeEndro) meta.push(typeEndro);
  if (meta.length) {
    html += `<p class="muted">${escapeHtml(meta.join(" · "))}</p>`;
  }
  html += `<p class="muted">Utilisez « Voir en détail » pour les règlements de l'exception et de la zone.</p>`;
  return html;
}

function dl(rows: [string, string][]): string {
  const items = rows
    .filter(([, v]) => v)
    .map(
      ([k, v]) =>
        `<div class="identify-row"><span>${escapeHtml(k)}</span><strong>${escapeHtml(v)}</strong></div>`,
    );
  return `<div class="identify-dl">${items.join("")}</div>`;
}

function linksHtml(urls: Record<string, string> | undefined): string {
  if (!urls) return "";
  const links = Object.entries(urls)
    .filter(([, u]) => u)
    .map(
      ([k, u]) =>
        `<a href="${escapeHtml(u)}" target="_blank" rel="noopener">${escapeHtml(k.replace(/_/g, " "))}</a>`,
    );
  return links.length ? `<p class="identify-links">${links.join(" · ")}</p>` : "";
}

function stripGeom(props: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(props)) {
    if (k === "geometry" || k === "features") continue;
    out[k] = v;
  }
  return out;
}

function str(v: unknown): string {
  if (v == null) return "";
  return String(v);
}

function fmt(n: number, digits: number): string {
  return n.toFixed(digits);
}

function coordsLabel(lon: number, lat: number): string {
  return `${lat.toFixed(4)}, ${lon.toFixed(4)}`;
}

export { escapeHtml };
