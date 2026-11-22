// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";
import type uPlot from "uplot";
import { hydroShortLabel, snapCursorToData } from "./hydroCharts";

describe("hydroShortLabel", () => {
  it("prefers uninverted waterbody name over verbose station description", () => {
    expect(
      hydroShortLabel({
        plan_eau: "Chicoutimi, Rivière",
        description: "À 0,3 km en aval du barrage de Portage-des-Roches",
      }),
    ).toBe("Rivière Chicoutimi");
  });

  it("disambiguates stations sharing a waterbody with a short tag", () => {
    expect(
      hydroShortLabel(
        {
          plan_eau: "Chicoutimi, Rivière",
          description: "À 0,3 km en aval du barrage de Portage-des-Roches",
        },
        true,
      ),
    ).toBe("Rivière Chicoutimi (Portage-d…");
  });
});

describe("snapCursorToData", () => {
  const fakePlot = {
    data: [
      [1000, 2000, 3000],
      [10, 20, 30],
      [100, 120, 140],
    ],
    series: [{}, { show: true }, { show: true }],
    posToVal: (px: number) => 1000 + px * 10,
    valToPos: (val: number, scale: string) => (scale === "x" ? (val - 1000) / 10 : 200 - val),
  } as unknown as uPlot;

  it("does not snap onto index 0 when cursor leaves the plot", () => {
    expect(snapCursorToData(fakePlot, -10, -10)).toEqual([-10, -10]);
  });

  it("snaps vertically to the visible series closest to the pointer", () => {
    // At x=2000 (px=100): series 1 yPos=180, series 2 yPos=80
    expect(snapCursorToData(fakePlot, 100, 85)).toEqual([100, 80]);
    expect(snapCursorToData(fakePlot, 100, 175)).toEqual([100, 180]);
  });
});
