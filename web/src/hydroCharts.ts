/** Tableau comparatif + graphiques niveau/débit (port Streamlit → uPlot). */

import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";

import type {
  HydroDailyPoint,
  HydroHistory,
  HydroResult,
  HydroSeriesPoint,
  ToolEntry,
} from "./types";

const HYDRO_TOOLS = new Set([
  "get_hydromet",
  "get_hydromet_at_plan",
  "get_hydromet_for_waterbody",
]);

const SERIES_COLORS = [
  "#2dd4bf",
  "#60a5fa",
  "#f472b6",
  "#fbbf24",
  "#a78bfa",
  "#34d399",
  "#fb923c",
  "#e879f9",
];

const plotsByRoot = new WeakMap<HTMLElement, uPlot[]>();

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function formatHydroValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    return Number.isFinite(value) ? String(Number(value.toPrecision(6))) : "—";
  }
  return String(value);
}

function hydroLabel(result: HydroResult): string {
  const desc = result.description || "";
  if (desc) {
    if (desc.toLowerCase().includes("barrage")) {
      const after = desc.split(/barrage/i).slice(1).join("barrage");
      for (const part of after.split(/\s+/)) {
        const cleaned = part.replace(/^[ .,\-]+|[ .,\-]+$/g, "");
        if (cleaned && cleaned.length > 2) return cleaned;
      }
    }
    if (desc.length <= 60) return desc;
    return desc.slice(0, 57) + "…";
  }
  const raw =
    result.plan_nom ||
    result.plan_eau ||
    (result.station_id != null ? String(result.station_id) : "Station");
  const text = String(raw);
  if (text.includes(" - ")) return text.split(" - ", 1)[0].trim();
  return text;
}

function flattenWaterbodyResult(wb: HydroResult): HydroResult[] {
  if (wb.error || wb.error_no_station) return [wb];
  const planNom = wb.plan_nom || "";
  const metrics = wb.requested_metrics || "both";
  const out: HydroResult[] = [];
  for (const st of wb.stations || []) {
    if (!st || typeof st !== "object") continue;
    const s = st as HydroResult;
    out.push({
      plan_nom: planNom,
      requested_metrics: metrics,
      station_id: s.station_id,
      plan_eau: s.plan_eau,
      description: s.description,
      distance_km: s.distance_km,
      match_reason: s.match_reason,
      niveau_m: s.niveau_m,
      debit_m3s: s.debit_m3s,
      observed_at: s.observed_at,
      history: s.history,
      error: s.error,
    });
  }
  return out.length ? out : [wb];
}

function hydroResultScore(r: HydroResult): number {
  let s = 0;
  if (r.history) s += 4;
  if (r.niveau_m != null) s += 1;
  if (r.debit_m3s != null) s += 1;
  if (r.observed_at) s += 1;
  return s;
}

export function collectHydroResults(tools: ToolEntry[]): HydroResult[] {
  const byStation = new Map<string, HydroResult>();
  const unkeyed: HydroResult[] = [];
  for (const entry of tools) {
    if (!HYDRO_TOOLS.has(entry.name)) continue;
    if (entry.result == null) continue;
    if (typeof entry.result !== "object") continue;
    const result = entry.result as HydroResult;
    const flat =
      entry.name === "get_hydromet_for_waterbody"
        ? flattenWaterbodyResult(result)
        : [result];
    for (const r of flat) {
      const sid = r.station_id != null ? String(r.station_id) : "";
      if (!sid) {
        unkeyed.push(r);
        continue;
      }
      const prev = byStation.get(sid);
      if (!prev || hydroResultScore(r) > hydroResultScore(prev)) {
        byStation.set(sid, r);
      }
    }
  }
  return [...byStation.values(), ...unkeyed];
}

function hydroMetricsMode(results: HydroResult[]): "level" | "flow" | "both" {
  for (const r of results) {
    const m = r.requested_metrics;
    if (m === "level" || m === "flow" || m === "both") return m;
  }
  return "both";
}

function uniqueChartLabel(base: string, used: Set<string>): string {
  let label = base || "Station";
  let suffix = 2;
  while (used.has(label)) {
    label = `${base} (${suffix})`;
    suffix += 1;
  }
  used.add(label);
  return label;
}

function destroyPlots(root: HTMLElement): void {
  const plots = plotsByRoot.get(root);
  if (plots) {
    for (const p of plots) {
      try {
        p.destroy();
      } catch {
        /* ignore */
      }
    }
    plotsByRoot.delete(root);
  }
}

export function destroyHydroCharts(el: HTMLElement): void {
  destroyPlots(el);
  el.innerHTML = "";
}

