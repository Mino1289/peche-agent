/** Désinversion toponymique CEHQ / RegPec : « X, Y » → « Y X ». */

const FR_SMALL_WORDS = new Set([
  "de",
  "du",
  "des",
  "la",
  "le",
  "les",
  "d'",
  "l'",
  "et",
  "à",
  "au",
  "aux",
  "en",
  "d",
]);

/** Capitalise un libellé FR (ex. CERF DE VIRGINIE → Cerf de Virginie). */
export function titleFr(raw: string): string {
  const words = raw.trim().toLowerCase().split(/\s+/).filter(Boolean);
  return words
    .map((word, i) => {
      if (i > 0 && FR_SMALL_WORDS.has(word)) return word;
      return word.charAt(0).toUpperCase() + word.slice(1);
    })
    .join(" ");
}

export function formatSpeciesList(raw: unknown): string {
  const text = String(raw ?? "").trim();
  if (!text) return "";
  return text
    .split(/[,;]/)
    .map((part) => titleFr(part.trim()))
    .filter(Boolean)
    .join(", ");
}

export function uninvertName(raw: string): string {
  const s = raw.trim();
  const idx = s.lastIndexOf(",");
  if (idx < 0) return s;
  const head = s.slice(0, idx).trim();
  const tail = s.slice(idx + 1).trim();
  if (!head || !tail) return s;
  return `${tail} ${head}`;
}
