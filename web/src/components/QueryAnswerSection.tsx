import type { RagQueryResponse } from "../api/payloads";
import type { UseRagQueryPlaybackReturn } from "../hooks/useRagQueryPlayback";
import { RagQueryRenderErrorBoundary } from "./RagQueryRenderErrorBoundary";

function CitationUl({ cites }: { cites: RagQueryResponse["citations"] }) {
  if (!Array.isArray(cites) || cites.length === 0) return null;
  return (
    <div className="mt-4">
      <p className="text-xs uppercase tracking-wide text-slate-500">Citations</p>
      <ul className="mt-2 list-none space-y-2 text-sm">
        {cites.map((c, i) => (
          <li key={`${i}-${c.id}`}>
            <code className="rounded bg-slate-900 px-2 py-0.5 text-emerald-300/90">{c.id}</code>
          </li>
        ))}
      </ul>
    </div>
  );
}

type Props = {
  playback: UseRagQueryPlaybackReturn;
};

export function QueryAnswerSection({ playback }: Props) {
  const {
    phase,
    error,
    displayedAnswer,
    fullResponse,
    streamingMode,
    runQuery,
    retry,
    attemptId,
  } = playback;

  const showAnswerRegion = displayedAnswer !== "" || phase === "revealing";

  return (
    <section className="rounded-lg border border-slate-800 bg-slate-900/35 p-4" aria-labelledby="query-answer-title">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="query-answer-title" className="text-sm font-medium text-slate-200">
          Model answer
        </h2>
        {(streamingMode || phase === "revealing") && phase !== "error" ? (
          <span className="text-xs tabular-nums text-slate-500 animate-pulse" aria-live="polite">
            {streamingMode ? "Streaming…" : "Revealing…"}
          </span>
        ) : null}
      </div>

      {phase === "error" && error ? (
        <div
          role="alert"
          className="mt-3 rounded border border-red-900/70 bg-red-950/35 p-3 text-sm text-red-100"
        >
          <p className="font-medium text-red-50">
            {error.status >= 502 && error.status <= 504
              ? "Search service or Bedrock generation is unavailable right now."
              : error.status === 429
                ? "Request rate limited — try again in a moment."
                : error.status >= 400
                  ? `The query request failed (${error.status}).`
                  : "Something went wrong with the query."}
          </p>
          {error.bodySnippet ? (
            <pre className="mt-2 max-h-28 overflow-auto text-xs whitespace-pre-wrap text-red-200/85">
              {error.bodySnippet}
            </pre>
          ) : null}
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              className="rounded bg-red-800 px-3 py-1.5 text-xs text-white hover:bg-red-700"
              onClick={() => retry()}
            >
              Retry query
            </button>
            <button
              type="button"
              className="rounded border border-slate-600 px-3 py-1.5 text-xs text-slate-100 hover:bg-slate-800"
              onClick={() => runQuery()}
            >
              Run again
            </button>
          </div>
        </div>
      ) : null}

      {!showAnswerRegion && phase === "idle" ? (
        <p className="mt-3 text-sm text-slate-500">
          Submit <strong className="text-slate-400">RAG query</strong> to stream or reveal the Bedrock reply. When the API
          returns JSON only, answers use a gradual typing reveal; when responses use{" "}
          <code className="text-emerald-500/95">text/event-stream</code> or NDJSON,
          incremental tokens appear as they arrive.
        </p>
      ) : null}

      {phase === "fetching" ? (
        <p className="mt-3 text-sm text-slate-400">Retrieving passages and invoking the generator…</p>
      ) : null}

      <RagQueryRenderErrorBoundary attemptToken={attemptId} onRetryQuery={() => retry()}>
        {showAnswerRegion && phase !== "error" ? (
          <>
            <article
              className="mt-3 whitespace-pre-wrap rounded border border-slate-800 bg-slate-950/55 p-3 text-base leading-relaxed text-slate-100"
              aria-busy={phase === "revealing"}
            >
              {displayedAnswer}
            </article>
            <p className="sr-only" aria-live="polite">
              {phase === "done" ? "Answer complete." : ""}
            </p>
          </>
        ) : null}

        {(phase === "done" || phase === "revealing") && fullResponse && phase !== "error" ? (
          <CitationUl cites={fullResponse.citations} />
        ) : phase === "done" && fullResponse?.citations?.length === 0 ? (
          <p className="mt-3 text-xs text-slate-600">No chunk citations returned for this answer.</p>
        ) : null}
      </RagQueryRenderErrorBoundary>
    </section>
  );
}
