/** Couches WFS faune / territoires : popup statique, détail JSON brut. */

import { t } from "../i18n";
import { formatSpeciesList, titleFr, uninvertName } from "../names";
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
      ["Type", titleFr(str(p.TYPE || p.TYPE_TFS))],
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

function habitatKind(fallbackTitle: string): FeatureKind {
  return {
    title(p) {
      const place = str(p.TOPONYME || p.NOM_HABITAT || p.NOM || p.nom);
      const category = str(p.CATEGORIE || p.STATUT || p.TYPE_HABITAT);
      if (place) return titleFr(place);
      if (category) return titleFr(category);
      return fallbackTitle;
    },
    pinKey: wfsPinKey,
    popup(p) {
      const species = formatSpeciesList(p.ESPECE || p.ESPECE_CIBLE || p.NOM_ESPECE);
      const rows: [string, string][] = [
        ["Lieu", titleFr(str(p.TOPONYME || p.NOM_HABITAT || p.NOM || p.nom || p.name))],
        ["Catégorie", titleFr(str(p.CATEGORIE || p.TYPE_HABITAT || p.TYPE || p.CLASSE))],
        ["Statut", titleFr(str(p.STATUT))],
        ["Espèces", species],
        ["Région faunique", titleFr(str(p.REG_FAUNE || p.REG_ADMIN))],
        ["Superficie", p.SUP_HA != null && String(p.SUP_HA).trim() ? `${p.SUP_HA} ha` : ""],
      ];
      return dl(rows.filter(([, v]) => v));
    },
  };
}

export const habitatLegalKind = habitatKind("Habitat faunique légal");
export const habitatInfoKind = habitatKind("Habitat faunique informationnel");

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
