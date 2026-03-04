"""Standard chunking strategies (fixed-size tokens approximated by chars, recursive split)."""

from __future__ import annotations


def fixed_char_chunks(text: str, max_chars: int, overlap: int) -> list[str]:
    if max_chars <= 0:
        return []
    if overlap >= max_chars:
        overlap = max(0, max_chars // 4)
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        end = min(n, i + max_chars)
        out.append(text[i:end])
        if end == n:
            break
        i = max(end - overlap, i + 1)
    return out or [""]


def recursive_char_chunks(
    text: str, max_chars: int, separators: tuple[str, ...] = ("\n\n", "\n", ". ", " ")
) -> list[str]:
    """Split on largest separator first, then recurse until pieces fit max_chars."""

    def split_piece(s: str) -> list[str]:
        if len(s) <= max_chars:
            return [s] if s else []
        for sep in separators:
            if sep in s:
                parts = s.split(sep)
                acc: list[str] = []
                for p in parts:
                    acc.extend(split_piece(p.strip()))
                return acc
        return fixed_char_chunks(s, max_chars, overlap=max_chars // 8)

    return split_piece(text.strip()) or [""]
