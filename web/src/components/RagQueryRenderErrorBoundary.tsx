import React, { type ErrorInfo, type ReactNode } from "react";

type Props = {
  children: ReactNode;
  /** Bumps whenever a fresh query completes or is retried — clears a render error without remounting the whole playground. */
  attemptToken: number;
  /** Re-run the `/query` POST (recommended after transient Bedrock / proxy failures). */
  onRetryQuery: () => void;
};

type State = { error: Error | null };

/** Catches synchronous render errors below the streaming / typing answer surface (robust citations, etc.). */
export class RagQueryRenderErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.warn("[RAG query UI render]", error.message, info.componentStack ?? "");
  }

  componentDidUpdate(prevProps: Readonly<Props>): void {
    const { attemptToken } = this.props;
    if (prevProps.attemptToken !== attemptToken && this.state.error) this.setState({ error: null });
  }

  render(): React.ReactNode {
    const { children, onRetryQuery } = this.props;
    const err = this.state.error;
    if (err) {
      return (
        <div
          className="rounded-lg border border-amber-800/70 bg-amber-950/30 p-4 text-sm text-amber-100"
          role="alert"
        >
          <p className="font-medium text-amber-50">Something went wrong while rendering this answer.</p>
          <p className="mt-1 font-mono text-xs text-amber-200/80">{err.message}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              className="rounded bg-amber-800 px-3 py-1.5 text-xs text-white hover:bg-amber-700"
              onClick={() => this.setState({ error: null })}
            >
              Try display again
            </button>
            <button
              type="button"
              className="rounded border border-slate-600 px-3 py-1.5 text-xs text-slate-100 hover:bg-slate-800"
              onClick={() => {
                this.setState({ error: null });
                onRetryQuery();
              }}
            >
              Retry query
            </button>
          </div>
        </div>
      );
    }
    return children;
  }
}
