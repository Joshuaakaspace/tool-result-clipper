from __future__ import annotations

_ENC = None


def _get_encoder():
    global _ENC
    if _ENC is not None:
        return _ENC
    try:
        import tiktoken

        _ENC = tiktoken.get_encoding("cl100k_base")
    except Exception:
        _ENC = False
    return _ENC


def count_tokens(text: str) -> int:
    """Return an approximate token count for text.

    Uses tiktoken cl100k_base when available. Falls back to a
    whitespace and punctuation heuristic otherwise (roughly 1 token per
    4 characters, which matches OpenAI's public guidance for English).
    """
    enc = _get_encoder()
    if enc:
        return len(enc.encode(text))
    if not text:
        return 0
    return max(1, len(text) // 4)


def encode(text: str) -> list[int]:
    enc = _get_encoder()
    if enc:
        return enc.encode(text)
    return list(text.encode("utf-8"))


def decode(tokens: list[int]) -> str:
    enc = _get_encoder()
    if enc:
        return enc.decode(tokens)
    return bytes(tokens).decode("utf-8", errors="replace")
