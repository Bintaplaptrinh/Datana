from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

from ..models import CrawlRequest
from .base import CrawlResult, ProviderError


def clean_comment_text(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = re.sub(r"\[sticker\]", " ", str(text), flags=re.IGNORECASE)
    cleaned = re.sub(r"@\w+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(re.findall(r"\w", cleaned, flags=re.UNICODE)) < 2:
        return None
    return cleaned


class TikTokCommentsProvider:
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0 Safari/537.36"
    )

    async def _video_id(self, client: httpx.AsyncClient, target_url: str) -> str:
        parsed = urlparse(target_url)
        if parsed.netloc in {"vm.tiktok.com", "vt.tiktok.com"}:
            response = await client.head(target_url, follow_redirects=True)
            parsed = urlparse(str(response.url))
        match = re.search(r"/video/(\d+)", parsed.path)
        if not match:
            raise ProviderError("TikTok URL must point to a video.")
        return match.group(1)

    async def crawl(self, request: CrawlRequest) -> CrawlResult:
        headers = {"user-agent": self.user_agent}
        comments: list[dict[str, object]] = []
        async with httpx.AsyncClient(headers=headers, timeout=20.0) as client:
            video_id = await self._video_id(client, request.target_url)
            headers["referer"] = f"https://www.tiktok.com/@x/video/{video_id}"
            cursor = 0
            seen_cursors: set[int] = set()
            while len(comments) < request.max_comments:
                if cursor in seen_cursors:
                    break
                seen_cursors.add(cursor)
                page_size = min(50, request.max_comments - len(comments))
                response = await client.get(
                    "https://www.tiktok.com/api/comment/list/",
                    params={
                        "aid": "1988",
                        "aweme_id": video_id,
                        "count": page_size,
                        "cursor": cursor,
                    },
                    headers=headers,
                )
                response.raise_for_status()
                payload = response.json()
                page = payload.get("comments") or []
                if not page:
                    break
                for item in page:
                    cleaned = clean_comment_text(item.get("text"))
                    if not cleaned:
                        continue
                    user = item.get("user") or {}
                    comments.append(
                        {
                            "id": str(item.get("cid") or ""),
                            "text": cleaned,
                            "author": user.get("unique_id") or user.get("nickname") or "",
                            "likes": item.get("digg_count", 0),
                            "created_at": item.get("create_time"),
                        }
                    )
                    if len(comments) >= request.max_comments:
                        break
                if not payload.get("has_more"):
                    break
                next_cursor = int(payload.get("cursor") or (cursor + page_size))
                cursor = next_cursor if next_cursor != cursor else cursor + page_size
        return CrawlResult(
            item_id=video_id,
            comments=comments,
            context={"video_id": video_id, "source_url": request.target_url},
        )
