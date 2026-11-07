/** Contrat d’un type d’entité identifiable (popup carte + panneau détail). */

import type { Coordinate } from "ol/coordinate";

export type Props = Record<string, unknown>;

/** Résultat d’un chargement live : données JSON, ou statut HTTP en échec. */
export type Loaded<D> = { data: D } | { status: number };

export type IdentifyHit = {
  layerId: string;
  props: Props;
  coordinate: Coordinate;
  /** Chargement lancé par le popup (promesse partagée avec le panneau détail). */
  loaded?: Promise<Loaded<unknown> | undefined>;
};

export type DetailCtx = {
  focusZone(zoneId: number): void;
  setTitle(text: string): void;
};

export type FeatureKind<D = any> = {
  title(props: Props, layerId: string): string;
  /** Identifiant stable de l’entité (sans préfixe de couche) ; null = non épinglable. */
  pinKey?(props: Props, lon?: number, lat?: number): string | null;
  /** undefined = rien à charger (identifiant absent). */
  load?(props: Props): Promise<Loaded<D> | undefined>;
  /** Absent = type détail seulement (non cliquable sur la carte). */
  popup?(props: Props, loaded: Loaded<D> | undefined): string;
  detail?(
    body: HTMLElement,
    hit: IdentifyHit,
    loaded: Loaded<D> | undefined,
    ctx: DetailCtx,
  ): Promise<void> | void;
  popupClass?: string;
};

export async function getJson<D>(url: string): Promise<Loaded<D>> {
  const resp = await fetch(url);
  if (!resp.ok) return { status: resp.status };
  return { data: (await resp.json()) as D };
}

export function stripGeom(props: Props): Props {
  const out: Props = {};
  for (const [k, v] of Object.entries(props)) {
    if (k === "geometry" || k === "features") continue;
    out[k] = v;
  }
  return out;
}

export function pick(props: Props, ...keys: string[]): string {
  for (const k of keys) {
    const v = props[k];
    if (v != null && String(v).trim() !== "") return String(v).trim();
  }
  return "";
}
