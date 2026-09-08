/** Paramètres utilisateur (localStorage). */

import type { Locale } from "./i18n";

const API_KEY_STORAGE = "peche_gemini_api_key";

export function getApiKey(): string {
  return localStorage.getItem(API_KEY_STORAGE) || "";
}

export function setApiKey(key: string): void {
  const trimmed = key.trim();
  if (trimmed) {
    localStorage.setItem(API_KEY_STORAGE, trimmed);
  } else {
    localStorage.removeItem(API_KEY_STORAGE);
  }
}

export function clearApiKey(): void {
  localStorage.removeItem(API_KEY_STORAGE);
}

export type HealthInfo = {
  data_ready: boolean;
  server_api_key: boolean;
  api_key: boolean;
  mcp_enabled: boolean;
};

export async function fetchHealth(): Promise<HealthInfo | null> {
  try {
    const resp = await fetch("/api/health");
    if (!resp.ok) return null;
    return (await resp.json()) as HealthInfo;
  } catch {
    return null;
  }
}

export function chatKeyAvailable(health: HealthInfo | null): boolean {
  return Boolean(health?.server_api_key || getApiKey());
}