function parseSeries(
  series: HydroSeriesPoint[],
): { xs: number[]; niveaux: (number | null)[]; debits: (number | null)[] } {
  const xs: number[] = [];
  const niveaux: (number | null)[] = [];
  const debits: (number | null)[] = [];
  const sorted = [...series].sort(
    (a, b) =>
      new Date(a.observed_at).getTime() - new Date(b.observed_at).getTime(),
  );
  for (const pt of sorted) {
    const t = new Date(pt.observed_at).getTime() / 1000;
    if (!Number.isFinite(t)) continue;
    xs.push(t);
    niveaux.push(
      typeof pt.niveau_m === "number" && Number.isFinite(pt.niveau_m)
        ? pt.niveau_m
        : null,
    );
    debits.push(
      typeof pt.debit_m3s === "number" && Number.isFinite(pt.debit_m3s)
        ? pt.debit_m3s
        : null,
    );
  }
  return { xs, niveaux, debits };
}

function fmtAxisTime(ts: number): string {
  const d = new Date(ts * 1000);
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  return `${dd}/${mm} ${hh}h`;
}

function makePlot(
  target: HTMLElement,
  title: string,
  xs: number[],
  series: { label: string; values: (number | null)[]; color: string }[],
): uPlot | null {
  if (!xs.length || !series.length) return null;
  const width = Math.max(240, Math.floor(target.clientWidth || target.parentElement?.clientWidth || 320));
  const opts: uPlot.Options = {
    width,
    height: 160,
    title,
    class: "hydro-uplot",
    scales: {
      x: { time: true },
    },
    axes: [
      {
        stroke: "#94a3b8",
        grid: { stroke: "#1e293b", width: 1 },
        ticks: { stroke: "#334155" },
        values: (_u, splits) => splits.map((v) => fmtAxisTime(v)),
        font: "10px sans-serif",
        size: 40,
      },
      {
        stroke: "#94a3b8",
        grid: { stroke: "#1e293b", width: 1 },
        ticks: { stroke: "#334155" },
        font: "10px sans-serif",
        size: 48,
      },
    ],
    series: [
      {},
      ...series.map((s) => ({
        label: s.label,
        stroke: s.color,
        width: 1.5,
        spanGaps: false,
        points: { show: false },
      })),
    ],
    legend: {
      show: series.length > 1,
    },
    cursor: {
      focus: { prox: 24 },
    },
  };
  const data: uPlot.AlignedData = [xs, ...series.map((s) => s.values)];
  return new uPlot(opts, data, target);
}

