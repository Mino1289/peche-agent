/** Stations de marées SHC / IWLS. */

import { escapeHtml } from "../regs";
import { t } from "../i18n";
import { renderTideChart } from "../hydroCharts";
import { dl, errorHtml, linksHtml, str } from "./html";
import { getJson, pick, type FeatureKind, type Props } from "./kind";

type Tides = Record<string, unknown>;

const stationCode = (p: Props) => str(p.code || p.station_code || p.id);
const stationName = (p: Props) => str(p.nom || p.officialName || p.name);

export const tidesKind: FeatureKind<Tides> = {
  title: (p) => String(p.nom || p.officialName || p.name || p.code || "Station de marée"),

  pinKey: (p) => pick(p, "code", "station_code", "id") || null,

  popupClass: "identify-popup--tides",

  async load(p) {
    const code = stationCode(p);
    if (!code) return undefined;
    // days=3 couvre le popup (4 lignes max) et la courbe du détail.
    return getJson<Tides>(`/api/tides/${encodeURIComponent(code)}?days=3`);
  },

  popup(p, loaded) {
    const m = t();
    const code = stationCode(p);
    if (!loaded) return dl([[m.name, stationName(p)]]);
    if ("status" in loaded) return errorHtml(m.tidesUnavailable(loaded.status));
    const live = loaded.data;
    if (live.error && live.niveau_m == null) return errorHtml(String(live.error));
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
    const table = tideTableHtml(lignes, 4);
    return (
      dl([
        [m.name, str(stationName(p) || live.station_nom)],
        ["Code", code],
      ]) +
      latest +
      table +
      linksHtml(live.urls as Record<string, string> | undefined)
    );
  },

  detail(body, hit, loaded) {
    const m = t();
    const code = stationCode(hit.props);
    if (!loaded) {
      body.innerHTML = errorHtml(m.missingTideCode);
      return;
    }
    if ("status" in loaded) {
      body.innerHTML = errorHtml(m.tidesUnavailable(loaded.status));
      return;
    }
    const live = loaded.data;
    body.innerHTML = "";
    const meta = document.createElement("div");
    const lignes =
      (live.table as { lignes?: Record<string, unknown>[] } | undefined)?.lignes || [];
    meta.innerHTML =
      dl([
        [m.name, str(stationName(hit.props) || live.station_nom)],
        ["Code", code],
        [m.observedLevel, live.niveau_m != null ? `${live.niveau_m} m` : ""],
      ]) +
      tideTableHtml(lignes, undefined, true) +
      linksHtml(live.urls as Record<string, string> | undefined);
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
  },
};

function tideTableHtml(
  lignes: Record<string, unknown>[],
  maxRows?: number,
  splitDayCol = false,
): string {
  const rows = maxRows != null ? lignes.slice(0, maxRows) : lignes;
  if (!rows.length) return "";
  const m = t();
  if (!splitDayCol) {
    let table = `<table class="identify-table identify-table--tides"><thead><tr><th>${escapeHtml(m.day)}</th><th>${escapeHtml(m.lowTide1)}</th><th>${escapeHtml(m.highTide1)}</th><th>${escapeHtml(m.lowTide2)}</th><th>${escapeHtml(m.highTide2)}</th></tr></thead><tbody>`;
    for (const row of rows) {
      table += tideTableRowHtml(row);
    }
    table += `</tbody></table>`;
    return table;
  }
  let dayTable = `<table class="identify-table identify-table--tides tide-table-day"><thead><tr><th>${escapeHtml(m.day)}</th></tr></thead><tbody>`;
  let colsTable = `<table class="identify-table identify-table--tides tide-table-cols"><thead><tr><th>${escapeHtml(m.lowTide1)}</th><th>${escapeHtml(m.highTide1)}</th><th>${escapeHtml(m.lowTide2)}</th><th>${escapeHtml(m.highTide2)}</th></tr></thead><tbody>`;
  for (const row of rows) {
    dayTable += `<tr><td>${escapeHtml(str(row.jour))}</td></tr>`;
    colsTable += `<tr><td>${escapeHtml(tideTableCell(row, "basse_1"))}</td><td>${escapeHtml(
      tideTableCell(row, "haute_1"),
    )}</td><td>${escapeHtml(tideTableCell(row, "basse_2"))}</td><td>${escapeHtml(
      tideTableCell(row, "haute_2"),
    )}</td></tr>`;
  }
  dayTable += `</tbody></table>`;
  colsTable += `</tbody></table>`;
  return `<div class="tide-table-split">${dayTable}<div class="tide-table-cols-scroll">${colsTable}</div></div>`;
}

function tideTableRowHtml(row: Record<string, unknown>): string {
  return `<tr><td>${escapeHtml(str(row.jour))}</td><td>${escapeHtml(
    tideTableCell(row, "basse_1"),
  )}</td><td>${escapeHtml(tideTableCell(row, "haute_1"))}</td><td>${escapeHtml(
    tideTableCell(row, "basse_2"),
  )}</td><td>${escapeHtml(tideTableCell(row, "haute_2"))}</td></tr>`;
}

function tideTableCell(row: Record<string, unknown>, suffix: string): string {
  const k = `maree_${suffix}`;
  return str(row[k] ?? row[`marée_${suffix}`] ?? "");
}

function tidePoints(live: Tides): { t: number; value: number }[] {
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
