from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..models import CrawlRequest


class ProviderError(RuntimeError):
    """A source rejected or could not complete a crawl."""


@dataclass
class CrawlResult:
    item_id: str
    comments: list[dict[str, Any]]
    context: dict[str, Any] = field(default_factory=dict)


class CommentsProvider(Protocol):
    async def crawl(self, request: CrawlRequest) -> CrawlResult: ...
