import type { components, paths } from "./types";

export type KnowledgeBaseCreate = components["schemas"]["KnowledgeBaseCreate"];
export type KnowledgeBasePatch = components["schemas"]["KnowledgeBasePatch"];
export type KnowledgeBase = components["schemas"]["KnowledgeBase"];
export type KnowledgeBaseMutation = components["schemas"]["knowledge-base-mutation.schema"];
export type DenseSearchRequest = components["schemas"]["DenseSearchRequest"];
export type RagQueryRequest = components["schemas"]["RagQueryRequest"];
export type DenseSearchResponse = components["schemas"]["DenseSearchResponse"];
export type RagQueryResponse = components["schemas"]["RagQueryResponse"];

export type StartIngestJobBody = NonNullable<
  NonNullable<paths["/v1/kbs/{kbId}/jobs"]["post"]["requestBody"]>["content"]["application/json"]
>;

/** Defaults match OpenAPI schema defaults (openapi-typescript marks defaulted fields as required). */
export function denseSearchBody(overrides: Partial<DenseSearchRequest> = {}): DenseSearchRequest {
  return {
    hybrid: false,
    bm25_weight: 1,
    vector_weight: 1,
    k: 5,
    ...overrides,
  };
}

export function ragQueryBody(question: string, overrides: Partial<RagQueryRequest> = {}): RagQueryRequest {
  return {
    ...denseSearchBody(),
    question,
    context_k: 8,
    guardrails_version: "DRAFT",
    ...overrides,
  };
}
