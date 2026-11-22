/** Tableau comparatif + graphiques niveau/débit (uPlot). */

import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";

import type {
  HydroHistory,
  HydroResult,
  HydroSeriesPoint,
  ToolEntry,
} from "./types";
import { t } from "./i18n";
import { uninvertName } from "./names";

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

const NEAREST_SAMPLE_WINDOW_SEC = 3600;

const plotsByRoot = new WeakMap<HTMLElement, uPlot[]>();
const observersByRoot = new WeakMap<HTMLElement, ResizeObserver>();

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

function truncateLabel(text: string, max: number): string {
  const clean = text.trim().replace(/\s+/g, " ");
  if (clean.length <= max) return clean;
  return clean.slice(0, max - 1).trimEnd() + "…";
}

function shortDescriptionTag(desc: string): string {
  const d = desc.trim();
  if (!d) return "";
  if (d.toLowerCase().includes("barrage")) {
    const after = d.split(/barrage/i).slice(1).join("barrage");
    const m = after.match(/\b(?:de\s+la\s+|du\s+|des\s+|de\s+|d['’])?([A-Za-zÀ-ÿ0-9][\wÀ-ÿ'-]*(?:-[\wÀ-ÿ']+)*)/u);
    if (m && m[1] && m[1].length > 2) return truncateLabel(m[1], 22);
  }
  return truncateLabel(d, 22);
}

/** Libellé complet (tableau / infobulle HTML). */
function hydroFullLabel(result: HydroResult): string {
  const water = uninvertName(String(result.plan_nom || result.plan_eau || "")).trim();
  const desc = (result.description || "").trim();
  if (water && desc && !desc.toLowerCase().includes(water.toLowerCase())) {
    return `${water} — ${desc}`;
  }
  return water || desc || (result.station_id != null ? String(result.station_id) : "Station");
}

/** Libellé court pour légende, pastilles et curseur graphique. */
export function hydroShortLabel(result: HydroResult, disambiguate = false): string {
  const water = uninvertName(String(result.plan_nom || result.plan_eau || "")).trim();
  const desc = (result.description || "").trim();
  if (water) {
    if (disambiguate) {
      const tag = shortDescriptionTag(desc) || (result.station_id != null ? String(result.station_id) : "");
      if (tag && tag.toLowerCase() !== water.toLowerCase()) {
        return truncateLabel(`${water} (${tag})`, 30);
      }
    }
    return truncateLabel(water, 26);
  }
  if (desc) {
    const first = desc.includes(" - ") ? desc.split(" - ", 1)[0].trim() : desc;
    return truncateLabel(first, 26);
  }
  return result.station_id != null ? String(result.station_id) : "Station";
}

function buildShortLabels(results: HydroResult[]): string[] {
  const bases = results.map((r) => hydroShortLabel(r, false));
  const counts = new Map<string, number>();
  for (const b of bases) counts.set(b, (counts.get(b) || 0) + 1);
  const used = new Set<string>();
  return results.map((r, i) => {
    const base = (counts.get(bases[i]) || 0) > 1 ? hydroShortLabel(r, true) : bases[i];
    return uniqueChartLabel(base, used);
  });
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

function isHqHistorySource(src: string | undefined): boolean {
  if (!src) return false;
  if (src === "hydroquebec_open") return true;
  const s = src.toLowerCase();
  return s.includes("hydroquebec.com") || s.includes("hydro-québec");
}

function hydroHistoryCaption(
  history: HydroHistory,
  mode: "single" | "compare",
): string {
  const m = t();
  const period = history.period_days ?? 7;
  if (isHqHistorySource(history.source)) {
    return m.hydroHistoryHq(period);
  }
  if (mode === "compare") return m.hydroHistoryCompareCeHQ(period);
  return m.hydroHistoryCeHQ(period);
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
  const obs = observersByRoot.get(root);
  if (obs) {
    obs.disconnect();
    observersByRoot.delete(root);
  }
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
    const ts = new Date(pt.observed_at).getTime() / 1000;
    if (!Number.isFinite(ts)) continue;
    xs.push(ts);
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

const DAY_TIME_INCRS_SEC = [24 * 3600, 2 * 24 * 3600, 7 * 24 * 3600];
/** doit correspondre à `xAxisDaily().size` */
const X_AXIS_CSS_PX = 36;

function fmtAxisDay(ts: number): string {
  const d = new Date(ts * 1000);
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  return `${dd}/${mm}`;
}

function axisDayTickValues(_u: uPlot, splits: number[]): string[] {
  let last = "";
  return splits.map((ts) => {
    const d = new Date(ts * 1000);
    const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
    if (key === last) return "";
    last = key;
    return fmtAxisDay(ts);
  });
}

function xAxisDaily(): uPlot.Axis {
  return {
    stroke: "#a1a1aa",
    grid: { stroke: "#27272a", width: 1 },
    ticks: { stroke: "#3f3f46" },
    space: 36,
    incrs: DAY_TIME_INCRS_SEC,
    values: axisDayTickValues,
    font: "10px sans-serif",
    size: 36,
  };
}

function fmtCursorTime(ts: number): string {
  const d = new Date(ts * 1000);
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  return `${dd}/${mm} ${hh}:${mi}`;
}

/** Compacité axe / infobulle : ~5 chiffres + décimale (ex. 557.4, 12.34, 1234). */
function formatChartNumber(y: number): string {
  if (!Number.isFinite(y)) return "";
  const a = Math.abs(y);
  if (a >= 10_000) return y.toFixed(0);
  if (a >= 1000) return y.toFixed(1);
  if (a >= 100) return y.toFixed(1);
  if (a >= 10) return y.toFixed(2);
  if (a >= 1) return y.toFixed(2);
  return y.toFixed(3);
}

function formatCursorY(title: string, y: number): string {
  const n = formatChartNumber(y);
  if (title.includes("Débit")) return `${n} m³/s`;
  return `${n} m`;
}

function formatAxisY(_title: string, y: number): string {
  if (!Number.isFinite(y)) return "";
  return formatChartNumber(y);
}

function innerWidth(el: HTMLElement): number {
  const cs = typeof getComputedStyle === "function" ? getComputedStyle(el) : null;
  const pad = cs
    ? (parseFloat(cs.paddingLeft) || 0) + (parseFloat(cs.paddingRight) || 0)
    : 0;
  const raw = Math.floor((el.clientWidth || el.parentElement?.clientWidth || 320) - pad);
  return Math.max(220, raw);
}

function nearestDataIdx(u: uPlot, mouseLeft: number): number {
  const xs = u.data[0] as number[];
  if (!xs.length) return 0;
  const xVal = u.posToVal(mouseLeft, "x");
  let best = 0;
  let bestD = Infinity;
  for (let i = 0; i < xs.length; i++) {
    const d = Math.abs(xs[i] - xVal);
    if (d < bestD) {
      bestD = d;
      best = i;
    }
  }
  return best;
}

/** Valeur au point `idx` ou, en cas d'horodatages décalés, voisin le plus proche ≤ 1 h. */
function valueNearIdx(
  xs: number[],
  vals: (number | null | undefined)[],
  idx: number,
): number | null {
  const direct = vals[idx];
  if (direct != null && Number.isFinite(direct)) return direct;
  const t0 = xs[idx];
  if (!Number.isFinite(t0)) return null;
  let bestVal: number | null = null;
  let bestDt = NEAREST_SAMPLE_WINDOW_SEC + 1;
  for (let d = 1; d <= 4; d++) {
    for (const j of [idx - d, idx + d]) {
      if (j < 0 || j >= xs.length) continue;
      const dt = Math.abs(xs[j] - t0);
      if (dt >= bestDt) continue;
      const v = vals[j];
      if (v != null && Number.isFinite(v)) {
        bestDt = dt;
        bestVal = v;
      }
    }
  }
  return bestVal;
}

export function snapCursorToData(
  u: uPlot,
  mouseLeft: number,
  mouseTop: number,
): uPlot.Cursor.LeftTop {
  // Hors du tracé (initialisation / mouseleave) : ne jamais coller au point 0.
  if (mouseLeft < 0 || mouseTop < 0 || !Number.isFinite(mouseLeft) || !Number.isFinite(mouseTop)) {
    return [mouseLeft, mouseTop];
  }
  const xs = u.data[0] as number[];
  if (!xs.length) return [mouseLeft, mouseTop];
  const idx = nearestDataIdx(u, mouseLeft);
  const x = xs[idx];
  const left = u.valToPos(x, "x");
  if (!Number.isFinite(left)) return [mouseLeft, mouseTop];

  let bestTop = mouseTop;
  let bestDist = Infinity;
  for (let si = 1; si < u.data.length; si++) {
    if (u.series[si]?.show === false) continue;
    const v = valueNearIdx(xs, u.data[si] as (number | null | undefined)[], idx);
    if (v == null) continue;
    const pos = u.valToPos(v, "y");
    if (!Number.isFinite(pos)) continue;
    const dist = Math.abs(pos - mouseTop);
    if (dist < bestDist) {
      bestDist = dist;
      bestTop = pos;
    }
  }
  return [left, bestTop];
}

function resetChartZoom(u: uPlot): void {
  u.setData(u.data, true);
}

function hydroChartCursor(): uPlot.Cursor {
  return {
    x: true,
    y: true,
    focus: { prox: 16 },
    hover: { prox: 16 },
    points: {
      show: true,
      one: true,
      size: 8,
      stroke: "#f4f4f5",
      width: 2,
    },
    drag: { setScale: false, x: false, y: false },
    move: snapCursorToData,
  };
}

function chartCursorLabelHooks(title: string): uPlot.Hooks.Arrays {
  let xLabel: HTMLDivElement | null = null;
  let yLabel: HTMLDivElement | null = null;

  const hide = () => {
    if (xLabel) xLabel.hidden = true;
    if (yLabel) yLabel.hidden = true;
  };

  const syncLabels = (u: uPlot) => {
    if (!xLabel || !yLabel) return;
    const { left, top, idx } = u.cursor;
    if (
      left == null ||
      top == null ||
      !Number.isFinite(left) ||
      !Number.isFinite(top) ||
      left < 0 ||
      top < 0
    ) {
      hide();
      return;
    }
    const xs = u.data[0] as number[];
    const pickIdx = idx != null && idx >= 0 ? idx : nearestDataIdx(u, left);
    const xVal = xs[pickIdx];
    if (!Number.isFinite(xVal)) {
      hide();
      return;
    }

    const visibleIndices: number[] = [];
    for (let si = 1; si < u.data.length; si++) {
      if (u.series[si]?.show !== false) visibleIndices.push(si);
    }
    const multi = visibleIndices.length > 1;

    type Row = { si: number; label: string; color: string; value: string; dist: number };
    const rows: Row[] = [];
    for (const si of visibleIndices) {
      const v = valueNearIdx(xs, u.data[si] as (number | null | undefined)[], pickIdx);
      if (v == null) continue;
      const pos = u.valToPos(v, "y");
      const color = typeof u.series[si]?.stroke === "string"
        ? (u.series[si].stroke as string)
        : SERIES_COLORS[(si - 1) % SERIES_COLORS.length];
      rows.push({
        si,
        label: String(u.series[si]?.label ?? ""),
        color,
        value: formatCursorY(title, v),
        dist: Number.isFinite(pos) ? Math.abs(pos - top) : Infinity,
      });
    }

    if (!rows.length) {
      hide();
      return;
    }

    let focusedSi = rows[0].si;
    let minD = rows[0].dist;
    for (const r of rows) {
      if (r.dist < minD) {
        minD = r.dist;
        focusedSi = r.si;
      }
    }

    const plotLft = u.over.offsetLeft;
    const plotTop = u.over.offsetTop;
    const plotW = u.over.clientWidth;
    const plotH = u.over.clientHeight;

    xLabel.textContent = fmtCursorTime(xVal);
    const xLeft = Math.max(plotLft + 34, Math.min(plotLft + left, plotLft + plotW - 34));
    xLabel.style.left = `${xLeft}px`;
    xLabel.style.top = `${plotTop + plotH + X_AXIS_CSS_PX / 2}px`;
    xLabel.removeAttribute("hidden");

    if (multi) {
      yLabel.innerHTML = rows
        .map(
          (r) =>
            `<div class="hydro-tip-row${r.si === focusedSi ? " is-focused" : ""}">` +
            `<span class="hydro-tip-dot" style="background:${r.color}"></span>` +
            `<span class="hydro-tip-name">${escapeHtml(r.label)}</span>` +
            `<strong class="hydro-tip-val">${escapeHtml(r.value)}</strong>` +
            `</div>`,
        )
        .join("");
    } else {
      yLabel.textContent = rows[0].value;
    }

    const tipLeft = plotLft + left;
    const flip = tipLeft > plotLft + plotW * 0.58;
    const clampedTop = Math.max(plotTop + 14, Math.min(plotTop + top, plotTop + plotH - 14));
    yLabel.style.left = `${tipLeft}px`;
    yLabel.style.top = `${clampedTop}px`;
    yLabel.dataset.flip = flip ? "1" : "0";
    yLabel.removeAttribute("hidden");
  };

  return {
    init: [
      (u) => {
        const wrap = u.root.querySelector(".u-wrap") as HTMLElement | null;
        if (!wrap) return;
        wrap.style.overflow = "visible";
        xLabel = document.createElement("div");
        xLabel.className = "hydro-cursor-x";
        xLabel.hidden = true;
        yLabel = document.createElement("div");
        yLabel.className = "hydro-cursor-y";
        yLabel.hidden = true;
        wrap.appendChild(xLabel);
        wrap.appendChild(yLabel);
        u.root.addEventListener("contextmenu", (e) => {
          e.preventDefault();
          resetChartZoom(u);
        });
      },
    ],
    setCursor: [(u) => syncLabels(u)],
    setSize: [(u) => syncLabels(u)],
  };
}

function yScaleRange(_u: uPlot, min: number, max: number): [number, number] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [0, 1];
  if (min === max) {
    const pad = Math.max(Math.abs(min) * 0.01, 0.1);
    return [min - pad, max + pad];
  }
  const pad = (max - min) * 0.08;
  return [min - pad, max + pad];
}

function makePlot(
  target: HTMLElement,
  title: string,
  xs: number[],
  series: { label: string; values: (number | null)[]; color: string }[],
): uPlot | null {
  if (!xs.length || !series.length) return null;
  const width = innerWidth(target);
  const isFlow = title.includes("Débit");
  const bridgeGaps = series.length > 1;

  const opts: uPlot.Options = {
    width,
    height: 165,
    title,
    class: "hydro-uplot",
    padding: [10, 10, 4, isFlow ? 6 : 4],
    scales: {
      x: { time: true },
      y: { range: yScaleRange },
    },
    axes: [
      xAxisDaily(),
      {
        stroke: "#a1a1aa",
        grid: { stroke: "#27272a", width: 1 },
        ticks: { stroke: "#3f3f46" },
        font: "10px sans-serif",
        size: isFlow ? 58 : 48,
        gap: 6,
        values: (_u, splits) => splits.map((v) => formatAxisY(title, v)),
      },
    ],
    series: [
      {},
      ...series.map((s) => ({
        label: s.label,
        stroke: s.color,
        width: 1.75,
        spanGaps: bridgeGaps,
        points: { show: false },
      })),
    ],
    legend: {
      show: false,
    },
    cursor: hydroChartCursor(),
    hooks: chartCursorLabelHooks(title),
  };
  const data: uPlot.AlignedData = [xs, ...series.map((s) => s.values)];
  return new uPlot(opts, data, target);
}

function attachResizeSync(root: HTMLElement, plots: uPlot[]): void {
  const resizeAll = () => {
    for (const p of plots) {
      const host = p.root.parentElement;
      if (!host || host.clientWidth <= 0) continue;
      const w = innerWidth(host);
      if (w !== p.width) p.setSize({ width: w, height: p.height });
    }
  };
  requestAnimationFrame(resizeAll);
  if (typeof ResizeObserver !== "undefined") {
    const obs = new ResizeObserver(resizeAll);
    obs.observe(root);
    observersByRoot.set(root, obs);
  }
}

function renderHydroSummaryTable(
  container: HTMLElement,
  results: HydroResult[],
): void {
  const metrics = hydroMetricsMode(results);
  const shortLabels = buildShortLabels(results);
  const rows: Record<string, string>[] = [];

  for (let i = 0; i < results.length; i++) {
    const result = results[i];
    const planLabel = uninvertName(String(result.plan_nom || result.plan_eau || "")).trim() || shortLabels[i];
    const stationLabel = shortLabels[i];
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
  const scrollWrap = document.createElement("div");
  scrollWrap.className = "table-scroll";
  scrollWrap.appendChild(table);
  container.appendChild(scrollWrap);
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

  const label = hydroShortLabel(result);
  if (label) {
    const h = document.createElement("div");
    h.className = "hydro-station-label";
    h.textContent = label;
    h.title = hydroFullLabel(result);
    container.appendChild(h);
  }

  const caption = document.createElement("div");
  caption.className = "hydro-caption";
  caption.textContent = hydroHistoryCaption(history, "single");
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
}

function renderCombinedHydroCharts(
  container: HTMLElement,
  results: HydroResult[],
  metrics: "level" | "flow" | "both",
  plots: uPlot[],
): void {
  type StationItem = {
    key: number;
    label: string;
    fullTitle: string;
    color: string;
  };
  type SeriesBag = {
    stationKey: number;
    label: string;
    color: string;
    xs: number[];
    values: (number | null)[];
  };

  const shortLabels = buildShortLabels(results);
  const stations: StationItem[] = [];
  const debitSeries: SeriesBag[] = [];
  const niveauSeries: SeriesBag[] = [];
  let period: number | null = null;

  for (let i = 0; i < results.length; i++) {
    const result = results[i];
    const history = result.history;
    if (!history || typeof history !== "object") continue;
    const series = history.series;
    if (!series?.length) continue;

    period = history.period_days ?? period;
    const { xs, niveaux, debits } = parseSeries(series);
    if (!xs.length) continue;

    const hasFlow =
      (metrics === "flow" || metrics === "both") &&
      Boolean(history.has_debit) &&
      debits.some((v) => v != null);
    const hasLevel =
      (metrics === "level" || metrics === "both") &&
      Boolean(history.has_niveau) &&
      niveaux.some((v) => v != null);
    if (!hasFlow && !hasLevel) continue;

    const key = stations.length;
    const color = SERIES_COLORS[key % SERIES_COLORS.length];
    const label = shortLabels[i];
    stations.push({
      key,
      label,
      fullTitle: hydroFullLabel(result),
      color,
    });

    if (hasFlow) debitSeries.push({ stationKey: key, label, color, xs, values: debits });
    if (hasLevel) niveauSeries.push({ stationKey: key, label, color, xs, values: niveaux });
  }

  if (!debitSeries.length && !niveauSeries.length) return;

  const sampleHist = results.find((r) => r.history)?.history;
  const caption = document.createElement("div");
  caption.className = "hydro-caption";
  caption.textContent = sampleHist
    ? hydroHistoryCaption(sampleHist, "compare")
    : t().hydroHistoryCompareCeHQ(period ?? 7);
  container.appendChild(caption);

  const plotBindings: { plot: uPlot; stationKeys: number[] }[] = [];

  // Barre de navigation par station : clic = isoler (recalibre l'axe Y), reclic / « Toutes » = tout afficher
  let selectedKey: number | null = null;
  if (stations.length >= 2) {
    const bar = document.createElement("div");
    bar.className = "hydro-station-bar";
    bar.setAttribute("role", "tablist");

    const buttons: { key: number | null; el: HTMLButtonElement }[] = [];
    const syncSelection = () => {
      for (const b of buttons) {
        const active = b.key === selectedKey;
        b.el.classList.toggle("is-active", active);
        b.el.setAttribute("aria-selected", active ? "true" : "false");
      }
      for (const { plot, stationKeys } of plotBindings) {
        const hasMatch =
          selectedKey === null || stationKeys.includes(selectedKey);
        const wrap = plot.root.parentElement;
        if (wrap) wrap.hidden = !hasMatch;
        if (!hasMatch) continue;
        stationKeys.forEach((sk, idx) => {
          plot.setSeries(idx + 1, { show: selectedKey === null || sk === selectedKey });
        });
      }
    };

    const allBtn = document.createElement("button");
    allBtn.type = "button";
    allBtn.className = "hydro-station-pill is-active";
    allBtn.textContent = t().allStations;
    allBtn.addEventListener("click", () => {
      selectedKey = null;
      syncSelection();
    });
    bar.appendChild(allBtn);
    buttons.push({ key: null, el: allBtn });

    for (const st of stations) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "hydro-station-pill";
      btn.title = st.fullTitle;
      btn.innerHTML = `<span class="hydro-tip-dot" style="background:${st.color}"></span><span>${escapeHtml(st.label)}</span>`;
      btn.addEventListener("click", () => {
        selectedKey = selectedKey === st.key ? null : st.key;
        syncSelection();
      });
      bar.appendChild(btn);
      buttons.push({ key: st.key, el: btn });
    }
    container.appendChild(bar);
  }

  function alignAndPlot(title: string, seriesList: SeriesBag[]): void {
    if (!seriesList.length) return;
    const allTs = new Set<number>();
    for (const s of seriesList) for (const ts of s.xs) allTs.add(ts);
    const xs = [...allTs].sort((a, b) => a - b);
    const aligned = seriesList.map((s) => {
      const map = new Map<number, number | null>();
      s.xs.forEach((ts, idx) => map.set(ts, s.values[idx]));
      return {
        label: s.label,
        values: xs.map((ts) => (map.has(ts) ? map.get(ts)! : null)),
        color: s.color,
      };
    });
    const wrap = document.createElement("div");
    wrap.className = "hydro-chart-wrap";
    container.appendChild(wrap);
    const plot = makePlot(wrap, title, xs, aligned);
    if (plot) {
      plots.push(plot);
      plotBindings.push({
        plot,
        stationKeys: seriesList.map((s) => s.stationKey),
      });
    }
  }

  alignAndPlot("Débit (m³/s)", debitSeries);
  alignAndPlot("Niveau (m)", niveauSeries);
}

/** Orchestrateur : tableau + graphiques. */
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

  attachResizeSync(el, plots);
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
  attachResizeSync(el, plots);
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
  const plot = makeTidePlot(wrap, "Hauteur (m)", xs, [
    { label: "Marée (m)", values, color: SERIES_COLORS[1] },
  ]);
  if (plot) {
    plotsByRoot.set(el, [plot]);
    attachResizeSync(el, [plot]);
  }
}

function makeTidePlot(
  target: HTMLElement,
  title: string,
  xs: number[],
  series: { label: string; values: (number | null)[]; color: string }[],
): uPlot | null {
  if (!xs.length || !series.length) return null;
  const width = innerWidth(target);
  const labelHooks = chartCursorLabelHooks(title);
  const opts: uPlot.Options = {
    width,
    height: 200,
    title,
    class: "hydro-uplot-tide",
    scales: {
      x: { time: true },
      y: { range: yScaleRange },
    },
    axes: [
      xAxisDaily(),
      {
        stroke: "#a1a1aa",
        grid: { stroke: "#27272a", width: 1 },
        ticks: { stroke: "#3f3f46" },
        font: "10px sans-serif",
        size: 48,
        values: (_u, splits) =>
          splits.map((v) => (Number.isFinite(v) ? `${v.toFixed(1)}` : "")),
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
      show: false,
    },
    cursor: hydroChartCursor(),
    hooks: labelHooks,
  };
  const data: uPlot.AlignedData = [xs, ...series.map((s) => s.values)];
  return new uPlot(opts, data, target);
}
