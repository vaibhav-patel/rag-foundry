import type { RagQueryResponse } from "../api/payloads";

export function isLikelyStreamingContentType(ct: string): boolean {
  const lower = ct.toLowerCase();
  return (
    lower.includes("text/event-stream") ||
    lower.includes("application/x-ndjson") ||
    lower.includes("application/ndjson")
  );
}

type StreamHandlers = {
  onDelta: (text: string) => void;
  onFinished: (response: RagQueryResponse) => void;
};

/** Merge streamed fields into a minimal valid RagQueryResponse. */
export function coerceRagResponse(
  fields: Partial<RagQueryResponse> & { answer: string },
): RagQueryResponse {
  return {
    answer: fields.answer,
    citations: fields.citations ?? [],
    kb_id: fields.kb_id ?? "",
    guardrails_applied: fields.guardrails_applied ?? false,
  };
}

/**
 * Consume optional future SSE payloads: `data: {"delta":"..."}`, `data: {"final":…}` plus full RagQuery JSON.
 */
export async function consumeSseRagBody(
  body: ReadableStream<Uint8Array> | null,
  signal: AbortSignal,
  h: StreamHandlers,
): Promise<void> {
  if (!body) return;
  const reader = body.getReader();
  const dec = new TextDecoder();
  let carry = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (signal.aborted) break;
      if (done) break;
      carry += dec.decode(value, { stream: true });
      const parts = carry.split(/\r?\n/);
      carry = parts.pop() ?? "";
      for (const rawLine of parts) {
        const line = rawLine.trimEnd();
        if (!line.startsWith("data:")) continue;
        const payload = line.slice(5).trim();
        if (payload === "[DONE]" || payload === "") continue;
        try {
          const json = JSON.parse(payload) as Record<string, unknown>;
          const delta =
            typeof json.delta === "string"
              ? json.delta
              : typeof json.answer_delta === "string"
                ? json.answer_delta
                : "";
          if (delta) h.onDelta(delta);
          const isFinal =
            json.final === true ||
            json.type === "final" ||
            (json.answer != null && typeof json.answer === "string" && delta === "" && json.citations !== undefined);
          if (
            isFinal &&
            typeof json.answer === "string" &&
            typeof json.kb_id === "string" &&
            Array.isArray(json.citations)
          ) {
            h.onFinished(coerceRagResponse(json as Partial<RagQueryResponse>));
          }
        } catch {
          /* ignore malformed frame */
        }
      }
    }
  } finally {
    reader.releaseLock?.();
  }
}

/**
 * One JSON object per line: `{delta}`, then optional `{answer,citations,...}` terminal row.
 */
export async function consumeNdjsonRagBody(
  body: ReadableStream<Uint8Array> | null,
  signal: AbortSignal,
  h: StreamHandlers,
): Promise<void> {
  if (!body) return;
  const reader = body.getReader();
  const dec = new TextDecoder();
  let buf = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (signal.aborted) break;
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let idx: number;
      while ((idx = buf.indexOf("\n")) !== -1) {
        const line = buf.slice(0, idx).trim();
        buf = buf.slice(idx + 1);
        if (!line) continue;
        try {
          const json = JSON.parse(line) as Record<string, unknown>;
          const delta = typeof json.delta === "string" ? json.delta : "";
          if (delta) h.onDelta(delta);
          if (
            typeof json.answer === "string" &&
            Array.isArray(json.citations) &&
            typeof json.kb_id === "string"
          ) {
            h.onFinished(coerceRagResponse(json as Partial<RagQueryResponse>));
          }
        } catch {
          /* skip bad line */
        }
      }
    }
  } finally {
    reader.releaseLock?.();
  }
}
