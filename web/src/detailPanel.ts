/** Panneau latéral de détail : cadre ; le contenu vient de `featureKinds`. */

import { renderDetail, titleFor, type IdentifyHit } from "./featureKinds";
import { escapeHtml } from "./regs";
import { destroyHydroCharts } from "./hydroCharts";
import type { MapController } from "./map";
import { t } from "./i18n";

export class DetailPanel {
  private el: HTMLElement;
  private tabMap: HTMLElement;
  private map: MapController;
  private lastHit: IdentifyHit | null = null;

  constructor(el: HTMLElement, tabMap: HTMLElement, map: MapController) {
    this.el = el;
    this.tabMap = tabMap;
    this.map = map;
    this.el.classList.add("detail-panel");
    this.el.hidden = true;
  }

  close(): void {
    destroyHydroCharts(this.el);
    this.el.innerHTML = "";
    this.el.hidden = true;
    this.el.classList.remove("detail-expanded");
    this.lastHit = null;
    this.tabMap.classList.remove("has-detail");
    requestAnimationFrame(() => this.map.map.updateSize());
  }

  async refreshLocale(): Promise<void> {
    if (!this.lastHit || this.el.hidden) return;
    await this.show(this.lastHit);
  }

  async show(hit: IdentifyHit): Promise<void> {
    this.lastHit = hit;
    this.el.hidden = false;
    this.tabMap.classList.add("has-detail");
    window.dispatchEvent(new CustomEvent("peche:close-drawers"));
    requestAnimationFrame(() => this.map.map.updateSize());
    const title = titleFor(hit);
    const m = t();
    const expanded = this.el.classList.contains("detail-expanded");
    this.el.innerHTML = `
      <div class="panel-header detail-header">
        <h2>${escapeHtml(title)}</h2>
        <div class="panel-header-actions">
          <button type="button" class="btn-icon mobile-only detail-expand" title="${escapeHtml(expanded ? m.collapsePanel : m.expandPanel)}" aria-label="${escapeHtml(expanded ? m.collapsePanel : m.expandPanel)}">${expanded ? "⤡" : "⤢"}</button>
          <button type="button" class="identify-close" title="${escapeHtml(m.close)}" aria-label="${escapeHtml(m.close)}">✕</button>
        </div>
      </div>
      <div class="detail-body"><p class="muted">${escapeHtml(m.loading)}</p></div>`;
    this.el.querySelector(".identify-close")?.addEventListener("click", () => this.close());
    const expandBtn = this.el.querySelector<HTMLButtonElement>(".detail-expand");
    expandBtn?.addEventListener("click", () => {
      const next = this.el.classList.toggle("detail-expanded");
      const label = next ? t().collapsePanel : t().expandPanel;
      expandBtn.textContent = next ? "⤡" : "⤢";
      expandBtn.title = label;
      expandBtn.setAttribute("aria-label", label);
    });
    const body = this.el.querySelector(".detail-body") as HTMLElement;
    const header = this.el.querySelector<HTMLElement>(".panel-header h2");
    try {
      await renderDetail(body, hit, {
        focusZone: (zoneId) => void this.map.focusZone(zoneId),
        setTitle: (text) => {
          if (header) header.textContent = text;
        },
      });
    } catch (err) {
      body.innerHTML = `<p class="identify-error">${escapeHtml(String(err))}</p>`;
    }
  }
}
