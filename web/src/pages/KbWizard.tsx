import { useMutation, useQuery } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";
import {
  ControlPlaneHttpError,
  createKnowledgeBaseApi,
  fetchHealth,
  fetchKnowledgeBase,
  patchKnowledgeBaseApi,
  startIngestJobApi,
} from "../api";
import type { KnowledgeBase, KnowledgeBaseMutation } from "../api/payloads";
import { validateKbMutation, validateKbPatch } from "../api/kb-mutation-validate";
import type { StartIngestJobBody } from "../api/payloads";
import { JobTimeline } from "../components/JobTimeline";

const api = import.meta.env.VITE_API_URL ?? "";
const token = import.meta.env.VITE_JWT_TOKEN ?? "";

type KbFormFields = {
  name: string;
  embeddingModelId: string;
  chunkChars: string;
  includeHybridDefault: boolean;
  hybridDefault: boolean;
  generationModelId: string;
  bedrockGuardrailId: string;
  bedrockGuardrailVersion: string;
};

const emptyForm = (): KbFormFields => ({
  name: "",
  embeddingModelId: "",
  chunkChars: "",
  includeHybridDefault: false,
  hybridDefault: false,
  generationModelId: "",
  bedrockGuardrailId: "",
  bedrockGuardrailVersion: "",
});

function kbFieldsToMutation(f: KbFormFields): Record<string, unknown> {
  const o: Record<string, unknown> = {};
  const nt = f.name.trim();
  if (nt) o.name = nt;
  const em = f.embeddingModelId.trim();
  if (em) o.embedding_model_id = em;
  const cc = f.chunkChars.trim();
  if (cc.length > 0) o.chunk_chars = Number(cc);
  if (f.includeHybridDefault) o.hybrid = f.hybridDefault;
  const gm = f.generationModelId.trim();
  if (gm.length > 0) o.generation_model_id = gm;
  const gid = f.bedrockGuardrailId.trim();
  const gv = f.bedrockGuardrailVersion.trim();
  if (gid) {
    o.bedrock_guardrail_id = gid;
    if (gv) o.bedrock_guardrail_version = gv;
  }
  return o;
}

/** PATCH payload: always includes core fields plus explicit clears (empty strings). */
function editFormToPatch(f: KbFormFields, loaded: KnowledgeBase): Record<string, unknown> {
  const o: Record<string, unknown> = {
    name: f.name.trim() || loaded.name,
    embedding_model_id: f.embeddingModelId.trim() || loaded.embedding_model_id,
    generation_model_id: f.generationModelId.trim(),
    bedrock_guardrail_id: f.bedrockGuardrailId.trim(),
    bedrock_guardrail_version: f.bedrockGuardrailVersion.trim(),
  };
  const cc = f.chunkChars.trim();
  if (cc.length > 0) o.chunk_chars = Number(cc);
  if (f.includeHybridDefault) o.hybrid = f.hybridDefault;
  return o;
}

function kbRecordToForm(k: KnowledgeBase): KbFormFields {
  return {
    name: k.name ?? "",
    embeddingModelId: k.embedding_model_id ?? "",
    chunkChars: k.chunk_chars != null ? String(k.chunk_chars) : "",
    includeHybridDefault: typeof k.hybrid === "boolean",
    hybridDefault: k.hybrid === true,
    generationModelId: k.generation_model_id ?? "",
    bedrockGuardrailId: k.bedrock_guardrail_id ?? "",
    bedrockGuardrailVersion: k.bedrock_guardrail_version ?? "",
  };
}

