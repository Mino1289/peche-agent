/** Couches WFS faune / territoires : popup statique, détail JSON brut. */

import { t } from "../i18n";
import { titleFr, uninvertName } from "../names";
import { dl, str } from "./html";
import { pick, type FeatureKind, type Props } from "./kind";

const wfsPinKey = (p: Props) =>
  pick(p, "OBJECTID", "objectid", "FID", "id", "NOM", "TOPONYME") || null;

export const tfsKind: FeatureKind = {
  title: (p) =>
    titleFr(
      uninvertName(String(p.NOM || p.NOM_TFS || p.NOM_ZEC || p.nom || p.name || t().wildlifeTerritory)),
    ),
  pinKey: wfsPinKey,
  /** Popup léger : pas de règlements (réservés au panneau détail). */
  popup: (p) =>
    dl([
      [t().name, titleFr(uninvertName(str(p.NOM || p.NOM_TFS || p.NOM_ZEC || p.nom || p.name)))],
      ["Type", titleFr(str(p.DESCRIPTION || p.TYPE || p.TYPE_TFS))],
    ]),
};

export const chasseInterditeKind: FeatureKind = {
  title: (p) => titleFr(uninvertName(String(p.TOPONYME || p.NOM || p.nom || t().huntingForbidden))),
  pinKey: wfsPinKey,
  popup(p) {
    const name = str(p.TOPONYME || p.NOM || p.nom || p.name);
    const kind = str(p.DESIGNOM || p.DESIG_GR);
    const rows: [string, string][] = [[t().name, titleFr(uninvertName(name))]];
    if (kind) rows.push(["Type", titleFr(kind)]);
    return dl(rows);
  },
};

export const stationLavageKind: FeatureKind = {
  title: (p) => String(p.NOM || p.nom || p.name || "Station de lavage"),
  pinKey: wfsPinKey,
  popup: (p) =>
    dl([
      [t().name, str(p.NOM || p.nom || p.name)],
      ["Adresse", str(p.ADRESSE || p.adresse)],
      [t().municipality, str(p.MUNICIPALITE || p.municipalite)],
    ]),
};
