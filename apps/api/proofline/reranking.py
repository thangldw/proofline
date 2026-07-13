from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

import httpx

from .model_gateway import ProviderConfigurationError, ProviderRequestError, is_loopback_url
from .schemas import SearchHit


@dataclass(frozen=True, slots=True)
class RerankScore:
    chunk_id: str
    score: float


class Reranker(Protocol):
    id: str
    model: str

    def health(self) -> bool: ...

    def rerank(self, query: str, hits: list[SearchHit]) -> list[RerankScore]: ...


def _terms(value: str) -> list[str]:
    return [term.casefold() for term in re.findall(r"[\w-]+", value, flags=re.UNICODE)]


class DeterministicTokenReranker:
    id = "deterministic_token"
    model = "token-overlap-v1"

    def health(self) -> bool:
        return True

    def rerank(self, query: str, hits: list[SearchHit]) -> list[RerankScore]:
        query_terms = _terms(query)
        query_set = set(query_terms)
        scores: list[RerankScore] = []
        for hit in hits:
            content_terms = _terms(hit.content)
            content_set = set(content_terms)
            coverage = len(query_set & content_set) / max(1, len(query_set))
            phrase = 1.0 if " ".join(query_terms) in " ".join(content_terms) else 0.0
            proximity = 0.0
            positions = [index for index, term in enumerate(content_terms) if term in query_set]
            if len(positions) > 1:
                proximity = 1 / (1 + max(positions) - min(positions))
            scores.append(RerankScore(hit.chunk_id, coverage + 0.25 * phrase + 0.1 * proximity))
        return scores


class HttpCrossEncoderReranker:
    id = "http_cross_encoder"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        allow_remote: bool = False,
        client: httpx.Client | None = None,
    ) -> None:
        if not is_loopback_url(base_url) and not allow_remote:
            raise ProviderConfigurationError("remote reranking is disabled")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=30)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def health(self) -> bool:
        try:
            return self.client.get(f"{self.base_url}/models", headers=self._headers()).is_success
        except httpx.HTTPError:
            return False

    def rerank(self, query: str, hits: list[SearchHit]) -> list[RerankScore]:
        try:
            response = self.client.post(
                f"{self.base_url}/rerank",
                headers=self._headers(),
                json={
                    "model": self.model,
                    "query": query,
                    "documents": [hit.content for hit in hits],
                },
            )
            response.raise_for_status()
            body = response.json()
            return [
                RerankScore(hits[item["index"]].chunk_id, float(item["relevance_score"]))
                for item in body["results"]
            ]
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderRequestError("reranking provider request failed") from exc


def apply_reranking(query: str, hits: list[SearchHit], reranker: Reranker) -> list[SearchHit]:
    scores = {item.chunk_id: item.score for item in reranker.rerank(query, hits)}
    if set(scores) != {hit.chunk_id for hit in hits}:
        raise ProviderRequestError("reranking provider returned incomplete results")
    ordered = sorted(hits, key=lambda hit: (-scores[hit.chunk_id], hit.rank, hit.chunk_id))
    return [
        hit.model_copy(
            update={
                "rerank_score": scores[hit.chunk_id],
                "rerank_rank": rank,
                "retrieval_channels": [*hit.retrieval_channels, "rerank"],
            }
        )
        for rank, hit in enumerate(ordered, start=1)
    ]
