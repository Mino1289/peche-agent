import "ol/ol.css";
import "./styles.css";

import { MapController } from "./map";
import { CatalogPanel } from "./catalogPanel";
import { ChatPanel } from "./chatPanel";
import { DetailPanel } from "./detailPanel";
import { getLocale, onLocaleChange, setLocale, t } from "./i18n";

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
    </div>
    <aside class="detail-panel" id="detail-panel" hidden></aside>
  </div>
  <div class="tab-chat" id="tab-chat" hidden>
    <aside class="left-panel chat-sidebar" id="chat-sidebar"></aside>
    <div id="chat-panel"></div>
  </div>`;

  for (const btn of app.querySelectorAll<HTMLButtonElement>(".lang-btn")) {
    btn.addEventListener("click", () => {
      const lang = btn.dataset.lang === "en" ? "en" : "fr";
      setLocale(lang);
    });
  }
}

function bindTabs(): void {
  for (const btn of app.querySelectorAll<HTMLButtonElement>(".tab-btn")) {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab === "chat" ? "chat" : "map";
      showTab(tab);
    });
  }
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
      const state = controllers.map.getMapState();
      for (const layer of state.layers) {
        if (layer.visible) void controllers.map.refreshVectorLayer(layer.id);
      }
    }, 300);
  });
}

function showTab(tab: "map" | "chat"): void {
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
controllers = initControllers();
bindMapMoveRefresh();
loadCatalog();

window.addEventListener("peche:show-map", () => showTab("map"));

onLocaleChange(() => {
  renderAppShell();
  bindTabs();
  controllers = initControllers();
  bindMapMoveRefresh();
  loadCatalog();
});
