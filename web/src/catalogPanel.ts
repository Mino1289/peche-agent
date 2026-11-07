/** Panneau catalogue + filtres + couches custom Forêt ouverte. */

import type { Catalog, LayerDef } from "./types";
import type { MapController } from "./map";
import { PENTE_COLORS } from "./filters";
import { legendSrc, stationEtatLegendItems, VIGILANCE_LAYER_DEFAULT_COLOR } from "./layers";
import { groupTitle, t } from "./i18n";
import {
  addStoredCustomLayer,
  discoverLayers,
  loadStoredCustomLayers,
  removeStoredCustomLayer,
  validateCustomLayer,
  type DiscoverHit,
} from "./customLayers";

/** Couches dont la couleur est modifiable dans le panneau catalogue. */
const COLOR_PICKER_LAYERS = new Set([
  "zones_chasse",
  "plans_regpec",
  "marees_shc",
  "barrages_cehq",
  "tfs",
  "habitat_legal",
  "habitat_info",
]);

function layerColorPickerEnabled(def: LayerDef): boolean {
  return COLOR_PICKER_LAYERS.has(def.id);
}

export class CatalogPanel {
  private el: HTMLElement;
  private map: MapController;
  private search = "";
  private zoom = 6;
  private catalog: Catalog | null = null;
  private addLayerOpen = false;

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
    this.catalog = catalog;
    this.zoom = this.map.getZoom();
    const m = t();
    this.el.innerHTML = "";
    const header = document.createElement("div");
    header.className = "panel-header catalog-header";
    header.innerHTML = `<h2>${escapeHtml(m.layersTitle)}</h2>`;
    const addBtn = document.createElement("button");
    addBtn.type = "button";
    addBtn.className = "btn-sidebar catalog-add-btn";
    addBtn.textContent = m.addLayer;
    addBtn.addEventListener("click", () => {
      this.addLayerOpen = !this.addLayerOpen;
      this.renderAddLayerForm();
    });
    header.appendChild(addBtn);
    const input = document.createElement("input");
    input.type = "search";
    input.placeholder = m.searchPlaceholder;
    input.className = "search-input";
    input.value = this.search;
    input.addEventListener("input", () => {
      this.search = input.value.trim().toLowerCase();
      this.renderGroups();
    });
    header.appendChild(input);
    this.el.appendChild(header);

    const addWrap = document.createElement("div");
    addWrap.id = "catalog-add-wrap";
    addWrap.hidden = !this.addLayerOpen;
    this.el.appendChild(addWrap);
    if (this.addLayerOpen) this.renderAddLayerForm();

