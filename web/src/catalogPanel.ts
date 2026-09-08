/** Panneau catalogue + filtres. */

import type { Catalog, LayerDef } from "./types";
import type { MapController } from "./map";
import { PENTE_COLORS } from "./filters";
import { legendSrc, ETAT_COLORS } from "./layers";

export class CatalogPanel {
  private el: HTMLElement;
  private map: MapController;
  private search = "";
  private zoom = 6;

  constructor(el: HTMLElement, map: MapController) {
    this.el = el;
    this.map = map;
    this.zoom = map.getZoom();
    map.onZoomChange((z) => {
      this.zoom = z;
      this.updateZoomBadges();
    });
  }

  render(catalog: Catalog): void {
    this.zoom = this.map.getZoom();
    this.el.innerHTML = "";
    const header = document.createElement("div");
    header.className = "panel-header";
    header.innerHTML = `<h2>Couches</h2>`;
    const input = document.createElement("input");
    input.type = "search";
    input.placeholder = "Rechercher…";
    input.className = "search-input";
    input.addEventListener("input", () => {
      this.search = input.value.trim().toLowerCase();
      this.renderGroups(catalog);
    });
    header.appendChild(input);
    this.el.appendChild(header);

    const body = document.createElement("div");
    body.className = "catalog-body";
    body.id = "catalog-body";
    this.el.appendChild(body);
    this.renderGroups(catalog);
  }

  private renderGroups(catalog: Catalog): void {
    const body = this.el.querySelector("#catalog-body")!;
    body.innerHTML = "";

    const bm = document.createElement("details");
    bm.open = false;
    bm.innerHTML = `<summary>Fonds de carte</summary>`;
    for (const b of catalog.basemaps) {
      bm.appendChild(this.basemapRow(b));
    }
    body.appendChild(bm);

    const hidden = new Set([
      "qualite_eau",
      "foret",
      "biodiversite",
      "perturbations",
      "autres",
    ]);
    for (const group of catalog.groups) {
      if (hidden.has(group.id)) continue;

      const searchLayers = group.layers.filter((l) => {
        if (!l.curated) return false;
        if (!this.search) return true;
        return (
          l.title.toLowerCase().includes(this.search) ||
          l.id.toLowerCase().includes(this.search)
        );
      });
      if (!searchLayers.length) continue;

      const details = document.createElement("details");
      details.open =
        Boolean(this.search) || group.layers.some((l) => l.visible_default);
      details.innerHTML = `<summary>${escapeHtml(group.title)} <span class="badge">${searchLayers.length}</span></summary>`;
      for (const layer of searchLayers) {
        details.appendChild(this.layerRow(layer));
      }
      body.appendChild(details);
    }
  }

  private basemapRow(def: LayerDef): HTMLElement {
    const row = document.createElement("label");
    row.className = "layer-row";
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "basemap";
    radio.checked = def.visible_default !== false && def.id === "fond_quebec";
    radio.addEventListener("change", () => {
      const cat = this.map.getCatalog();
      if (!cat) return;
      for (const b of cat.basemaps) {
        this.map.setLayerVisible(b.id, b.id === def.id);
      }
    });
    row.appendChild(radio);
    row.appendChild(document.createTextNode(" " + def.title));
    return row;
  }

