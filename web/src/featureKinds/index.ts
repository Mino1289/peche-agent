/** Registre des types d’entités : un type par couche identifiable. */

import { escapeHtml } from "../regs";
import { uninvertName } from "../names";
import { barrageKind } from "./barrage";
import {
  chasseInterditeKind,
  stationLavageKind,
  tfsKind,
} from "./faune";
import { hydroKind } from "./hydro";
import { stripGeom, type DetailCtx, type FeatureKind, type IdentifyHit, type Props } from "./kind";
import { planKind } from "./plan";
import { tidesKind } from "./tides";
import { weatherKind } from "./weather";
import { zoneKind } from "./zone";

export type { DetailCtx, IdentifyHit } from "./kind";

const KINDS: Record<string, FeatureKind> = {
  barrages_cehq: barrageKind,
  vigilance_stations: hydroKind,
  marees_shc: tidesKind,
  meteo_eccc: weatherKind,
  plans_regpec: planKind,
  tfs: tfsKind,
  chasse_interdite: chasseInterditeKind,
  stations_lavage: stationLavageKind,
  zone: zoneKind,
};

const rawKind: Required<Pick<FeatureKind, "title" | "pinKey" | "popup" | "detail">> = {
  title: (p, layerId) => uninvertName(String(p.nom || p.name || layerId)),
  pinKey: (_p, lon, lat) =>
    lon != null && lat != null ? `${lon.toFixed(5)},${lat.toFixed(5)}` : null,
  popup: (p) =>
    `<pre class="identify-raw">${escapeHtml(JSON.stringify(stripGeom(p), null, 2).slice(0, 800))}</pre>`,
  detail(body, hit) {
    body.innerHTML = `<pre class="identify-raw">${escapeHtml(
      JSON.stringify(hit.props, null, 2).slice(0, 2000),
    )}</pre>`;
  },
};

function kindOf(layerId: string): FeatureKind {
  return KINDS[layerId] ?? rawKind;
}

function loadOnce(hit: IdentifyHit): NonNullable<IdentifyHit["loaded"]> {
  if (!hit.loaded) {
    const kind = kindOf(hit.layerId);
    hit.loaded = (kind.load ? kind.load(hit.props) : Promise.resolve(undefined)).catch((err) => {
      hit.loaded = undefined;
      throw err;
    });
  }
  return hit.loaded;
}

/** Couche cliquable sur la carte (les types détail seulement, comme `zone`, sont exclus). */
export function isIdentifiable(layerId: string): boolean {
  if (layerId.startsWith("custom:")) return true;
  return Boolean(KINDS[layerId]?.popup);
}

export function titleFor(hit: Pick<IdentifyHit, "layerId" | "props">): string {
  return kindOf(hit.layerId).title(hit.props, hit.layerId);
}

/** Clé stable pour éviter les doublons « ajouter en point » sur la même entité. */
export function featurePinKey(layer: string, props: Props, lon?: number, lat?: number): string | null {
  const key = (kindOf(layer).pinKey ?? rawKind.pinKey)(props, lon, lat);
  return key ? `${layer}:${key}` : null;
}

export function popupClass(layerId: string): string | undefined {
  return kindOf(layerId).popupClass;
}

export async function popupHtml(hit: IdentifyHit): Promise<string> {
  const kind = kindOf(hit.layerId);
  return (kind.popup ?? rawKind.popup)(hit.props, await loadOnce(hit));
}

export async function renderDetail(body: HTMLElement, hit: IdentifyHit, ctx: DetailCtx): Promise<void> {
  const kind = kindOf(hit.layerId);
  await (kind.detail ?? rawKind.detail)(body, hit, await loadOnce(hit), ctx);
}