    const body = document.createElement("div");
    body.className = "catalog-body";
    body.id = "catalog-body";
    this.el.appendChild(body);
    this.renderGroups();
  }

  private renderGroups(): void {
    const catalog = this.catalog;
    if (!catalog) return;
    const m = t();
    const body = this.el.querySelector("#catalog-body")!;
    body.innerHTML = "";

    const customLayers = loadStoredCustomLayers();
    if (customLayers.length) {
      const details = document.createElement("details");
      details.open = true;
      details.innerHTML = `<summary>${escapeHtml(m.customLayers)} <span class="badge">${customLayers.length}</span></summary>`;
      for (const layer of customLayers) {
        details.appendChild(this.customLayerRow(layer));
      }
      body.appendChild(details);
    }

    const bm = document.createElement("details");
    bm.open = false;
    bm.innerHTML = `<summary>${escapeHtml(m.basemaps)}</summary>`;
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
      const groupLabel = groupTitle(group.id, group.title);
      details.innerHTML = `<summary>${escapeHtml(groupLabel)} <span class="badge">${searchLayers.length}</span></summary>`;
      for (const layer of searchLayers) {
        details.appendChild(this.layerRow(layer));
      }
      body.appendChild(details);
    }
  }

  private renderAddLayerForm(): void {
    const wrap = this.el.querySelector("#catalog-add-wrap") as HTMLElement | null;
    if (!wrap) return;
    wrap.hidden = !this.addLayerOpen;
    if (!this.addLayerOpen) {
      wrap.innerHTML = "";
      return;
    }
    const m = t();
    wrap.innerHTML = `
      <div class="catalog-add-form">
        <h3>${escapeHtml(m.addLayerTitle)}</h3>
        <p class="muted catalog-add-hint">${escapeHtml(m.addLayerDiscoverHint)}</p>
        <label class="catalog-add-field">
          <span>${escapeHtml(m.addLayerSearch)}</span>
          <input type="search" class="search-input" id="discover-q" />
        </label>
        <div id="discover-results" class="discover-results"></div>
        <hr />
        <p class="muted catalog-add-hint">${escapeHtml(m.addLayerManualHint)}</p>
        <label class="catalog-add-field">
          <span>${escapeHtml(m.addLayerUrl)}</span>
          <input type="url" class="search-input" id="custom-url" placeholder="https://…" />
        </label>
        <label class="catalog-add-field">
          <span>${escapeHtml(m.addLayerName)}</span>
          <input type="text" class="search-input" id="custom-layer-name" />
        </label>
        <label class="catalog-add-field">
          <span>${escapeHtml(m.addLayerType)}</span>
          <select id="custom-layer-type" class="search-input">
            <option value="wms">WMS</option>
            <option value="wfs">WFS</option>
          </select>
        </label>
        <p id="custom-layer-error" class="filter-error muted" hidden></p>
        <div class="catalog-add-actions">
          <button type="button" class="btn-secondary" id="custom-layer-submit">${escapeHtml(m.addLayerSubmit)}</button>
          <button type="button" class="btn-muted" id="custom-layer-cancel">${escapeHtml(m.addLayerCancel)}</button>
        </div>
      </div>`;

    const qInput = wrap.querySelector("#discover-q") as HTMLInputElement;
    const results = wrap.querySelector("#discover-results") as HTMLElement;
    let debounce: number | undefined;
    qInput.addEventListener("input", () => {
      window.clearTimeout(debounce);
      debounce = window.setTimeout(() => void this.runDiscover(qInput.value, results), 350);
    });

    wrap.querySelector("#custom-layer-cancel")!.addEventListener("click", () => {
      this.addLayerOpen = false;
      this.renderAddLayerForm();
    });

    wrap.querySelector("#custom-layer-submit")!.addEventListener("click", () => {
      void this.submitCustomLayer(wrap);
    });
  }

  private async runDiscover(q: string, container: HTMLElement): Promise<void> {
    if (!q.trim()) {
      container.innerHTML = "";
      return;
    }
    container.innerHTML = `<p class="muted">${escapeHtml(t().loading)}</p>`;
    try {
      const hits = await discoverLayers(q.trim());
      container.innerHTML = "";
      if (!hits.length) {
        container.innerHTML = `<p class="muted">—</p>`;
        return;
      }
      for (const hit of hits.slice(0, 12)) {
        container.appendChild(this.discoverHitRow(hit));
      }
    } catch (err) {
      container.innerHTML = `<p class="filter-error">${escapeHtml(String(err))}</p>`;
    }
  }

  private discoverHitRow(hit: DiscoverHit): HTMLElement {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "discover-hit";
    btn.innerHTML = `<strong>${escapeHtml(hit.title)}</strong><br><span class="muted">${escapeHtml(hit.layer_name || "")} · ${escapeHtml(hit.source_title)}</span>`;
    btn.addEventListener("click", () => {
      const urlInput = this.el.querySelector("#custom-url") as HTMLInputElement | null;
      const nameInput = this.el.querySelector("#custom-layer-name") as HTMLInputElement | null;
      const typeInput = this.el.querySelector("#custom-layer-type") as HTMLSelectElement | null;
      if (urlInput) urlInput.value = hit.url;
      if (nameInput) nameInput.value = hit.layer_name || hit.title;
      if (typeInput) typeInput.value = hit.source_type === "wfs" ? "wfs" : "wms";
    });
    return btn;
  }

  private async submitCustomLayer(wrap: HTMLElement): Promise<void> {
    const m = t();
    const url = (wrap.querySelector("#custom-url") as HTMLInputElement).value.trim();
    const layer_name = (wrap.querySelector("#custom-layer-name") as HTMLInputElement).value.trim();
    const source_type = (wrap.querySelector("#custom-layer-type") as HTMLSelectElement).value;
    const errEl = wrap.querySelector("#custom-layer-error") as HTMLElement;
    const submit = wrap.querySelector("#custom-layer-submit") as HTMLButtonElement;
    errEl.hidden = true;
    submit.disabled = true;
    submit.textContent = m.addLayerValidating;
    try {
      const result = await validateCustomLayer({ url, layer_name, source_type });
      if (!result.ok || !result.layer) {
        errEl.hidden = false;
        errEl.textContent = result.error || "Error";
        return;
      }
      addStoredCustomLayer(result.layer);
      this.map.addCustomLayer(result.layer);
      this.addLayerOpen = false;
      if (this.catalog) this.render(this.catalog);
    } finally {
      submit.disabled = false;
      submit.textContent = m.addLayerSubmit;
    }
  }

  private customLayerRow(def: LayerDef): HTMLElement {
    const wrap = document.createElement("div");
    wrap.className = "layer-block";
    const row = document.createElement("label");
    row.className = "layer-row";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = this.map.getMapState().layers.some((l) => l.id === def.id && l.visible);
    cb.addEventListener("change", () => {
      this.map.setLayerVisible(def.id, cb.checked);
    });
    row.appendChild(cb);
    const title = document.createElement("span");
    title.className = "layer-title";
    title.textContent = def.title;
    row.appendChild(title);
    const rm = document.createElement("button");
    rm.type = "button";
    rm.className = "btn-icon custom-layer-rm";
    rm.title = t().removePin;
    rm.textContent = "✕";
    rm.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      removeStoredCustomLayer(def.id);
      this.map.removeCustomLayer(def.id);
      if (this.catalog) this.render(this.catalog);
    });
    row.appendChild(rm);
    wrap.appendChild(row);
    return wrap;
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
    const m = t();
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

    const colorPicker = layerColorPickerEnabled(def);
    if (def.color && colorPicker) {
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
      swatch.title = outline ? m.layerOutline : m.layerColor;
      row.appendChild(swatch);
    }

    const title = document.createElement("span");
    title.className = "layer-title";
    title.textContent = def.title;
    row.appendChild(title);

    const zBadge = zoomBadge(def);
    if (zBadge) {
      const b = document.createElement("span");
      b.className = "zoom-badge";
      b.dataset.min = def.min_zoom != null ? String(def.min_zoom) : "";
      b.dataset.max = def.max_zoom != null ? String(def.max_zoom) : "";
      b.textContent = zBadge;
      b.title = m.zoomBadgeTitle;
      row.appendChild(b);
      applyZoomBadgeState(b, this.zoom);
    }

    if (colorPicker && def.color) {
      const colorInput = document.createElement("input");
      colorInput.type = "color";
      colorInput.className = "layer-color-picker";
      colorInput.value = normalizeHex(def.color);
      colorInput.title = m.changeColor;
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
      wrap.appendChild(etatLegend(def));
    }

    const src = legendSrc(def.legend_url);
    if (src) {
      const img = document.createElement("img");
      img.className = "legend";
      img.alt = m.legendAlt;
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
          ? m.zoneFilterPlaceholder
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

function etatLegend(def: LayerDef): HTMLElement {
  const m = t();
  const box = document.createElement("div");
  box.className = "etat-legend";
  const title = document.createElement("div");
  title.className = "etat-legend-title";
  title.textContent = m.etatLegendTitle;
  box.appendChild(title);
  const layerFallback = def.color || VIGILANCE_LAYER_DEFAULT_COLOR;
  const items = stationEtatLegendItems(layerFallback);
  for (const { color, key } of items) {
    const label = m[key];
    const lab = document.createElement("span");
    lab.className = "etat-legend-item";
    const sw = document.createElement("span");
    sw.className = "swatch";
    sw.style.background = color;
    lab.appendChild(sw);
    lab.appendChild(document.createTextNode(` ${label}`));
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
