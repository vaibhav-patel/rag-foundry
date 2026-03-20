import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { authHeaders, fetchHealth } from "../api";
import type { KnowledgeBaseCreate, StartIngestJobBody } from "../api/payloads";
import { JobTimeline } from "../components/JobTimeline";

const api = import.meta.env.VITE_API_URL ?? "";
const token = import.meta.env.VITE_JWT_TOKEN ?? "";

async function createKnowledgeBase(body: KnowledgeBaseCreate): Promise<unknown> {
  const r = await fetch(`${api}/v1/kbs`, {
    method: "POST",
    headers: {
      ...authHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`create kb ${r.status}`);
  return r.json();
}

async function startIngestJob(kbId: string, body: StartIngestJobBody): Promise<unknown> {
  const r = await fetch(`${api}/v1/kbs/${encodeURIComponent(kbId)}/jobs`, {
    method: "POST",
    headers: {
      ...authHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`start job ${r.status}`);
  return r.json();
}

export function KbWizard() {
  const q = useQuery({ queryKey: ["health"], queryFn: fetchHealth });

  const [name, setName] = useState("");
  const [embeddingModelId, setEmbeddingModelId] = useState("");

  const [jobKbId, setJobKbId] = useState("");
  const [s3Key, setS3Key] = useState("");
  const [jobEmbeddingId, setJobEmbeddingId] = useState("");
  const [chunkChars, setChunkChars] = useState("");

  const createMut = useMutation({
    mutationFn: () => {
      const body: KnowledgeBaseCreate = {
        name: name.trim() || undefined,
        embedding_model_id: embeddingModelId.trim() || undefined,
      };
      return createKnowledgeBase(body);
    },
  });

  const jobMut = useMutation({
    mutationFn: () => {
      const body: StartIngestJobBody = {
        s3_key: s3Key.trim() || undefined,
        embedding_model_id: jobEmbeddingId.trim() || undefined,
        chunk_chars: chunkChars.trim() ? Number(chunkChars) : undefined,
      };
      return startIngestJob(jobKbId.trim(), body);
    },
  });

  const credsReady = Boolean(api && token);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-medium">Knowledge base</h1>
      <p className="text-slate-400 text-sm">
        Chunking / embedding / retrieval forms ship incrementally. API health:
      </p>
      <pre className="rounded-lg bg-slate-900 p-4 text-sm overflow-auto">
        {q.isLoading ? "Loading…" : q.isError ? String(q.error) : JSON.stringify(q.data, null, 2)}
      </pre>

      {!credsReady ? (
        <p className="text-slate-400 text-sm">
          Set <code className="text-emerald-400">VITE_API_URL</code> and{" "}
          <code className="text-emerald-400">VITE_JWT_TOKEN</code> in <code>.env.local</code> to create KBs and
          jobs.
        </p>
      ) : (
        <>
          <section className="space-y-3 rounded-lg border border-slate-800 bg-slate-900/40 p-4">
            <h2 className="text-sm font-medium text-slate-300">Create knowledge base</h2>
            <label className="block text-xs text-slate-400">
              Name
              <input
                className="mt-1 block w-full max-w-md rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="orders-docs"
              />
            </label>
            <label className="block text-xs text-slate-400">
              Default embedding model id (optional)
              <input
                className="mt-1 block w-full max-w-md rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
                value={embeddingModelId}
                onChange={(e) => setEmbeddingModelId(e.target.value)}
                placeholder="amazon.titan-embed-text-v1"
              />
            </label>
            <button
              type="button"
              className="rounded bg-emerald-700 px-3 py-2 text-sm text-white hover:bg-emerald-600 disabled:opacity-40"
              disabled={createMut.isPending}
              onClick={() => createMut.mutate()}
            >
              POST /v1/kbs
            </button>
            {createMut.isError ? (
              <p className="text-xs text-red-400">{String(createMut.error)}</p>
            ) : null}
            {createMut.data ? (
              <pre className="rounded bg-slate-950 p-3 text-xs overflow-auto text-slate-300">
                {JSON.stringify(createMut.data, null, 2)}
              </pre>
            ) : null}
          </section>

          <section className="space-y-3 rounded-lg border border-slate-800 bg-slate-900/40 p-4">
            <h2 className="text-sm font-medium text-slate-300">Start ingest job</h2>
            <label className="block text-xs text-slate-400">
              KB id
              <input
                className="mt-1 block w-full max-w-md rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
                value={jobKbId}
                onChange={(e) => setJobKbId(e.target.value)}
              />
            </label>
            <label className="block text-xs text-slate-400">
              s3_key (optional)
              <input
                className="mt-1 block w-full max-w-md rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
                value={s3Key}
                onChange={(e) => setS3Key(e.target.value)}
              />
            </label>
            <label className="block text-xs text-slate-400">
              embedding_model_id (optional)
              <input
                className="mt-1 block w-full max-w-md rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
                value={jobEmbeddingId}
                onChange={(e) => setJobEmbeddingId(e.target.value)}
              />
            </label>
            <label className="block text-xs text-slate-400">
              chunk_chars (optional)
              <input
                className="mt-1 block w-full max-w-md rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
                value={chunkChars}
                onChange={(e) => setChunkChars(e.target.value)}
                inputMode="numeric"
              />
            </label>
            <button
              type="button"
              className="rounded bg-slate-600 px-3 py-2 text-sm text-white hover:bg-slate-500 disabled:opacity-40"
              disabled={jobMut.isPending || !jobKbId.trim()}
              onClick={() => jobMut.mutate()}
            >
              POST /v1/kbs/…/jobs
            </button>
            {jobMut.isError ? <p className="text-xs text-red-400">{String(jobMut.error)}</p> : null}
            {jobMut.data ? (
              <pre className="rounded bg-slate-950 p-3 text-xs overflow-auto text-slate-300">
                {JSON.stringify(jobMut.data, null, 2)}
              </pre>
            ) : null}
          </section>
        </>
      )}

      <section>
        <h2 className="text-sm font-medium text-slate-300 mb-2">Ingest job</h2>
        <JobTimeline />
      </section>
    </div>
  );
}
