# Glossary

**Feature kind** — what the SPA knows about one identifiable map layer: title, pin key, live load, popup body, detail panel. One kind per layer id, registered in `web/src/featureKinds/index.ts`; unknown layers fall back to the raw-JSON kind. A kind without popup (e.g. `zone`) is detail-only and not clickable on the map.

**Identify hit** — a clicked map entity (`layerId`, `props`, `coordinate`) plus the popup's in-flight load, shared with the detail panel so it never re-fetches.
