"use client";

import { FormEvent, useMemo, useRef, useState } from "react";
import { sendMessage } from "@/lib/investra-api";

type ChatRole = "user" | "assistant";

type ChatItem = {
  id: string;
  role: ChatRole;
  content: string;
};

type ChatStatus = "idle" | "thinking" | "streaming";

function getOrCreateSessionId(): string {
  const storageKey = "investra-session-id";
  const existing = window.localStorage.getItem(storageKey);
  if (existing && existing.trim().length > 0) {
    return existing;
  }

  if (
    typeof crypto === "undefined" ||
    typeof crypto.randomUUID !== "function"
  ) {
    throw new Error("crypto.randomUUID is required to create a chat session");
  }

  const generated = crypto.randomUUID();

  window.localStorage.setItem(storageKey, generated);
  return generated;
}

function chunkResponse(text: string): string[] {
  const normalized = text.trim();

  if (!normalized) {
    return [""];
  }

  const chunks: string[] = [];
  const size = 18;

  for (let index = 0; index < normalized.length; index += size) {
    chunks.push(normalized.slice(index, index + size));
  }

  return chunks;
}

export function InvestraChat() {
  const [messages, setMessages] = useState<ChatItem[]>([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState<ChatStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const sessionIdRef = useRef<string>("");

  const canSend = useMemo(
    () => input.trim().length > 0 && status === "idle",
    [input, status],
  );

  const scrollToBottom = () => {
    requestAnimationFrame(() => {
      if (listRef.current) {
        listRef.current.scrollTop = listRef.current.scrollHeight;
      }
    });
  };

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const trimmed = input.trim();
    if (!trimmed || status !== "idle") {
      return;
    }

    setError(null);
    setInput("");
    setStatus("thinking");

    const userMessage: ChatItem = {
      id: crypto.randomUUID(),
      role: "user",
      content: trimmed,
    };

    setMessages((prev) => [...prev, userMessage]);
    scrollToBottom();

    try {
      if (!sessionIdRef.current) {
        sessionIdRef.current = getOrCreateSessionId();
      }

      const backendResponse = await sendMessage(trimmed, sessionIdRef.current);

      const assistantId = crypto.randomUUID();
      setMessages((prev) => [
        ...prev,
        {
          id: assistantId,
          role: "assistant",
          content: "",
        },
      ]);

      setStatus("streaming");

      for (const chunk of chunkResponse(backendResponse)) {
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantId
              ? { ...msg, content: `${msg.content}${chunk}` }
              : msg,
          ),
        );

        await new Promise<void>((resolve) => {
          setTimeout(resolve, 18);
        });
      }

      setStatus("idle");
      scrollToBottom();
    } catch (_error) {
      setStatus("idle");
      setError("Backend unavailable");
    }
  };

  return (
    <div className="mx-auto flex h-[calc(100dvh-2rem)] w-full max-w-4xl flex-col rounded-xl border border-border/60 bg-background shadow-sm">
      <div className="border-b border-border/50 px-5 py-4">
        <h1 className="text-lg font-semibold">Investra AI</h1>
        <p className="text-sm text-muted-foreground">
          Financial assistant for stock analysis and investment guidance.
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4" ref={listRef}>
        {messages.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border/60 p-4 text-sm text-muted-foreground">
            Ask about markets, portfolio ideas, or compare companies.
          </div>
        ) : (
          <div className="space-y-3">
            {messages.map((message) => (
              <div
                className={
                  message.role === "user"
                    ? "ml-auto max-w-[85%] rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground"
                    : "mr-auto max-w-[85%] rounded-lg border border-border/60 bg-muted/40 px-3 py-2 text-sm whitespace-pre-wrap"
                }
                key={message.id}
              >
                {message.content}
              </div>
            ))}

            {status === "thinking" && (
              <div className="mr-auto max-w-[85%] rounded-lg border border-border/60 bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
                Thinking...
              </div>
            )}
          </div>
        )}
      </div>

      <div className="border-t border-border/50 p-4">
        {error && <p className="mb-2 text-sm text-destructive">{error}</p>}

        <form className="flex gap-2" onSubmit={onSubmit}>
          <input
            className="h-10 flex-1 rounded-md border border-border bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onChange={(event) => setInput(event.target.value)}
            placeholder="Ask Investra about stocks, risk, or portfolio strategy..."
            value={input}
          />
          <button
            className="inline-flex h-10 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!canSend}
            type="submit"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
