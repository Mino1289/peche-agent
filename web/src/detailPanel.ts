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
    requestAnimationFrame(() => this.map.map.updateSize());
    const title = titleFor(hit);
    const m = t();
    this.el.innerHTML = `
      <div class="panel-header">
        <h2>${escapeHtml(title)}</h2>
        <button type="button" class="identify-close" title="${escapeHtml(m.close)}">✕</button>
      </div>
      <div class="detail-body"><p class="muted">${escapeHtml(m.loading)}</p></div>`;
    this.el.querySelector(".identify-close")?.addEventListener("click", () => this.close());
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
