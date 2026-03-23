import type { KeyboardEvent } from "react";
import type { DenseSearchHit } from "../api/payloads";
import { highlightSnippet } from "../lib/highlightQuery";

const MAX_QUESTION_CHARS = 2000;

export type SearchResultsPanelProps = {
  hits: DenseSearchHit[];
  query: string;
  status: "idle" | "pending" | "success" | "error";
  total?: number | null;
  backend?: string | null;
  errorMessage?: string | null;
  /** Called when the user chooses a hit to prefills the Playground question. */
  onSendToQuery: (suggestedQuestion: string) => void;
};

function listNavigateActions(e: KeyboardEvent<HTMLUListElement>) {
  if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
  e.preventDefault();
  const buttons = [...e.currentTarget.querySelectorAll<HTMLButtonElement>("button[data-send-to-query]")];
  if (buttons.length === 0) return;
  const active = document.activeElement;
  let idx = buttons.findIndex((b) => b === active);
  if (idx === -1) {
    buttons[e.key === "ArrowDown" ? 0 : buttons.length - 1]?.focus();
    return;
  }
  const nextIdx =
    e.key === "ArrowDown" ? Math.min(idx + 1, buttons.length - 1) : Math.max(idx - 1, 0);
  buttons[nextIdx]?.focus();
}

export function SearchResultsPanel(props: SearchResultsPanelProps) {
  const { hits, query, status, total, backend, errorMessage, onSendToQuery } = props;

  const liveMsg =
    status === "pending"
      ? "Search in progress."
      : status === "error"
        ? `Search failed.${errorMessage ? ` ${errorMessage}` : ""}`
        : status === "success"
          ? hits.length === 0
            ? "No search hits returned."
            : `${hits.length} search hit${hits.length === 1 ? "" : "s"} returned.`
          : "Run Search to fetch hits from this knowledge base.";

  const sendSnippet = (text: string) => {
    const t = text.trim();
    const body = (t.slice(0, MAX_QUESTION_CHARS) || t).slice(0, MAX_QUESTION_CHARS);
    onSendToQuery(body);
  };

  return (
    <section
      className="rounded-lg border border-slate-800 bg-slate-900/35 p-4"
      aria-labelledby="search-results-title"
      aria-busy={status === "pending"}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="search-results-title" className="text-sm font-medium text-slate-200">
          Search results
        </h2>
        {backend ? (
          <span className="text-xs text-slate-500" title="dense search backend identifier">
            {backend}
          </span>
        ) : null}
      </div>

      <p role="status" aria-live="polite" aria-atomic="true" className="sr-only">
        {liveMsg}
      </p>

      {status === "error" && (
        <p className="mt-2 text-sm text-red-400" role="alert">
          {errorMessage ?? "Search request failed"}
        </p>
      )}

      {status === "pending" && (
        <p className="mt-2 text-sm text-slate-400" aria-hidden="false">
          Loading hits…
        </p>
      )}

      {status === "success" && (
        <>
          <p id="search-results-summary" className="mt-2 text-xs text-slate-500">
            {hits.length === 0
              ? "No hits yet — widen the query or ingest more documents."
              : `Showing ${hits.length}${total != null && total > hits.length ? ` of ${total}` : ""}`}
          </p>
          {hits.length > 0 ? (
            <ul
              className="mt-4 space-y-3"
              aria-labelledby="search-results-title"
              aria-describedby="search-results-summary"
              aria-label={`${hits.length === 1 ? "1 hit" : `${hits.length} hits`}`}
              onKeyDown={listNavigateActions}
            >
              {hits.map((hit, idx) => {
                const scoreId = `hit-score-${hit.id}-${idx}`;
                const snippetId = `hit-snippet-${hit.id}-${idx}`;
                const sendId = `hit-send-${hit.id}-${idx}`;
                return (
                  <li key={`${hit.id}-${idx}`} data-hit-item>
                    <article
                      className="rounded border border-slate-800 bg-slate-950/45 p-3"
                      aria-labelledby={scoreId}
                      aria-describedby={snippetId}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                        <span id={scoreId} className="text-xs font-medium text-emerald-400/95">
                          score {hit.score.toFixed(hit.score >= 100 ? 0 : 4)}
                        </span>
                        <button
                          type="button"
                          id={sendId}
                          data-send-to-query
                          className="rounded bg-sky-900/70 px-2 py-1 text-xs text-sky-100 hover:bg-sky-800 "
                          aria-label={`Send hit ${idx + 1} text to playground question`}
                          onClick={() => sendSnippet(hit.text)}
                        >
                          Send to query
                        </button>
                      </div>
                      <div
                        id={snippetId}
                        className="text-sm leading-relaxed text-slate-300 line-clamp-6"
                        aria-label="Matched chunk snippet"
                      >
                        {highlightSnippet(hit.text, query, `${hit.id}-${idx}`)}
                      </div>
                    </article>
                  </li>
                );
              })}
            </ul>
          ) : null}
        </>
      )}

      {status === "idle" && (
        <p className="mt-3 text-sm text-slate-500">Run <strong className="text-slate-400">Search</strong> to populate this panel.</p>
      )}
    </section>
  );
}
