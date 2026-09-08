/** Panneau latéral de détail (graphiques hydro / tableaux règlements). */

import type { IdentifyHit } from "./identify";
import { titleFor, zoneLabelFromProps } from "./identify";
import { uninvertName } from "./names";
import { timelineHtml, escapeHtml, type TimelinePayload } from "./regs";
import {
  destroyHydroCharts,
  renderStationHydroCharts,
  renderTideChart,
} from "./hydroCharts";
import type { HydroResult } from "./types";
import type { MapController } from "./map";
import { loadZoneOptions, mountZonePicker, type ZoneOption } from "./zonePicker";

export class DetailPanel {
  private el: HTMLElement;
  private tabMap: HTMLElement;
  private map: MapController;

  constructor(el: HTMLElement, tabMap: HTMLElement, map: MapController) {
    this.el = el;
    this.tabMap = tabMap;
    this.map = map;
    this.el.classList.add("detail-panel");
    this.el.hidden = true;
  }

  close(): void {
    destroyHydroCharts(this.el);
    this.el.innerHTML = "";
    this.el.hidden = true;
    this.tabMap.classList.remove("has-detail");
    requestAnimationFrame(() => this.map.map.updateSize());
  }

  async show(hit: IdentifyHit): Promise<void> {
    this.el.hidden = false;
    this.tabMap.classList.add("has-detail");
    requestAnimationFrame(() => this.map.map.updateSize());
    const title = titleFor(hit);
    this.el.innerHTML = `
      <div class="panel-header">
        <h2>${escapeHtml(title)}</h2>
        <button type="button" class="identify-close" title="Fermer">✕</button>
      </div>
      <div class="detail-body"><p class="muted">Chargement…</p></div>`;
    this.el.querySelector(".identify-close")?.addEventListener("click", () => this.close());
    const body = this.el.querySelector(".detail-body") as HTMLElement;
    try {
      await this.fill(body, hit);
    } catch (err) {
      body.innerHTML = `<p class="identify-error">${escapeHtml(String(err))}</p>`;
    }
  }

  private async fill(body: HTMLElement, hit: IdentifyHit): Promise<void> {
    if (hit.layerId === "vigilance_stations") {
      await this.fillHydro(body, hit);
      return;
    }
    if (hit.layerId === "marees_shc") {
      await this.fillTides(body, hit);
      return;
    }
    if (hit.layerId === "plans_regpec") {
      await this.fillPlan(body, hit);
      return;
    }
    if (hit.layerId === "zone") {
      await this.fillZone(body, hit);
      return;
    }
    if (hit.layerId === "barrages_cehq") {
      this.fillBarrage(body, hit);
      return;
    }
    body.innerHTML = `<pre class="identify-raw">${escapeHtml(
      JSON.stringify(hit.props, null, 2).slice(0, 2000),
    )}</pre>`;
  }

  private async fillHydro(body: HTMLElement, hit: IdentifyHit): Promise<void> {
    const sid = str(hit.props.station || hit.props.station_id || hit.props.id);
    if (!sid) {
      body.innerHTML = `<p class="identify-error">Station inconnue</p>`;
      return;
    }
    const resp = await fetch(
      `/api/hydromet/${encodeURIComponent(sid)}?include_history=true`,
    );
    if (!resp.ok) {
      body.innerHTML = `<p class="identify-error">Mesures indisponibles (${resp.status})</p>`;
      return;
    }
    const live = (await resp.json()) as HydroResult & Record<string, unknown>;
    body.innerHTML = "";
    const meta = document.createElement("div");
    meta.innerHTML = dl([
      ["Station", sid],
      ["Plan d'eau", uninvertName(str(live.plan_eau || hit.props.plan_eau))],
      ["État", str(live.etat)],
      ["Niveau", live.niveau_m != null ? `${live.niveau_m} m` : ""],
      ["Débit", live.debit_m3s != null ? `${live.debit_m3s} m³/s` : ""],
      ["Observé", str(live.observed_at)],
    ]);
    body.appendChild(meta);
    const charts = document.createElement("div");
    charts.className = "detail-charts";
    body.appendChild(charts);
    if (live.history) {
      renderStationHydroCharts(charts, live);
    } else {
      charts.innerHTML = `<p class="muted">Pas d'historique CEHQ pour cette station.</p>`;
    }
  }

