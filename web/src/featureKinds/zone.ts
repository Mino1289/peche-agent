/** Règlements généraux d’une zone de pêche (détail seulement, ouvert depuis un point). */

import { escapeHtml, timelineHtml, type TimelinePayload } from "../regs";
import { t } from "../i18n";
import { loadZoneOptions, mountZonePicker, type ZoneOption } from "../zonePicker";
import { errorHtml, zoneLabelFromProps } from "./html";
import type { DetailCtx, FeatureKind, Props } from "./kind";

export const zoneKind: FeatureKind = {
  title(p) {
    const z = zoneLabelFromProps(p);
    return z ? t().zoneRegsTitle(z) : t().zoneRegs;
  },
  detail: (body, hit, _loaded, ctx) => fillZone(body, hit.props, ctx),
};

async function fillZone(body: HTMLElement, props: Props, ctx: DetailCtx): Promise<void> {
  const m = t();
  let zoneId = Number(props.zone_id);
  if (!Number.isFinite(zoneId)) {
    const lon = Number(props.lon);
    const lat = Number(props.lat);
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) {
      body.innerHTML = errorHtml(m.unknownZone);
      return;
    }
    const atResp = await fetch(
      `/api/zones/at?lon=${encodeURIComponent(String(lon))}&lat=${encodeURIComponent(String(lat))}`,
    );
    if (!atResp.ok) {
      body.innerHTML = errorHtml(m.noZoneAtPoint);
      return;
    }
    const at = (await atResp.json()) as Record<string, unknown>;
    zoneId = Number(at.zone_id);
  }
  if (!Number.isFinite(zoneId)) {
    body.innerHTML = errorHtml(m.unknownZone);
    return;
  }

  body.innerHTML = "";
  const picker = document.createElement("div");
  picker.className = "zone-picker";
  body.appendChild(picker);

  const content = document.createElement("div");
  content.className = "zone-regs-content";
  content.innerHTML = `<p class="muted">${escapeHtml(m.loading)}</p>`;
  body.appendChild(content);

  let zones: ZoneOption[];
  try {
    zones = await loadZoneOptions();
  } catch (err) {
    content.innerHTML = errorHtml(String(err));
    return;
  }

  let selectedId = zoneId;

  const reload = async (zid: number) => {
    selectedId = zid;
    content.innerHTML = `<p class="muted">${escapeHtml(m.loading)}</p>`;
    const zone = zones.find((z) => z.zone_id === zid);
    if (zone) ctx.setTitle(t().zoneRegsTitle(zone.zone_nom));
    await renderZoneReglements(content, zid, zone?.zone_nom);
  };

  mountZonePicker(picker, zones, selectedId, (zone) => {
    if (zone.zone_id === selectedId) return;
    void reload(zone.zone_id);
    ctx.focusZone(zone.zone_id);
  });

  await reload(selectedId);
}

async function renderZoneReglements(
  content: HTMLElement,
  zoneId: number,
  fallbackLabel?: string,
): Promise<void> {
  const m = t();
  const zoneResp = await fetch(`/api/zones/${zoneId}/reglements?id_kind=regpec`);
  if (!zoneResp.ok) {
    content.innerHTML = errorHtml(m.zoneRulesUnavailable(zoneResp.status));
    return;
  }
  const z = (await zoneResp.json()) as Record<string, unknown>;
  const label =
    z.zone_nom ?? fallbackLabel ?? (z.no_zone != null ? `Zone ${z.no_zone}` : `Zone ${zoneId}`);
  content.innerHTML = "";
  const wrap = document.createElement("section");
  wrap.className = "detail-reg-block";
  wrap.innerHTML = timelineHtml(
    (z.timeline || {}) as TimelinePayload,
    m.generalZoneRules(String(label)),
  );
  content.appendChild(wrap);
}
