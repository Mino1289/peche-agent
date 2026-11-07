/** Internationalisation UI (FR par défaut). */

export type Locale = "fr" | "en";

const LOCALE_STORAGE = "peche_locale";

type Messages = {
  tabMap: string;
  tabChat: string;
  conversations: string;
  newChat: string;
  loading: string;
  noConversations: string;
  assistant: string;
  chatPlaceholder: string;
  send: string;
  viewOnMap: string;
  toolsCount: (n: number) => string;
  errorPrefix: string;
  restoreMap: string;
  emptyTitle: string;
  emptyHint: string;
  prompt1: string;
  prompt2: string;
  prompt3: string;
  settings: string;
  apiKeyTitle: string;
  apiKeyHint: string;
  apiKeyPlaceholder: string;
  apiKeySave: string;
  apiKeyClear: string;
  apiKeyBanner: string;
  apiKeyGetLink: string;
  about: string;
  aboutTitle: string;
  aboutBody: string;
  aboutDisclaimer: string;
  catalogError: string;
  msgs: string;
  // Carte — catalogue
  layersTitle: string;
  searchPlaceholder: string;
  basemaps: string;
  addLayer: string;
  addLayerTitle: string;
  addLayerSearch: string;
  addLayerUrl: string;
  addLayerName: string;
  addLayerType: string;
  addLayerSubmit: string;
  addLayerCancel: string;
  addLayerValidating: string;
  addLayerDiscoverHint: string;
  addLayerManualHint: string;
  customLayers: string;
  agentThinking: string;
  agentUsingTools: string;
  deleteConversation: string;
  deleteConversationConfirm: string;
  yes: string;
  no: string;
  // Carte — identify / détail
  close: string;
  viewDetail: string;
  addPin: string;
  removeFeaturePin: string;
  removePin: string;
  showOnGmaps: string;
  zoneRegs: string;
  loadingAria: string;
  userPin: string;
  fromLayer: (layer: string) => string;
  regulatoryException: string;
  useDetailForRegs: string;
  station: string;
  waterbody: string;
  state: string;
  level: string;
  flow: string;
  observed: string;
  hqRegion: string;
  hqSeries: string;
  hqTempSpread: string;
  linkHydroQuebec: string;
  linkCeHQGraph: string;
  linkCeHQTable: string;
  linkVigilance: string;
  linkSource: string;
  dataSource: string;
  cachedState: string;
  liveUnavailable: (status: number) => string;
  tidesUnavailable: (status: number) => string;
  observedLevel: string;
  day: string;
  lowTide: string;
  highTide: string;
  lowTide1: string;
  highTide1: string;
  lowTide2: string;
  highTide2: string;
  name: string;
  number: string;
  category: string;
  municipality: string;
  mrc: string;
  cehqSheet: string;
  fishingZone: string;
  exception: string;
  wildlifeTerritory: string;
  huntingForbidden: string;
  unknownStation: string;
  measuresUnavailable: (status: number) => string;
  temperature: string;
  humidity: string;
  wind: string;
  windGust: string;
  pressure: string;
  forecast: string;
  weatherUnavailable: (status: number) => string;
  ecccWeatherPage: string;
  noHistory: string;
  hydroHistoryCeHQ: (days: number) => string;
  hydroHistoryHq: (days: number) => string;
  hydroHistoryCompareCeHQ: (days: number) => string;
  missingTideCode: string;
  unknownZone: string;
  noZoneAtPoint: string;
  zoneRulesUnavailable: (status: number) => string;
  incompletePlan: string;
  planNotFound: (status: number) => string;
  generalZoneRules: (label: string) => string;
  exceptionPlanRules: string;
  zoneRegsTitle: (zone: string) => string;
  // Guide poisson
  speciesGuide: string;
  speciesGuideDisclaimer: string;
  speciesGuideEmpty: string;
  speciesGuideLink: string;
  speciesMeals: (p: string, m: string, g: string) => string;
  speciesStatus: string;
  // Légendes / filtres catalogue
  layerOutline: string;
  layerColor: string;
  changeColor: string;
  legendAlt: string;
  zoomBadgeTitle: string;
  zoneFilterPlaceholder: string;
  etatLegendTitle: string;
  etatNormal: string;
  etatSurveillance: string;
  etatAlerte: string;
  etatAutre: string;
  etatHydroQuebec: string;
  etatIndisponible: string;
};

