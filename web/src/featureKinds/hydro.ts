/** Stations hydrométriques (Vigilance, Hydro-Québec, CEHQ). */

import { escapeHtml } from "../regs";
import { getLocale, t } from "../i18n";
import { uninvertName } from "../names";
import { renderStationHydroCharts } from "../hydroCharts";
import type { HydroResult } from "../types";
import { dl, errorHtml, linksHtml, str } from "./html";
import { getJson, pick, type FeatureKind, type Props } from "./kind";

type Live = Record<string, unknown>;

const stationId = (p: Props) => str(p.station || p.station_id || p.id);

export const hydroKind: FeatureKind<Live> = {
  title: (p) => String(p.description || p.plan_eau || p.station || t().station),

  pinKey: (p) => pick(p, "station", "station_id", "id") || null,

  async load(p) {
    const sid = stationId(p);
    if (!sid) return undefined;
    return getJson<Live>(`/api/hydromet/${encodeURIComponent(sid)}`);
  },

  popup(p, loaded) {
    const m = t();
    const cached = dl([
      [m.station, stationId(p)],
      [m.waterbody, uninvertName(str(p.plan_eau))],
      [m.cachedState, str(p.etat)],
    ]);
    if (!loaded) return cached;
    if ("status" in loaded) return cached + errorHtml(m.liveUnavailable(loaded.status));
    const live = loaded.data;
    if (live.error) return cached + errorHtml(String(live.error));
    return (
      hydrometMetaHtml(live, p) +
      hqMetricsTableHtml(live.hq_metrics) +
      linksHtml(live.urls as Record<string, string> | undefined)
    );
  },

  // L’historique n’est demandé qu’au détail (lent côté Hydro-Québec / CEHQ).
  async detail(body, hit) {
    const m = t();
    const sid = stationId(hit.props);
    if (!sid) {
      body.innerHTML = errorHtml(m.unknownStation);
      return;
    }
    const loaded = await getJson<HydroResult & Live>(
      `/api/hydromet/${encodeURIComponent(sid)}?include_history=true`,
    );
    if ("status" in loaded) {
      body.innerHTML = errorHtml(m.measuresUnavailable(loaded.status));
      return;
    }
    const live = loaded.data;
    body.innerHTML = "";
    const meta = document.createElement("div");
    meta.innerHTML =
      hydrometMetaHtml(live, hit.props) +
      hqMetricsTableHtml(live.hq_metrics) +
      linksHtml(live.urls as Record<string, string> | undefined);
    body.appendChild(meta);
    const hasHistory =
      live.history &&
      typeof live.history === "object" &&
      Array.isArray(live.history.series) &&
      live.history.series.length > 0;
    if (hasHistory) {
      const charts = document.createElement("div");
      charts.className = "detail-charts";
      body.appendChild(charts);
      renderStationHydroCharts(charts, live);
    }
  },
};

/** Bloc résumé hydro popup / détail (champs vides omis). */
function hydrometMetaHtml(live: Live, props?: Props): string {
  const m = t();
  const sid = str(live.station_id || props?.station || props?.station_id);
  const rows: [string, string][] = [];
  if (sid) rows.push([m.station, sid]);
  const src = formatHydrometSource(str(live.source));
  if (src) rows.push([m.dataSource, src]);
  const plan = uninvertName(str(live.plan_eau || props?.plan_eau));
  if (plan) rows.push([m.waterbody, plan]);
  const etat = str(live.etat);
  if (etat) rows.push([m.state, etat]);
  if (live.niveau_m != null && live.niveau_m !== "")
    rows.push([m.level, `${live.niveau_m} m`]);
  if (live.debit_m3s != null && live.debit_m3s !== "")
    rows.push([m.flow, `${live.debit_m3s} m³/s`]);
  const obs = str(live.observed_at);
  if (obs) rows.push([m.observed, obs]);
  const reg = str(live.hq_region);
  if (reg) rows.push([m.hqRegion, reg]);
  return dl(rows);
}

const WIND_COMPASS_FR = [
  "N",
  "NNE",
  "NE",
  "ENE",
  "E",
  "ESE",
  "SE",
  "SSE",
  "S",
  "SSO",
  "SO",
  "OSO",
  "O",
  "ONO",
  "NO",
  "NNO",
] as const;

const WIND_COMPASS_EN = [
  "N",
  "NNE",
  "NE",
  "ENE",
  "E",
  "ESE",
  "SE",
  "SSE",
  "S",
  "SSW",
  "SW",
  "WSW",
  "W",
  "WNW",
  "NW",
  "NNW",
] as const;

