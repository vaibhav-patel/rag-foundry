import { useQuery } from "@tanstack/react-query";
import { fetchHealth } from "../api";

export function KbWizard() {
  const q = useQuery({ queryKey: ["health"], queryFn: fetchHealth });
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-medium">Knowledge base</h1>
      <p className="text-slate-400 text-sm">
        Configure chunking, embeddings, and retrieval in later iterations. API health:
      </p>
      <pre className="rounded-lg bg-slate-900 p-4 text-sm overflow-auto">
        {q.isLoading ? "Loading…" : q.isError ? String(q.error) : JSON.stringify(q.data, null, 2)}
      </pre>
    </div>
  );
}
