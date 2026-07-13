import json

import httpx
import pytest
from proofline.reranking import (
    DeterministicTokenReranker,
    HttpCrossEncoderReranker,
    apply_reranking,
)
from proofline.schemas import SearchHit


def hit(chunk_id: str, content: str, rank: float) -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id,
        source_id=chunk_id,
        source_version_id=f"v-{chunk_id}",
        source_title=chunk_id,
        content=content,
        start_offset=0,
        end_offset=len(content),
        start_line=1,
        end_line=1,
        rank=rank,
    )


def test_deterministic_reranker_reorders_after_rrf_with_diagnostics():
    hits = [
        hit("broad", "Cache operations and general notes", -0.03),
        hit("exact", "Decision: Redis cache eviction uses allkeys-lru", -0.02),
    ]
    reranked = apply_reranking("Redis cache eviction", hits, DeterministicTokenReranker())
    assert [item.chunk_id for item in reranked] == ["exact", "broad"]
    assert reranked[0].rerank_rank == 1
    assert reranked[0].rerank_score > reranked[1].rerank_score
    assert reranked[0].retrieval_channels[-1] == "rerank"


def test_http_cross_encoder_normalizes_indexed_scores_and_requires_remote_opt_in():
    with pytest.raises(ValueError, match="remote reranking is disabled"):
        HttpCrossEncoderReranker(base_url="https://rerank.example.com/v1", model="mini")

    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["documents"] == ["first", "second"]
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 1, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.2},
                ]
            },
        )

    reranker = HttpCrossEncoderReranker(
        base_url="http://127.0.0.1:8001/v1",
        model="mini-cross-encoder",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    scores = reranker.rerank("query", [hit("a", "first", -1), hit("b", "second", -2)])
    assert [(item.chunk_id, item.score) for item in scores] == [("b", 0.9), ("a", 0.2)]
