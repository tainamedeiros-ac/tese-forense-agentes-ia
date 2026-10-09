"""Busca na web usando DuckDuckGo (sem necessidade de API key)."""
from dataclasses import dataclass

from ddgs import DDGS


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


def search_web(query: str, max_results: int = 3) -> list[SearchResult]:
    """Retorna os `max_results` links mais relevantes para a query."""
    results: list[SearchResult] = []
    with DDGS() as ddgs:
        for item in ddgs.text(query, max_results=max_results):
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("href", ""),
                    snippet=item.get("body", ""),
                )
            )
    return results
