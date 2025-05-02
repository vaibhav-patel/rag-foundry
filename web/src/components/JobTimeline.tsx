/** Polling placeholder for ingest jobs (wire to GET /v1/jobs/:id). */
export function JobTimeline(props: { jobId?: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-4 text-sm text-slate-400">
      Job timeline {props.jobId ? `(job ${props.jobId})` : ""}: connect to control-plane job API and Step
      Functions execution ARN in a later pass.
    </div>
  );
}