function degToCompass16(deg: number): string {
  const d = ((deg % 360) + 360) % 360;
  const idx = Math.round(d / 22.5) % 16;
  const labels = getLocale() === "fr" ? WIND_COMPASS_FR : WIND_COMPASS_EN;
  return labels[idx] ?? "—";
}

function formatHydrometSource(raw: string): string {
  if (/hydro-qu[eé]bec/i.test(raw)) return "Hydro-Québec";
  return raw;
}

function hqMetricLabel(r: Record<string, unknown>): string {
  const raw = str(r.variable || r.type_point_donnee);
  return raw
    .replace(/\s*—\s*(Moyenne|Instantanée|Maximum|Minimum|Somme)\s*—\s*Horaire$/iu, "")
    .replace(/\s*—\s*Journalier$/iu, "");
}

function hqTypeKey(r: Record<string, unknown>): string {
  return str(r.type_point_donnee).toLowerCase();
}

function isHqWindDirection(r: Record<string, unknown>): boolean {
  const u = str(r.nom_unite_mesure);
  const t = hqTypeKey(r);
  return u === "°" && t.includes("direction") && t.includes("vent");
}

function isHqWindSpeed(r: Record<string, unknown>): boolean {
  const t = hqTypeKey(r);
  return t.includes("vitesse") && t.includes("vent");
}

function isHqTempMin(r: Record<string, unknown>): boolean {
  return hqTypeKey(r).includes("température minimum");
}

function isHqTempMax(r: Record<string, unknown>): boolean {
  return hqTypeKey(r).includes("température maximum");
}

function hqMetricRow(label: string, value: string): string {
  return `<tr><td>${escapeHtml(label)}</td><td>${value}</td></tr>`;
}

function hqMetricsTableHtml(metrics: unknown): string {
  if (!Array.isArray(metrics) || !metrics.length) return "";
  const m = t();
  const rows = metrics.filter(
    (row): row is Record<string, unknown> => !!row && typeof row === "object",
  );
  const used = new Set<Record<string, unknown>>();
  const bodyParts: string[] = [];

  const windDir = rows.find((r) => isHqWindDirection(r));
  const windSpd = rows.find((r) => isHqWindSpeed(r));
  const tempMin = rows.find((r) => isHqTempMin(r));
  const tempMax = rows.find((r) => isHqTempMax(r));

  if (windDir) {
    used.add(windDir);
    const deg = Number(windDir.valeur);
    const compass = Number.isFinite(deg) ? degToCompass16(deg) : "—";
    bodyParts.push(
      hqMetricRow(
        hqMetricLabel(windDir),
        `<strong>${escapeHtml(compass)}</strong> <span class="muted">(${escapeHtml(
          String(windDir.valeur),
        )}°)</span>`,
      ),
    );
  }
  if (windSpd) {
    used.add(windSpd);
    const unit = str(windSpd.nom_unite_mesure);
    bodyParts.push(
      hqMetricRow(
        hqMetricLabel(windSpd),
        `<strong>${escapeHtml(String(windSpd.valeur ?? "—"))}</strong> ${escapeHtml(unit)}`,
      ),
    );
  }
  if (tempMin || tempMax) {
    if (tempMin) used.add(tempMin);
    if (tempMax) used.add(tempMax);
    const vmin = tempMin?.valeur != null ? `${tempMin.valeur} °C` : "—";
    const vmax = tempMax?.valeur != null ? `${tempMax.valeur} °C` : "—";
    bodyParts.push(
      hqMetricRow(
        m.hqTempSpread,
        `<strong>${escapeHtml(vmin)} ~ ${escapeHtml(vmax)}</strong>`,
      ),
    );
  }

  let n = 0;
  for (const r of rows) {
    if (used.has(r)) continue;
    if (n >= 14) break;
    const label = hqMetricLabel(r);
    const val = r.valeur != null ? String(r.valeur) : "—";
    const unit = str(r.nom_unite_mesure);
    bodyParts.push(
      hqMetricRow(
        label,
        `<strong>${escapeHtml(val)}</strong> ${escapeHtml(unit)}`,
      ),
    );
    n += 1;
  }

  if (!bodyParts.length) return "";
  return `<p class="muted identify-hq-hint">${escapeHtml(m.hqSeries)}</p><table class="identify-table"><thead><tr><th>${escapeHtml(
    m.name,
  )}</th><th>${escapeHtml(m.observed)}</th></tr></thead><tbody>${bodyParts.join("")}</tbody></table>`;
}