function ServerError({ err }: { err: unknown }) {
  if (!ControlPlaneHttpError.is(err)) {
    return <p className="text-xs text-red-400">{String(err)}</p>;
  }
  const b = err.body;
  return (
    <div className="text-xs text-red-300 space-y-1 rounded border border-red-900/50 bg-red-950/30 p-2">
      <p>
        <span className="font-medium text-red-200">{b?.title ?? "Error"}</span>
        {": "}
        {b?.detail ?? err.message}
      </p>
      {b?.schema_errors?.length ? (
        <ul className="list-disc pl-4 text-red-400/90">
          {b.schema_errors.map((s, i) => (
            <li key={i}>{s.message}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function ClientErrors({ messages }: { messages: string[] }) {
  if (!messages.length) return null;
  return (
    <ul className="text-xs text-amber-300 list-disc pl-4 space-y-0.5">
      {messages.map((m, i) => (
        <li key={i}>{m}</li>
      ))}
    </ul>
  );
}

function KbAdvancedFields({
  f,
  set,
}: {
  f: KbFormFields;
  set: (p: Partial<KbFormFields>) => void;
}) {
  return (
    <>
      <label className="block text-xs text-slate-400">
        Default chunk_chars (ingest jobs)
        <input
          className="mt-1 block w-full max-w-md rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
          value={f.chunkChars}
          onChange={(e) => set({ chunkChars: e.target.value })}
          placeholder="1200 (256–65536 when set)"
          inputMode="numeric"
        />
      </label>
      <label className="flex items-center gap-2 text-xs text-slate-400">
        <input
          type="checkbox"
          checked={f.includeHybridDefault}
          onChange={(e) => set({ includeHybridDefault: e.target.checked })}
        />
        Store default hybrid flag on KB
      </label>
      {f.includeHybridDefault ? (
        <label className="flex items-center gap-2 text-xs text-slate-400 pl-6">
          <input
            type="checkbox"
            checked={f.hybridDefault}
            onChange={(e) => set({ hybridDefault: e.target.checked })}
          />
          Hybrid default (true = hybrid-capable default)
        </label>
      ) : null}
      <label className="block text-xs text-slate-400">
        Default generation_model_id (RAG)
        <input
          className="mt-1 block w-full max-w-md rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
          value={f.generationModelId}
          onChange={(e) => set({ generationModelId: e.target.value })}
          placeholder="anthropic.claude-3-5-sonnet-20240620-v1:0"
        />
      </label>
      <label className="block text-xs text-slate-400">
        bedrock_guardrail_id
        <input
          className="mt-1 block w-full max-w-md rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
          value={f.bedrockGuardrailId}
          onChange={(e) => set({ bedrockGuardrailId: e.target.value })}
        />
      </label>
      <label className="block text-xs text-slate-400">
        bedrock_guardrail_version
        <input
          className="mt-1 block w-full max-w-md rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
          value={f.bedrockGuardrailVersion}
          onChange={(e) => set({ bedrockGuardrailVersion: e.target.value })}
          placeholder="DRAFT"
        />
      </label>
    </>
  );
}

export function KbWizard() {
  const q = useQuery({ queryKey: ["health"], queryFn: fetchHealth });

  const [createForm, setCreateForm] = useState<KbFormFields>(() => emptyForm());
  const [createClientErr, setCreateClientErr] = useState<string[]>([]);

  const [editKbId, setEditKbId] = useState("");
  const [editForm, setEditForm] = useState<KbFormFields>(() => emptyForm());
  const [editLoaded, setEditLoaded] = useState<KnowledgeBase | null>(null);
  const [editClientErr, setEditClientErr] = useState<string[]>([]);

  const [jobKbId, setJobKbId] = useState("");
  const [s3Key, setS3Key] = useState("");
  const [jobEmbeddingId, setJobEmbeddingId] = useState("");
  const [chunkChars, setChunkChars] = useState("");

  const setCreate = useCallback((p: Partial<KbFormFields>) => {
    setCreateForm((s) => ({ ...s, ...p }));
  }, []);
  const setEdit = useCallback((p: Partial<KbFormFields>) => {
    setEditForm((s) => ({ ...s, ...p }));
  }, []);

  const createMut = useMutation({
    mutationFn: (body: KnowledgeBaseMutation) => createKnowledgeBaseApi(body),
    retry: false,
  });

  const patchMut = useMutation({
    mutationFn: ({ kbId, body }: { kbId: string; body: KnowledgeBaseMutation }) =>
      patchKnowledgeBaseApi(kbId, body),
    retry: false,
  });

  const jobMut = useMutation({
    mutationFn: ({ kbId, body }: { kbId: string; body: StartIngestJobBody }) => startIngestJobApi(kbId, body),
    retry: false,
  });

  const loadEditMut = useMutation({
    mutationFn: (kbId: string) => fetchKnowledgeBase(kbId),
    retry: false,
    onSuccess: (data) => {
      setEditLoaded(data);
      setEditForm(kbRecordToForm(data));
      setEditClientErr([]);
    },
  });

  const lastCreateId = useRef<string | null>(null);

  const onCreate = () => {
    setCreateClientErr([]);
    const raw = kbFieldsToMutation(createForm);
    const v = validateKbMutation(raw);
    if (!v.ok) {
      setCreateClientErr(v.errors);
      return;
    }
    createMut.mutate(v.value, {
      onSuccess: (res) => {
        lastCreateId.current = res.id;
        setCreateForm(emptyForm());
      },
    });
  };

  const onSaveEdit = () => {
    if (!editLoaded) return;
    setEditClientErr([]);
    const raw = editFormToPatch(editForm, editLoaded);
    const v = validateKbPatch(raw);
    if (!v.ok) {
      setEditClientErr(v.errors);
      return;
    }
    patchMut.mutate({ kbId: editLoaded.id, body: v.value });
  };

  const credsReady = Boolean(api && token);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-medium">Knowledge base</h1>
      <p className="text-slate-400 text-sm">
        Create and edit KB defaults (validated client-side against the same JSON Schema as the control
        plane). API health:
      </p>
      <pre className="rounded-lg bg-slate-900 p-4 text-sm overflow-auto">
        {q.isLoading ? "Loading…" : q.isError ? String(q.error) : JSON.stringify(q.data, null, 2)}
      </pre>

      {!credsReady ? (
        <p className="text-slate-400 text-sm">
          Set <code className="text-emerald-400">VITE_API_URL</code> and{" "}
          <code className="text-emerald-400">VITE_JWT_TOKEN</code> in <code>.env.local</code> for KB and job
          calls.
        </p>
      ) : (
        <>
          <section className="space-y-3 rounded-lg border border-slate-800 bg-slate-900/40 p-4">
            <h2 className="text-sm font-medium text-slate-300">Create knowledge base</h2>
            <p className="text-xs text-slate-500">
              Leave name unset to let the API default to <code className="text-slate-400">kb</code>.
            </p>
            <label className="block text-xs text-slate-400">
              Name
              <input
                className="mt-1 block w-full max-w-md rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
                value={createForm.name}
                onChange={(e) => setCreate({ name: e.target.value })}
                placeholder="orders-docs"
              />
            </label>
            <label className="block text-xs text-slate-400">
              embedding_model_id
              <input
                className="mt-1 block w-full max-w-md rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
                value={createForm.embeddingModelId}
                onChange={(e) => setCreate({ embeddingModelId: e.target.value })}
                placeholder="amazon.titan-embed-text-v1 (optional; server default if empty)"
              />
            </label>
            <KbAdvancedFields f={createForm} set={setCreate} />
            <ClientErrors messages={createClientErr} />
            {createMut.isError ? <ServerError err={createMut.error} /> : null}
            <button
              type="button"
              className="rounded bg-emerald-700 px-3 py-2 text-sm text-white hover:bg-emerald-600 disabled:opacity-40"
              disabled={createMut.isPending}
              onClick={onCreate}
            >
              POST /v1/kbs
            </button>
            {createMut.isSuccess && createMut.data ? (
              <p className="text-xs text-emerald-400/90">
                Created KB <code className="text-emerald-300">{createMut.data.id}</code>
              </p>
            ) : null}
          </section>

          <section className="space-y-3 rounded-lg border border-slate-800 bg-slate-900/40 p-4">
            <h2 className="text-sm font-medium text-slate-300">Edit knowledge base</h2>
            <div className="flex flex-wrap gap-2 items-end max-w-xl">
              <label className="block text-xs text-slate-400 flex-1 min-w-[12rem]">
                KB id
                <input
                  className="mt-1 block w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
                  value={editKbId}
                  onChange={(e) => setEditKbId(e.target.value)}
                  placeholder={lastCreateId.current ?? "uuid"}
                />
              </label>
              <button
                type="button"
                className="rounded bg-slate-700 px-3 py-2 text-sm text-white hover:bg-slate-600 disabled:opacity-40"
                disabled={loadEditMut.isPending || !editKbId.trim()}
                onClick={() => loadEditMut.mutate(editKbId.trim())}
              >
                GET /v1/kbs/…
              </button>
            </div>
            {loadEditMut.isError ? <ServerError err={loadEditMut.error} /> : null}
            {editLoaded ? (
              <>
                <label className="block text-xs text-slate-400">
                  Name
                  <input
                    className="mt-1 block w-full max-w-md rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
                    value={editForm.name}
                    onChange={(e) => setEdit({ name: e.target.value })}
                  />
                </label>
                <label className="block text-xs text-slate-400">
                  embedding_model_id
                  <input
                    className="mt-1 block w-full max-w-md rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
                    value={editForm.embeddingModelId}
                    onChange={(e) => setEdit({ embeddingModelId: e.target.value })}
                  />
                </label>
                <KbAdvancedFields f={editForm} set={setEdit} />
                <p className="text-xs text-slate-500">
                  Clear default generation model by saving with an empty generation field; clear guardrails
                  by clearing guardrail id and saving.
                </p>
                <ClientErrors messages={editClientErr} />
                {patchMut.isError ? <ServerError err={patchMut.error} /> : null}
                <button
                  type="button"
                  className="rounded bg-emerald-700/90 px-3 py-2 text-sm text-white hover:bg-emerald-600 disabled:opacity-40"
                  disabled={patchMut.isPending}
                  onClick={onSaveEdit}
                >
                  PATCH /v1/kbs/…
                </button>
                {patchMut.isSuccess && patchMut.data ? (
                  <pre className="rounded bg-slate-950 p-3 text-xs overflow-auto text-slate-300">
                    {JSON.stringify(patchMut.data, null, 2)}
                  </pre>
                ) : null}
              </>
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
              s3_key (required)
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
              chunk_chars (optional; defaults from KB when omitted)
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
              disabled={jobMut.isPending || !jobKbId.trim() || !s3Key.trim()}
              onClick={() =>
                jobMut.mutate({
                  kbId: jobKbId.trim(),
                  body: {
                    s3_key: s3Key.trim(),
                    embedding_model_id: jobEmbeddingId.trim() || undefined,
                    chunk_chars: chunkChars.trim() ? Number(chunkChars) : undefined,
                  },
                })
              }
            >
              POST /v1/kbs/…/jobs
            </button>
            {jobMut.isError ? <ServerError err={jobMut.error} /> : null}
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
