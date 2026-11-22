import "ol/ol.css";
import "./styles.css";

import { MapController } from "./map";
import { CatalogPanel } from "./catalogPanel";
import { ChatPanel } from "./chatPanel";
import { DetailPanel } from "./detailPanel";
import { getLocale, onLocaleChange, setLocale, t } from "./i18n";
import { navigate, parseRoute, type Route } from "./router";

const app = document.querySelector<HTMLDivElement>("#app")!;
app.classList.add("view-map");

type Controllers = {
  map: MapController;
  catalogPanel: CatalogPanel;
  detailPanel: DetailPanel;
  chatPanel: ChatPanel;
};

let controllers: Controllers;

function renderAppShell(): void {
  const m = t();
  app.innerHTML = `
  <nav class="app-tabs" role="tablist">
    <button type="button" class="tab-btn active" data-tab="map" role="tab" aria-selected="true">${m.tabMap}</button>
    <button type="button" class="tab-btn" data-tab="chat" role="tab" aria-selected="false">${m.tabChat}</button>
    <div class="lang-toggle" role="group" aria-label="Language">
      <button type="button" class="lang-btn ${getLocale() === "fr" ? "active" : ""}" data-lang="fr">FR</button>
      <button type="button" class="lang-btn ${getLocale() === "en" ? "active" : ""}" data-lang="en">EN</button>
    </div>
  </nav>
  <div class="tab-map" id="tab-map">
    <aside class="left-panel" id="catalog-panel"></aside>
    <div class="map-wrap">
      <main id="map"></main>
      <div id="pin-list" class="pin-list" hidden></div>
      <button type="button" id="mobile-layers-btn" class="mobile-fab mobile-only" aria-controls="catalog-panel" aria-expanded="false">
        <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <polygon points="12 2 2 7 12 12 22 7 12 2"/>
          <polyline points="2 17 12 22 22 17"/>
          <polyline points="2 12 12 17 22 12"/>
        </svg>
        <span class="mobile-fab-label">${m.layersTitle}</span>
        <span class="badge mobile-fab-count" hidden></span>
      </button>
    </div>
    <aside class="detail-panel" id="detail-panel" hidden></aside>
  </div>
  <div class="tab-chat" id="tab-chat" hidden>
    <aside class="left-panel chat-sidebar" id="chat-sidebar"></aside>
    <div id="chat-panel"></div>
  </div>
  <div class="mobile-backdrop" id="mobile-backdrop" hidden></div>`;

  for (const btn of app.querySelectorAll<HTMLButtonElement>(".lang-btn")) {
    btn.addEventListener("click", () => {
      const lang = btn.dataset.lang === "en" ? "en" : "fr";
      setLocale(lang);
    });
  }
}

function updateAppShellLocale(): void {
  const m = t();
  const mapBtn = app.querySelector<HTMLButtonElement>('[data-tab="map"]');
  const chatBtn = app.querySelector<HTMLButtonElement>('[data-tab="chat"]');
  const layersFabLabel = app.querySelector<HTMLElement>("#mobile-layers-btn .mobile-fab-label");
  if (mapBtn) mapBtn.textContent = m.tabMap;
  if (chatBtn) chatBtn.textContent = m.tabChat;
  if (layersFabLabel) layersFabLabel.textContent = m.layersTitle;
  for (const btn of app.querySelectorAll<HTMLButtonElement>(".lang-btn")) {
    btn.classList.toggle("active", btn.dataset.lang === getLocale());
  }
}

function closeMobileDrawers(): void {
  const catalog = document.querySelector<HTMLElement>("#catalog-panel");
  const chatSidebar = document.querySelector<HTMLElement>("#chat-sidebar");
  const backdrop = document.querySelector<HTMLElement>("#mobile-backdrop");
  catalog?.classList.remove("is-open");
  chatSidebar?.classList.remove("is-open");
  if (backdrop) backdrop.hidden = true;
  document.querySelector("#mobile-layers-btn")?.setAttribute("aria-expanded", "false");
  document.querySelector("#btn-mobile-history")?.setAttribute("aria-expanded", "false");
}

function toggleMobileDrawer(panel: HTMLElement | null, triggerSelector: string): void {
  if (!panel) return;
  const opening = !panel.classList.contains("is-open");
  closeMobileDrawers();
  if (!opening) return;
  panel.classList.add("is-open");
  const backdrop = document.querySelector<HTMLElement>("#mobile-backdrop");
  if (backdrop) backdrop.hidden = false;
  document.querySelector(triggerSelector)?.setAttribute("aria-expanded", "true");
}

function bindMobileDrawers(): void {
  document.querySelector("#mobile-layers-btn")?.addEventListener("click", () => {
    toggleMobileDrawer(document.querySelector<HTMLElement>("#catalog-panel"), "#mobile-layers-btn");
  });
  document.querySelector("#mobile-backdrop")?.addEventListener("click", closeMobileDrawers);
  window.addEventListener("peche:close-drawers", closeMobileDrawers);
  window.addEventListener("peche:toggle-chat-sidebar", () => {
    toggleMobileDrawer(document.querySelector<HTMLElement>("#chat-sidebar"), "#btn-mobile-history");
  });
  window.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") closeMobileDrawers();
  });
}

