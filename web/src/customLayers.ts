/** Couches custom Forêt ouverte — localStorage + validation API. */

import type { LayerDef } from "./types";

const STORAGE_KEY = "peche_custom_layers";

export function loadStoredCustomLayers(): LayerDef[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as LayerDef[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveStoredCustomLayers(layers: LayerDef[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(layers));
}

export function addStoredCustomLayer(layer: LayerDef): LayerDef[] {
  const layers = loadStoredCustomLayers().filter((l) => l.id !== layer.id);
  layers.push(layer);
  saveStoredCustomLayers(layers);
  return layers;
}

export function removeStoredCustomLayer(id: string): LayerDef[] {
  const layers = loadStoredCustomLayers().filter((l) => l.id !== id);
  saveStoredCustomLayers(layers);
  return layers;
}

export type DiscoverHit = {
  id: string;
  title: string;
  layer_name?: string | null;
  source_type: string;
  url: string;
  source_id: string;
  source_title: string;
};

export async function discoverLayers(q: string): Promise<DiscoverHit[]> {
  const resp = await fetch(`/api/catalog/discover?q=${encodeURIComponent(q)}`);
  if (!resp.ok) throw new Error(`Discover failed (${resp.status})`);
  const data = (await resp.json()) as { layers?: DiscoverHit[] };
  return data.layers || [];
}

export async function validateCustomLayer(args: {
  url: string;
  layer_name: string;
  source_type: string;
}): Promise<{ ok: boolean; layer?: LayerDef; error?: string }> {
  const resp = await fetch("/api/catalog/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(args),
  });
  const data = (await resp.json()) as {
    ok?: boolean;
    layer?: LayerDef;
    error?: string;
  };
  if (!resp.ok || !data.ok || !data.layer) {
    return { ok: false, error: data.error || `Validation failed (${resp.status})` };
  }
  return { ok: true, layer: data.layer };
}
