// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";
import type OlMap from "ol/Map";
import { IdentifyOverlay, MOBILE_MEDIA } from "./identify";
import { mountZonePicker } from "./zonePicker";

function stubMatchMedia(initialMatches: boolean) {
  let matches = initialMatches;
  const listeners: Array<() => void> = [];
  vi.stubGlobal("matchMedia", (query: string) => ({
    get matches() {
      return query === MOBILE_MEDIA ? matches : false;
    },
    media: query,
    addEventListener: (_ev: string, cb: () => void) => listeners.push(cb),
    removeEventListener: () => {},
  }));
  return {
    setMatches(next: boolean) {
      matches = next;
      for (const cb of listeners) cb();
    },
  };
}

function fakeMap(target: HTMLElement): OlMap {
  return {
    getTargetElement: () => target,
    addOverlay: vi.fn(),
  } as unknown as OlMap;
}

describe("IdentifyOverlay mobile bottom card", () => {
  it("mounts inside map-wrap on mobile and restores overlay on desktop", () => {
    const mm = stubMatchMedia(true);
    const wrap = document.createElement("div");
    wrap.className = "map-wrap";
    const mapEl = document.createElement("div");
    wrap.appendChild(mapEl);
    document.body.appendChild(wrap);

    const overlay = new IdentifyOverlay(fakeMap(mapEl), {
      onToggleFeaturePin: vi.fn(),
      getFeaturePin: () => null,
      onDeletePin: vi.fn(),
      onShowDetail: vi.fn(),
    });

    overlay.showPin(
      { id: "p1", n: 1, lon: -73, lat: 47, label: "Point 1", source: "user" },
      [0, 0],
    );
    const card = wrap.querySelector(".identify-popup");
    expect(card).not.toBeNull();
    expect(card?.classList.contains("identify-mobile-card")).toBe(true);

    mm.setMatches(false);
    expect(card?.classList.contains("identify-mobile-card")).toBe(false);

    mm.setMatches(true);
    expect(wrap.querySelector(".identify-mobile-card")).not.toBeNull();

    overlay.hide();
    expect(wrap.querySelector(".identify-popup")).toBeNull();

    wrap.remove();
    vi.unstubAllGlobals();
  });
});

describe("mountZonePicker touch selection", () => {
  it("keeps list open across touchstart+blur so click picks the zone", () => {
    vi.useFakeTimers();
    const host = document.createElement("div");
    document.body.appendChild(host);
    const onSelect = vi.fn();
    mountZonePicker(
      host,
      [
        { zone_id: 1, zone_nom: "Zone 8", no_zone: 8 },
        { zone_id: 2, zone_nom: "Zone 21", no_zone: 21 },
      ],
      1,
      onSelect,
    );

    const input = host.querySelector<HTMLInputElement>("#zone-combo-input")!;
    const list = host.querySelector<HTMLUListElement>("#zone-combo-list")!;
    input.dispatchEvent(new Event("focus"));
    expect(list.hidden).toBe(false);

    list.dispatchEvent(new Event("touchstart"));
    input.dispatchEvent(new Event("blur"));
    vi.advanceTimersByTime(200);
    expect(list.hidden).toBe(false);

    const item = list.querySelector<HTMLLIElement>('[data-zone-id="2"]')!;
    item.click();
    expect(onSelect).toHaveBeenCalledWith({ zone_id: 2, zone_nom: "Zone 21", no_zone: 21 });
    expect(list.hidden).toBe(true);

    host.remove();
    vi.useRealTimers();
  });
});
