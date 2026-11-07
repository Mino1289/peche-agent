// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { t } from "../i18n";
import {
  featurePinKey,
  isIdentifiable,
  popupClass,
  popupHtml,
  renderDetail,
  titleFor,
  type IdentifyHit,
} from "./index";

const ctx = { focusZone: () => {}, setTitle: () => {} };

function hit(layerId: string, props: Record<string, unknown>): IdentifyHit {
  return { layerId, props, coordinate: [0, 0] };
}

function stubFetch(body: unknown, status = 200) {
  const fn = vi.fn(async (_url: string) => new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("isIdentifiable", () => {
  it("matches the clickable map layers", () => {
    for (const id of [
      "barrages_cehq",
      "vigilance_stations",
      "marees_shc",
      "meteo_eccc",
      "plans_regpec",
      "tfs",
      "chasse_interdite",
      "habitat_legal",
      "habitat_info",
      "stations_lavage",
    ]) {
      expect(isIdentifiable(id), id).toBe(true);
    }
  });

  it("excludes detail-only and unknown layers", () => {
    expect(isIdentifiable("zone")).toBe(false);
    expect(isIdentifiable("zones_peche")).toBe(false);
  });
});

describe("featurePinKey", () => {
  it("uses the entity id per kind", () => {
    expect(featurePinKey("vigilance_stations", { station: "061004" })).toBe("vigilance_stations:061004");
    expect(featurePinKey("marees_shc", { station_code: "03480" })).toBe("marees_shc:03480");
    expect(featurePinKey("plans_regpec", { plan_id: 12 })).toBe("plans_regpec:12");
    expect(featurePinKey("tfs", { OBJECTID: 7 })).toBe("tfs:7");
  });

  it("returns null for a known kind without id, even with coordinates", () => {
    expect(featurePinKey("vigilance_stations", {}, -71, 48)).toBeNull();
  });

  it("includes coordinates for weather cities", () => {
    expect(featurePinKey("meteo_eccc", { ville: "Saguenay" }, -71.06, 48.43)).toBe(
      "meteo_eccc:Saguenay:-71.0600,48.4300",
    );
    expect(featurePinKey("meteo_eccc", { ville: "Saguenay" })).toBe("meteo_eccc:Saguenay");
  });

  it("falls back to coordinates for unknown layers", () => {
    expect(featurePinKey("custom_x", {}, -71.123456, 48.5)).toBe("custom_x:-71.12346,48.50000");
    expect(featurePinKey("custom_x", {})).toBeNull();
  });
});

describe("titleFor", () => {
  it("uses kind-specific fallbacks", () => {
    expect(titleFor(hit("habitat_legal", {}))).toBe("Habitat faunique légal");
    expect(titleFor(hit("zone", { no_zone: 28 }))).toBe(t().zoneRegsTitle("Zone 28"));
    expect(titleFor(hit("custom_x", {}))).toBe("custom_x");
  });
});

describe("popup → detail data reuse", () => {
  it("weather: one fetch shared by popup and detail", async () => {
    const fetch = stubFetch({ ville: "Saguenay", previsions: [{ periode: "Ce soir", resume: "Nuageux" }] });
    const h = hit("meteo_eccc", { ville: "Saguenay", lat: 48.43, lon: -71.06 });
    expect(await popupHtml(h)).toContain("Saguenay");
    const body = document.createElement("div");
    await renderDetail(body, h, ctx);
    expect(body.innerHTML).toContain("Ce soir");
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("tides: popup loads days=3 once; detail opened mid-load waits for it", async () => {
    const fetch = stubFetch({ niveau_m: 2.1, table: { lignes: [{ jour: "lun" }] } });
    const h = hit("marees_shc", { code: "03480", nom: "Chicoutimi" });
    const body = document.createElement("div");
    await Promise.all([popupHtml(h), renderDetail(body, h, ctx)]);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][0]).toBe("/api/tides/03480?days=3");
    expect(body.innerHTML).toContain("2.1 m");
    expect(body.innerHTML).toContain("tide-table-split");
    expect(popupClass("marees_shc")).toBe("identify-popup--tides");
  });

  it("hydro: detail fetches history separately", async () => {
    const fetch = stubFetch({ station_id: "061004", niveau_m: 3 });
    const h = hit("vigilance_stations", { station: "061004" });
    await popupHtml(h);
    await renderDetail(document.createElement("div"), h, ctx);
    expect(fetch.mock.calls.map((c) => c[0])).toEqual([
      "/api/hydromet/061004",
      "/api/hydromet/061004?include_history=true",
    ]);
  });
});

describe("errors", () => {
  it("hydro popup keeps cached props and shows the HTTP status", async () => {
    stubFetch({}, 503);
    const html = await popupHtml(hit("vigilance_stations", { station: "061004", etat: "Normal" }));
    expect(html).toContain("Normal");
    expect(html).toContain(t().liveUnavailable(503));
  });

  it("a network failure is not cached: the next open retries", async () => {
    const fetch = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("offline"))
      .mockResolvedValue(new Response(JSON.stringify({ ville: "Alma" })));
    vi.stubGlobal("fetch", fetch);
    const h = hit("meteo_eccc", { lat: 48.5, lon: -71.6 });
    await expect(popupHtml(h)).rejects.toThrow("offline");
    expect(await popupHtml(h)).toContain("Alma");
  });

  it("unknown layer renders raw props without geometry", async () => {
    const html = await popupHtml(hit("custom_x", { NOM: "X", geometry: { type: "Point" } }));
    expect(html).toContain("NOM");
    expect(html).not.toContain("geometry");
  });
});
