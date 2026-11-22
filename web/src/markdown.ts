/** Rendu Markdown sûr (sans HTML brut) pour les messages du chat. */

export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function formatMarkdown(raw: string): string {
  if (!raw) return "";
  const lines = raw.replace(/\r\n?/g, "\n").split("\n");
  const blocks: string[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (line.trim() === "") {
      i++;
      continue;
    }

    // Bloc de code clôturé ```
    const fence = line.trim().match(/^```([a-zA-Z0-9_-]*)$/);
    if (fence) {
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      if (i < lines.length) i++;
      blocks.push(`<pre class="chat-pre"><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
      continue;
    }

    // Règle horizontale --- / *** / ___
    if (isHorizontalRule(line)) {
      blocks.push('<hr class="chat-hr"/>');
      i++;
      continue;
    }

    // Titre # .. ######
    const heading = parseHeadingLine(line);
    if (heading) {
      blocks.push(
        `<h${heading.level} class="chat-h${heading.level}">${formatInline(heading.text)}</h${heading.level}>`,
      );
      i++;
      continue;
    }

    // Tableau Markdown
    const table = parseMarkdownTable(lines, i);
    if (table) {
      blocks.push(table.html);
      i = table.next;
      continue;
    }

    // Citation > ...
    if (/^\s*>\s?/.test(line)) {
      const quoteLines: string[] = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
        quoteLines.push(lines[i].replace(/^\s*>\s?/, ""));
        i++;
      }
      blocks.push(`<blockquote class="chat-quote">${formatMarkdown(quoteLines.join("\n"))}</blockquote>`);
      continue;
    }

    // Liste à puces ou numérotée
    if (isListItem(line)) {
      const list = parseList(lines, i);
      blocks.push(list.html);
      i = list.next;
      continue;
    }

    // Paragraphe : lignes consécutives jusqu'à une ligne vide ou un autre bloc
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() !== "") {
      if (
        para.length > 0 &&
        (isHorizontalRule(lines[i]) ||
          parseHeadingLine(lines[i]) !== null ||
          lines[i].trim().startsWith("```") ||
          /^\s*>\s?/.test(lines[i]) ||
          isListItem(lines[i]) ||
          parseMarkdownTable(lines, i) !== null)
      ) {
        break;
      }
      para.push(formatInline(lines[i]));
      i++;
    }
    if (para.length) {
      blocks.push(`<p>${para.join("<br/>")}</p>`);
    }
  }

  return blocks.join("");
}

function isHorizontalRule(line: string): boolean {
  return /^\s*([-*_])(?:\s*\1){2,}\s*$/.test(line);
}

function parseHeadingLine(line: string): { level: number; text: string } | null {
  const m = line.trim().match(/^(#{1,6})\s+(.+?)\s*#*$/);
  if (!m) return null;
  return { level: m[1].length, text: m[2].trim() };
}

type ListMatch = { ordered: boolean; indent: number; text: string };

function matchListLine(line: string): ListMatch | null {
  const ul = line.match(/^(\s*)[-*+]\s+(.+)$/);
  if (ul) return { ordered: false, indent: ul[1].length, text: ul[2] };
  const ol = line.match(/^(\s*)\d+[.)]\s+(.+)$/);
  if (ol) return { ordered: true, indent: ol[1].length, text: ol[2] };
  return null;
}

function isListItem(line: string): boolean {
  return matchListLine(line) !== null;
}

function parseList(
  lines: string[],
  start: number,
): { html: string; next: number } {
  const first = matchListLine(lines[start])!;
  const ordered = first.ordered;
  const baseIndent = first.indent;
  const tag = ordered ? "ol" : "ul";
  const items: string[] = [];
  let i = start;

  while (i < lines.length) {
    // Sauter une ligne vide uniquement si elle précède un autre élément de même liste
    if (lines[i].trim() === "") {
      let peek = i + 1;
      while (peek < lines.length && lines[peek].trim() === "") peek++;
      const nextItem = peek < lines.length ? matchListLine(lines[peek]) : null;
      if (nextItem && nextItem.ordered === ordered && nextItem.indent === baseIndent) {
        i = peek;
        continue;
      }
      break;
    }

    const m = matchListLine(lines[i]);
    if (!m) break;

    if (m.indent > baseIndent) {
      // Sous-liste imbriquée rattachée au dernier <li>
      const sub = parseList(lines, i);
      if (items.length > 0) {
        items[items.length - 1] += sub.html;
      } else {
        items.push(sub.html);
      }
      i = sub.next;
      continue;
    }

    if (m.indent < baseIndent || m.ordered !== ordered) break;

    const parts = [formatInline(m.text)];
    i++;
    // Lignes de continuation indentées
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !matchListLine(lines[i]) &&
      !isHorizontalRule(lines[i]) &&
      !parseHeadingLine(lines[i]) &&
      !/^\s*>\s?/.test(lines[i]) &&
      !lines[i].trim().startsWith("```") &&
      parseMarkdownTable(lines, i) === null &&
      /^\s{2,}/.test(lines[i])
    ) {
      parts.push(formatInline(lines[i].trim()));
      i++;
    }
    items.push(parts.join("<br/>"));
  }

  return {
    html: `<${tag} class="chat-list">${items.map((it) => `<li>${it}</li>`).join("")}</${tag}>`,
    next: i,
  };
}