  private layerRow(def: LayerDef): HTMLElement {
    const wrap = document.createElement("div");
    wrap.className = "layer-block";

    const row = document.createElement("label");
    row.className = "layer-row";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = Boolean(def.visible_default);
    cb.addEventListener("change", () => {
      this.map.setLayerVisible(def.id, cb.checked);
      const filtersEl = wrap.querySelector(".layer-filters") as HTMLElement | null;
      if (filtersEl) filtersEl.hidden = !cb.checked;
    });
    row.appendChild(cb);


    const hideColor =
      Boolean(def.extra?.etat_colors) || def.id === "vigilance_stations";
    if (
      def.color &&
      !hideColor &&
      (def.source_type === "wfs" ||
        def.source_type === "local" ||
        def.source_type === "geojson" ||
        def.source_type === "arcgis")
    ) {
      const swatch = document.createElement("span");
      swatch.className = "swatch layer-color";
      const outline = def.id === "zones_chasse" || Boolean(def.extra?.outline);
      if (outline) {
        swatch.classList.add("swatch-outline");
        swatch.style.borderColor = def.color;
        swatch.style.background = "transparent";
      } else {
        swatch.style.background = def.color;
      }
      swatch.title = outline ? "Contour de la couche" : "Couleur de la couche";
      row.appendChild(swatch);
    }

    const title = document.createElement("span");
    title.className = "layer-title";
    title.textContent = def.title;
    if (def.curated) {
      const badge = document.createElement("span");
      badge.className = "curated";
      badge.textContent = "★";
      title.appendChild(badge);
    }
    row.appendChild(title);

    const zBadge = zoomBadge(def);
    if (zBadge) {
      const b = document.createElement("span");
      b.className = "zoom-badge";
      b.dataset.min = def.min_zoom != null ? String(def.min_zoom) : "";
      b.dataset.max = def.max_zoom != null ? String(def.max_zoom) : "";
      b.textContent = zBadge;
      b.title = "Niveau de zoom pour afficher cette couche";
      row.appendChild(b);
      applyZoomBadgeState(b, this.zoom);
    }

    if (def.color && !hideColor) {
      const colorInput = document.createElement("input");
      colorInput.type = "color";
      colorInput.className = "layer-color-picker";
      colorInput.value = normalizeHex(def.color);
      colorInput.title = "Changer la couleur";
      colorInput.addEventListener("input", () => {
        this.map.setLayerColor(def.id, colorInput.value);
        const sw = row.querySelector(".layer-color") as HTMLElement | null;
        if (sw) {
          if (sw.classList.contains("swatch-outline")) {
            sw.style.borderColor = colorInput.value;
            sw.style.background = "transparent";
          } else {
            sw.style.background = colorInput.value;
          }
        }
      });
      row.appendChild(colorInput);
    }

    wrap.appendChild(row);

    if (def.id === "vigilance_stations" || def.extra?.etat_colors) {
      wrap.appendChild(etatLegend());
    }

    const src = legendSrc(def.legend_url);
    if (src) {
      const img = document.createElement("img");
      img.className = "legend";
      img.alt = "légende";
      img.loading = "lazy";
      img.src = src;
      img.onerror = () => {
        img.hidden = true;
      };
      wrap.appendChild(img);
    }

    if (def.filter_spec && def.filter_spec.kind !== "none") {
      const filters = document.createElement("div");
      filters.className = "layer-filters";
      filters.hidden = !def.visible_default;
      if (def.filter_spec.kind === "colorkey") {
        filters.appendChild(this.slopeFilters(def));
      } else if (def.filter_spec.options?.length) {
        for (const opt of def.filter_spec.options) {
          const lab = document.createElement("label");
          lab.className = "filter-opt";
          const c = document.createElement("input");
          c.type = def.filter_spec.multi === false ? "radio" : "checkbox";
          c.name = `filter-${def.id}`;
          c.value = opt.value;
          c.checked = false;
          c.addEventListener("change", () => this.applyFilterFromUi(def, filters));
          lab.appendChild(c);
          if (opt.color) {
            const sw = document.createElement("span");
            sw.className = "swatch";
            sw.style.background = opt.color.startsWith("#")
              ? opt.color
              : `rgb(${opt.color})`;
            lab.appendChild(sw);
          }
          lab.appendChild(document.createTextNode(" " + opt.label));
          filters.appendChild(lab);
        }
      } else if (def.filter_spec.attr) {
        const input = document.createElement("input");
        input.type = "text";
        const isZone =
          def.id === "zones_chasse" ||
          def.id === "plans_regpec" ||
          def.filter_spec.attr === "No_zone" ||
          def.filter_spec.attr === "zone_id";
        input.placeholder = isZone
          ? "ex. 21,23,25-28 ou *"
          : def.filter_spec.attr;
        input.className = "filter-text";
        const err = document.createElement("p");
        err.className = "filter-error muted";
        err.hidden = true;
        let debounce: number | undefined;
        const run = () => {
          window.clearTimeout(debounce);
          if (isZone) {
            void this.map.applyZoneFilter(def.id, input.value).then((msg) => {
              err.hidden = !msg;
              err.textContent = msg || "";
            });
          } else {
            const attr = def.filter_spec!.attr!;
            void this.map.setLayerFilters(def.id, { [attr]: input.value });
          }
        };
        input.addEventListener("input", () => {
          window.clearTimeout(debounce);
          debounce = window.setTimeout(run, 400);
        });
        input.addEventListener("keydown", (e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            run();
          }
        });
        filters.appendChild(input);
        if (isZone) filters.appendChild(err);
      }
      wrap.appendChild(filters);
    }
    return wrap;
  }

  private updateZoomBadges(): void {
    for (const b of this.el.querySelectorAll<HTMLElement>(".zoom-badge")) {
      applyZoomBadgeState(b, this.zoom);
    }
  }

  private slopeFilters(def: LayerDef): HTMLElement {
    const box = document.createElement("div");
    box.className = "slope-filters";
    for (const [cls, rgb] of Object.entries(PENTE_COLORS)) {
      const lab = document.createElement("label");
      lab.className = "filter-opt";
      const c = document.createElement("input");
      c.type = "checkbox";
      c.value = cls;
      c.checked = true;
      c.addEventListener("change", () => {
        const checked = [
          ...box.querySelectorAll<HTMLInputElement>("input:checked"),
        ].map((i) => i.value);
        void this.map.setLayerFilters(def.id, { classes: checked });
      });
      const swatch = document.createElement("span");
      swatch.className = "swatch";
      swatch.style.background = `rgb(${rgb.join(",")})`;
      lab.appendChild(c);
      lab.appendChild(swatch);
      lab.appendChild(
        document.createTextNode(
          ` ${def.filter_spec?.options?.find((o) => o.value === cls)?.label || cls}`,
        ),
      );
      box.appendChild(lab);
    }
    return box;
  }

  private applyFilterFromUi(def: LayerDef, container: HTMLElement): void {
    const inputs = [
      ...container.querySelectorAll<HTMLInputElement>("input:checked"),
    ];
    const attr = def.filter_spec?.attr;
    if (!attr) return;
    if (def.filter_spec?.multi === false) {
      const v = inputs[0]?.value;
      void this.map.setLayerFilters(def.id, v ? { [attr]: v } : {});
    } else {
      void this.map.setLayerFilters(def.id, {
        [attr]: inputs.map((i) => i.value),
      });
    }
  }
}

