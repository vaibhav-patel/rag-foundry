import type { ReactNode } from "react";

function escapeRegExp(segment: string): string {
  return segment.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Tokenize query for highlighting (drops very short tokens to avoid noisy marks). */
export function queryTokensForHighlight(raw: string, minLen = 2): string[] {
  const uniq = new Set<string>();
  for (const m of raw.toLowerCase().match(/\w+/g) ?? []) {
    if (m.length >= minLen) uniq.add(m);
  }
  return [...uniq];
}

/**
 * Highlights whole-word matches from the search query inside `text` using `<mark>`.
 * `reactKeySalt` avoids duplicate React keys when the same substring repeats.
 */
export function highlightSnippet(text: string, queryRaw: string, reactKeySalt = ""): ReactNode {
  const tokens = queryTokensForHighlight(queryRaw);
  if (tokens.length === 0) return text;

  const prefix = reactKeySalt ? `${reactKeySalt}-` : "";
  const inner = tokens.map((t) => escapeRegExp(t)).join("|");
  const re = new RegExp(`\\b(?:${inner})\\b`, "gi");
  const out: ReactNode[] = [];
  let last = 0;
  let markSeq = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const slice = m[0];
    markSeq += 1;
    out.push(<mark key={`${prefix}${m.index}-${markSeq}-${slice}`}>{slice}</mark>);
    last = m.index + slice.length;
    if (m.index === re.lastIndex) re.lastIndex += 1;
  }
  out.push(text.slice(last));
  return out;
}
