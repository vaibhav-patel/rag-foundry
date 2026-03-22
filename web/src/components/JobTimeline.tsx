import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { ControlPlaneHttpError, fetchJobManifestPresign, fetchJobPoll } from "../api";
import type { JobPollResponse } from "../api/payloads";

export type TimelineJobRef = {
  jobId: string;
  kbId?: string;
};

const TERMINAL = new Set<string>(["SUCCEEDED", "PARTIAL", "FAILED"]);
const INITIAL_DELAY_MS = 1300;
const BACKOFF_FACTOR = 1.65;
const BACKOFF_CAP_MS = 30000;

function statusTone(status: string): string {
  switch (status) {
    case "SUCCEEDED":
      return "text-emerald-400";
    case "PARTIAL":
      return "text-amber-400";
    case "FAILED":
      return "text-red-400";
    case "RUNNING":
      return "text-sky-400";
    default:
      return "text-slate-300";
  }
}

function InlineHttpErr({ label, err }: { label: string; err: unknown }) {
  const msg =
    ControlPlaneHttpError.is(err) && err.body
      ? `${err.body.title}: ${err.body.detail}`
      : String(err);
  return (
    <p className="text-xs text-red-400 mt-2">
      {label}: {msg}
    </p>
  );
}

function JobPollerCard({
  jobRef,
  onRemoveJob,
}: {
  jobRef: TimelineJobRef;
  onRemoveJob?: (jobId: string) => void;
}) {
  const { jobId, kbId } = jobRef;
  const [snapshot, setSnapshot] = useState<JobPollResponse | null>(null);
  const [pollError, setPollError] = useState<unknown>(null);

  const manifestKeyEarly =
    snapshot?.manifest_key !== undefined && snapshot.manifest_key !== null
      ? String(snapshot.manifest_key)
      : "";
  const terminalEarly = snapshot ? TERMINAL.has(snapshot.status) : false;

  const manifestQ = useQuery({
    queryKey: ["manifest", jobId, kbId, manifestKeyEarly, snapshot?.status],
    queryFn: () => fetchJobManifestPresign(jobId, kbId),
    enabled: terminalEarly && Boolean(manifestKeyEarly),
    retry: false,
  });

  useEffect(() => {
    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout> | undefined;
    let delayMs = INITIAL_DELAY_MS;

    function schedule(fn: () => void, ms: number) {
      timeoutId = setTimeout(fn, ms);
    }

    const tick = async () => {
      if (cancelled) return;
      try {
        const j = await fetchJobPoll(jobId, kbId);
        if (cancelled) return;
        setSnapshot(j);
        setPollError(null);
        if (TERMINAL.has(j.status)) return;
      } catch (e) {
        if (!cancelled) setPollError(e);
      }
      if (cancelled) return;
      delayMs = Math.min(Math.round(delayMs * BACKOFF_FACTOR), BACKOFF_CAP_MS);
      schedule(tick, delayMs);
    };

    delayMs = INITIAL_DELAY_MS;
    schedule(tick, 0);
    return () => {
      cancelled = true;
      if (timeoutId !== undefined) clearTimeout(timeoutId);
    };
  }, [jobId, kbId]);

  const manifestKey = manifestKeyEarly;
  const terminal = terminalEarly;
  const emphasizeManifestRow =
    terminal &&
    Boolean(manifestKey) &&
    (snapshot?.status === "PARTIAL" || snapshot?.status === "FAILED");

  return (
    <div
      className={`rounded-lg border p-4 text-sm ${emphasizeManifestRow ? "border-amber-800/70 bg-amber-950/20" : "border-slate-800 bg-slate-900/50"}`}
    >
      <div className="flex flex-wrap justify-between gap-2 items-start">
        <div>
          <div className="font-medium text-slate-200">
            Job <code className="text-xs text-emerald-400/90">{jobId}</code>
            {kbId ? (
              <>
                {" "}
                <span className="text-slate-500 text-xs">
                  KB <code className="text-slate-400">{kbId}</code>
                </span>
              </>
            ) : (
              <span className="text-slate-500 text-xs ml-2">(GSI poll — prefer kb id when known)</span>
            )}
          </div>
          {snapshot ? (
            <p className={`mt-1 ${statusTone(snapshot.status)}`}>{snapshot.status}</p>
          ) : (
            <p className="mt-1 text-slate-500 text-xs">
              Polling GET /v1/jobs/… · backoff capped at {(BACKOFF_CAP_MS / 1000).toFixed(0)}s
            </p>
          )}
        </div>
        {onRemoveJob ? (
          <button
            type="button"
            className="text-xs text-slate-500 hover:text-slate-300"
            onClick={() => onRemoveJob(jobId)}
          >
            Dismiss
          </button>
        ) : null}
      </div>

      {snapshot ? (
        <>
          <dl className="mt-3 grid gap-1 text-xs text-slate-400 sm:grid-cols-2">
            <dt>Chunks</dt>
            <dd className="text-slate-300">{snapshot.chunk_count ?? "—"}</dd>
            <dt>Bulk indexed / failed</dt>
            <dd className="text-slate-300">
              {snapshot.bulk_indexed} / {snapshot.bulk_failed}
            </dd>
            <dt>Manifest key</dt>
            <dd className="text-slate-300 break-all">{snapshot.manifest_key ?? "—"}</dd>
          </dl>
          {snapshot.errors?.length ? (
            <details className="mt-2 text-xs text-red-300/90">
              <summary className="cursor-pointer text-red-400">Errors ({snapshot.errors.length})</summary>
              <pre className="mt-1 overflow-auto text-[11px] text-red-400/90">
                {JSON.stringify(snapshot.errors, null, 2)}
              </pre>
            </details>
          ) : null}
          {emphasizeManifestRow ? (
            <p className="mt-3 text-xs text-amber-200/90">
              This job stopped with failures or bulk errors — inspect the ingest manifest below.
            </p>
          ) : null}
          {terminal && manifestKey ? (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className="text-xs text-slate-500">Manifest</span>
              {manifestQ.isLoading ? (
                <span className="text-xs text-slate-400">Fetching presigned URL…</span>
              ) : manifestQ.data ? (
                <a
                  className="text-xs font-medium text-sky-400 hover:text-sky-300 underline"
                  href={manifestQ.data.manifest_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open manifest ({manifestQ.data.expires_in}s)
                </a>
              ) : null}
              {manifestQ.isError ? <InlineHttpErr label="Manifest URL" err={manifestQ.error} /> : null}
            </div>
          ) : null}
        </>
      ) : null}
      {pollError ? <InlineHttpErr label="Poll" err={pollError} /> : null}
    </div>
  );
}

export function JobTimeline(props: {
  jobs: TimelineJobRef[];
  onRemoveJob?: (jobId: string) => void;
}) {
  const { jobs, onRemoveJob } = props;

  if (jobs.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-slate-700 bg-slate-950/40 px-6 py-8 text-center text-sm text-slate-500">
        No ingest jobs queued for polling. Start a job in the section above — successful submissions
        are appended here automatically.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {jobs.map((j) => (
        <JobPollerCard key={`${j.jobId}:${j.kbId ?? ""}`} jobRef={j} onRemoveJob={onRemoveJob} />
      ))}
    </div>
  );
}
