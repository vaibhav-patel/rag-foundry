# Changelog

## 0.2.0 — 2026-03-26

- Add OpenAPI-aligned dataclasses: `DenseSearchHit`, `DenseSearchResponse`, `RagCitation`, `RagQueryResponse`.
- Add `ControlPlaneClient.search_kb` and `ControlPlaneClient.query_kb` returning those models (`ResponseShapeError` on unexpected JSON shape).
- `search` / `query` unchanged (still return decoded JSON objects).