const FR: Messages = {
  tabMap: "Carte",
  tabChat: "Assistant",
  conversations: "Conversations",
  newChat: "＋ Nouvelle",
  loading: "Chargement…",
  noConversations: "Aucune conversation",
  assistant: "Assistant",
  chatPlaceholder:
    "Posez une question… (règlements, météo, hydro, carte)",
  send: "Envoyer",
  viewOnMap: "Voir sur la carte",
  toolsCount: (n) => `${n} outil(s)`,
  errorPrefix: "Erreur",
  restoreMap: "Voir sur la carte",
  emptyTitle: "Assistant pêche Québec",
  emptyHint:
    "Posez une question sur les règlements, la météo, l'hydrométrie ou demandez d'afficher des couches sur la carte.",
  prompt1: "Quelles sont les règles pour le doré dans la zone 8 aujourd'hui ?",
  prompt2: "Affiche les stations hydro sur le Saguenay",
  prompt3: "Quels plans d'eau sont réglementés près du lac Saint-Jean ?",
  settings: "Paramètres",
  apiKeyTitle: "Clé API Gemini",
  apiKeyHint:
    "Entrez votre clé gratuite Google AI Studio. Elle reste dans votre navigateur.",
  apiKeyPlaceholder: "AIza…",
  apiKeySave: "Enregistrer",
  apiKeyClear: "Effacer",
  apiKeyBanner:
    "Pour utiliser l'assistant, ajoutez votre clé Google AI Studio (gratuite).",
  apiKeyGetLink: "Obtenir une clé",
  about: "À propos",
  aboutTitle: "peche-agent",
  aboutBody:
    "Carte interactive et assistant pour la pêche sportive au Québec. Données : RegPec, Données Québec / MRNF, SHC, Open-Meteo, Atlas de l'eau.",
  aboutDisclaimer:
    "Information à titre indicatif seulement — ne remplace pas les textes officiels de réglementation.",
  catalogError: "Erreur catalogue",
  msgs: "msgs",
  layersTitle: "Couches",
  searchPlaceholder: "Rechercher…",
  basemaps: "Fonds de carte",
  addLayer: "Ajouter une couche",
  addLayerTitle: "Ajouter une couche externe",
  addLayerSearch: "Rechercher dans GetCapabilities…",
  addLayerUrl: "URL du service (WMS/WFS)",
  addLayerName: "Nom technique de la couche",
  addLayerType: "Type",
  addLayerSubmit: "Ajouter",
  addLayerCancel: "Annuler",
  addLayerValidating: "Validation…",
  addLayerDiscoverHint:
    "La recherche interroge quelques services OGC enregistrés (Forêt ouverte, GRHQ, etc.), pas l'intégralité du portail. Si un service est en panne, les résultats peuvent être incomplets.",
  addLayerManualHint:
    "Ajout manuel : collez l'URL WMS ou WFS et le nom exact de la couche (champ « Name » dans GetCapabilities). La couche est validée puis enregistrée dans votre navigateur.",
  customLayers: "Couches ajoutées",
  agentThinking: "Réflexion…",
  agentUsingTools: "Consultation des outils…",
  deleteConversation: "Supprimer",
  deleteConversationConfirm: "Supprimer cette conversation ?",
  yes: "Oui",
  no: "Non",
  close: "Fermer",
  viewDetail: "Voir en détail",
  addPin: "Ajouter en point",
  removeFeaturePin: "Retirer le point",
  removePin: "Retirer",
  showOnGmaps: "Afficher sur Google Maps",
  zoneRegs: "Voir la réglementation de la zone",
  loadingAria: "Chargement",
  userPin: "Point utilisateur",
  fromLayer: (layer) => `Issu de ${layer}`,
  regulatoryException: "Exception réglementaire",
  useDetailForRegs:
    "Utilisez « Voir en détail » pour les règlements de l'exception et de la zone.",
  station: "Station",
  waterbody: "Plan d'eau",
  state: "État",
  level: "Niveau",
  flow: "Débit",
  observed: "Observé",
  hqRegion: "Région",
  hqSeries: "Dernières mesures horaires",
  hqTempSpread: "Température (min ~ max)",
  linkHydroQuebec: "Outil débits et niveaux (HQ)",
  linkCeHQGraph: "Graphique CEHQ",
  linkCeHQTable: "Tableau CEHQ",
  linkVigilance: "Fiche Vigilance",
  linkSource: "Source des données",
  dataSource: "Source",
  cachedState: "État (cache)",
  liveUnavailable: (s) => `Mesures live indisponibles (${s})`,
  tidesUnavailable: (s) => `Marées indisponibles (${s})`,
  observedLevel: "Niveau observé",
  day: "Jour",
  lowTide: "Basse",
  highTide: "Haute",
  lowTide1: "Basse 1",
  highTide1: "Haute 1",
  lowTide2: "Basse 2",
  highTide2: "Haute 2",
  name: "Nom",
  number: "N°",
  category: "Catégorie",
  municipality: "Municipalité",
  mrc: "MRC",
  cehqSheet: "Fiche CEHQ",
  fishingZone: "Zone de pêche",
  exception: "Exception",
  wildlifeTerritory: "Territoire faunique",
  huntingForbidden: "Chasse interdite",
  unknownStation: "Station inconnue",
  measuresUnavailable: (s) => `Mesures indisponibles (${s})`,
  temperature: "Température",
  humidity: "Humidité",
  wind: "Vent",
  windGust: "Rafales",
  pressure: "Pression",
  forecast: "Prévisions",
  weatherUnavailable: (s) => `Météo indisponible (HTTP ${s}).`,
  ecccWeatherPage: "Fiche ECCC",
  noHistory: "Pas d'historique disponible pour cette station.",
  hydroHistoryCeHQ: (days) =>
    `Historique CEHQ — ${days} derniers jours (points horaires)`,
  hydroHistoryHq: (days) =>
    `Historique Hydro-Québec — ${days} jour(s)`,
  hydroHistoryCompareCeHQ: (days) =>
    `Historique CEHQ — ${days} derniers jours (comparaison, points horaires)`,
  missingTideCode: "Code de station manquant",
  unknownZone: "Zone inconnue",
  noZoneAtPoint: "Aucune zone de pêche à cet endroit",
  zoneRulesUnavailable: (s) => `Règles de zone indisponibles (${s})`,
  incompletePlan: "Plan incomplet",
  planNotFound: (s) => `Exception introuvable (${s})`,
  generalZoneRules: (label) => `${label} — règles générales`,
  exceptionPlanRules: "Exception — plan d'eau",
  zoneRegsTitle: (zone) => `Réglementation — ${zone}`,
  speciesGuide: "Espèces (guide consommation)",
  speciesGuideDisclaimer:
    "Sites échantillonnés seulement — ce n'est pas un inventaire exhaustif du plan d'eau.",
  speciesGuideEmpty: "Aucun site du guide pour ce plan d'eau.",
  speciesGuideLink: "Guide officiel MELCCFP",
  speciesMeals: (p, m, g) => `Repas/semaine — P:${p} M:${m} G:${g}`,
  speciesStatus: "Statut pêche",
  layerOutline: "Contour de la couche",
  layerColor: "Couleur de la couche",
  changeColor: "Changer la couleur",
  legendAlt: "légende",
  zoomBadgeTitle: "Niveau de zoom pour afficher cette couche",
  zoneFilterPlaceholder: "ex. 21,23,25-28 ou *",
  etatLegendTitle: "Code couleur des points",
  etatNormal: "Vigilance — normal",
  etatSurveillance: "Vigilance — surveillance",
  etatAlerte: "Vigilance — alerte",
  etatAutre: "Vigilance — sans palier",
  etatHydroQuebec: "Hydro-Québec",
  etatIndisponible: "Hors service / désactivée",
};

