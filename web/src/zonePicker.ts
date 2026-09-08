/** Sélecteur de zone avec recherche (combobox). */

import { escapeHtml } from "./regs";

export type ZoneOption = {
  zone_id: number;
  zone_nom: string;
  no_zone: number | null;
};

let zonesCache: ZoneOption[] | null = null;

export async function loadZoneOptions(): Promise<ZoneOption[]> {
  if (zonesCache) return zonesCache;
  const resp = await fetch("/api/zones");
  if (!resp.ok) throw new Error(`Zones indisponibles (${resp.status})`);
  zonesCache = (await resp.json()) as ZoneOption[];
  return zonesCache;
}

function zoneSearchKey(z: ZoneOption): string {
  const parts = [z.zone_nom, z.no_zone != null ? String(z.no_zone) : "", String(z.zone_id)];
  return parts.join(" ").toLowerCase();
}

function sortZones(zones: ZoneOption[]): ZoneOption[] {
  return [...zones].sort((a, b) => {
    const na = a.no_zone ?? a.zone_id;
    const nb = b.no_zone ?? b.zone_id;
    if (na !== nb) return na - nb;
    return a.zone_id - b.zone_id;
  });
}

export function mountZonePicker(
  host: HTMLElement,
  zones: ZoneOption[],
  selectedId: number,
  onSelect: (zone: ZoneOption) => void,
): void {
  const sorted = sortZones(zones);
  const byId = new Map(sorted.map((z) => [z.zone_id, z]));

  host.innerHTML = `
    <label class="zone-picker-label" for="zone-combo-input">Zone de pêche</label>
    <div class="zone-combo">
      <input
        id="zone-combo-input"
        type="search"
        class="zone-combo-input"
        autocomplete="off"
        spellcheck="false"
        role="combobox"
        aria-expanded="false"
        aria-controls="zone-combo-list"
        aria-autocomplete="list"
      />
      <ul id="zone-combo-list" class="zone-combo-list" role="listbox" hidden></ul>
    </div>`;

  const input = host.querySelector<HTMLInputElement>("#zone-combo-input")!;
  const list = host.querySelector<HTMLUListElement>("#zone-combo-list")!;
  let query = "";
  let active = -1;
  let suppressNextFocus = false;
  let currentId = selectedId;

  const setInputValue = (zone: ZoneOption) => {
    input.value = zone.zone_nom;
    query = "";
  };

  const pick = (zone: ZoneOption) => {
    currentId = zone.zone_id;
    setInputValue(zone);
    closeList();
    onSelect(zone);
  };

  const renderList = (items: ZoneOption[]) => {
    list.innerHTML = items
      .map(
        (z, i) =>
          `<li class="zone-combo-item${i === active ? " active" : ""}" role="option" data-zone-id="${z.zone_id}" aria-selected="${i === active}">${escapeHtml(z.zone_nom)}</li>`,
      )
      .join("");
    list.hidden = items.length === 0;
    input.setAttribute("aria-expanded", items.length ? "true" : "false");
  };

  const filtered = () => {
    const q = query.trim().toLowerCase();
    if (!q) return sorted;
    return sorted.filter((z) => zoneSearchKey(z).includes(q));
  };

  const openList = () => {
    active = -1;
    renderList(filtered());
  };

  const closeList = () => {
    list.hidden = true;
    active = -1;
    input.setAttribute("aria-expanded", "false");
  };

  const syncActive = () => {
    const items = list.querySelectorAll<HTMLLIElement>(".zone-combo-item");
    items.forEach((el, i) => {
      el.classList.toggle("active", i === active);
      el.setAttribute("aria-selected", i === active ? "true" : "false");
    });
    const activeEl = items[active];
    if (activeEl) activeEl.scrollIntoView({ block: "nearest" });
  };

  const selectActive = () => {
    const items = filtered();
    if (active < 0 || active >= items.length) return;
    pick(items[active]);
  };

  const initial = byId.get(selectedId) ?? sorted[0];
  if (initial) setInputValue(initial);

  input.addEventListener("focus", () => {
    if (suppressNextFocus) {
      suppressNextFocus = false;
      return;
    }
    openList();
  });

  input.addEventListener("input", () => {
    query = input.value;
    active = 0;
    renderList(filtered());
  });

  input.addEventListener("keydown", (ev) => {
    const items = filtered();
    if (ev.key === "ArrowDown") {
      ev.preventDefault();
      if (list.hidden) openList();
      active = Math.min(active + 1, items.length - 1);
      syncActive();
    } else if (ev.key === "ArrowUp") {
      ev.preventDefault();
      active = Math.max(active - 1, 0);
      syncActive();
    } else if (ev.key === "Enter") {
      ev.preventDefault();
      if (!list.hidden && active >= 0) {
        selectActive();
        return;
      }
      const exact = sorted.find((z) => z.zone_nom.toLowerCase() === input.value.trim().toLowerCase());
      if (exact) pick(exact);
    } else if (ev.key === "Escape") {
      closeList();
      const current = byId.get(currentId);
      if (current) setInputValue(current);
    }
  });

  list.addEventListener("mousedown", (ev) => {
    ev.preventDefault();
    const item = (ev.target as HTMLElement).closest<HTMLLIElement>(".zone-combo-item");
    if (!item) return;
    const zone = byId.get(Number(item.dataset.zoneId));
    if (zone) {
      suppressNextFocus = true;
      pick(zone);
    }
  });

  input.addEventListener("blur", () => {
    window.setTimeout(() => {
      closeList();
      const current = byId.get(currentId);
      if (current) setInputValue(current);
    }, 120);
  });
}
