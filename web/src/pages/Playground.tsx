import { useMutation, useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { authHeaders, fetchKnowledgeBaseList, type KnowledgeBaseListJson } from "../api";
import { denseSearchBody, ragQueryBody, type DenseSearchResponse } from "../api/payloads";
import { QueryAnswerSection } from "../components/QueryAnswerSection";
import { SearchResultsPanel } from "../components/SearchResultsPanel";
import { useRagQueryPlayback } from "../hooks/useRagQueryPlayback";

const api = import.meta.env.VITE_API_URL ?? "";
const token = import.meta.env.VITE_JWT_TOKEN ?? "";

async function searchKb(kbId: string, body: ReturnType<typeof denseSearchBody>): Promise<DenseSearchResponse> {
  const r = await fetch(`${api}/v1/kbs/${kbId}/search`, {
    method: "POST",
    headers: {
      ...authHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`search ${r.status}`);
  return r.json();
}

export function Playground() {
  const questionRef = useRef<HTMLInputElement>(null);
  const [kbId, setKbId] = useState("");
  const [q, setQ] = useState("hello");
  const [question, setQuestion] = useState("What is this KB about?");
  const kbs = useQuery<KnowledgeBaseListJson>({
    queryKey: ["kbs"],
    queryFn: fetchKnowledgeBaseList,
    enabled: Boolean(token && api),
  });
  const searchMut = useMutation({
    mutationFn: () => searchKb(kbId, denseSearchBody({ q, k: 5 })),
  });

  const ragPlayback = useRagQueryPlayback({
    apiBaseUrl: api,
    kbId,
    question,
    authHeaders,
  });

  const searchPanelStatus = searchMut.isPending
    ? "pending"
    : searchMut.isError
      ? "error"
      : searchMut.isSuccess
        ? "success"
        : "idle";

  const onSendToQuery = (snippet: string) => {
    setQuestion(snippet);
    queueMicrotask(() => {
      questionRef.current?.focus();
      questionRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  };

  const canQuery = Boolean(kbId.trim()) && Boolean(question.trim());
  const rawJsonBusy = searchMut.isPending || ragPlayback.phase === "fetching";

  if (!api || !token) {
    return (
      <div className="text-slate-400 text-sm">
        Set <code className="text-emerald-400">VITE_API_URL</code> and{" "}
        <code className="text-emerald-400">VITE_JWT_TOKEN</code> in <code>.env.local</code> for live calls.
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <h1 className="text-xl font-medium">Search playground</h1>
      <label className="block text-sm text-slate-400">
        KB id
        <input
          className="mt-1 block w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100"
          value={kbId}
          onChange={(e) => setKbId(e.target.value)}
          placeholder="from list below"
        />
      </label>
      <div className="text-xs text-slate-500">
        KBs:{" "}
        {kbs.isLoading ? "…" : kbs.isError ? String(kbs.error) : JSON.stringify(kbs.data?.items ?? [])}
      </div>
      <div className="flex gap-2 flex-wrap">
        <button
          type="button"
          className="rounded bg-emerald-700 px-3 py-2 text-sm text-white hover:bg-emerald-600"
          onClick={() => searchMut.mutate()}
          disabled={!kbId}
        >
          Search
        </button>
        <button
          type="button"
          className="rounded bg-slate-700 px-3 py-2 text-sm text-white hover:bg-slate-600 disabled:opacity-45"
          onClick={() => ragPlayback.runQuery()}
          disabled={!canQuery}
          title={!canQuery ? "Provide KB id and a non-empty question" : undefined}
        >
          RAG query
        </button>
      </div>
      <label className="block text-sm text-slate-400">
        Search text
        <input
          className="mt-1 block w-full rounded border border-slate-700 bg-slate-900 px-3 py-2"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </label>
      <label className="block text-sm text-slate-400">
        Question
        <input
          ref={questionRef}
          className="mt-1 block w-full rounded border border-slate-700 bg-slate-900 px-3 py-2"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
      </label>

      <SearchResultsPanel
        hits={searchMut.data?.hits ?? []}
        query={q}
        status={searchPanelStatus}
        total={searchMut.data?.total ?? null}
        backend={searchMut.data?.backend ?? null}
        errorMessage={searchMut.error ? String(searchMut.error) : null}
        onSendToQuery={onSendToQuery}
      />

      <QueryAnswerSection playback={ragPlayback} />

      <details className="rounded-lg border border-slate-800 bg-slate-900/30 p-3 text-xs">
        <summary className="cursor-pointer text-slate-400 select-none">Raw API JSON</summary>
        <pre className="mt-2 overflow-auto text-slate-300 max-h-64">
          {rawJsonBusy
            ? "Loading…"
            : JSON.stringify(
                {
                  search: searchMut.data ?? null,
                  ragQuery: ragQueryBody(question.trim() || "(empty)"),
                  ragAnswer: ragPlayback.fullResponse ?? null,
                },
                null,
                2,
              )}
        </pre>
      </details>
    </div>
  );
}
