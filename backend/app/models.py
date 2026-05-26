from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


SourceName = Literal["tiktok", "reddit", "facebook", "x"]
ContextMode = Literal["global", "pairwise"]
JobStatus = Literal["queued", "running", "succeeded", "failed"]
NodeStatus = Literal["pending", "running", "succeeded", "failed"]
DataFormat = Literal["csv", "json", "jsonl", "text"]
FileOrigin = Literal["crawled", "uploaded", "edited"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProviderInfo(BaseModel):
    key: SourceName
    label: str
    availability: Literal["ready", "connector_required"]
    accepts: str
    description: str


class CrawlRequest(BaseModel):
    source: SourceName
    target_url: str = Field(min_length=4, max_length=2048)
    max_comments: int = Field(default=200, ge=1, le=2000)
    context_mode: ContextMode = "global"
    metadata: dict[str, Any] = Field(default_factory=dict)


class MetadataUpdate(BaseModel):
    metadata: dict[str, Any] = Field(default_factory=dict)
    context_mode: ContextMode | None = None


class LogEntry(BaseModel):
    timestamp: str = Field(default_factory=utc_now)
    level: Literal["info", "warning", "error"] = "info"
    message: str


class PipelineNode(BaseModel):
    id: str
    label: str
    status: NodeStatus = "pending"
    detail: str = ""


class JobRecord(BaseModel):
    id: str
    status: JobStatus = "queued"
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    finished_at: str | None = None
    retry_of: str | None = None
    request: CrawlRequest
    nodes: list[PipelineNode]
    logs: list[LogEntry] = Field(default_factory=list)
    record_count: int = 0
    raw_path: str | None = None
    output_files: list[str] = Field(default_factory=list)
    discovered_context: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class WranglerFileRecord(BaseModel):
    id: str
    name: str
    format: DataFormat
    origin: FileOrigin
    size: int
    modified_at: str
    relative_path: str


class WranglerFileContent(BaseModel):
    file: WranglerFileRecord
    content: str


class WranglerUploadRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    content: str = Field(max_length=10_000_000)


class WranglerEditRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    content: str = Field(max_length=10_000_000)