function zoomBadge(def: LayerDef): string | null {
  const parts: string[] = [];
  if (def.min_zoom != null) parts.push(`≥ z${def.min_zoom}`);
  if (def.max_zoom != null) parts.push(`≤ z${def.max_zoom}`);
  return parts.length ? parts.join(" ") : null;
}

function applyZoomBadgeState(el: HTMLElement, zoom: number): void {
  const min = el.dataset.min ? Number(el.dataset.min) : null;
  const max = el.dataset.max ? Number(el.dataset.max) : null;
  const out =
    (min != null && zoom < min) || (max != null && zoom > max);
  el.classList.toggle("zoom-badge-out", out);
}

function etatLegend(): HTMLElement {
  const box = document.createElement("div");
  box.className = "etat-legend";
  const items: [string, string][] = [
    [ETAT_COLORS.normal, "Normal"],
    [ETAT_COLORS.surveillance, "Surveillance"],
    [ETAT_COLORS.alerte, "Alerte"],
    [ETAT_COLORS.inconnu, "Inconnu / désactivée"],
  ];
  for (const [color, label] of items) {
    const lab = document.createElement("span");
    lab.className = "etat-legend-item";
    const sw = document.createElement("span");
    sw.className = "swatch";
    sw.style.background = color;
    lab.appendChild(sw);
    lab.appendChild(document.createTextNode(" " + label));
    box.appendChild(lab);
  }
  return box;
}

function normalizeHex(color: string): string {
  if (/^#[0-9a-fA-F]{6}$/.test(color)) return color;
  if (/^#[0-9a-fA-F]{3}$/.test(color)) {
    const h = color.slice(1);
    return `#${h[0]}${h[0]}${h[1]}${h[1]}${h[2]}${h[2]}`;
  }
  return "#1d4ed8";
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
