/** Panneau chat + historique (sidebar gauche). */

import type { ChatEvent, ChatMessage, MapPin, MapState } from "./types";
import { toolLabels } from "./toolLabels";
import type { MapController } from "./map";
import {
  deleteConversation as deleteConversationApi,
  listConversations,
  loadConversation,
  streamChat,
} from "./chat";
import {
  destroyHydroCharts,
  renderVisibleHydroOutputs,
} from "./hydroCharts";
import { getLocale, onLocaleChange, t } from "./i18n";
import {
  chatKeyAvailable,
  clearApiKey,
  fetchHealth,
  getApiKey,
  setApiKey,
  type HealthInfo,
} from "./settings";
import { navigate, parseRoute } from "./router";
import { escapeHtml, formatMarkdown } from "./markdown";

const AI_STUDIO_URL = "https://aistudio.google.com/app/apikey";

const SVG_ATTRS =
  'viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"';
const ICON_COPY = `<svg ${SVG_ATTRS}><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;
const ICON_CHECK = `<svg ${SVG_ATTRS}><polyline points="20 6 9 17 4 12"/></svg>`;
const ICON_REGEN = `<svg ${SVG_ATTRS}><path d="M21 12a9 9 0 1 1-2.64-6.36L21 8"/><path d="M21 3v5h-5"/></svg>`;
const ICON_PIN = `<svg ${SVG_ATTRS}><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0z"/><circle cx="12" cy="10" r="3"/></svg>`;

export class ChatPanel {
  private el: HTMLElement;
  private sidebar: HTMLElement;
  private map: MapController;
  private sessionId: string | null = null;
  private messages: ChatMessage[] = [];
  private running = false;
  private health: HealthInfo | null = null;
  private ready: Promise<void>;

  constructor(el: HTMLElement, sidebar: HTMLElement, map: MapController) {
    this.el = el;
    this.sidebar = sidebar;
    this.map = map;
    onLocaleChange(() => {
      this.renderSidebar();
      this.renderShell();
      this.renderMessages();
    });
    this.ready = this.init();
  }

  getSessionId(): string | null {
    return this.sessionId;
  }

  /** Affiche une conversation (ou une nouvelle si null). N'écrit pas l'URL. */
  async showConversation(id: string | null): Promise<void> {
    await this.ready;
    if (this.running) return;
    if (!id) {
      this.resetChat();
      return;
    }
    const loaded = await loadConversation(id);
    if (!loaded) {
      navigate({ tab: "chat", id: null }, "replace");
      this.resetChat();
      return;
    }
    this.sessionId = id;
    this.messages = loaded.messages;
    this.renderMessages();
    void this.refreshHistoryList();
    if (loaded.map_state) await this.map.applyMapState(loaded.map_state);
  }

