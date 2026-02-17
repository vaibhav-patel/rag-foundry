import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

const api = import.meta.env.VITE_API_URL ?? "";
const token = import.meta.env.VITE_JWT_TOKEN ?? "";

async function listKbs(): Promise<{ items: { id: string; name: string }[] }> {
  const r = await fetch(`${api}/v1/kbs`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!r.ok) throw new Error(`kbs ${r.status}`);
  return r.json();
}

async function searchKb(kbId: string, q: string) {
  const r = await fetch(`${api}/v1/kbs/${kbId}/search`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ q, top_k: 5 }),
  });
  if (!r.ok) throw new Error(`search ${r.status}`);
  return r.json();
}

async function queryKb(kbId: string, question: string) {
  const r = await fetch(`${api}/v1/kbs/${kbId}/query`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ question }),
  });
  if (!r.ok) throw new Error(`query ${r.status}`);
  return r.json();
}

export function Playground() {
  const [kbId, setKbId] = useState("");
  const [q, setQ] = useState("hello");
  const [question, setQuestion] = useState("What is this KB about?");
  const kbs = useQuery({ queryKey: ["kbs"], queryFn: listKbs, enabled: Boolean(token && api) });
  const searchMut = useMutation({ mutationFn: () => searchKb(kbId, q) });
  const queryMut = useMutation({ mutationFn: () => queryKb(kbId, question) });

  if (!api || !token) {
    return (
      <div className="text-slate-400 text-sm">
        Set <code className="text-emerald-400">VITE_API_URL</code> and{" "}
        <code className="text-emerald-400">VITE_JWT_TOKEN</code> in <code>.env.local</code> for live calls.
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-xl">
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
          className="rounded bg-slate-700 px-3 py-2 text-sm text-white hover:bg-slate-600"
          onClick={() => queryMut.mutate()}
          disabled={!kbId}
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
          className="mt-1 block w-full rounded border border-slate-700 bg-slate-900 px-3 py-2"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
      </label>
      <pre className="rounded-lg bg-slate-900 p-3 text-xs overflow-auto text-slate-300">
        {searchMut.isPending || queryMut.isPending
          ? "Loading…"
          : JSON.stringify(
              { search: searchMut.data ?? null, query: queryMut.data ?? null },
              null,
              2,
            )}
      </pre>
    </div>
  );
}
