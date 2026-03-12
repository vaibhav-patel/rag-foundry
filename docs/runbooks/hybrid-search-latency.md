# Runbook: Hybrid search (BM25 + kNN) — latency trade-offs

## What hybrid does

`/v1/kbs/{kbId}/search` with **`hybrid: true`** runs a **`bool`** query whose **`should`** clauses include:

1. **`multi_match`** on **`chunk_text`** (Lexical BM25-style scoring via the inverted index.)
2. **`knn`** on **`embedding`** (approximate nearest neighbors over the vector index.)

Each clause carries a **`boost`** equal to the request **`bm25_weight`** and **`vector_weight`** so the combined **`_score`** is a simple **weighted additive** contribution from clauses that matched (Lucene **`bool`** `should` sum semantics).

## Latency characteristics

| Cost driver | Typical effect |
|-------------|----------------|
| **`multi_match`** | Extra inverted-index work vs dense-only; usually modest compared to **`k`**-NN graph traversal at large corpora. |
| **`knn`** with **`k`** | Recall/latency trade-off: larger **`k`** inside the **`knn`** clause considers more neighbors before **`size`** truncation — often the dominant CPU cost under load. |
| **Two retrieval paths in one round trip** | You pay for **both** lexical and vector evaluation vs a single-vector query; AoSS/OpenSearch concurrency and OCUs matter (see **`opensearch-throttling.md`**). |
| **`min_score`** | Post-filter by score reduces returned hits **after** scoring; rarely reduces planner work upstream. |

## Operational guidance

- Start with **`bm25_weight` = **`vector_weight` = 1.0`; tune when you see lexical-only drift (keywords) vs semantic drift (paraphrases).
- For **budget-constrained P99**, prefer **`SEARCH_MODE`** dense-only paths or **`hybrid: false`** while keeping **`hybrid`** for quality-sensitive routes.
- If latency spikes correlate with **`hybrid: true`** traffic: lower **`k`**, temporarily reduce **`vector_weight`**, or shard traffic (separate replicas / capacity).
- **`_score` interpretability**: additive boosted **`should`** is a **baseline** scorer; swapping to **`dis_max`**, reciprocal rank fusion (RRF), or staged rerank pipelines is possible later — expect different latency profiles.
