#!/usr/bin/env bash
# Régénère les données dérivées (locations, index, hydro, matches, catalogue, zones).
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"

echo "==> Suppression des artefacts dérivés…"
rm -rf data/locations data/hydromet/matches
rm -f data/search_index.json data/hydromet/stations.json

echo "==> Extraction coords + index de recherche…"
"$PYTHON" -m peche.coords extract --build-index

echo "==> Sync stations Vigilance…"
"$PYTHON" -m peche.hydromet sync-stations

echo "==> Matching plans ↔ stations…"
"$PYTHON" -m peche.hydromet match --all

echo "==> Sync stations marées (SHC / IWLS)…"
"$PYTHON" -m peche.tides sync

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

echo "==> Harvest plans RegPec offline (optionnel, réseau)…"
"$PYTHON" -m peche.spatial plans-regpec || echo "    (plans-regpec ignoré si réseau indisponible)"

echo "==> Récolte catalogue de couches…"
"$PYTHON" -m peche.catalog harvest

echo "==> Terminé."
echo "    (Les zones RegPec dans data/zones/ sont conservées ;"
echo "     lancer 'python3 -m peche.reglements sync' pour les rafraîchir.)"
