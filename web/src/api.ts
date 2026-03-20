const base = import.meta.env.VITE_API_URL ?? "";
const token = import.meta.env.VITE_JWT_TOKEN ?? "";

/** Narrow client shape until OpenAPI documents GET /v1/kbs 200 body. */
export type KnowledgeBaseListJson = { items: { id: string; name: string }[] };

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
  if (!r.ok) throw new Error(`kbs ${r.status}`);
  return r.json();
}