const EN: Messages = {
  tabMap: "Map",
  tabChat: "Assistant",
  conversations: "Conversations",
  newChat: "＋ New",
  loading: "Loading…",
  noConversations: "No conversations",
  assistant: "Assistant",
  chatPlaceholder:
    "Ask about regulations, weather, hydrometry, or the map…",
  send: "Send",
  viewOnMap: "View on map",
  toolsCount: (n) => `${n} tool(s)`,
  errorPrefix: "Error",
  restoreMap: "View on map",
  emptyTitle: "Quebec fishing assistant",
  emptyHint:
    "Ask about regulations, weather, streamflow, or request map layers.",
  prompt1: "What are the walleye rules in zone 8 today?",
  prompt2: "Show hydrometric stations on the Saguenay River",
  prompt3: "Which regulated water bodies are near Lake Saint-Jean?",
  settings: "Settings",
  apiKeyTitle: "Gemini API key",
  apiKeyHint:
    "Enter your free Google AI Studio key. It stays in your browser only.",
  apiKeyPlaceholder: "AIza…",
  apiKeySave: "Save",
  apiKeyClear: "Clear",
  apiKeyBanner:
    "To use the assistant, add your free Google AI Studio API key.",
  apiKeyGetLink: "Get a key",
  about: "About",
  aboutTitle: "peche-agent",
  aboutBody:
    "Interactive map and assistant for sport fishing in Quebec. Data: RegPec, Données Québec / MRNF, CHS, Open-Meteo, Atlas de l'eau.",
  aboutDisclaimer:
    "For information only — not a substitute for official regulations.",
  catalogError: "Catalog error",
  msgs: "msgs",
  layersTitle: "Layers",
  searchPlaceholder: "Search…",
  basemaps: "Basemaps",
  addLayer: "Add layer",
  addLayerTitle: "Add an external layer",
  addLayerSearch: "Search GetCapabilities…",
  addLayerUrl: "Service URL (WMS/WFS)",
  addLayerName: "Technical layer name",
  addLayerType: "Type",
  addLayerSubmit: "Add",
  addLayerCancel: "Cancel",
  addLayerValidating: "Validating…",
  addLayerDiscoverHint:
    "Search queries a few registered OGC services (open forest, GRHQ, etc.), not the entire portal. If a service is down, results may be incomplete.",
  addLayerManualHint:
    "Manual add: paste the WMS or WFS URL and the exact layer name (the “Name” field in GetCapabilities). The layer is validated then stored in your browser.",
  customLayers: "Added layers",
  agentThinking: "Thinking…",
  agentUsingTools: "Using tools…",
  deleteConversation: "Delete",
  deleteConversationConfirm: "Delete this conversation?",
  yes: "Yes",
  no: "No",
  close: "Close",
  viewDetail: "View details",
  addPin: "Add as pin",
  removeFeaturePin: "Remove pin",
  removePin: "Remove",
  showOnGmaps: "Open in Google Maps",
  zoneRegs: "View zone regulations",
  loadingAria: "Loading",
  userPin: "User pin",
  fromLayer: (layer) => `From ${layer}`,
  regulatoryException: "Regulatory exception",
  useDetailForRegs:
    "Use “View details” for exception and zone regulations.",
  station: "Station",
  waterbody: "Water body",
  state: "Status",
  level: "Level",
  flow: "Flow",
  observed: "Observed",
  hqRegion: "Region",
  hqSeries: "Latest hourly readings",
  hqTempSpread: "Temperature (min ~ max)",
  linkHydroQuebec: "Flows & levels tool (HQ)",
  linkCeHQGraph: "CHS chart",
  linkCeHQTable: "CHS table",
  linkVigilance: "Vigilance sheet",
  linkSource: "Data source",
  dataSource: "Source",
  cachedState: "Status (cache)",
  liveUnavailable: (s) => `Live readings unavailable (${s})`,
  tidesUnavailable: (s) => `Tides unavailable (${s})`,
  observedLevel: "Observed level",
  day: "Day",
  lowTide: "Low",
  highTide: "High",
  lowTide1: "Low 1",
  highTide1: "High 1",
  lowTide2: "Low 2",
  highTide2: "High 2",
  name: "Name",
  number: "No.",
  category: "Category",
  municipality: "Municipality",
  mrc: "MRC",
  cehqSheet: "CEHQ sheet",
  fishingZone: "Fishing zone",
  exception: "Exception",
  wildlifeTerritory: "Wildlife territory",
  huntingForbidden: "Hunting prohibited",
  unknownStation: "Unknown station",
  measuresUnavailable: (s) => `Readings unavailable (${s})`,
  temperature: "Temperature",
  humidity: "Humidity",
  wind: "Wind",
  windGust: "Gusts",
  pressure: "Pressure",
  forecast: "Forecast",
  weatherUnavailable: (s) => `Weather unavailable (HTTP ${s}).`,
  ecccWeatherPage: "ECCC weather page",
  noHistory: "No history available for this station.",
  hydroHistoryCeHQ: (days) =>
    `CEHQ history — last ${days} days (hourly points)`,
  hydroHistoryHq: (days) =>
    `Hydro-Québec history — ${days} day(s)`,
  hydroHistoryCompareCeHQ: (days) =>
    `CEHQ history — last ${days} days (comparison, hourly points)`,
  missingTideCode: "Missing station code",
  unknownZone: "Unknown zone",
  noZoneAtPoint: "No fishing zone at this location",
  zoneRulesUnavailable: (s) => `Zone rules unavailable (${s})`,
  incompletePlan: "Incomplete plan",
  planNotFound: (s) => `Exception not found (${s})`,
  generalZoneRules: (label) => `${label} — general rules`,
  exceptionPlanRules: "Exception — water body",
  zoneRegsTitle: (zone) => `Regulations — ${zone}`,
  speciesGuide: "Species (consumption guide)",
  speciesGuideDisclaimer:
    "Sampled sites only — not a complete inventory of the water body.",
  speciesGuideEmpty: "No guide site matched this water body.",
  speciesGuideLink: "Official MELCCFP guide",
  speciesMeals: (p, m, g) => `Meals/week — S:${p} M:${m} L:${g}`,
  speciesStatus: "Fishing status",
  layerOutline: "Layer outline",
  layerColor: "Layer color",
  changeColor: "Change color",
  legendAlt: "legend",
  zoomBadgeTitle: "Zoom level required to show this layer",
  zoneFilterPlaceholder: "e.g. 21,23,25-28 or *",
  etatLegendTitle: "Point colour code",
  etatNormal: "Vigilance — normal",
  etatSurveillance: "Vigilance — watch",
  etatAlerte: "Vigilance — alert",
  etatAutre: "Vigilance — no tier",
  etatHydroQuebec: "Hydro-Québec",
  etatIndisponible: "Out of service / inactive",
};