  private async fillTides(body: HTMLElement, hit: IdentifyHit): Promise<void> {
    const code = str(hit.props.code || hit.props.station_code || hit.props.id);
    if (!code) {
      body.innerHTML = `<p class="identify-error">Code de station manquant</p>`;
      return;
    }
    const resp = await fetch(`/api/tides/${encodeURIComponent(code)}?days=3`);
    if (!resp.ok) {
      body.innerHTML = `<p class="identify-error">Marées indisponibles (${resp.status})</p>`;
      return;
    }
    const live = (await resp.json()) as Record<string, unknown>;
    body.innerHTML = "";
    const meta = document.createElement("div");
    meta.innerHTML = dl([
      [
        "Nom",
        str(hit.props.nom || hit.props.officialName || hit.props.name || live.station_nom),
      ],
      ["Code", code],
      [
        "Niveau observé",
        live.niveau_m != null ? `${live.niveau_m} m` : "",
      ],
    ]);
    body.appendChild(meta);
    const curve = (live.curve as { t: number; value: number }[] | undefined) || [];
    const points = curve.length ? curve : tidePoints(live);
    const charts = document.createElement("div");
    charts.className = "detail-charts";
    body.appendChild(charts);
    if (points.length) {
      renderTideChart(charts, points);
    } else {
      charts.innerHTML = `<p class="muted">Pas de série de marée à tracer.</p>`;
    }
  }

  private async fillZone(body: HTMLElement, hit: IdentifyHit): Promise<void> {
    let zoneId = Number(hit.props.zone_id);
    if (!Number.isFinite(zoneId)) {
      const lon = Number(hit.props.lon);
      const lat = Number(hit.props.lat);
      if (!Number.isFinite(lon) || !Number.isFinite(lat)) {
        body.innerHTML = `<p class="identify-error">Zone inconnue</p>`;
        return;
      }
      const atResp = await fetch(
        `/api/zones/at?lon=${encodeURIComponent(String(lon))}&lat=${encodeURIComponent(String(lat))}`,
      );
      if (!atResp.ok) {
        body.innerHTML = `<p class="identify-error">Aucune zone de pêche à cet endroit</p>`;
        return;
      }
      const at = (await atResp.json()) as Record<string, unknown>;
      zoneId = Number(at.zone_id);
    }
    if (!Number.isFinite(zoneId)) {
      body.innerHTML = `<p class="identify-error">Zone inconnue</p>`;
      return;
    }

    body.innerHTML = "";
    const picker = document.createElement("div");
    picker.className = "zone-picker";
    body.appendChild(picker);

    const content = document.createElement("div");
    content.className = "zone-regs-content";
    content.innerHTML = `<p class="muted">Chargement…</p>`;
    body.appendChild(content);

    let zones: ZoneOption[];
    try {
      zones = await loadZoneOptions();
    } catch (err) {
      content.innerHTML = `<p class="identify-error">${escapeHtml(String(err))}</p>`;
      return;
    }

    let selectedId = zoneId;
    const headerTitle = this.el.querySelector<HTMLElement>(".panel-header h2");

    const reload = async (zid: number) => {
      selectedId = zid;
      content.innerHTML = `<p class="muted">Chargement…</p>`;
      const zone = zones.find((z) => z.zone_id === zid);
      if (headerTitle && zone) {
        headerTitle.textContent = `Réglementation — ${zone.zone_nom}`;
      }
      await this.renderZoneReglements(content, zid, zone?.zone_nom);
    };

    mountZonePicker(picker, zones, selectedId, (zone) => {
      if (zone.zone_id === selectedId) return;
      void reload(zone.zone_id);
      void this.map.focusZone(zone.zone_id);
    });

    await reload(selectedId);
  }

  private async renderZoneReglements(
    content: HTMLElement,
    zoneId: number,
    fallbackLabel?: string,
  ): Promise<void> {
    const zoneResp = await fetch(`/api/zones/${zoneId}/reglements?id_kind=regpec`);
    if (!zoneResp.ok) {
      content.innerHTML = `<p class="identify-error">Règles de zone indisponibles (${zoneResp.status})</p>`;
      return;
    }
    const z = (await zoneResp.json()) as Record<string, unknown>;
    const label =
      z.zone_nom ??
      fallbackLabel ??
      (z.no_zone != null ? `Zone ${z.no_zone}` : `Zone ${zoneId}`);
    content.innerHTML = "";
    const wrap = document.createElement("section");
    wrap.className = "detail-reg-block";
    wrap.innerHTML = timelineHtml(
      (z.timeline || {}) as TimelinePayload,
      `${label} — règles générales`,
    );
    content.appendChild(wrap);
  }

