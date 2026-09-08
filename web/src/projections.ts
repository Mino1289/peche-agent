/** Projections — EPSG:3857 (affichage) + EPSG:32198 (Québec Lambert). */

import proj4 from "proj4";
import { register } from "ol/proj/proj4";
import { get as getProjection } from "ol/proj";

const QUEBEC_LAMBERT =
  "+proj=lcc +lat_1=60 +lat_2=46 +lat_0=44 +lon_0=-68.5 +x_0=0 +y_0=0 " +
  "+ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs";

export function registerProjections(): void {
  proj4.defs("EPSG:32198", QUEBEC_LAMBERT);
  register(proj4);
  const p = getProjection("EPSG:32198");
  if (p) {
    p.setExtent([-799574, 45802, 891595.4, 1849567.5]);
  }
}
