/** Désinversion toponymique CEHQ / RegPec : « X, Y » → « Y X ». */

export function uninvertName(raw: string): string {
  const s = raw.trim();
  const idx = s.lastIndexOf(",");
  if (idx < 0) return s;
  const head = s.slice(0, idx).trim();
  const tail = s.slice(idx + 1).trim();
  if (!head || !tail) return s;
  return `${tail} ${head}`;
}