  private resetChat(): void {
    this.sessionId = null;
    this.messages = [];
    this.renderMessages();
    this.renderEmptyState();
    void this.refreshHistoryList();
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
        <button type="button" class="identify-close mobile-only" id="btn-chat-sidebar-close" title="${escapeHtml(m.close)}" aria-label="${escapeHtml(m.close)}">✕</button>
      </div>
      <div class="chat-sidebar-actions">
        <button type="button" id="btn-new-chat" class="btn-sidebar" title="${m.newChat}">${m.newChat}</button>
      </div>
      <div id="history-list" class="history-list"></div>`;
    this.sidebar.querySelector("#btn-chat-sidebar-close")?.addEventListener("click", () => {
      window.dispatchEvent(new CustomEvent("peche:close-drawers"));
    });
    this.sidebar.querySelector("#btn-new-chat")!.addEventListener("click", () => {
      navigate({ tab: "chat", id: null });
      this.resetChat();
      window.dispatchEvent(new CustomEvent("peche:close-drawers"));
    });
    void this.refreshHistoryList({ showLoading: true });
  }

  private async refreshHistoryList(opts?: { showLoading?: boolean }): Promise<void> {
    const m = t();
    const list = this.sidebar.querySelector("#history-list") as HTMLElement;
    if (opts?.showLoading) {
      list.innerHTML = `<p class='muted'>${m.loading}</p>`;
    }
    const convs = await listConversations();
    list.innerHTML = "";
    if (!convs.length) {
      list.innerHTML = `<p class='muted history-empty'>${m.noConversations}</p>`;
      return;
    }
    for (const c of convs) {
      const row = document.createElement("div");
      row.className = "history-item-row";
      row.dataset.convId = c.id;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "history-item";
      if (c.id === this.sessionId) btn.classList.add("active");
      const updated = new Date(c.updated_at);
      const when = Number.isNaN(updated.getTime())
        ? c.updated_at
        : updated.toLocaleDateString(getLocale() === "en" ? "en-CA" : "fr-CA", {
            day: "numeric",
            month: "short",
            year: "numeric",
          });
      btn.innerHTML = `<span class="history-item-title">${escapeHtml(c.title)}</span><span class="history-item-meta">${escapeHtml(when)}, ${c.message_count} ${m.msgs}</span>`;
      btn.addEventListener("click", () => {
        navigate({ tab: "chat", id: c.id });
        void this.showConversation(c.id);
        window.dispatchEvent(new CustomEvent("peche:close-drawers"));
      });
      const del = document.createElement("button");
      del.type = "button";
      del.className = "btn-icon history-delete";
      del.title = m.deleteConversation;
      del.setAttribute("aria-label", m.deleteConversation);
      del.textContent = "✕";
      del.addEventListener("click", (ev) => {
        ev.stopPropagation();
        this.confirmDeleteConversation(c.id);
      });
      row.appendChild(btn);
      row.appendChild(del);
      list.appendChild(row);
    }
  }

  private confirmDeleteConversation(id: string): void {
    const m = t();
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.innerHTML = `
      <div class="modal-card" role="dialog">
        <div class="modal-header">
          <h3>${escapeHtml(m.deleteConversation)}</h3>
          <button type="button" class="modal-close" aria-label="${escapeHtml(m.close)}">✕</button>
        </div>
        <p>${escapeHtml(m.deleteConversationConfirm)}</p>
        <div class="modal-actions">
          <button type="button" class="btn-danger" id="confirm-delete-yes">${escapeHtml(m.yes)}</button>
          <button type="button" class="btn-sidebar btn-muted" id="confirm-delete-no">${escapeHtml(m.no)}</button>
        </div>
      </div>`;
    const close = () => overlay.remove();
    overlay.querySelector(".modal-close")!.addEventListener("click", close);
    overlay.querySelector("#confirm-delete-no")!.addEventListener("click", close);
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) close();
    });
    overlay.querySelector("#confirm-delete-yes")!.addEventListener("click", () => {
      close();
      void this.deleteConversation(id);
    });
    document.body.appendChild(overlay);
  }

  private async deleteConversation(id: string): Promise<void> {
    const list = this.sidebar.querySelector("#history-list") as HTMLElement | null;
    list
      ?.querySelector(`.history-item-row[data-conv-id="${id}"]`)
      ?.remove();
    const ok = await deleteConversationApi(id);
    if (!ok) {
      void this.refreshHistoryList();
      return;
    }
    if (this.sessionId === id) {
      navigate({ tab: "chat", id: null }, "replace");
      this.resetChat();
    }
    if (list && !list.querySelector(".history-item-row")) {
      list.innerHTML = `<p class='muted history-empty'>${t().noConversations}</p>`;
    }
  }

  private renderShell(): void {
    const m = t();
    this.el.innerHTML = `
      <div class="panel-header chat-header">
        <div class="chat-header-title">
          <button type="button" id="btn-mobile-history" class="btn-icon mobile-only" title="${escapeHtml(m.conversations)}" aria-label="${escapeHtml(m.conversations)}" aria-controls="chat-sidebar" aria-expanded="false">☰</button>
          <h2>${m.assistant}</h2>
        </div>
        <div class="chat-header-actions">
          <button type="button" id="btn-mobile-new-chat" class="btn-icon mobile-only" title="${escapeHtml(m.newChat)}" aria-label="${escapeHtml(m.newChat)}">＋</button>
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
    this.el.querySelector("#btn-mobile-history")?.addEventListener("click", () => {
      window.dispatchEvent(new CustomEvent("peche:toggle-chat-sidebar"));
    });
    this.el.querySelector("#btn-mobile-new-chat")?.addEventListener("click", () => {
      navigate({ tab: "chat", id: null });
      this.resetChat();
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
    if (msg.role === "assistant" && this.running && index === this.messages.length - 1) {
      body.appendChild(this.buildThinkingEl(!msg.text && !msg.tools?.length));
    }
    if (msg.text || msg.role !== "assistant") {
      const textEl = document.createElement("div");
      textEl.className = "msg-text";
      textEl.innerHTML = formatMarkdown(
        msg.text || (msg.role === "assistant" ? "" : ""),
      );
      body.appendChild(textEl);
    }
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
      div.appendChild(this.buildToolsEl(msg.tools, msg.map_state?.pins));
    }

    const actions = this.buildMessageActions(index, msg);
    if (actions) div.appendChild(actions);
    return div;
  }

  private buildMessageActions(index: number, msg: ChatMessage): HTMLElement | null {
    const m = t();
    const bar = document.createElement("div");
    bar.className = "msg-actions";
    const next = this.messages[index + 1];
    const copyable = msg.role === "user" || !(this.running && index === this.messages.length - 1);
    if (copyable && msg.text) {
      bar.appendChild(
        this.actionButton(ICON_COPY, m.copy, (btn) => void this.copyText(msg.text, btn)),
      );
    }
    if (msg.role === "user" && !this.running && next?.role === "assistant" && next.text) {
      bar.appendChild(
        this.actionButton(ICON_REGEN, m.regenerate, () => void this.regenerate(index)),
      );
    }
    if (msg.map_state) {
      bar.appendChild(
        this.actionButton(ICON_PIN, m.restoreMap, () => {
          void this.map.restoreMapStateFromChat(msg.map_state!, msg);
        }),
      );
    }
    return bar.childElementCount ? bar : null;
  }

  private actionButton(
    icon: string,
    label: string,
    onClick: (btn: HTMLButtonElement) => void,
  ): HTMLButtonElement {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn-msg-action";
    btn.title = label;
    btn.setAttribute("aria-label", label);
    btn.innerHTML = icon;
    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      onClick(btn);
    });
    return btn;
  }

  private async copyText(text: string, btn: HTMLButtonElement): Promise<void> {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      return;
    }
    btn.innerHTML = ICON_CHECK;
    window.setTimeout(() => {
      btn.innerHTML = ICON_COPY;
    }, 1500);
  }

  /** Réécrit la réponse au message `index` ; les messages suivants sont supprimés. */
  private async regenerate(index: number): Promise<void> {
    if (this.running || !this.sessionId) return;
    if (!chatKeyAvailable(this.health)) {
      this.showSettingsDialog();
      return;
    }
    const text = this.messages[index].text;
    const ordinal = this.messages.slice(0, index).filter((x) => x.role === "user").length;
    this.messages = this.messages.slice(0, index);
    await this.submit(text, ordinal);
  }

  private buildThinkingEl(show: boolean, usingTools = false): HTMLElement {
    const wrap = document.createElement("div");
    wrap.className = "msg-thinking";
    wrap.hidden = !show;
    const m = t();
    wrap.innerHTML = `
      <span class="msg-thinking-dots" aria-hidden="true"><span></span><span></span><span></span></span>
      <span class="msg-thinking-label">${escapeHtml(usingTools ? m.agentUsingTools : m.agentThinking)}</span>`;
    return wrap;
  }

  private setAssistantThinking(usingTools = false): void {
    const box = this.el.querySelector("#chat-messages") as HTMLElement;
    const msgEl = box.querySelector(
      `.msg-assistant[data-index="${this.messages.length - 1}"]`,
    ) as HTMLElement | null;
    if (!msgEl) return;
    const body = msgEl.querySelector(".msg-body");
    if (!body) return;
    let thinking = body.querySelector(".msg-thinking") as HTMLElement | null;
    if (!thinking) {
      thinking = this.buildThinkingEl(true, usingTools);
      body.prepend(thinking);
    } else {
      thinking.hidden = false;
      const label = thinking.querySelector(".msg-thinking-label");
      if (label) {
        label.textContent = usingTools ? t().agentUsingTools : t().agentThinking;
      }
    }
  }

  private clearAssistantThinking(): void {
    const box = this.el.querySelector("#chat-messages") as HTMLElement;
    const msgEl = box.querySelector(
      `.msg-assistant[data-index="${this.messages.length - 1}"]`,
    ) as HTMLElement | null;
    msgEl?.querySelector(".msg-thinking")?.remove();
  }

  private buildToolsEl(
    tools: NonNullable<ChatMessage["tools"]>,
    pins: MapPin[] = [],
  ): HTMLDetailsElement {
    const details = document.createElement("details");
    details.className = "msg-tools";
    details.innerHTML = `<summary>${t().toolsCount(tools.length)}</summary>`;
    if (!import.meta.env.DEV) {
      // Prod : seulement les libellés lisibles (pas d'IDs ni de JSON brut).
      const list = document.createElement("div");
      list.className = "msg-tool-lines";
      details.appendChild(list);
      void toolLabels(tools, pins).then((labels) => {
        list.innerHTML = "";
        for (const label of labels) {
          const line = document.createElement("div");
          line.textContent = label;
          list.appendChild(line);
        }
      });
      return details;
    }
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
    const body = box.querySelector(
      `.msg-assistant[data-index="${this.messages.length - 1}"] .msg-body`,
    ) as HTMLElement | null;
    if (body) {
      if (assistant.text) this.clearAssistantThinking();
      let textEl = body.querySelector(".msg-text") as HTMLElement | null;
      if (!textEl) {
        textEl = document.createElement("div");
        textEl.className = "msg-text";
        body.appendChild(textEl);
      }
      textEl.innerHTML = formatMarkdown(assistant.text || "");
      if (!assistant.text && this.running) this.setAssistantThinking(Boolean(assistant.tools?.length));
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
      msgEl.appendChild(this.buildToolsEl(assistant.tools, this.map.getMapState().pins));
      if (this.running && !assistant.text) this.setAssistantThinking(true);
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
    await this.submit(text, null);
  }

  private async submit(text: string, regenerateFrom: number | null): Promise<void> {
    this.running = true;
    this.messages.push({ role: "user", text });
    const assistant: ChatMessage = { role: "assistant", text: "", tools: [] };
    this.messages.push(assistant);
    this.renderMessages();
    this.setAssistantThinking();

    const mapState = this.map.getMapState();
    const errLabel = t().errorPrefix;
    await streamChat(text, this.sessionId, mapState, {
      onEvent: (ev: ChatEvent) => {
        if (ev.type === "session") {
          this.sessionId = ev.session_id;
          if (parseRoute().tab === "chat") {
            navigate({ tab: "chat", id: ev.session_id }, "replace");
          }
          void this.refreshHistoryList();
        } else if (ev.type === "text") {
          assistant.text += ev.text;
          this.updateAssistantText(assistant);
        } else if (ev.type === "tool_call") {
          assistant.tools = assistant.tools || [];
          assistant.tools.push({ name: ev.name, args: ev.args });
          this.updateAssistantTools(assistant);
        } else if (ev.type === "tool_result") {
          const pending =
            assistant.tools?.find((t) => t.name === ev.name && t.result === undefined) ??
            [...(assistant.tools || [])].reverse().find((t) => t.name === ev.name);
          if (pending) pending.result = ev.result;
          this.updateAssistantTools(assistant);
        } else if (ev.type === "map_action") {
          void this.map.applyMapAction(ev);
        } else if (ev.type === "error") {
          assistant.text += `\n\n**${errLabel} :** ${ev.error}`;
          this.updateAssistantText(assistant);
        }
      },
    }, regenerateFrom);
    assistant.map_state = this.map.getMapState();
    this.running = false;
    this.clearAssistantThinking();
    this.renderMessages();
    void this.refreshHistoryList();
  }
}

export type { MapState };
