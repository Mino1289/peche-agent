#!/usr/bin/env bash
# Régénère les données dérivées (locations, index, hydro, matches, catalogue, zones).
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"

# Artefacts régénérés ci-dessous. En cas d'échec, ils sont restaurés depuis la sauvegarde.
ARTEFACTS=(data/locations data/hydromet/matches data/search_index.json data/hydromet/stations.json data/hydromet/hydroquebec_points.json)
BACKUP="$(mktemp -d data/.refresh-backup.XXXXXX)"
restore_on_error() {
  local rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "==> Échec (code $rc) : restauration des artefacts précédents…"
    for p in "${ARTEFACTS[@]}"; do
      if [ -e "$BACKUP/$p" ]; then rm -rf "$p"; mv "$BACKUP/$p" "$p"; fi
    done
  fi
  rm -rf "$BACKUP"
}
trap restore_on_error EXIT

echo "==> Suppression des artefacts dérivés (sauvegardés)…"
for p in "${ARTEFACTS[@]}"; do
  if [ -e "$p" ]; then mkdir -p "$BACKUP/$(dirname "$p")"; mv "$p" "$BACKUP/$p"; fi
done

echo "==> Extraction coords + index de recherche…"
"$PYTHON" -m peche.coords extract --build-index

echo "==> Sync stations Vigilance…"
"$PYTHON" -m peche.hydromet sync-stations

echo "==> Matching plans ↔ stations…"
"$PYTHON" -m peche.hydromet match --all

echo "==> Sync stations marées (SHC / IWLS)…"
"$PYTHON" -m peche.tides sync

echo "==> Sync villes météo GeoMet (qc-*)…"
"$PYTHON" -m peche.weather sync || echo "    (météo ignorée si réseau indisponible)"

echo "==> Sync répertoire barrages CEHQ…"
"$PYTHON" -m peche.barrages sync

echo "==> Sync LCE (lacs et cours d'eau)…"
"$PYTHON" -m peche.lce sync

echo "==> Sync bassins hydrographiques…"
"$PYTHON" -m peche.bassins sync

echo "==> Liens RegPec ↔ LCE…"
"$PYTHON" -m peche.spatial link

echo "==> Sync polygones zones de pêche…"
"$PYTHON" -m peche.spatial zones-peche

echo "==> Sync guide consommation poisson (CKAN)…"
"$PYTHON" -m peche.guide_poisson sync || echo "    (guide-poisson ignoré si réseau indisponible)"

echo "==> Harvest plans RegPec offline (optionnel, réseau)…"
"$PYTHON" -m peche.spatial plans-regpec || echo "    (plans-regpec ignoré si réseau indisponible)"
"$PYTHON" -m peche.spatial tfs-sync || echo "    (TFS ignoré si réseau indisponible)"

echo "==> Récolte catalogue de couches…"
"$PYTHON" -m peche.catalog harvest

echo "==> Pré-charge GetCapabilities (découverte couches)…"
"$PYTHON" -m peche.catalog warm-caps || echo "    (warm-caps ignoré si réseau indisponible)"

echo "==> Terminé."
echo "    (Les zones RegPec dans data/zones/ sont conservées ;"
echo "     lancer 'python3 -m peche.reglements sync' pour les rafraîchir.)"
