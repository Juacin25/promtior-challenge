from math import sqrt
from unittest.mock import Mock

import pytest

from app.cache.semantic_cache import (
    SIMILARITY_THRESHOLD,
    SemanticCache,
    is_cacheable,
)


def test_static_capacity_query_can_be_stored_and_retrieved():
    query = "What is room B's capacity?"
    answer = "Room B holds 2 people."
    embedder = Mock()
    embedder.embed_query.return_value = [1.0, 0.0]
    cache = SemanticCache(embedder)

    cache.set(query, answer)

    assert is_cacheable(query) is True
    assert cache.get(query) == answer
    assert len(cache) == 1


def test_semantically_similar_static_phrasing_hits():
    embedder = Mock()
    embedder.embed_query.side_effect = [[1.0, 0.0], [0.99, 0.01]]
    cache = SemanticCache(embedder)
    cache.set("What is room B's capacity?", "Room B holds 2 people.")

    result = cache.get("How many people fit in room B?")

    assert result == "Room B holds 2 people."


def test_semantically_distant_static_query_misses():
    embedder = Mock()
    embedder.embed_query.side_effect = [[1.0, 0.0], [0.0, 1.0]]
    cache = SemanticCache(embedder)
    cache.set("What is room B's capacity?", "Room B holds 2 people.")

    result = cache.get("Which meeting rooms exist?")

    assert is_cacheable("Which meeting rooms exist?") is True
    assert result is None


@pytest.mark.parametrize(
    "query",
    [
        "Is room C free tomorrow at 10?",
        "What are my bookings?",
        "What's D's schedule?",
        "Which rooms are available?",
        "Show me the occupied slots in room A.",
    ],
)
def test_state_dependent_queries_always_bypass(query):
    embedder = Mock()
    cache = SemanticCache(embedder)

    cache.set(query, "This stale answer must never be stored.")

    assert is_cacheable(query) is False
    assert cache.get(query) is None
    assert len(cache) == 0
    embedder.embed_query.assert_not_called()


def test_unrecognized_query_bypasses_cache_by_default():
    embedder = Mock()
    cache = SemanticCache(embedder)

    cache.set("Tell me a joke.", "No.")

    assert is_cacheable("Tell me a joke.") is False
    assert cache.get("Tell me a joke.") is None
    assert len(cache) == 0
    embedder.embed_query.assert_not_called()


def test_similarity_just_below_threshold_misses():
    below_threshold = SIMILARITY_THRESHOLD - 0.001
    embedder = Mock()
    embedder.embed_query.side_effect = [
        [1.0, 0.0],
        [below_threshold, sqrt(1 - below_threshold**2)],
    ]
    cache = SemanticCache(embedder)
    cache.set("What is room B's capacity?", "Room B holds 2 people.")

    result = cache.get("How many people fit in room B?")

    assert result is None
