import { useQuery } from "@tanstack/react-query";
import { fetchHealth } from "../api";
import { JobTimeline } from "../components/JobTimeline";

export function KbWizard() {
  const q = useQuery({ queryKey: ["health"], queryFn: fetchHealth });
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-medium">Knowledge base</h1>
      <p className="text-slate-400 text-sm">
        Chunking / embedding / retrieval forms ship incrementally. API health:
      </p>
      <pre className="rounded-lg bg-slate-900 p-4 text-sm overflow-auto">
        {q.isLoading ? "Loading…" : q.isError ? String(q.error) : JSON.stringify(q.data, null, 2)}
      </pre>
      <section>
        <h2 className="text-sm font-medium text-slate-300 mb-2">Ingest job</h2>
        <JobTimeline />
      </section>
    </div>
  );
}
