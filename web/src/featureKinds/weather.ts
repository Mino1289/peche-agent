/** Villes météo ECCC GeoMet. */

import { escapeHtml } from "../regs";
import { t } from "../i18n";
import { dl, errorHtml, str } from "./html";
import { hqMetricsTableHtml } from "./hydro";
import { getJson, pick, type FeatureKind, type Loaded } from "./kind";

type Weather = Record<string, unknown>;

/** Station Hydro-Québec portant de la météo (affichée dans la couche ECCC). */
const isHqStation = (p: Record<string, unknown>) =>
  str(p.station).toUpperCase().startsWith("HQ-");

function hqStationBody(p: Record<string, unknown>): string {
  const m = t();
  const rows: [string, string][] = [
    [m.station, str(p.station)],
    [m.dataSource, "Hydro-Québec"],
  ];
  const region = str(p.hq_region);
  if (region) rows.push([m.hqRegion, region]);
  const obs = str(p.observed_at);
  if (obs) rows.push([m.observed, obs]);
  return dl(rows) + hqMetricsTableHtml(p.hq_metrics);
}

export const weatherKind: FeatureKind<Weather> = {
  title: (p) => String(p.ville || p.name || "Météo"),

  pinKey(p, lon, lat) {
    const ville = pick(p, "ville", "name");
    if (ville && lon != null && lat != null) {
      return `${ville}:${lon.toFixed(4)},${lat.toFixed(4)}`;
    }
    return ville || null;
  },

  async load(p) {
    // Station HQ : mesures déjà dans les props, pas de GeoMet.
    if (isHqStation(p)) return undefined;
    const lat = Number(p.lat);
    const lon = Number(p.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return undefined;
    return getJson<Weather>(
      `/api/weather?lat=${encodeURIComponent(String(lat))}&lon=${encodeURIComponent(String(lon))}`,
    );
  },

  popup(p, loaded) {
    if (isHqStation(p)) return hqStationBody(p);
    if (!loaded) return dl([[t().name, str(p.ville)]]);
    return weatherBody(loaded, { hideEmpty: true });
  },

  detail(body, hit, loaded) {
    if (isHqStation(hit.props)) {
      body.innerHTML = hqStationBody(hit.props);
      return;
    }
    body.innerHTML = loaded
      ? weatherBody(loaded, { showForecasts: true })
      : errorHtml(t().weatherUnavailable(0));
  },
};

function weatherBody(
  loaded: Loaded<Weather>,
  opts: { showForecasts?: boolean; hideEmpty?: boolean },
): string {
  if ("status" in loaded) return errorHtml(t().weatherUnavailable(loaded.status));
  if (loaded.data.error) return errorHtml(String(loaded.data.error));
  return weatherDetailHtml(loaded.data, opts);
}

function weatherMetric(v: unknown, unit: string, hideEmpty: boolean): string {
  if (v == null || String(v).trim() === "") {
    return hideEmpty ? "" : "—";
  }
  return `${v} ${unit}`;
}

function weatherText(v: unknown, hideEmpty: boolean): string {
  const s = str(v);
  if (s) return s;
  return hideEmpty ? "" : "—";
}

function weatherDetailHtml(
  w: Weather,
  opts?: { showForecasts?: boolean; hideEmpty?: boolean },
): string {
  const m = t();
  const hideEmpty = Boolean(opts?.hideEmpty);
  const wind = (() => {
    if (w.vent_kmh == null || String(w.vent_kmh).trim() === "") {
      return hideEmpty ? "" : "—";
    }
    const dir = w.vent_dir ? ` ${w.vent_dir}` : "";
    return `${w.vent_kmh} km/h${dir}`;
  })();
  let html = dl([
    [m.name, str(w.ville)],
    [m.dataSource, weatherText(w.source, hideEmpty)],
    [m.temperature, weatherMetric(w.temperature_c, "°C", hideEmpty)],
    [m.humidity, weatherMetric(w.humidite_pct, "%", hideEmpty)],
    [m.wind, wind],
    [m.windGust, weatherMetric(w.rafales_kmh, "km/h", hideEmpty)],
    [m.pressure, weatherMetric(w.pression_kpa, "kPa", hideEmpty)],
    [m.observed, weatherText(w.observed_at, hideEmpty)],
    [m.station, weatherText(w.station, hideEmpty)],
  ]);
  if (opts?.showForecasts) {
    const previsions = w.previsions;
    if (Array.isArray(previsions) && previsions.length) {
      html += `<p class="muted">${escapeHtml(m.forecast)}</p><ul class="identify-forecast">`;
      for (const fc of previsions.slice(0, 4)) {
        if (!fc || typeof fc !== "object") continue;
        const f = fc as Record<string, unknown>;
        const periode = str(f.periode);
        const resume = str(f.resume);
        html += `<li><strong>${escapeHtml(periode)}</strong>${resume ? ` — ${escapeHtml(resume)}` : ""}</li>`;
      }
      html += "</ul>";
    }
  }
  const url = ecccPageUrl(w);
  if (url) {
    html += `<p><a href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(m.ecccWeatherPage)}</a></p>`;
  }
  return html;
}

function ecccPageUrl(w: Weather): string {
  const raw = w.url;
  if (typeof raw === "string" && raw.trim() && !raw.startsWith("[object")) {
    return raw.trim();
  }
  if (raw && typeof raw === "object") {
    const o = raw as Record<string, unknown>;
    const u = str(o.fr) || str(o.en);
    if (u) return u;
  }
  const lat = Number(w.ville_lat ?? w.lat);
  const lon = Number(w.ville_lon ?? w.lon);
  if (Number.isFinite(lat) && Number.isFinite(lon)) {
    return `https://meteo.gc.ca/fr/location/index.html?coords=${lat.toFixed(2)},${lon.toFixed(2)}`;
  }
  return "";
}
