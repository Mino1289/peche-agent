/** Libellés lisibles des appels d'outils de l'agent (affichage prod). */

import { getLocale } from "./i18n";
import type { MapPin, ToolEntry } from "./types";
import { loadZoneOptions, type ZoneOption } from "./zonePicker";

type Args = Record<string, unknown>;
type Ctx = { fr: boolean; zones: ZoneOption[]; pins: MapPin[] };

const TITLES: Record<string, [string, string]> = {
  list_zones: ["Zones de pêche", "Fishing zones"],
  search_plans: ["Recherche de plans d'eau", "Water body search"],
  get_reglements: ["Règlements", "Regulations"],
  get_weather: ["Météo", "Weather"],
  search_stations: ["Recherche de stations", "Station search"],
  get_hydromet: ["Hydrométrie", "Hydrometry"],
  get_hydromet_for_waterbody: ["Hydrométrie du plan d'eau", "Hydrometry for water body"],
  get_hydromet_at_plan: ["Hydrométrie au plan", "Hydrometry at plan"],
  get_iqbp: ["Qualité de l'eau (IQBP)", "Water quality (IQBP)"],
  search_tide_stations: ["Recherche de stations de marée", "Tide station search"],
  get_tides: ["Marées", "Tides"],
  get_tides_at_place: ["Marées au lieu", "Tides at place"],
  get_tides_at_plan: ["Marées au plan", "Tides at plan"],
  get_water_levels: ["Niveaux d'eau", "Water levels"],
  search_barrages: ["Recherche de barrages", "Dam search"],
  get_barrages_at_plan: ["Barrages au plan", "Dams at plan"],
  get_barrages_at_place: ["Barrages au lieu", "Dams at place"],
  get_species_at_plan: ["Espèces au plan", "Species at plan"],
  get_fishing_advice: ["Conseils de pêche", "Fishing advice"],
  get_map_context: ["Contexte de la carte", "Map context"],
  set_map_view: ["Vue de la carte", "Map view"],
  toggle_layers: ["Couches affichées", "Layer visibility"],
  set_layer_filter: ["Filtre de couche", "Layer filter"],
  filter_by_zone: ["Filtre par zone", "Zone filter"],
  highlight_features: ["Mise en évidence", "Highlight"],
  get_point_info: ["Informations du point", "Point info"],
  scout_at_plan: ["Conditions au plan", "Conditions at plan"],
};

/** Tolérance (degrés) pour retrouver le pin d'un point passé en lat/lon. */
const PIN_TOL = 1e-4;

function pinNumber(ctx: Ctx, lat: unknown, lon: unknown): number | undefined {
  return ctx.pins.find(
    (p) => Math.abs(p.lat - Number(lat)) < PIN_TOL && Math.abs(p.lon - Number(lon)) < PIN_TOL,
  )?.n;
}

function zoneNumber(ctx: Ctx, zoneId: unknown): string | undefined {
  const z = ctx.zones.find((x) => x.zone_id === Number(zoneId));
  return z ? String(z.no_zone ?? z.zone_nom) : undefined;
}

/** Libellés sur mesure : les IDs y sont remplacés par le nom auquel ils se rapportent. */
const SPECIFIC: Record<string, (args: Args, ctx: Ctx) => string | undefined> = {
  get_point_info: (a, c) =>
    a.pin_number == null
      ? undefined
      : c.fr
        ? `Récupération des informations du point N°${a.pin_number}`
        : `Getting info for point #${a.pin_number}`,
  get_weather: (a, c) => {
    const n = pinNumber(c, a.lat, a.lon);
    if (n == null) return undefined;
    return c.fr ? `Récupération météo au point N°${n}` : `Weather at point #${n}`;
  },
  search_plans: (a, c) => {
    const zone = zoneNumber(c, a.zone_id);
    const q = a.query ? String(a.query) : "";
    if (c.fr) {
      return `Recherche${q ? ` du "${q}"` : " de plans d'eau"}${zone ? ` dans la Zone ${zone}` : ""}`;
    }
    return `Searching${q ? ` "${q}"` : " water bodies"}${zone ? ` in zone ${zone}` : ""}`;
  },
};

function genericLabel(tool: ToolEntry, args: Args, ctx: Ctx): string {
  const title = TITLES[tool.name];
  let label = title ? (ctx.fr ? title[0] : title[1]) : tool.name;
  const result = tool.result as { plan_nom?: unknown } | undefined;
  const name = args.query ?? args.place ?? result?.plan_nom;
  if (name) label += ` : ${name}`;
  const zone = args.zone_id != null ? zoneNumber(ctx, args.zone_id) : undefined;
  if (zone) label += ctx.fr ? ` (Zone ${zone})` : ` (zone ${zone})`;
  return label;
}

/** Une ligne lisible par appel d'outil, dans l'ordre des appels. */
export async function toolLabels(tools: ToolEntry[], pins: MapPin[]): Promise<string[]> {
  const zones = await loadZoneOptions().catch(() => [] as ZoneOption[]);
  const ctx: Ctx = { fr: getLocale() === "fr", zones, pins };
  return tools.map((tool) => {
    const args = (tool.args ?? {}) as Args;
    return SPECIFIC[tool.name]?.(args, ctx) ?? genericLabel(tool, args, ctx);
  });
}
