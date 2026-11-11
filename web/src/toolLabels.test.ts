// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";
import { toolLabels } from "./toolLabels";

const pins = [{ id: "a", n: 1, lon: -70.80880185683075, lat: 48.017805787469115 }];

describe("toolLabels", () => {
  it("remplace les IDs par les noms auxquels ils se rapportent", async () => {
    vi.stubGlobal(
      "fetch",
      async () =>
        new Response(JSON.stringify([{ zone_id: 32, zone_nom: "Zone 28", no_zone: 28 }])),
    );
    const labels = await toolLabels(
      [
        { name: "get_point_info", args: { pin_number: 1 } },
        { name: "search_plans", args: { zone_id: 32, query: "Petit lac Ha! Ha!" } },
        { name: "get_weather", args: { lat: 48.017805787469115, lon: -70.80880185683075 } },
      ],
      pins,
    );
    expect(labels).toEqual([
      "Récupération des informations du point N°1",
      'Recherche du "Petit lac Ha! Ha!" dans la Zone 28',
      "Récupération météo au point N°1",
    ]);
    vi.unstubAllGlobals();
  });
});
