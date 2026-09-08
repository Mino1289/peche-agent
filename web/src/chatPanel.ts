/** Panneau chat + historique (sidebar gauche). */

import type { ChatEvent, ChatMessage, MapState } from "./types";
import type { MapController } from "./map";
import { listConversations, loadConversation, streamChat } from "./chat";
import {
  destroyHydroCharts,
  renderVisibleHydroOutputs,
} from "./hydroCharts";
import { onLocaleChange, t } from "./i18n";
import {
  chatKeyAvailable,
  clearApiKey,
  fetchHealth,
  getApiKey,
  setApiKey,
  type HealthInfo,
} from "./settings";

const AI_STUDIO_URL = "https://aistudio.google.com/app/apikey";

export class ChatPanel {
  private el: HTMLElement;
  private sidebar: HTMLElement;
  private map: MapController;
  private sessionId: string | null = null;
  private messages: ChatMessage[] = [];
  private running = false;
  private health: HealthInfo | null = null;

  constructor(el: HTMLElement, sidebar: HTMLElement, map: MapController) {
    this.el = el;
    this.sidebar = sidebar;
    this.map = map;
    onLocaleChange(() => {
      this.renderSidebar();
      this.renderShell();
      this.renderMessages();
    });
    void this.init();
  }

  private async init(): Promise<void> {
    this.health = await fetchHealth();
    this.renderSidebar();
    this.renderShell();
    this.renderEmptyState();
  }

  private renderSidebar(): void {
    const m = t();
    this.sidebar.innerHTML = `
      <div class="panel-header chat-sidebar-header">
        <h2>${m.conversations}</h2>
      </div>
      <div class="chat-sidebar-actions">
        <button type="button" id="btn-new-chat" class="btn-sidebar" title="${m.newChat}">${m.newChat}</button>
      </div>
      <div id="history-list" class="history-list"></div>`;
    this.sidebar.querySelector("#btn-new-chat")!.addEventListener("click", () => {
      this.sessionId = null;
      this.messages = [];
      this.renderMessages();
      this.renderEmptyState();
      void this.refreshHistoryList();
    });
    void this.refreshHistoryList();
  }

