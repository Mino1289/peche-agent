/** Petits gabarits HTML partagés par les types d’entités. */

import { escapeHtml } from "../regs";
import { t } from "../i18n";

export function str(v: unknown): string {
  if (v == null) return "";
  return String(v);
}

export function dl(rows: [string, string][]): string {
  const items = rows
    .filter(([, v]) => v)
    .map(
      ([k, v]) =>
        `<div class="identify-row"><span>${escapeHtml(k)}</span><strong>${escapeHtml(v)}</strong></div>`,
    );
  return `<div class="identify-dl">${items.join("")}</div>`;
}

export function errorHtml(message: string): string {
  return `<p class="identify-error">${escapeHtml(message)}</p>`;
}

function linkLabel(key: string): string {
  const m = t();
  const labels: Record<string, string> = {
    hydroquebec: m.linkHydroQuebec,
    cehq: m.linkCeHQGraph,
    cehq_tableau: m.linkCeHQTable,
    cehq_export: "Export CEHQ",
    vigilance: m.linkVigilance,
    source: m.linkSource,
  };
  return labels[key] ?? key.replace(/_/g, " ");
}

export function linksHtml(urls: Record<string, string> | undefined): string {
  if (!urls) return "";
  const links = Object.entries(urls)
    .filter(([, u]) => u)
    .map(
      ([k, u]) =>
        `<a href="${escapeHtml(u)}" target="_blank" rel="noopener">${escapeHtml(linkLabel(k))}</a>`,
    );
  return links.length ? `<p class="identify-links">${links.join(" · ")}</p>` : "";
}

export function zoneLabelFromProps(p: Record<string, unknown>): string {
  if (p.zone_nom) return String(p.zone_nom);
  if (p.no_zone != null && p.no_zone !== "") return `Zone ${p.no_zone}`;
  if (p.zone_id != null && p.zone_id !== "") return `Zone (id ${p.zone_id})`;
  return "";
}
