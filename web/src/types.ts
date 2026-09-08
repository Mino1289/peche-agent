/** Types partagés SPA ↔ API. */

export type MapPin = {
  id: string;
  n?: number;
  lon: number;
  lat: number;
  label?: string;
  source?: "user" | "feature";
  layer?: string;
  props?: Record<string, unknown>;
};

export type MapState = {
  center: [number, number]; // [lon, lat]
  zoom: number;
  bbox: [number, number, number, number];
  basemap: string;
  layers: LayerState[];
  zoneFilter?: { zoneId: number };
  selection?: { layer: string; feature: Record<string, unknown> };
  pins?: MapPin[];
};

export type LayerState = {
  id: string;
  visible: boolean;
  opacity: number;
  filters?: Record<string, unknown>;
};

export type FilterSpec = {
  kind: "cql" | "arcgis" | "local" | "none" | "colorkey";
  attr?: string | null;
  options?: { value: string; label: string; color?: string }[];
  multi?: boolean;
};

export type LayerDef = {
  id: string;
  title: string;
  group: string;
  source_type: string;
  url: string;
  layer_name?: string | null;
  curated?: boolean;
  filter_spec?: FilterSpec | null;
  legend_url?: string | null;
  min_zoom?: number | null;
  max_zoom?: number | null;
  opacity?: number;
  visible_default?: boolean;
  identify?: boolean;
  attribution?: string | null;
  color?: string | null;
  extra?: Record<string, unknown>;
};

export type CatalogGroup = {
  id: string;
  title: string;
  layers: LayerDef[];
};

export type Catalog = {
  version: number;
  harvested_at: string;
  basemaps: LayerDef[];
  groups: CatalogGroup[];
  curated_ids: string[];
};

export type MapAction = {
  type: "map_action";
  action: string;
  [key: string]: unknown;
};

export type ChatEvent =
  | { type: "session"; session_id: string }
  | { type: "text"; text: string }
  | { type: "tool_call"; name: string; args: Record<string, unknown> }
  | { type: "tool_result"; name: string; result: unknown }
  | MapAction
  | { type: "error"; error: string }
  | { type: "done" };

export type ToolEntry = {
  name: string;
  args: unknown;
  result?: unknown;
};

export type ChatMessage = {
  role: "user" | "assistant";
  text: string;
  tools?: ToolEntry[];
  map_state?: MapState;
};

/** Point de série CEHQ (~horaire). */
export type HydroSeriesPoint = {
  observed_at: string;
  niveau_m?: number | null;
  debit_m3s?: number | null;
};

export type HydroDailyPoint = {
  date: string;
  niveau_m_mean?: number | null;
  niveau_m_min?: number | null;
  niveau_m_max?: number | null;
  debit_m3s_mean?: number | null;
  debit_m3s_min?: number | null;
  debit_m3s_max?: number | null;
};

export type HydroHistory = {
  period_days?: number;
  has_niveau?: boolean;
  has_debit?: boolean;
  series?: HydroSeriesPoint[];
  daily?: HydroDailyPoint[];
  trend?: {
    niveau_m?: string | null;
    debit_m3s?: string | null;
  };
};

/** Résultat hydromet aplati (une station = une entrée chartable). */
export type HydroResult = {
  plan_nom?: string;
  plan_eau?: string;
  matched_station_plan_eau?: string;
  station_id?: string | number;
  description?: string;
  requested_metrics?: "level" | "flow" | "both" | string;
  niveau_m?: number | null;
  debit_m3s?: number | null;
  observed_at?: string | null;
  distance_km?: number | null;
  match_reason?: string | null;
  history?: HydroHistory | null;
  error?: string;
  error_no_station?: boolean;
  stations?: Record<string, unknown>[];
};