const GROUP_TITLES_EN: Record<string, string> = {
  reglementation: "Fishing regulations",
  faune: "Wildlife",
  hydro_temps_reel: "Real-time hydrometry",
  hydrographie: "Hydrography",
  lidar: "LiDAR",
  territoire: "Territory",
  basemaps: "Basemaps",
};

const TABLE: Record<Locale, Messages> = { fr: FR, en: EN };

let locale: Locale = (localStorage.getItem(LOCALE_STORAGE) as Locale) || "fr";
if (locale !== "fr" && locale !== "en") locale = "fr";

const listeners = new Set<() => void>();

export function getLocale(): Locale {
  return locale;
}

export function setLocale(next: Locale): void {
  if (next === locale) return;
  locale = next;
  localStorage.setItem(LOCALE_STORAGE, next);
  document.documentElement.lang = next;
  for (const cb of listeners) cb();
}

export function onLocaleChange(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

export function t(): Messages {
  return TABLE[locale];
}

export function localeForApi(): Locale {
  return locale;
}

/** Titre de groupe catalogue (API renvoie le FR). */
export function groupTitle(groupId: string, apiTitle: string): string {
  if (locale === "en") {
    return GROUP_TITLES_EN[groupId] || apiTitle;
  }
  return apiTitle;
}

document.documentElement.lang = locale;
