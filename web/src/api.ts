const base = import.meta.env.VITE_API_URL ?? "";

export async function fetchHealth(): Promise<unknown> {
  const r = await fetch(`${base}/v1/health`);
  if (!r.ok) throw new Error(`health ${r.status}`);
  return r.json();
}
