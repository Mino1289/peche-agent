/** Plans d’eau RegPec (exceptions réglementaires) + guide de consommation. */

import { escapeHtml, timelineHtml, type TimelinePayload } from "../regs";
import { t } from "../i18n";
import { uninvertName } from "../names";
import { errorHtml, str, zoneLabelFromProps } from "./html";
import { pick, type FeatureKind, type Props } from "./kind";

type GuidePoissonResponse = {
  site?: {
    id: string;
    nom: string;
    zone_id?: number;
    lon?: number;
    lat?: number;
  };
  species?: {
    nom_commun: string;
    nom_latin?: string;
    statut?: string;
    repas_p?: string;
    repas_m?: string;
    repas_g?: string;
  }[];
  message?: string;
  guide_url?: string;
};

export const planKind: FeatureKind = {
  title: (p) => uninvertName(String(p.nom || p.name || `Plan ${p.plan_id || ""}`)),

  pinKey: (p) => pick(p, "plan_id") || null,

  popup(p) {
    const m = t();
    const nom = uninvertName(str(p.nom || p.name));
    const zone = zoneLabelFromProps(p);
    const planId = str(p.plan_id);
    const typeEndro = str(p.type_endro);
    let html = `<p><span class="badge exception-badge">${escapeHtml(m.regulatoryException)}</span></p>`;
    if (nom) html += `<p><strong>${escapeHtml(nom)}</strong></p>`;
    const meta: string[] = [];
    if (planId) meta.push(`Plan ${planId}`);
    if (zone) meta.push(zone);
    if (typeEndro) meta.push(typeEndro);
    if (meta.length) {
      html += `<p class="muted">${escapeHtml(meta.join(" · "))}</p>`;
    }
    html += `<p class="muted">${escapeHtml(m.useDetailForRegs)}</p>`;
    return html;
  },

  detail: (body, hit) => fillPlan(body, hit.props),
};

async function fillPlan(body: HTMLElement, props: Props): Promise<void> {
  const m = t();
  const zoneId = Number(props.zone_id);
  const planId = Number(props.plan_id);
  if (!Number.isFinite(zoneId) || !Number.isFinite(planId)) {
    body.innerHTML = errorHtml(m.incompletePlan);
    return;
  }
  const idQ = "id_kind=regpec";
  const nom = uninvertName(str(props.nom || props.name));
  const lon = Number(props.lon);
  const lat = Number(props.lat);
  const guideQ = new URLSearchParams({
    zone_id: String(zoneId),
    nom,
  });
  if (Number.isFinite(lon)) guideQ.set("lon", String(lon));
  if (Number.isFinite(lat)) guideQ.set("lat", String(lat));

  const [planResp, zoneResp, guideResp] = await Promise.all([
    fetch(`/api/plans/${zoneId}/${planId}?${idQ}`),
    fetch(`/api/zones/${zoneId}/reglements?${idQ}`),
    fetch(`/api/guide-poisson?${guideQ.toString()}`),
  ]);
  body.innerHTML = "";
  if (planResp.ok) {
    const d = (await planResp.json()) as Record<string, unknown>;
    const wrap = document.createElement("section");
    wrap.className = "detail-reg-block";
    const planNom = uninvertName(str(d.nom || props.nom));
    const zoneLbl = zoneLabelFromProps({
      zone_nom: d.zone_nom,
      no_zone: d.no_zone,
      zone_id: d.zone_id,
    });
    wrap.innerHTML =
      `<p class="muted">${escapeHtml(planNom)} · Plan ${d.plan_id}${zoneLbl ? ` · ${escapeHtml(zoneLbl)}` : ""}</p>` +
      timelineHtml((d.timeline || {}) as TimelinePayload, m.exceptionPlanRules);
    body.appendChild(wrap);
  } else {
    body.innerHTML += errorHtml(m.planNotFound(planResp.status));
  }
  if (zoneResp.ok) {
    const z = (await zoneResp.json()) as Record<string, unknown>;
    const wrap = document.createElement("section");
    wrap.className = "detail-reg-block";
    wrap.innerHTML = timelineHtml(
      (z.timeline || {}) as TimelinePayload,
      m.generalZoneRules(String(z.zone_nom ?? `Zone ${z.no_zone ?? z.zone_id}`)),
    );
    body.appendChild(wrap);
  } else {
    body.innerHTML += errorHtml(m.zoneRulesUnavailable(zoneResp.status));
  }

  if (guideResp.ok) {
    const guide = (await guideResp.json()) as GuidePoissonResponse;
    body.appendChild(renderSpeciesGuide(guide));
  }
}

function renderSpeciesGuide(guide: GuidePoissonResponse): HTMLElement {
  const m = t();
  const section = document.createElement("section");
  section.className = "detail-reg-block species-guide";
  const title = document.createElement("h3");
  title.textContent = m.speciesGuide;
  section.appendChild(title);

  const disclaimer = document.createElement("p");
  disclaimer.className = "muted";
  disclaimer.textContent = m.speciesGuideDisclaimer;
  section.appendChild(disclaimer);

  const species = guide.species || [];
  if (!species.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = guide.message || m.speciesGuideEmpty;
    section.appendChild(empty);
  } else {
    if (guide.site?.nom) {
      const site = document.createElement("p");
      site.innerHTML = `<strong>${escapeHtml(guide.site.nom)}</strong>`;
      section.appendChild(site);
    }
    const list = document.createElement("ul");
    list.className = "species-list";
    for (const sp of species) {
      const li = document.createElement("li");
      const meals = m.speciesMeals(sp.repas_p || "—", sp.repas_m || "—", sp.repas_g || "—");
      li.innerHTML = `<strong>${escapeHtml(sp.nom_commun)}</strong>${
        sp.nom_latin ? ` <span class="muted"><em>${escapeHtml(sp.nom_latin)}</em></span>` : ""
      }${sp.statut ? `<br><span class="muted">${escapeHtml(m.speciesStatus)} : ${escapeHtml(sp.statut)}</span>` : ""}<br><span class="muted">${escapeHtml(meals)}</span>`;
      list.appendChild(li);
    }
    section.appendChild(list);
  }

  if (guide.guide_url) {
    const link = document.createElement("p");
    link.innerHTML = `<a href="${escapeHtml(guide.guide_url)}" target="_blank" rel="noopener">${escapeHtml(m.speciesGuideLink)}</a>`;
    section.appendChild(link);
  }
  return section;
}
