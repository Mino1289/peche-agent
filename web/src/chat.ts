/** Client chat SSE. */

import { localeForApi } from "./i18n";
import { getApiKey } from "./settings";
import type { ChatEvent, ChatMessage, MapState } from "./types";

export type ChatHandlers = {
  onEvent: (ev: ChatEvent) => void;
  onDone?: () => void;
};

export async function streamChat(
  message: string,
  sessionId: string | null,
  mapState: MapState,
  handlers: ChatHandlers,
): Promise<string | null> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  const apiKey = getApiKey();
  if (apiKey) {
    headers["X-Gemini-Api-Key"] = apiKey;
  }

  const resp = await fetch("/api/chat", {
    method: "POST",
    headers,
    body: JSON.stringify({
      message,
      session_id: sessionId,
      map_state: mapState,
      locale: localeForApi(),
    }),
  });
  if (!resp.ok || !resp.body) {
    handlers.onEvent({
      type: "error",
      error: `HTTP ${resp.status}`,
    });
    handlers.onEvent({ type: "done" });
    return sessionId;
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let newSession = sessionId;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      const line = part
        .split("\n")
        .find((l) => l.startsWith("data: "));
      if (!line) continue;
      try {
        const ev = JSON.parse(line.slice(6)) as ChatEvent;
        if (ev.type === "session") newSession = ev.session_id;
        handlers.onEvent(ev);
      } catch {
        /* ignore parse errors */
      }
    }
  }
  handlers.onDone?.();
  return newSession;
}

export async function listConversations(): Promise<
  { id: string; title: string; updated_at: string; message_count: number }[]
> {
  const resp = await fetch("/api/conversations");
  const data = await resp.json();
  return data.conversations || [];
}

export async function loadConversation(
  id: string,
): Promise<{ messages: ChatMessage[]; map_state?: MapState } | null> {
  const resp = await fetch(`/api/conversations/${id}`);
  if (!resp.ok) return null;
  const data = await resp.json();
  const messages: ChatMessage[] = data.messages || [];
  let map_state: MapState | undefined;
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].map_state) {
      map_state = messages[i].map_state;
      break;
    }
  }
  return { messages, map_state };
}
