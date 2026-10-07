"""Simple text chunking — no vector DB required for Phase 6."""

from __future__ import annotations


def chunk_text(
    text: str,
    *,
    max_chars: int = 800,
    overlap: int = 100,
) -> list[str]:
    """
    Split text into overlapping chunks by character budget.

    Prefers paragraph boundaries when possible.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return []

    if len(cleaned) <= max_chars:
        return [cleaned]

    paragraphs = [p.strip() for p in cleaned.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [cleaned]

    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if not current:
            current = para
            continue
        if len(current) + 2 + len(para) <= max_chars:
            current = current + "\n\n" + para
        else:
            chunks.append(current)
            # overlap tail
            if overlap > 0 and len(current) > overlap:
                current = current[-overlap:] + "\n\n" + para
            else:
                current = para

    if current:
        chunks.append(current)

    # hard-split any oversized chunk
    final: list[str] = []
    for ch in chunks:
        if len(ch) <= max_chars:
            final.append(ch)
            continue
        start = 0
        while start < len(ch):
            end = min(start + max_chars, len(ch))
            final.append(ch[start:end])
            if end >= len(ch):
                break
            start = max(end - overlap, start + 1)

    return final


def estimate_tokens(text: str) -> int:
    # rough heuristic ~4 chars per token
    return max(1, len(text) // 4) if text else 0
