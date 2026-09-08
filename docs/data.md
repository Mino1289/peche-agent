# Data layout

## Bundled in git / Docker image (~130 MB)

| Path | Description |
|------|-------------|
| `data/zones/` | RegPec regulations per zone (JSON) |
| `data/locations/` | Water body locations |
| `data/hydromet/`, `data/tides/`, `data/barrages/` | Stations and matches |
| `data/catalog/` | Curated layer catalog + GetCapabilities XML |
| `data/spatial/` | Fishing zones GeoJSON, plans, LCE/basin indexes |
| `data/index.json`, `data/search_index.json` | Zone index and search |

## Generated at runtime (gitignored)

| Path | Description |
|------|-------------|
| `data/cache/` | OGC proxy cache, sync caches (~large) |
| `data/runtime/conversations.db` | Chat history (Docker volume `peche-runtime`) |

## Refresh pipeline

```bash
./scripts/refresh-data.sh
```

Regenerates locations, hydromet matches, spatial zones, catalog harvest, etc.  
RegPec zone JSON: `python3 -m peche.reglements sync`

## Docker volumes

`docker-compose.yml` mounts only:

- `peche-runtime` → `/app/data/runtime`
- `peche-cache` → `/app/data/cache`

Bundled data inside the image is not overwritten.
