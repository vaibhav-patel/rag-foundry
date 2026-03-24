/** Non-OK HTTP response from `/v1/kbs/{id}/query`, or downstream failure surfaced to UI. */
export class RagQueryHttpError extends Error {
  readonly status: number;
  readonly bodySnippet: string;

  constructor(status: number, bodySnippet: string) {
    super(status > 0 ? `RAG query failed (${status})` : bodySnippet.slice(0, 200));
    this.name = "RagQueryHttpError";
    this.status = status;
    this.bodySnippet = bodySnippet;
  }
}
