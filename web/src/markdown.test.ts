import { describe, expect, it } from "vitest";
import { formatMarkdown } from "./markdown";

describe("formatMarkdown", () => {
  it("renders headings, bullet lists, italics, and hr without extra <br/> gaps", () => {
    const src = [
      "Pour la **rivière Saguenay** (`plan_id: 12040`).",
      "",
      "### Règlements spécifiques",
      "* **Bar rayé** : Pêche interdite",
      "* **Éperlan** : Interdit *(règle spécifique)*",
      "",
      "---",
      "",
      "### Zone 21",
      "",
      "* **Achigans** : 6",
    ].join("\n");

    const html = formatMarkdown(src);
    expect(html).not.toContain("<br/><br/>");
    expect(html).toContain('<h3 class="chat-h3">Règlements spécifiques</h3>');
    expect(html).toContain('<ul class="chat-list">');
    expect(html).toContain("<li><strong>Bar rayé</strong> : Pêche interdite</li>");
    expect(html).toContain("<em>(règle spécifique)</em>");
    expect(html).toContain('<hr class="chat-hr"/>');
    expect(html).toContain("<code>plan_id: 12040</code>");
  });

  it("renders tables with <br>, nested-bracket links, and unit exponents", () => {
    const src = [
      "| Cours d'eau | Débit ($m^3/s$) | Liens |",
      "| :--- | :---: | :--- |",
      "| **Rivière Chicoutimi**<br>*(En aval)* | **46,93** | [[CEHQ]](https://example.com/g) - [[Tableau]](https://example.com/t) |",
    ].join("\n");

    const html = formatMarkdown(src);
    expect(html).toContain("m<sup>3</sup>/s");
    expect(html).toContain("<strong>Rivière Chicoutimi</strong><br/><em>(En aval)</em>");
    expect(html).toContain('<a href="https://example.com/g" target="_blank" rel="noopener">[CEHQ]</a>');
    expect(html).toContain('<a href="https://example.com/t" target="_blank" rel="noopener">[Tableau]</a>');
  });

  it("escapes raw HTML and preserves code spans and dollar amounts", () => {
    const html = formatMarkdown("Coût $15 à $20 avec `*brut*` et <script>x</script>");
    expect(html).toContain("$15 à $20");
    expect(html).toContain("<code>*brut*</code>");
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;x&lt;/script&gt;");
  });

  it("renders ordered lists, blockquotes, and fenced code blocks", () => {
    const src = "1. Premier\n2. Deuxième\n\n> Attention au vent\n\n```\nconst x = 1;\n```";
    const html = formatMarkdown(src);
    expect(html).toContain('<ol class="chat-list"><li>Premier</li><li>Deuxième</li></ol>');
    expect(html).toContain('<blockquote class="chat-quote"><p>Attention au vent</p></blockquote>');
    expect(html).toContain('<pre class="chat-pre"><code>const x = 1;</code></pre>');
  });
});