function renderDailyTable(
  container: HTMLElement,
  blocks: { label: string; daily: HydroDailyPoint[] }[],
): void {
  if (!blocks.length) return;
  const details = document.createElement("details");
  details.className = "hydro-daily";
  details.innerHTML = `<summary>Résumé${blocks.length > 1 ? "s" : ""} journalier${blocks.length > 1 ? "s" : ""}</summary>`;
  for (const block of blocks) {
    if (blocks.length > 1) {
      const h = document.createElement("div");
      h.className = "hydro-daily-label";
      h.textContent = block.label;
      details.appendChild(h);
    }
    const table = document.createElement("table");
    table.className = "hydro-table hydro-daily-table";
    const keys = Object.keys(block.daily[0] || {});
    table.innerHTML = `<thead><tr>${keys.map((k) => `<th>${escapeHtml(k)}</th>`).join("")}</tr></thead>`;
    const tbody = document.createElement("tbody");
    for (const row of block.daily) {
      const tr = document.createElement("tr");
      tr.innerHTML = keys
        .map((k) => `<td>${escapeHtml(formatHydroValue((row as Record<string, unknown>)[k]))}</td>`)
        .join("");
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    details.appendChild(table);
  }
  container.appendChild(details);
}

function renderHydroSummaryTable(
  container: HTMLElement,
  results: HydroResult[],
): void {
  const metrics = hydroMetricsMode(results);
  const rows: Record<string, string>[] = [];

  for (const result of results) {
    const planLabel = result.plan_nom || hydroLabel(result);
    const stationLabel = hydroLabel(result);
    if (result.error_no_station) {
      rows.push({
        "Plan d'eau": planLabel,
        Station: "—",
        "Niveau (m)": "—",
        "Débit (m³/s)": "—",
        Observé: "—",
        Note: "Pas de station à moins de 25 km",
      });
      continue;
    }
    if (result.error) {
      rows.push({
        "Plan d'eau": planLabel,
        Station: stationLabel,
        "Niveau (m)": "—",
        "Débit (m³/s)": "—",
        Observé: "—",
        Note: String(result.error),
      });
      continue;
    }

    const history =
      result.history && typeof result.history === "object"
        ? result.history
        : ({} as HydroHistory);
    const trend =
      history.trend && typeof history.trend === "object" ? history.trend : {};
    const station =
      result.matched_station_plan_eau || result.plan_eau || "";
    let note = "";
    if (result.distance_km != null) note = `${result.distance_km} km`;
    if (result.match_reason === "geo" && station) {
      note = `rivière voisine (${station}). ${note}`.trim();
    }

    const row: Record<string, string> = {
      "Plan d'eau": planLabel,
      Station: stationLabel,
      Observé: formatHydroValue(result.observed_at),
      Note: note || "—",
    };
    if (metrics === "level" || metrics === "both") {
      row["Niveau (m)"] = formatHydroValue(result.niveau_m);
      if (trend.niveau_m) row["Tendance niveau"] = formatHydroValue(trend.niveau_m);
    }
    if (metrics === "flow" || metrics === "both") {
      row["Débit (m³/s)"] = formatHydroValue(result.debit_m3s);
      if (trend.debit_m3s) row["Tendance débit"] = formatHydroValue(trend.debit_m3s);
    }
    rows.push(row);
  }

  if (!rows.length) return;

  const title = document.createElement("div");
  title.className = "hydro-section-title";
  title.textContent = "Comparatif hydrométrique";
  container.appendChild(title);

  // Colonnes stables dans un ordre lisible
  const preferred = [
    "Plan d'eau",
    "Station",
    "Niveau (m)",
    "Tendance niveau",
    "Débit (m³/s)",
    "Tendance débit",
    "Observé",
    "Note",
  ];
  const present = new Set(rows.flatMap((r) => Object.keys(r)));
  const cols = preferred.filter((c) => present.has(c));

  const table = document.createElement("table");
  table.className = "hydro-table";
  table.innerHTML = `<thead><tr>${cols.map((c) => `<th>${escapeHtml(c)}</th>`).join("")}</tr></thead>`;
  const tbody = document.createElement("tbody");
  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = cols
      .map((c) => `<td>${escapeHtml(row[c] ?? "—")}</td>`)
      .join("");
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  container.appendChild(table);
}

function renderHydroHistory(
  container: HTMLElement,
  result: HydroResult,
  metrics: "level" | "flow" | "both",
  plots: uPlot[],
): void {
  const history = result.history;
  if (!history || typeof history !== "object") return;
  const series = history.series;
  if (!series?.length) return;

  const label = hydroLabel(result);
  if (label) {
    const h = document.createElement("div");
    h.className = "hydro-station-label";
    h.textContent = label;
    container.appendChild(h);
  }

  const period = history.period_days ?? 7;
  const caption = document.createElement("div");
  caption.className = "hydro-caption";
  caption.textContent = `Historique CEHQ — ${period} derniers jours (points horaires)`;
  container.appendChild(caption);

  const { xs, niveaux, debits } = parseSeries(series);
  if (!xs.length) return;

  if (
    (metrics === "level" || metrics === "both") &&
    history.has_niveau &&
    niveaux.some((v) => v != null)
  ) {
    const wrap = document.createElement("div");
    wrap.className = "hydro-chart-wrap";
    container.appendChild(wrap);
    const plot = makePlot(wrap, "Niveau (m)", xs, [
      { label: "Niveau (m)", values: niveaux, color: SERIES_COLORS[0] },
    ]);
    if (plot) plots.push(plot);
  }

  if (
    (metrics === "flow" || metrics === "both") &&
    history.has_debit &&
    debits.some((v) => v != null)
  ) {
    const wrap = document.createElement("div");
    wrap.className = "hydro-chart-wrap";
    container.appendChild(wrap);
    const plot = makePlot(wrap, "Débit (m³/s)", xs, [
      { label: "Débit (m³/s)", values: debits, color: SERIES_COLORS[1] },
    ]);
    if (plot) plots.push(plot);
  }

  if (history.daily?.length) {
    renderDailyTable(container, [{ label, daily: history.daily }]);
  }
}

function renderCombinedHydroCharts(
  container: HTMLElement,
  results: HydroResult[],
  metrics: "level" | "flow" | "both",
  plots: uPlot[],
): void {
  type SeriesBag = { label: string; xs: number[]; values: (number | null)[] };
  const debitSeries: SeriesBag[] = [];
  const niveauSeries: SeriesBag[] = [];
  const usedLabels = new Set<string>();
  let period: number | null = null;

  for (const result of results) {
    const history = result.history;
    if (!history || typeof history !== "object") continue;
    const series = history.series;
    if (!series?.length) continue;

    const label = uniqueChartLabel(hydroLabel(result), usedLabels);
    period = history.period_days ?? period;

    const { xs, niveaux, debits } = parseSeries(series);
    if (!xs.length) continue;

    if (
      (metrics === "flow" || metrics === "both") &&
      history.has_debit &&
      debits.some((v) => v != null)
    ) {
      debitSeries.push({ label, xs, values: debits });
    }
    if (
      (metrics === "level" || metrics === "both") &&
      history.has_niveau &&
      niveaux.some((v) => v != null)
    ) {
      niveauSeries.push({ label, xs, values: niveaux });
    }
  }

  if (!debitSeries.length && !niveauSeries.length) return;

  const days = period ?? 7;
  const caption = document.createElement("div");
  caption.className = "hydro-caption";
  caption.textContent = `Historique CEHQ — ${days} derniers jours (comparaison, points horaires)`;
  container.appendChild(caption);

  function alignAndPlot(
    title: string,
    seriesList: SeriesBag[],
  ): void {
    if (!seriesList.length) return;
    // Union des timestamps, alignement avec nulls
    const allTs = new Set<number>();
    for (const s of seriesList) for (const t of s.xs) allTs.add(t);
    const xs = [...allTs].sort((a, b) => a - b);
    const aligned = seriesList.map((s, i) => {
      const map = new Map<number, number | null>();
      s.xs.forEach((t, idx) => map.set(t, s.values[idx]));
      return {
        label: s.label,
        values: xs.map((t) => (map.has(t) ? map.get(t)! : null)),
        color: SERIES_COLORS[i % SERIES_COLORS.length],
      };
    });
    const wrap = document.createElement("div");
    wrap.className = "hydro-chart-wrap";
    container.appendChild(wrap);
    const plot = makePlot(wrap, title, xs, aligned);
    if (plot) plots.push(plot);
  }

  alignAndPlot("Niveau (m)", niveauSeries);
  alignAndPlot("Débit (m³/s)", debitSeries);

  const dailyBlocks = results
    .filter(
      (r) =>
        r.history &&
        typeof r.history === "object" &&
        Array.isArray(r.history.daily) &&
        r.history.daily.length,
    )
    .map((r) => ({
      label: hydroLabel(r),
      daily: r.history!.daily!,
    }));
  renderDailyTable(container, dailyBlocks);
}

/** Orchestrateur : tableau + graphiques (même logique que Streamlit master). */
export function renderVisibleHydroOutputs(
  el: HTMLElement,
  tools: ToolEntry[] | undefined,
): void {
  destroyPlots(el);
  el.innerHTML = "";
  if (!tools?.length) {
    el.hidden = true;
    return;
  }

  const results = collectHydroResults(tools);
  if (!results.length) {
    el.hidden = true;
    return;
  }

  el.hidden = false;
  const plots: uPlot[] = [];
  plotsByRoot.set(el, plots);

  const metrics = hydroMetricsMode(results);
  const withHistory = results.filter(
    (r) =>
      r.history &&
      typeof r.history === "object" &&
      Array.isArray(r.history.series) &&
      r.history.series.length,
  );

  renderHydroSummaryTable(el, results);

  if (withHistory.length >= 2) {
    renderCombinedHydroCharts(el, withHistory, metrics, plots);
  } else if (withHistory.length === 1) {
    renderHydroHistory(el, withHistory[0], metrics, plots);
  }

  // Redimensionner si le panneau change de largeur
  requestAnimationFrame(() => {
    const w = Math.max(240, Math.floor(el.clientWidth || 320));
    for (const p of plots) {
      if (p.width !== w) p.setSize({ width: w, height: p.height });
    }
  });
}

/** Graphiques d'une station pour le panneau détail carte. */
export function renderStationHydroCharts(
  el: HTMLElement,
  result: HydroResult,
): void {
  destroyPlots(el);
  el.innerHTML = "";
  const plots: uPlot[] = [];
  plotsByRoot.set(el, plots);
  const metrics = hydroMetricsMode([result]);
  renderHydroHistory(el, result, metrics, plots);
  requestAnimationFrame(() => {
    const w = Math.max(240, Math.floor(el.clientWidth || 320));
    for (const p of plots) {
      if (p.width !== w) p.setSize({ width: w, height: p.height });
    }
  });
}

export function renderTideChart(
  el: HTMLElement,
  points: { t: number; value: number; kind?: string }[],
): void {
  destroyPlots(el);
  el.innerHTML = "";
  if (!points.length) return;
  const sorted = [...points].sort((a, b) => a.t - b.t);
  const xs = sorted.map((p) => p.t);
  const values = sorted.map((p) => p.value);
  const wrap = document.createElement("div");
  wrap.className = "hydro-chart-wrap";
  el.appendChild(wrap);
  const plot = makePlot(wrap, "Hauteur (m)", xs, [
    { label: "Marée (m)", values, color: SERIES_COLORS[1] },
  ]);
  if (plot) {
    plotsByRoot.set(el, [plot]);
    requestAnimationFrame(() => {
      const w = Math.max(240, Math.floor(el.clientWidth || 320));
      if (plot.width !== w) plot.setSize({ width: w, height: plot.height });
    });
  }
}