  private async refreshHistoryList(): Promise<void> {
    const m = t();
    const list = this.sidebar.querySelector("#history-list") as HTMLElement;
    list.innerHTML = `<p class='muted'>${m.loading}</p>`;
    const convs = await listConversations();
    list.innerHTML = "";
    if (!convs.length) {
      list.innerHTML = `<p class='muted history-empty'>${m.noConversations}</p>`;
      return;
    }
    for (const c of convs) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "history-item";
      if (c.id === this.sessionId) btn.classList.add("active");
      btn.innerHTML = `<strong>${escapeHtml(c.title)}</strong><br/><small>${c.message_count} ${m.msgs} · ${c.updated_at}</small>`;
      btn.addEventListener("click", async () => {
        const loaded = await loadConversation(c.id);
        if (!loaded) return;
        this.sessionId = c.id;
        this.messages = loaded.messages;
        this.renderMessages();
        if (loaded.map_state) await this.map.applyMapState(loaded.map_state);
        void this.refreshHistoryList();
      });
      list.appendChild(btn);
    }
  }

  private renderShell(): void {
    const m = t();
    this.el.innerHTML = `
      <div class="panel-header chat-header">
        <h2>${m.assistant}</h2>
        <div class="chat-header-actions">
          <button type="button" id="btn-settings" class="btn-icon" title="${m.settings}">⚙</button>
          <button type="button" id="btn-about" class="btn-icon" title="${m.about}">ℹ</button>
        </div>
      </div>
      <div id="api-key-banner" class="api-key-banner" hidden></div>
      <div id="chat-messages" class="chat-messages"></div>
      <form id="chat-form" class="chat-form">
        <div class="chat-input-wrap">
          <textarea id="chat-input" rows="2" placeholder="${escapeHtml(m.chatPlaceholder)}"></textarea>
          <button type="submit" id="chat-send" title="${m.send}" aria-label="${m.send}">
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path fill="currentColor" d="M3.4 20.6 21 12 3.4 3.4l.1 6.8L15 12 3.5 13.8z"/>
            </svg>
          </button>
        </div>
      </form>
    `;
    this.el.querySelector("#chat-form")!.addEventListener("submit", (e) => {
      e.preventDefault();
      void this.send();
    });
    const input = this.el.querySelector("#chat-input") as HTMLTextAreaElement;
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        void this.send();
      }
    });
    this.el.querySelector("#btn-settings")!.addEventListener("click", () => {
      this.showSettingsDialog();
    });
    this.el.querySelector("#btn-about")!.addEventListener("click", () => {
      this.showAboutDialog();
    });
    this.updateApiKeyBanner();
  }

  private updateApiKeyBanner(): void {
    const banner = this.el.querySelector("#api-key-banner") as HTMLElement;
    if (!banner) return;
    const m = t();
    if (chatKeyAvailable(this.health)) {
      banner.hidden = true;
      return;
    }
    banner.hidden = false;
    banner.innerHTML = `
      <p>${escapeHtml(m.apiKeyBanner)}
        <a href="${AI_STUDIO_URL}" target="_blank" rel="noopener">${escapeHtml(m.apiKeyGetLink)}</a>
      </p>
      <button type="button" class="btn-sidebar" id="banner-open-settings">${escapeHtml(m.settings)}</button>`;
    banner.querySelector("#banner-open-settings")?.addEventListener("click", () => {
      this.showSettingsDialog();
    });
  }

  private showSettingsDialog(): void {
    const m = t();
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.innerHTML = `
      <div class="modal-card" role="dialog" aria-labelledby="settings-title">
        <div class="modal-header">
          <h3 id="settings-title">${escapeHtml(m.apiKeyTitle)}</h3>
          <button type="button" class="modal-close" aria-label="Close">✕</button>
        </div>
        <p class="muted modal-hint">${escapeHtml(m.apiKeyHint)}</p>
        <input type="password" id="settings-api-key" class="modal-input" placeholder="${escapeHtml(m.apiKeyPlaceholder)}" value="${escapeHtml(getApiKey())}" autocomplete="off" />
        <p><a href="${AI_STUDIO_URL}" target="_blank" rel="noopener">${escapeHtml(m.apiKeyGetLink)}</a></p>
        <div class="modal-actions">
          <button type="button" id="settings-save" class="btn-sidebar">${escapeHtml(m.apiKeySave)}</button>
          <button type="button" id="settings-clear" class="btn-sidebar btn-muted">${escapeHtml(m.apiKeyClear)}</button>
        </div>
      </div>`;
    const close = () => overlay.remove();
    overlay.querySelector(".modal-close")!.addEventListener("click", close);
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) close();
    });
    overlay.querySelector("#settings-save")!.addEventListener("click", () => {
      const input = overlay.querySelector("#settings-api-key") as HTMLInputElement;
      setApiKey(input.value);
      this.updateApiKeyBanner();
      close();
    });
    overlay.querySelector("#settings-clear")!.addEventListener("click", () => {
      clearApiKey();
      this.updateApiKeyBanner();
      close();
    });
    document.body.appendChild(overlay);
  }

  private showAboutDialog(): void {
    const m = t();
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.innerHTML = `
      <div class="modal-card" role="dialog">
        <div class="modal-header">
          <h3>${escapeHtml(m.aboutTitle)}</h3>
          <button type="button" class="modal-close" aria-label="Close">✕</button>
        </div>
        <p>${escapeHtml(m.aboutBody)}</p>
        <p class="muted about-disclaimer">${escapeHtml(m.aboutDisclaimer)}</p>
        <p class="muted">MIT License · v0</p>
      </div>`;
    const close = () => overlay.remove();
    overlay.querySelector(".modal-close")!.addEventListener("click", close);
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) close();
    });
    document.body.appendChild(overlay);
  }

  private renderEmptyState(): void {
    if (this.messages.length > 0) return;
    const box = this.el.querySelector("#chat-messages") as HTMLElement;
    if (!box) return;
    const m = t();
    box.innerHTML = `
      <div class="chat-empty">
        <h3>${escapeHtml(m.emptyTitle)}</h3>
        <p class="muted">${escapeHtml(m.emptyHint)}</p>
        <div class="chat-prompts">
          <button type="button" class="chat-prompt-btn" data-prompt="0">${escapeHtml(m.prompt1)}</button>
          <button type="button" class="chat-prompt-btn" data-prompt="1">${escapeHtml(m.prompt2)}</button>
          <button type="button" class="chat-prompt-btn" data-prompt="2">${escapeHtml(m.prompt3)}</button>
        </div>
      </div>`;
    const prompts = [m.prompt1, m.prompt2, m.prompt3];
    box.querySelectorAll<HTMLButtonElement>(".chat-prompt-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = Number(btn.dataset.prompt || "0");
        const input = this.el.querySelector("#chat-input") as HTMLTextAreaElement;
        input.value = prompts[idx] || "";
        void this.send();
      });
    });
  }

  private renderMessages(): void {
    const box = this.el.querySelector("#chat-messages") as HTMLElement;
    if (!box) return;
    if (!this.messages.length) {
      this.renderEmptyState();
      return;
    }
    box.querySelectorAll<HTMLElement>(".msg-hydro").forEach((el) => {
      destroyHydroCharts(el);
    });
    box.innerHTML = "";
    for (let i = 0; i < this.messages.length; i++) {
      box.appendChild(this.buildMessageEl(i, this.messages[i]));
    }
    box.scrollTop = box.scrollHeight;
  }

  private buildMessageEl(index: number, msg: ChatMessage): HTMLElement {
    const m = t();
    const div = document.createElement("div");
    div.className = `msg msg-${msg.role}`;
    div.dataset.index = String(index);

    const body = document.createElement("div");
    body.className = "msg-body";
    body.innerHTML = formatMarkdownLite(msg.text || (msg.role === "assistant" ? "…" : ""));
    div.appendChild(body);

    if (msg.role === "assistant") {
      const hydro = document.createElement("div");
      hydro.className = "msg-hydro";
      hydro.hidden = true;
      div.appendChild(hydro);
      if (msg.tools?.length) {
        renderVisibleHydroOutputs(hydro, msg.tools);
      }
    }

    if (msg.tools?.length) {
      div.appendChild(this.buildToolsEl(msg.tools));
    }

    if (msg.map_state) {
      const restore = document.createElement("button");
      restore.type = "button";
      restore.className = "btn-map-restore";
      restore.textContent = m.restoreMap;
      restore.addEventListener("click", (ev) => {
        ev.stopPropagation();
        void this.map.restoreMapStateFromChat(msg.map_state!, msg);
      });
      div.appendChild(restore);
    }
    return div;
  }

  private buildToolsEl(
    tools: NonNullable<ChatMessage["tools"]>,
  ): HTMLDetailsElement {
    const details = document.createElement("details");
    details.className = "msg-tools";
    details.innerHTML = `<summary>${t().toolsCount(tools.length)}</summary>`;
    for (const tool of tools) {
      const pre = document.createElement("pre");
      const resultPreview =
        tool.result !== undefined
          ? JSON.stringify(tool.result, null, 0).slice(0, 500)
          : "…";
      pre.textContent = `${tool.name}(${JSON.stringify(tool.args)})\n→ ${resultPreview}`;
      details.appendChild(pre);
    }
    return details;
  }

  private updateAssistantText(assistant: ChatMessage): void {
    const box = this.el.querySelector("#chat-messages") as HTMLElement;
    const last = box.querySelector(
      `.msg-assistant[data-index="${this.messages.length - 1}"] .msg-body`,
    );
    if (last) {
      last.innerHTML = formatMarkdownLite(assistant.text || "…");
      box.scrollTop = box.scrollHeight;
    } else {
      this.renderMessages();
    }
  }

  private updateAssistantTools(assistant: ChatMessage): void {
    const box = this.el.querySelector("#chat-messages") as HTMLElement;
    const msgEl = box.querySelector(
      `.msg-assistant[data-index="${this.messages.length - 1}"]`,
    ) as HTMLElement | null;
    if (!msgEl) {
      this.renderMessages();
      return;
    }

    let hydro = msgEl.querySelector(".msg-hydro") as HTMLElement | null;
    if (!hydro) {
      hydro = document.createElement("div");
      hydro.className = "msg-hydro";
      const body = msgEl.querySelector(".msg-body");
      body?.after(hydro);
    }
    renderVisibleHydroOutputs(hydro, assistant.tools);

    msgEl.querySelector(".msg-tools")?.remove();
    if (assistant.tools?.length) {
      msgEl.appendChild(this.buildToolsEl(assistant.tools));
    }
    box.scrollTop = box.scrollHeight;
  }

  private async send(): Promise<void> {
    if (this.running) return;
    const input = this.el.querySelector("#chat-input") as HTMLTextAreaElement;
    const text = input.value.trim();
    if (!text) return;
    if (!chatKeyAvailable(this.health)) {
      this.showSettingsDialog();
      return;
    }
    input.value = "";
    this.running = true;
    this.messages.push({ role: "user", text });
    const assistant: ChatMessage = { role: "assistant", text: "", tools: [] };
    this.messages.push(assistant);
    this.renderMessages();

    const mapState = this.map.getMapState();
    const errLabel = t().errorPrefix;
    await streamChat(text, this.sessionId, mapState, {
      onEvent: (ev: ChatEvent) => {
        if (ev.type === "session") {
          this.sessionId = ev.session_id;
          void this.refreshHistoryList();
        } else if (ev.type === "text") {
          assistant.text += ev.text;
          this.updateAssistantText(assistant);
        } else if (ev.type === "tool_call") {
          assistant.tools = assistant.tools || [];
          assistant.tools.push({ name: ev.name, args: ev.args });
          this.updateAssistantTools(assistant);
        } else if (ev.type === "tool_result") {
          const last = assistant.tools?.[assistant.tools.length - 1];
          if (last && last.name === ev.name) last.result = ev.result;
          this.updateAssistantTools(assistant);
        } else if (ev.type === "map_action") {
          void this.map.applyMapAction(ev);
        } else if (ev.type === "error") {
          assistant.text += `\n\n**${errLabel} :** ${ev.error}`;
          this.updateAssistantText(assistant);
        }
      },
    });
    assistant.map_state = this.map.getMapState();
    this.running = false;
    this.renderMessages();
    void this.refreshHistoryList();
  }
}

