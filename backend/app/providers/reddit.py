from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

from ..models import CrawlRequest
from .base import CrawlResult, ProviderError


def clean_reddit_text(text: str | None) -> str | None:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    return cleaned if cleaned and cleaned not in {"[deleted]", "[removed]"} else None


def collect_replies(children: list[dict], output: list[dict[str, object]], limit: int) -> None:
    for item in children:
        if len(output) >= limit:
            return
        if item.get("kind") != "t1":
            continue
        data = item.get("data") or {}
        text = clean_reddit_text(data.get("body"))
        if text:
            output.append(
                {
                    "id": str(data.get("id") or ""),
                    "text": text,
                    "author": data.get("author") or "",
                    "likes": data.get("score", 0),
                    "created_at": data.get("created_utc"),
                }
            )
        replies = data.get("replies")
        if isinstance(replies, dict):
            nested = ((replies.get("data") or {}).get("children")) or []
            collect_replies(nested, output, limit)


class RedditCommentsProvider:
    async def crawl(self, request: CrawlRequest) -> CrawlResult:
        parsed = urlparse(request.target_url)
        if "reddit.com" not in parsed.netloc:
            raise ProviderError("Reddit input must be a reddit.com post URL.")
        json_url = parsed._replace(
            path=parsed.path.rstrip("/") + ".json", query="", fragment=""
        ).geturl()
        async with httpx.AsyncClient(
            headers={"user-agent": "DataEngineerTool/0.1 research crawler"},
            timeout=20.0,
            follow_redirects=True,
        ) as client:
            response = await client.get(
                json_url, params={"raw_json": 1, "limit": request.max_comments}
            )
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, list) or len(payload) < 2:
            raise ProviderError("Reddit response did not contain a comment listing.")
        post = (((payload[0].get("data") or {}).get("children") or [{}])[0]).get("data") or {}
        children = ((payload[1].get("data") or {}).get("children")) or []
        comments: list[dict[str, object]] = []
        collect_replies(children, comments, request.max_comments)
        item_id = str(post.get("id") or parsed.path.rstrip("/").split("/")[-1])
        return CrawlResult(
            item_id=item_id,
            comments=comments,
            context={
                "post_id": item_id,
                "title": post.get("title") or "",
                "subreddit": post.get("subreddit_name_prefixed") or "",
                "source_url": request.target_url,
            },
        )
