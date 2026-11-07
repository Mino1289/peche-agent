/** Barrages CEHQ (données locales, sans chargement live). */

import { escapeHtml } from "../regs";
import { t } from "../i18n";
import { uninvertName } from "../names";
import { dl, str } from "./html";
import { pick, type FeatureKind, type Props } from "./kind";

function barrageHtml(p: Props): string {
  const m = t();
  let html = dl([
    [m.name, uninvertName(str(p.nom || p.name))],
    [m.number, str(p.numero)],
    [m.category, str(p.categorie)],
    [m.waterbody, uninvertName(str(p.plan_eau))],
    [m.municipality, str(p.municipalite)],
    [m.mrc, str(p.mrc)],
  ]);
  const url = str(p.url_fiche);
  if (url) {
    html += `<p><a href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(m.cehqSheet)}</a></p>`;
  }
  return html;
}

export const barrageKind: FeatureKind = {
  title: (p) => uninvertName(String(p.nom || p.name || `Barrage ${p.numero || ""}`.trim())),
  pinKey: (p) => pick(p, "numero", "id") || null,
  popup: (p) => barrageHtml(p),
  detail(body, hit) {
    body.innerHTML = barrageHtml(hit.props);
  },
};
