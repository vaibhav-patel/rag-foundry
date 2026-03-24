import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { RagQueryResponse } from "../api/payloads";
import { ragQueryBody } from "../api/payloads";
import { RagQueryHttpError } from "../lib/queryErrors";
import {
  coerceRagResponse,
  consumeNdjsonRagBody,
  consumeSseRagBody,
  isLikelyStreamingContentType,
} from "../lib/ragQueryResponseReader";

function revealTyping(
  full: string,
  signal: AbortSignal,
  push: (slice: string) => void,
  opts?: { charsPerTick?: number; ms?: number },
): Promise<void> {
  const charsPerTick = opts?.charsPerTick ?? 2;
  const ms = opts?.ms ?? 18;
  return new Promise((resolve) => {
    let i = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const cleanup = () => {
      if (timer !== undefined) clearTimeout(timer);
      signal.removeEventListener("abort", onAbort);
    };

    const onAbort = () => {
      cleanup();
      resolve();
    };

    signal.addEventListener("abort", onAbort, { once: true });

    const step = () => {
      if (signal.aborted) {
        cleanup();
        resolve();
        return;
      }
      i = Math.min(full.length, i + charsPerTick);
      push(full.slice(0, i));
      if (i >= full.length) {
        cleanup();
        resolve();
        return;
      }
      timer = setTimeout(step, ms);
    };

    step();
  });
}

export type UseRagQueryPlaybackOpts = {
  apiBaseUrl: string;
  kbId: string;
  question: string;
  authHeaders: () => HeadersInit | Record<string, string>;
  fetchImpl?: typeof fetch;
};

export type PlaybackPhase = "idle" | "fetching" | "revealing" | "done" | "error";

export type UseRagQueryPlaybackReturn = {
  phase: PlaybackPhase;
  error: RagQueryHttpError | null;
  displayedAnswer: string;
  fullResponse: RagQueryResponse | null;
  streamingMode: boolean;
  runQuery: () => void;
  retry: () => void;
  /** Bump this with retries so error boundaries keyed on it reset. */
  attemptId: number;
};

export function useRagQueryPlayback(o: UseRagQueryPlaybackOpts): UseRagQueryPlaybackReturn {
  const fetchFn = o.fetchImpl ?? fetch;
  const [phase, setPhase] = useState<PlaybackPhase>("idle");
  const [error, setError] = useState<RagQueryHttpError | null>(null);
  const [displayedAnswer, setDisplayedAnswer] = useState("");
  const [fullResponse, setFullResponse] = useState<RagQueryResponse | null>(null);
  const [streamingMode, setStreamingMode] = useState(false);
  const [attemptId, setAttemptId] = useState(0);

  const ragBody = useMemo(() => ragQueryBody(o.question.trim() || "(empty)"), [o.question]);

  const abortFetchRef = useRef<AbortController | null>(null);
  const abortTypingRef = useRef<AbortController | null>(null);
  const requestGenRef = useRef(0);

  useEffect(() => {
    return () => {
      abortFetchRef.current?.abort();
      abortTypingRef.current?.abort();
    };
  }, []);

  const invalidateRun = () => {
    requestGenRef.current += 1;
    abortFetchRef.current?.abort();
    abortTypingRef.current?.abort();
  };

  const run = useCallback(() => {
    const kbOk = Boolean(o.kbId.trim()) && Boolean(o.question.trim());
    if (!kbOk) return;

    invalidateRun();
    const gen = requestGenRef.current;
    const ac = new AbortController();
    abortFetchRef.current = ac;

    setAttemptId((id) => id + 1);
    setDisplayedAnswer("");
    setFullResponse(null);
    setError(null);
    setStreamingMode(false);
    setPhase("fetching");

    void (async () => {
      try {
        const url = `${o.apiBaseUrl}/v1/kbs/${encodeURIComponent(o.kbId)}/query`;
        const res = await fetchFn(url, {
          method: "POST",
          headers: {
            ...o.authHeaders(),
            "Content-Type": "application/json",
          },
          body: JSON.stringify(ragBody),
          signal: ac.signal,
        });

        if (requestGenRef.current !== gen || ac.signal.aborted) return;

        if (!res.ok) {
          const text = await res.text().catch(() => "");
          setError(new RagQueryHttpError(res.status, text.slice(0, 2000)));
          setPhase("error");
          return;
        }

        const ct = res.headers.get("content-type") ?? "";

        if (isLikelyStreamingContentType(ct)) {
          setStreamingMode(true);
          setPhase("revealing");

          let aggregated = "";
          let receivedFinal = false;

          const finalize = (r: RagQueryResponse) => {
            if (receivedFinal || requestGenRef.current !== gen || ac.signal.aborted) return;
            receivedFinal = true;
            setFullResponse(r);
            setDisplayedAnswer(r.answer);
            setPhase("done");
          };

          try {
            if (ct.includes("event-stream")) {
              await consumeSseRagBody(res.body, ac.signal, {
                onDelta: (d) => {
                  aggregated += d;
                  setDisplayedAnswer(aggregated);
                },
                onFinished: finalize,
              });
            } else {
              await consumeNdjsonRagBody(res.body, ac.signal, {
                onDelta: (d) => {
                  aggregated += d;
                  setDisplayedAnswer(aggregated);
                },
                onFinished: finalize,
              });
            }

            if (requestGenRef.current !== gen || ac.signal.aborted) return;
            if (!receivedFinal)
              finalize(
                coerceRagResponse({
                  answer: aggregated.trim(),
                  kb_id: o.kbId,
                }),
              );
          } catch (e) {
            if (e instanceof DOMException && e.name === "AbortError") return;
            setError(new RagQueryHttpError(0, String(e ?? "stream read failed")));
            setPhase("error");
          }

          return;
        }

        setStreamingMode(false);
        let data: RagQueryResponse;
        try {
          data = (await res.json()) as RagQueryResponse;
        } catch {
          throw new RagQueryHttpError(0, "Invalid JSON response from query endpoint.");
        }

        if (requestGenRef.current !== gen || ac.signal.aborted) return;

        const answer = typeof data.answer === "string" ? data.answer : "";
        setFullResponse(data);
        setDisplayedAnswer("");
        setPhase("revealing");

        abortTypingRef.current?.abort();
        const tac = new AbortController();
        abortTypingRef.current = tac;

        await revealTyping(answer, tac.signal, setDisplayedAnswer);

        if (requestGenRef.current !== gen || ac.signal.aborted || tac.signal.aborted) return;
        setDisplayedAnswer(answer);
        setPhase("done");
      } catch (e) {
        if (e instanceof DOMException && e.name === "AbortError") return;
        if (requestGenRef.current !== gen) return;
        if (e instanceof RagQueryHttpError) {
          setError(e);
        } else {
          setError(new RagQueryHttpError(0, String(e)));
        }
        setPhase("error");
      }
    })();
  }, [fetchFn, o.apiBaseUrl, o.authHeaders, o.kbId, ragBody]);
