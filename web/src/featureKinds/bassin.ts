/** Bassins hydrographiques (couche locale : identify hors ligne, sans appel réseau). */

import { getLocale, t } from "../i18n";
import { dl, str } from "./html";
import { pick, type FeatureKind, type Props } from "./kind";

function bassinHtml(p: Props): string {
  const m = t();
  const km2 = typeof p.superf_km2 === "number" ? p.superf_km2 : NaN;
  const area = Number.isFinite(km2)
    ? `${km2.toLocaleString(getLocale() === "en" ? "en-CA" : "fr-CA", { maximumFractionDigits: 1 })} km²`
    : "";
  return dl([
    [m.basinName, str(p.nom_bv)],
    [m.basinWatercourse, str(p.nom_cours_eau)],
    [m.basinArea, area],
    [m.basinLevel, str(p.niveau)],
    [m.basinRegion, str(p.reg_hydro)],
  ]);
}

export const bassinKind: FeatureKind = {
  title: (p) => str(p.nom_bv || p.nom_cours_eau) || "Bassin",
  pinKey: (p) => pick(p, "objectid") || null,
  popup: (p) => bassinHtml(p),
  detail(body, hit) {
    body.innerHTML = bassinHtml(hit.props);
  },
};
