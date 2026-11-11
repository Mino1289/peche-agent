/** Routes d'URL : /map et /chat/:id (historique navigateur). */

export type Route = { tab: "map" } | { tab: "chat"; id: string | null };

export function parseRoute(path = window.location.pathname): Route {
  const m = path.match(/^\/chat(?:\/([^/]+))?\/?$/);
  if (!m) return { tab: "map" };
  return { tab: "chat", id: m[1] ? decodeURIComponent(m[1]) : null };
}

export function routePath(route: Route): string {
  if (route.tab === "map") return "/map";
  return route.id ? `/chat/${encodeURIComponent(route.id)}` : "/chat";
}

export function navigate(route: Route, mode: "push" | "replace" = "push"): void {
  const path = routePath(route);
  if (window.location.pathname === path) return;
  if (mode === "replace") window.history.replaceState(null, "", path);
  else window.history.pushState(null, "", path);
}