export function formatInline(
  text: string,
  opts?: { allowBr?: boolean },
): string {
  // Protéger les spans `code` avant toute transformation inline
  const codes: string[] = [];
  const withPlaceholders = text.replace(/`([^`\n]+)`/g, (_m, code: string) => {
    const idx = codes.length;
    codes.push(`<code>${escapeHtml(code)}</code>`);
    return `\u0000CODE${idx}\u0000`;
  });

  let s = escapeHtml(withPlaceholders);

  if (opts?.allowBr) {
    s = s.replace(/&lt;br\s*\/?&gt;/gi, "<br/>");
  }

  // Unités LaTeX simples (ex. $m^3/s$ → m³/s) sans toucher aux montants ($15)
  s = s.replace(/\$([a-zA-Z][a-zA-Z0-9^_/\\{} .,-]*)\$/g, (_m, expr: string) =>
    expr
      .replace(/\^\{([^}]+)\}/g, "<sup>$1</sup>")
      .replace(/\^([0-9a-zA-Z+-]+)/g, "<sup>$1</sup>")
      .replace(/_\{([^}]+)\}/g, "<sub>$1</sub>"),
  );

  // Liens [label](https://...) — tolère les crochets imbriqués ex. [[CEHQ]](https://...)
  s = s.replace(
    /\[((?:[^\[\]]|\[[^\]]*\])+)\]\((https?:\/\/[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener">$1</a>',
  );

  // Gras + italique, gras, italique, barré
  s = s.replace(/\*\*\*([^*\n]+?)\*\*\*/g, "<strong><em>$1</em></strong>");
  s = s.replace(/\*\*([^*\n]+?)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/__([^_\n]+?)__/g, "<strong>$1</strong>");
  s = s.replace(/(^|[^*])\*([^\s*\n](?:[^*\n]*?[^\s*\n])?)\*(?!\*)/g, "$1<em>$2</em>");
  s = s.replace(/(^|[\s(])_([^\s_\n](?:[^_\n]*?[^\s_\n])?)_(?=[\s).,;:!?]|$)/g, "$1<em>$2</em>");
  s = s.replace(/~~([^~\n]+?)~~/g, "<del>$1</del>");

  // Restaurer les spans `code`
  s = s.replace(/\u0000CODE(\d+)\u0000/g, (_m, idx: string) => codes[Number(idx)] ?? "");
  return s;
}

function splitTableCells(row: string): string[] {
  const trow = row.trim();
  const inner = trow.startsWith("|") ? trow.slice(1) : trow;
  const body = inner.endsWith("|") ? inner.slice(0, -1) : inner;
  return body.split("|").map((c) => c.trim());
}

function isTableRow(line: string): boolean {
  const tline = line.trim();
  return tline.includes("|") && (tline.startsWith("|") || tline.split("|").length >= 2);
}

function isTableSeparator(line: string): boolean {
  if (!isTableRow(line)) return false;
  const cells = splitTableCells(line);
  return cells.length > 0 && cells.every((c) => /^:?-{3,}:?$/.test(c));
}

function tableCellAlign(cell: string): "left" | "center" | "right" | null {
  const tcell = cell.trim();
  const left = tcell.startsWith(":");
  const right = tcell.endsWith(":");
  if (left && right) return "center";
  if (right) return "right";
  if (left) return "left";
  return null;
}

function parseMarkdownTable(
  lines: string[],
  start: number,
): { html: string; next: number } | null {
  if (start + 1 >= lines.length) return null;
  const headerLine = lines[start];
  const sepLine = lines[start + 1];
  if (!isTableRow(headerLine) || !isTableSeparator(sepLine)) return null;

  const headers = splitTableCells(headerLine);
  const aligns = splitTableCells(sepLine).map(tableCellAlign);
  let i = start + 2;
  const rows: string[][] = [];
  while (i < lines.length && isTableRow(lines[i]) && !isTableSeparator(lines[i])) {
    rows.push(splitTableCells(lines[i]));
    i++;
  }

  let html = '<table class="chat-table"><thead><tr>';
  for (let c = 0; c < headers.length; c++) {
    const align = aligns[c];
    const style = align ? ` style="text-align:${align}"` : "";
    html += `<th${style}>${formatInline(headers[c], { allowBr: true })}</th>`;
  }
  html += "</tr></thead><tbody>";
  for (const row of rows) {
    html += "<tr>";
    for (let c = 0; c < headers.length; c++) {
      const align = aligns[c];
      const style = align ? ` style="text-align:${align}"` : "";
      html += `<td${style}>${formatInline(row[c] ?? "", { allowBr: true })}</td>`;
    }
    html += "</tr>";
  }
  html += "</tbody></table>";
  return { html: `<div class="table-scroll">${html}</div>`, next: i };
}
