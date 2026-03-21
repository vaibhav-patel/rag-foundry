import type { KnowledgeBase, KnowledgeBaseMutation, StartIngestJobBody } from "./api/payloads";

const base = import.meta.env.VITE_API_URL ?? "";
const token = import.meta.env.VITE_JWT_TOKEN ?? "";

/** Narrow client shape until OpenAPI documents GET /v1/kbs 200 body. */
export type KnowledgeBaseListJson = { items: { id: string; name: string }[] };

export type ApiErrorBody = {
  title: string;
  detail: string;
  schema_errors?: { message: string }[];
};

export class ControlPlaneHttpError extends Error {
  readonly status: number;
  readonly body: ApiErrorBody | null;

  constructor(status: number, body: ApiErrorBody | null) {
    super(body?.detail ?? `HTTP ${status}`);
    this.name = "ControlPlaneHttpError";
    this.status = status;
    this.body = body;
  }

  static is(e: unknown): e is ControlPlaneHttpError {
    return e instanceof ControlPlaneHttpError;
  }
}

function jsonHeaders(): HeadersInit {
  return { ...authHeaders(), "Content-Type": "application/json" };
}

async function readJsonResponse<T>(res: Response): Promise<T> {
  const text = await res.text();
  let data: unknown;
  try {
    data = text.length > 0 ? JSON.parse(text) : null;
  } catch {
    throw new ControlPlaneHttpError(res.status, {
      title: "Bad Response",
      detail: "Server returned non-JSON body",
    });
  }
  if (!res.ok) {
    const err =
      data && typeof data === "object" && "title" in data && "detail" in data
        ? (data as ApiErrorBody)
        : null;
    throw new ControlPlaneHttpError(res.status, err);
  }
  return data as T;
}

export function authHeaders(): HeadersInit {
  const h: Record<string, string> = {};
  if (token) h.Authorization = `Bearer ${token}`;
  return h;
}

export async function fetchHealth(): Promise<unknown> {
  const r = await fetch(`${base}/v1/health`);
  if (!r.ok) throw new Error(`health ${r.status}`);
  return r.json();
}

export async function fetchKnowledgeBaseList(): Promise<KnowledgeBaseListJson> {
  const r = await fetch(`${base}/v1/kbs`, { headers: authHeaders() });
  return readJsonResponse<KnowledgeBaseListJson>(r);
}

export async function fetchKnowledgeBase(kbId: string): Promise<KnowledgeBase> {
  const r = await fetch(`${base}/v1/kbs/${encodeURIComponent(kbId)}`, { headers: authHeaders() });
  return readJsonResponse<KnowledgeBase>(r);
}

export async function createKnowledgeBaseApi(
  body: KnowledgeBaseMutation,
): Promise<{ id: string; tenant_id: string }> {
  const r = await fetch(`${base}/v1/kbs`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  return readJsonResponse<{ id: string; tenant_id: string }>(r);
}

export async function patchKnowledgeBaseApi(
  kbId: string,
  body: KnowledgeBaseMutation,
): Promise<KnowledgeBase> {
  const r = await fetch(`${base}/v1/kbs/${encodeURIComponent(kbId)}`, {
    method: "PATCH",
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  return readJsonResponse<KnowledgeBase>(r);
}

export async function startIngestJobApi(kbId: string, body: StartIngestJobBody): Promise<unknown> {
  const r = await fetch(`${base}/v1/kbs/${encodeURIComponent(kbId)}/jobs`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  return readJsonResponse<unknown>(r);
}
