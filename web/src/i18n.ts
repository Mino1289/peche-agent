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