function formatMarkdownLite(text: string): string {
  const lines = text.split("\n");
  const parts: string[] = [];
  let i = 0;
  while (i < lines.length) {
    const table = parseMarkdownTable(lines, i);
    if (table) {
      parts.push(table.html);
      i = table.next;
      continue;
    }
    const chunk: string[] = [];
    while (i < lines.length) {
      if (parseMarkdownTable(lines, i)) break;
      chunk.push(lines[i]);
      i++;
    }
    if (chunk.length) {
      parts.push(formatTextLines(chunk));
    }
  }
  return parts.join("");
}

function formatTextLines(lines: string[]): string {
  const out: string[] = [];
  for (const line of lines) {
    const heading = parseHeadingLine(line);
    if (heading) {
      out.push(
        `<h${heading.level} class="chat-h${heading.level}">${formatInlineMarkdown(heading.text)}</h${heading.level}>`,
      );
      continue;
    }
    if (line === "") {
      out.push("<br/>");
      continue;
    }
    out.push(formatInlineMarkdown(line));
  }
  return out.join("<br/>");
}

function parseHeadingLine(line: string): { level: number; text: string } | null {
  const m = line.trim().match(/^(#{1,5})\s+(.+)$/);
  if (!m) return null;
  return { level: m[1].length, text: m[2].trim() };
}

function formatInlineMarkdown(text: string): string {
  let s = escapeHtml(text);
  s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(
    /\[([^\]]+)\]\((https?:[^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener">$1</a>',
  );
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
    html += `<th${style}>${formatInlineMarkdown(headers[c])}</th>`;
  }
  html += "</tr></thead><tbody>";
  for (const row of rows) {
    html += "<tr>";
    for (let c = 0; c < headers.length; c++) {
      const align = aligns[c];
      const style = align ? ` style="text-align:${align}"` : "";
      html += `<td${style}>${formatInlineMarkdown(row[c] ?? "")}</td>`;
    }
    html += "</tr>";
  }
  html += "</tbody></table>";
  return { html, next: i };
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export type { MapState };
