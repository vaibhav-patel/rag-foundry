import Ajv2020, { type ErrorObject } from "ajv";
import addFormats from "ajv-formats";
import mutationSchema from "@contracts/schemas/knowledge-base-mutation.schema.json";
import type { KnowledgeBaseMutation } from "./payloads";

const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);
const validateMutation = ajv.compile(mutationSchema);

function formatAjvError(err: ErrorObject): string {
  const loc = err.instancePath && err.instancePath.length > 0 ? err.instancePath : "/";
  return `${loc} ${err.message ?? "invalid"}`;
}

export function validateKbMutation(body: unknown): { ok: true; value: KnowledgeBaseMutation } | { ok: false; errors: string[] } {
  if (typeof body !== "object" || body === null || Array.isArray(body)) {
    return { ok: false, errors: ["Request body must be a JSON object"] };
  }
  const data = body as Record<string, unknown>;
  if (validateMutation(data)) {
    return { ok: true, value: data as KnowledgeBaseMutation };
  }
  return {
    ok: false,
    errors: (validateMutation.errors ?? []).map(formatAjvError),
  };
}

export function validateKbPatch(body: unknown): { ok: true; value: KnowledgeBaseMutation } | { ok: false; errors: string[] } {
  const base = validateKbMutation(body);
  if (!base.ok) return base;
  if (Object.keys(base.value).length === 0) {
    return { ok: false, errors: ["PATCH body must include at least one field"] };
  }
  return base;
}