  private async fillPlan(body: HTMLElement, hit: IdentifyHit): Promise<void> {
    const zoneId = Number(hit.props.zone_id);
    const planId = Number(hit.props.plan_id);
    if (!Number.isFinite(zoneId) || !Number.isFinite(planId)) {
      body.innerHTML = `<p class="identify-error">Plan incomplet</p>`;
      return;
    }
    const idQ = "id_kind=regpec";
    const [planResp, zoneResp] = await Promise.all([
      fetch(`/api/plans/${zoneId}/${planId}?${idQ}`),
      fetch(`/api/zones/${zoneId}/reglements?${idQ}`),
    ]);
    body.innerHTML = "";
    if (planResp.ok) {
      const d = (await planResp.json()) as Record<string, unknown>;
      const wrap = document.createElement("section");
      wrap.className = "detail-reg-block";
      const nom = uninvertName(str(d.nom || hit.props.nom));
      const zoneLbl = zoneLabelFromProps({
        zone_nom: d.zone_nom,
        no_zone: d.no_zone,
        zone_id: d.zone_id,
      });
      wrap.innerHTML =
        `<p class="muted">${escapeHtml(nom)} · Plan ${d.plan_id}${zoneLbl ? ` · ${escapeHtml(zoneLbl)}` : ""}</p>` +
        timelineHtml((d.timeline || {}) as TimelinePayload, "Exception — plan d'eau");
      body.appendChild(wrap);
    } else {
      body.innerHTML += `<p class="identify-error">Exception introuvable (${planResp.status})</p>`;
    }
    if (zoneResp.ok) {
      const z = (await zoneResp.json()) as Record<string, unknown>;
      const wrap = document.createElement("section");
      wrap.className = "detail-reg-block";
      wrap.innerHTML = timelineHtml(
        (z.timeline || {}) as TimelinePayload,
        `${z.zone_nom ?? `Zone ${z.no_zone ?? z.zone_id}`} — règles générales`,
      );
      body.appendChild(wrap);
    } else {
      body.innerHTML += `<p class="identify-error">Règles de zone indisponibles (${zoneResp.status})</p>`;
    }
  }

  private fillBarrage(body: HTMLElement, hit: IdentifyHit): void {
    const p = hit.props;
    body.innerHTML = dl([
      ["Nom", uninvertName(str(p.nom || p.name))],
      ["N°", str(p.numero)],
      ["Catégorie", str(p.categorie)],
      ["Plan d'eau", uninvertName(str(p.plan_eau))],
      ["Municipalité", str(p.municipalite)],
      ["MRC", str(p.mrc)],
    ]);
    const url = str(p.url_fiche);
    if (url) {
      body.innerHTML += `<p><a href="${escapeHtml(url)}" target="_blank" rel="noopener">Fiche CEHQ</a></p>`;
    }
  }
}

function tidePoints(
  live: Record<string, unknown>,
): { t: number; value: number }[] {
  const out: { t: number; value: number }[] = [];
  const byDay = (live["marées"] || live.marees) as
    | Record<string, { datetime_utc?: string; hauteur_m?: number }[]>
    | undefined;
  if (byDay && typeof byDay === "object") {
    for (const evts of Object.values(byDay)) {
      if (!Array.isArray(evts)) continue;
      for (const e of evts) {
        const iso = e.datetime_utc;
        const v = e.hauteur_m;
        if (!iso || v == null) continue;
        const t = new Date(iso).getTime() / 1000;
        if (Number.isFinite(t)) out.push({ t, value: Number(v) });
      }
    }
  }
  const obs = live.observation as Record<string, unknown> | undefined;
  const wloIso = str(obs?.observed_at_utc || live.observed_at);
  const wloVal = obs?.niveau_m ?? live.niveau_m;
  if (wloIso && wloVal != null) {
    const t = new Date(wloIso).getTime() / 1000;
    if (Number.isFinite(t)) out.push({ t, value: Number(wloVal) });
  }
  return out.sort((a, b) => a.t - b.t);
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

function str(v: unknown): string {
  if (v == null) return "";
  return String(v);
}
