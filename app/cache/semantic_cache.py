"""In-memory semantic cache for explicitly allowed static room facts."""

import re
from math import sqrt

SIMILARITY_THRESHOLD = 0.92

_STATE_DEPENDENT = re.compile(
    r"\b(available|availability|free|occupied|booking|bookings|booked|"
    r"reservation|reservations|schedule|slots?|today|tomorrow)\b",
    re.IGNORECASE,
)
_ROOM = re.compile(r"\broom\s+[a-e]\b", re.IGNORECASE)
_CAPACITY = re.compile(
    r"\b(capacity|fit|fits|hold|holds|accommodate|accommodates)\b",
    re.IGNORECASE,
)
_ROOM_LIST = re.compile(
    r"(?:\blist\b.*\brooms?\b)|"
    r"(?:\b(?:which|what|show)\b.*\brooms?\b.*\b(?:exist|existing|have)\b)",
    re.IGNORECASE,
)


def is_cacheable(query: str) -> bool:
    """Return whether a query clearly asks for an allowlisted static fact."""
    if _STATE_DEPENDENT.search(query):
        return False
    if _ROOM.search(query) and _CAPACITY.search(query):
        return True
    return _ROOM_LIST.search(query) is not None


class SemanticCache:
    """Process-local semantic cache with an injected embedding provider."""

    def __init__(self, embedder) -> None:
        self._embedder = embedder
        self._entries: dict[str, tuple[list[float], str]] = {}

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, query: str) -> str | None:
        """Return the closest cached static answer above the safe threshold."""
        if not is_cacheable(query):
            return None

        query_embedding = self._embedder.embed_query(query)
        best_similarity = SIMILARITY_THRESHOLD
        best_answer = None
        for cached_embedding, answer in self._entries.values():
            similarity = _cosine_similarity(query_embedding, cached_embedding)
            if similarity > best_similarity:
                best_similarity = similarity
                best_answer = answer
        return best_answer

    def set(self, query: str, answer: str) -> None:
        """Store an answer only when its query is explicitly cacheable."""
        if not is_cacheable(query):
            return
        self._entries[query] = (self._embedder.embed_query(query), answer)


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    dot_product = sum(a * b for a, b in zip(left, right, strict=True))
    left_magnitude = sqrt(sum(value * value for value in left))
    right_magnitude = sqrt(sum(value * value for value in right))
    return dot_product / (left_magnitude * right_magnitude)
