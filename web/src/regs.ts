/** Tableaux de règlements (popup identify + panneau détail). */

export type RegRow = {
  periode?: string;
  debut?: string | null;
  fin?: string | null;
  segment?: string;
  limite_prise?: string;
  limite_longueur?: string;
  engin?: string;
  note?: string;
};

export type SpeciesTimeline = {
  espece: string;
  current: RegRow[];
  upcoming: RegRow[];
  past: RegRow[];
  unknown?: RegRow[];
  has_current?: boolean;
};

export type TimelinePayload = {
  as_of?: string;
  counts?: { current?: number; upcoming?: number; past?: number };
  species?: SpeciesTimeline[];
};

export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

export function statusTable(title: string, status: string, rows: RegRow[]): string {
  if (!rows.length) return "";
  let html = `<div class="reg-block reg-${status}"><h4>${escapeHtml(title)}</h4>
    <table class="reg-table"><thead><tr><th>Période</th><th>Prise</th><th>Longueur</th><th>Engin</th></tr></thead><tbody>`;
  for (const r of rows) {
    const dates =
      r.debut && r.fin
        ? `<div class="muted">${escapeHtml(r.debut)} → ${escapeHtml(r.fin)}</div>`
        : "";
    const seg = r.segment
      ? `<div class="muted reg-seg">${escapeHtml(r.segment)}</div>`
      : "";
    html += `<tr>
      <td>${escapeHtml(r.periode || "")}${dates}${seg}</td>
      <td>${escapeHtml(r.limite_prise || "—")}</td>
      <td>${escapeHtml(r.limite_longueur || "—")}</td>
      <td>${escapeHtml(r.engin || "—")}${
        r.note ? `<div class="muted">${escapeHtml(r.note)}</div>` : ""
      }</td>
    </tr>`;
  }
  html += `</tbody></table></div>`;
  return html;
}

export function timelineHtml(timeline: TimelinePayload, heading?: string): string {
  const counts = timeline.counts || {};
  let html = "";
  if (heading) html += `<h3 class="detail-section-title">${escapeHtml(heading)}</h3>`;
  html += `<div class="reg-summary">
    <span class="reg-pill current">${counts.current ?? 0} en vigueur</span>
    <span class="reg-pill upcoming">${counts.upcoming ?? 0} à venir</span>
    <span class="reg-pill past">${counts.past ?? 0} passées</span>
  </div>`;
  const species = timeline.species || [];
  if (!species.length) {
    html += `<p class="muted">Aucun règlement trouvé.</p>`;
    return html;
  }
  for (const sp of species) {
    html += `<details class="reg-species" ${sp.has_current ? "open" : ""}>
      <summary><strong>${escapeHtml(sp.espece)}</strong>
      <span class="muted">${sp.current.length} · ${sp.upcoming.length} · ${sp.past.length}</span></summary>`;
    html += statusTable("En vigueur", "current", sp.current);
    html += statusTable("À venir", "upcoming", sp.upcoming);
    html += statusTable("Passées", "past", sp.past);
    if (sp.unknown?.length) html += statusTable("Non datées", "unknown", sp.unknown);
    html += `</details>`;
  }
  return html;
}