function updateMobileLayersBadge(): void {
  const badge = document.querySelector<HTMLElement>("#mobile-layers-btn .mobile-fab-count");
  if (!badge || !controllers) return;
  const count = controllers.map.visibleOverlayCount();
  badge.hidden = count === 0;
  badge.textContent = String(count);
}

function bindTabs(): void {
  for (const btn of app.querySelectorAll<HTMLButtonElement>(".tab-btn")) {
    btn.addEventListener("click", () => {
      if (btn.dataset.tab === "chat") {
        goTo({ tab: "chat", id: controllers.chatPanel.getSessionId() });
      } else {
        goTo({ tab: "map" });
      }
    });
  }
}

/** Affiche une route (onglet + conversation) sans toucher à l'historique. */
function applyRoute(route: Route): void {
  if (route.tab === "map") {
    showTab("map");
    return;
  }
  showTab("chat");
  if (route.id !== controllers.chatPanel.getSessionId()) {
    void controllers.chatPanel.showConversation(route.id);
  }
}

/** Change de route et l'inscrit dans l'historique navigateur (avant/arrière). */
function goTo(route: Route): void {
  navigate(route, "push");
  applyRoute(route);
}

function initControllers(): Controllers {
  const mapEl = document.querySelector<HTMLElement>("#map")!;
  const catalogEl = document.querySelector<HTMLElement>("#catalog-panel")!;
  const chatEl = document.querySelector<HTMLElement>("#chat-panel")!;
  const chatSidebarEl = document.querySelector<HTMLElement>("#chat-sidebar")!;
  const pinListEl = document.querySelector<HTMLElement>("#pin-list")!;
  const detailEl = document.querySelector<HTMLElement>("#detail-panel")!;
  const tabMap = document.querySelector<HTMLElement>("#tab-map")!;

  const map = new MapController(mapEl);
  map.setPinListEl(pinListEl);
  const catalogPanel = new CatalogPanel(catalogEl, map);
  const detailPanel = new DetailPanel(detailEl, tabMap, map);
  map.setDetailHandler((hit) => {
    void detailPanel.show(hit);
  });
  const chatPanel = new ChatPanel(chatEl, chatSidebarEl, map);
  return { map, catalogPanel, detailPanel, chatPanel };
}

function loadCatalog(): void {
  controllers.map
    .loadCatalog()
    .then((catalog) => {
      controllers.catalogPanel.render(catalog);
      updateMobileLayersBadge();
    })
    .catch((err) => {
      const catalogEl = document.querySelector<HTMLElement>("#catalog-panel")!;
      catalogEl.innerHTML = `<div class="panel-header"><h2>${t().catalogError}</h2></div><p class="muted" style="padding:12px">${String(err)}</p>`;
    });
}

function bindMapMoveRefresh(): void {
  let tMove: number | undefined;
  controllers.map.map.on("moveend", () => {
    window.clearTimeout(tMove);
    tMove = window.setTimeout(() => {
      void controllers.map.refreshVisibleVectorLayers();
    }, 450);
  });
}

function showTab(tab: "map" | "chat"): void {
  closeMobileDrawers();
  const tabMap = document.querySelector<HTMLElement>("#tab-map")!;
  const tabChat = document.querySelector<HTMLElement>("#tab-chat")!;
  const isMap = tab === "map";
  app.classList.toggle("view-map", isMap);
  app.classList.toggle("view-chat", !isMap);
  tabMap.hidden = !isMap;
  tabChat.hidden = isMap;
  for (const btn of app.querySelectorAll<HTMLButtonElement>(".tab-btn")) {
    const on = btn.dataset.tab === tab;
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
  }
  if (isMap) {
    requestAnimationFrame(() => controllers.map.map.updateSize());
  }
}

renderAppShell();
bindTabs();
bindMobileDrawers();
controllers = initControllers();
controllers.map.onLayersChange(updateMobileLayersBadge);
if (import.meta.env.DEV) {
  (window as unknown as { pecheMap: typeof controllers.map.map }).pecheMap = controllers.map.map;
}
bindMapMoveRefresh();
loadCatalog();

window.addEventListener("peche:show-map", () => goTo({ tab: "map" }));
window.addEventListener("popstate", () => applyRoute(parseRoute()));

const initialRoute = parseRoute();
navigate(initialRoute, "replace");
applyRoute(initialRoute);

onLocaleChange(() => {
  updateAppShellLocale();
  const catalog = controllers.map.getCatalog();
  if (catalog) controllers.catalogPanel.render(catalog);
  controllers.map.refreshLocale();
  void controllers.detailPanel.refreshLocale();
  requestAnimationFrame(() => controllers.map.map.updateSize());
});
