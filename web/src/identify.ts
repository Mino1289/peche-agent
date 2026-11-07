/** Overlay d’identification d’entités + fiches live (hydro / marées / plan). */

import Overlay from "ol/Overlay";
import type OlMap from "ol/Map";
import type { Coordinate } from "ol/coordinate";
import { toLonLat } from "ol/proj";
import type { MapPin } from "./types";
import { formatSpeciesList, titleFr, uninvertName } from "./names";
import { escapeHtml } from "./regs";
import { t } from "./i18n";

export const IDENTIFY_LAYERS = new Set([
  "barrages_cehq",
  "vigilance_stations",
  "marees_shc",
  "plans_regpec",
  "tfs",
  "chasse_interdite",
  "habitat_legal",
  "habitat_info",
  "stations_lavage",
]);

const PINS_LAYER_ID = "__pins";

const LAYER_TITLES: Record<string, string> = {
  habitat_legal: "Habitat faunique légal",
  habitat_info: "Habitat faunique informationnel",
  tfs: "Territoire faunique structuré",
  chasse_interdite: "Chasse interdite",
  stations_lavage: "Station de lavage",
};

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
  private lastPinOpts: { loading?: boolean } | undefined;

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

  showLoading(coord: Coordinate, title: string): void {
    const m = t();
    this.el.innerHTML = `
      <div class="identify-header">
        <h3>${escapeHtml(title)}</h3>
        <button type="button" class="identify-close" data-act="close" title="${escapeHtml(m.close)}">✕</button>
      </div>
      <div class="identify-body">${spinnerHtml()}</div>`;
    this.overlay.setPosition(coord);
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
    this.el.className =
      hit.layerId === "marees_shc"
        ? "identify-popup identify-popup--tides"
        : "identify-popup";
    this.el.innerHTML = `
      <div class="identify-header">
        <h3>${escapeHtml(title)}</h3>
        <button type="button" class="identify-close" data-act="close" title="${escapeHtml(m.close)}">✕</button>
      </div>
      <div class="identify-body">${body}</div>
      <div class="identify-actions">
        <button type="button" class="btn-secondary" data-act="detail">${escapeHtml(m.viewDetail)}</button>
        <button type="button" class="btn-secondary" data-act="add-pin">${escapeHtml(m.addPin)}</button>
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
    const p = hit.props;
    try {
      if (hit.layerId === "barrages_cehq") return barrageHtml(p);
      if (hit.layerId === "vigilance_stations") return await hydrometHtml(p);
      if (hit.layerId === "marees_shc") return await tidesHtml(p);
      if (hit.layerId === "plans_regpec") return planPopupHtml(p);
      if (hit.layerId === "tfs") return tfsHtml(p);
      if (hit.layerId === "chasse_interdite") return chasseInterditeHtml(p);
      if (hit.layerId === "habitat_legal" || hit.layerId === "habitat_info") {
        return habitatHtml(p);
      }
      if (hit.layerId === "stations_lavage") return stationLavageHtml(p);
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
    return String(p.description || p.plan_eau || p.station || t().station);
  }
  if (hit.layerId === "marees_shc") {
    return String(p.nom || p.officialName || p.name || p.code || "Station de marée");
  }
  if (hit.layerId === "plans_regpec") {
    return uninvertName(String(p.nom || p.name || `Plan ${p.plan_id || ""}`));
  }
  if (hit.layerId === "tfs") {
    return titleFr(
      uninvertName(String(p.NOM || p.NOM_TFS || p.NOM_ZEC || p.nom || p.name || t().wildlifeTerritory)),
    );
  }
  if (hit.layerId === "chasse_interdite") {
    return titleFr(
      uninvertName(String(p.TOPONYME || p.NOM || p.nom || t().huntingForbidden)),
    );
  }
  if (hit.layerId === "habitat_legal" || hit.layerId === "habitat_info") {
    const place = str(p.TOPONYME || p.NOM_HABITAT || p.NOM || p.nom);
    const category = str(p.CATEGORIE || p.STATUT || p.TYPE_HABITAT);
    if (place) return titleFr(place);
    if (category) return titleFr(category);
    return LAYER_TITLES[hit.layerId] || hit.layerId;
  }
  if (hit.layerId === "stations_lavage") {
    return String(p.NOM || p.nom || p.name || "Station de lavage");
  }
  if (hit.layerId === "zone") {
    const z = zoneLabelFromProps(p);
    return z ? t().zoneRegsTitle(z) : t().zoneRegs;
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

function barrageHtml(p: Record<string, unknown>): string {
  const m = t();
  const rows: [string, string][] = [
    [m.name, uninvertName(str(p.nom || p.name))],
    [m.number, str(p.numero)],
    [m.category, str(p.categorie)],
    [m.waterbody, uninvertName(str(p.plan_eau))],
    [m.municipality, str(p.municipalite)],
    [m.mrc, str(p.mrc)],
  ];
  let html = dl(rows);
  const url = str(p.url_fiche);
  if (url) {
    html += `<p><a href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(m.cehqSheet)}</a></p>`;
  }
  return html;
}

async function hydrometHtml(p: Record<string, unknown>): Promise<string> {
  const m = t();
  const sid = str(p.station || p.station_id || p.id);
  const cached = dl([
    [m.station, sid],
    [m.waterbody, uninvertName(str(p.plan_eau))],
    [m.cachedState, str(p.etat)],
  ]);
  if (!sid) return cached;
  const resp = await fetch(`/api/hydromet/${encodeURIComponent(sid)}`);
  if (!resp.ok) {
    return `${cached}<p class="identify-error">${escapeHtml(m.liveUnavailable(resp.status))}</p>`;
  }
  const live = (await resp.json()) as Record<string, unknown>;
  if (live.error) {
    return `${cached}<p class="identify-error">${escapeHtml(String(live.error))}</p>`;
  }
  const base = dl([
    [m.station, str(live.station_id || sid)],
    [m.waterbody, uninvertName(str(live.plan_eau || p.plan_eau))],
    [m.dataSource, str(live.source)],
    [m.state, str(live.etat)],
    [m.level, live.niveau_m != null ? `${live.niveau_m} m` : "—"],
    [m.flow, live.debit_m3s != null ? `${live.debit_m3s} m³/s` : "—"],
    [m.observed, str(live.observed_at)],
    [m.hqRegion, str(live.hq_region)],
  ]);
  const metrics = hqMetricsTableHtml(live.hq_metrics);
  return base + metrics + linksHtml(live.urls as Record<string, string> | undefined);
}

function hqMetricsTableHtml(metrics: unknown): string {
  if (!Array.isArray(metrics) || !metrics.length) return "";
  const m = t();
  let body = "";
  for (const row of metrics.slice(0, 16)) {
    if (!row || typeof row !== "object") continue;
    const r = row as Record<string, unknown>;
    const label = str(r.variable || r.type_point_donnee);
    const val = r.valeur != null ? String(r.valeur) : "—";
    const unit = str(r.nom_unite_mesure);
    body += `<tr><td>${escapeHtml(label)}</td><td><strong>${escapeHtml(
      val,
    )}</strong> ${escapeHtml(unit)}</td></tr>`;
  }
  if (!body) return "";
  return `<p class="muted">${escapeHtml(m.hqSeries)}</p><table class="identify-table"><thead><tr><th>${escapeHtml(
    m.name,
  )}</th><th>${escapeHtml(m.observed)}</th></tr></thead><tbody>${body}</tbody></table>`;
}

async function tidesHtml(p: Record<string, unknown>): Promise<string> {
  const m = t();
  const code = str(p.code || p.station_code || p.id);
  const nom = str(p.nom || p.officialName || p.name);
  if (!code) {
    return dl([[m.name, nom]]);
  }
  const resp = await fetch(`/api/tides/${encodeURIComponent(code)}?days=2`);
  if (!resp.ok) {
    return `<p class="identify-error">${escapeHtml(m.tidesUnavailable(resp.status))}</p>`;
  }
  const live = (await resp.json()) as Record<string, unknown>;
  if (live.error && live.niveau_m == null) {
    return `<p class="identify-error">${escapeHtml(String(live.error))}</p>`;
  }
  const latest =
    live.niveau_m != null
      ? `<p>${escapeHtml(m.observedLevel)} : <strong>${escapeHtml(String(live.niveau_m))} m</strong>${
          live.observed_at
            ? ` <span class="muted">(${escapeHtml(String(live.observed_at))})</span>`
            : ""
        }</p>`
      : "";
  const lignes =
    (live.table as { lignes?: Record<string, unknown>[] } | undefined)?.lignes || [];
  let table = "";
  if (lignes.length) {
    table = `<table class="identify-table identify-table--tides"><thead><tr><th>${escapeHtml(m.day)}</th><th>${escapeHtml(m.lowTide1)}</th><th>${escapeHtml(m.highTide1)}</th><th>${escapeHtml(m.lowTide2)}</th><th>${escapeHtml(m.highTide2)}</th></tr></thead><tbody>`;
    for (const row of lignes.slice(0, 4)) {
      table += `<tr><td>${escapeHtml(str(row.jour))}</td><td>${escapeHtml(
        tideTableCell(row, "basse_1"),
      )}</td><td>${escapeHtml(tideTableCell(row, "haute_1"))}</td><td>${escapeHtml(
        tideTableCell(row, "basse_2"),
      )}</td><td>${escapeHtml(tideTableCell(row, "haute_2"))}</td></tr>`;
    }
    table += `</tbody></table>`;
  }
  return (
    dl([
      [m.name, str(nom || live.station_nom)],
      ["Code", code],
    ]) +
    latest +
    table +
    linksHtml(live.urls as Record<string, string> | undefined)
  );
}

/** Popup léger : pas de règlements (réservés au panneau détail). */
function tfsHtml(p: Record<string, unknown>): string {
  const m = t();
  return dl([
    [m.name, titleFr(uninvertName(str(p.NOM || p.NOM_TFS || p.NOM_ZEC || p.nom || p.name)))],
    ["Type", titleFr(str(p.TYPE || p.TYPE_TFS))],
  ]);
}

function chasseInterditeHtml(p: Record<string, unknown>): string {
  const m = t();
  const name = str(p.TOPONYME || p.NOM || p.nom || p.name);
  const kind = str(p.DESIGNOM || p.DESIG_GR);
  const rows: [string, string][] = [[m.name, titleFr(uninvertName(name))]];
  if (kind) rows.push(["Type", titleFr(kind)]);
  return dl(rows);
}

function habitatHtml(p: Record<string, unknown>): string {
  const species = formatSpeciesList(p.ESPECE || p.ESPECE_CIBLE || p.NOM_ESPECE);
  const rows: [string, string][] = [
    ["Lieu", titleFr(str(p.TOPONYME || p.NOM_HABITAT || p.NOM || p.nom || p.name))],
    ["Catégorie", titleFr(str(p.CATEGORIE || p.TYPE_HABITAT || p.TYPE || p.CLASSE))],
    ["Statut", titleFr(str(p.STATUT))],
    ["Espèces", species],
    ["Région faunique", titleFr(str(p.REG_FAUNE || p.REG_ADMIN))],
    [
      "Superficie",
      p.SUP_HA != null && String(p.SUP_HA).trim() ? `${p.SUP_HA} ha` : "",
    ],
  ];
  return dl(rows.filter(([, v]) => v));
}

function stationLavageHtml(p: Record<string, unknown>): string {
  const m = t();
  return dl([
    [m.name, str(p.NOM || p.nom || p.name)],
    ["Adresse", str(p.ADRESSE || p.adresse)],
    [m.municipality, str(p.MUNICIPALITE || p.municipalite)],
  ]);
}

function planPopupHtml(p: Record<string, unknown>): string {
  const m = t();
  const nom = uninvertName(str(p.nom || p.name));
  const zone = zoneLabelFromProps(p);
  const planId = str(p.plan_id);
  const typeEndro = str(p.type_endro);
  let html = `<p><span class="badge exception-badge">${escapeHtml(m.regulatoryException)}</span></p>`;
  if (nom) html += `<p><strong>${escapeHtml(nom)}</strong></p>`;
  const meta: string[] = [];
  if (planId) meta.push(`Plan ${planId}`);
  if (zone) meta.push(zone);
  if (typeEndro) meta.push(typeEndro);
  if (meta.length) {
    html += `<p class="muted">${escapeHtml(meta.join(" · "))}</p>`;
  }
  html += `<p class="muted">${escapeHtml(m.useDetailForRegs)}</p>`;
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

function tideTableCell(row: Record<string, unknown>, suffix: string): string {
  const k = `maree_${suffix}`;
  return str(row[k] ?? row[`marée_${suffix}`] ?? "");
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

export { escapeHtml, hqMetricsTableHtml };
