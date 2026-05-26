from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from .models import (
    CrawlRequest,
    JobRecord,
    LogEntry,
    MetadataUpdate,
    PipelineNode,
    ProviderInfo,
    utc_now,
)
from .providers import RedditCommentsProvider, TikTokCommentsProvider
from .providers.base import CommentsProvider, CrawlResult, ProviderError


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATUS_DIR = PROJECT_ROOT / "status"
STORAGE_DIR = PROJECT_ROOT / "storage"
JOBS_DIR = STORAGE_DIR / "jobs"

PIPELINE = [
    ("fetch", "Collect source comments"),
    ("normalize", "Clean and normalize records"),
    ("context", "Apply metadata context"),
    ("export", "Write JSON output"),
]

PROVIDER_INFO = [
    ProviderInfo(
        key="tiktok",
        label="TikTok Comments",
        availability="ready",
        accepts="Public TikTok video URL",
        description="Comment pages adapted from the supplied TikTok workflow.",
    ),
    ProviderInfo(
        key="reddit",
        label="Reddit Comments",
        availability="ready",
        accepts="Public Reddit post URL",
        description="Public post discussion threads through Reddit JSON.",
    ),
    ProviderInfo(
        key="facebook",
        label="Facebook",
        availability="connector_required",
        accepts="Provider/API configuration required",
        description="Reserved for an authenticated data connector.",
    ),
    ProviderInfo(
        key="x",
        label="X",
        availability="connector_required",
        accepts="Provider/API configuration required",
        description="Reserved for an authenticated data connector.",
    ),
]


class JobManager:
    def __init__(self) -> None:
        STATUS_DIR.mkdir(parents=True, exist_ok=True)
        JOBS_DIR.mkdir(parents=True, exist_ok=True)
        self.jobs: dict[str, JobRecord] = {}
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.providers: dict[str, CommentsProvider] = {
            "tiktok": TikTokCommentsProvider(),
            "reddit": RedditCommentsProvider(),
        }
        self._load()

    def _load(self) -> None:
        for path in STATUS_DIR.glob("*.json"):
            try:
                job = JobRecord.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if job.status in {"queued", "running"}:
                job.status = "failed"
                job.error = "API restarted before the crawl completed."
                job.finished_at = utc_now()
                job.logs.append(LogEntry(level="error", message=job.error))
                for node in job.nodes:
                    if node.status == "running":
                        node.status = "failed"
                self._save(job)
            self.jobs[job.id] = job

    def _save(self, job: JobRecord) -> None:
        job.updated_at = utc_now()
        status_file = STATUS_DIR / f"{job.id}.json"
        temporary = status_file.with_suffix(".tmp")
        temporary.write_text(job.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(status_file)
        self.jobs[job.id] = job

    def _append_log(self, job: JobRecord, message: str, level: str = "info") -> None:
        entry = LogEntry(level=level, message=message)
        job.logs.append(entry)
        job_dir = JOBS_DIR / job.id
        job_dir.mkdir(parents=True, exist_ok=True)
        with (job_dir / "pipeline.log").open("a", encoding="utf-8") as output:
            output.write(f"{entry.timestamp} [{level.upper()}] {message}\n")
        self._save(job)

    def _set_node(self, job: JobRecord, node_id: str, status: str, detail: str = "") -> None:
        for node in job.nodes:
            if node.id == node_id:
                node.status = status
                node.detail = detail
                break
        self._save(job)

    def list_jobs(self) -> list[JobRecord]:
        return sorted(self.jobs.values(), key=lambda job: job.created_at, reverse=True)

    def get(self, job_id: str) -> JobRecord | None:
        return self.jobs.get(job_id)

    def create(self, request: CrawlRequest, retry_of: str | None = None) -> JobRecord:
        job = JobRecord(
            id=uuid4().hex[:12],
            request=request,
            retry_of=retry_of,
            nodes=[PipelineNode(id=node_id, label=label) for node_id, label in PIPELINE],
        )
        self._save(job)
        self._append_log(job, "Crawl queued.")
        return job

    def schedule(self, job_id: str) -> None:
        self.tasks[job_id] = asyncio.create_task(self.run(job_id))

    async def run(self, job_id: str) -> None:
        job = self.jobs[job_id]
        provider = self.providers.get(job.request.source)
        if provider is None:
            self._fail(job, "This source needs an authenticated connector before it can run.")
            return
        job.status = "running"
        self._save(job)
        self._append_log(job, f"Starting {job.request.source} crawl.")
        try:
            self._set_node(job, "fetch", "running", "Requesting source pages")
            result = await provider.crawl(job.request)
            self._set_node(job, "fetch", "succeeded", f"{len(result.comments)} comments fetched")
            self._append_log(job, f"Fetched {len(result.comments)} comments.")

            self._set_node(job, "normalize", "running", "Writing normalized source records")
            raw_path = self._write_raw(job, result)
            job.raw_path = str(raw_path.relative_to(PROJECT_ROOT))
            job.record_count = len(result.comments)
            job.discovered_context = result.context
            self._set_node(job, "normalize", "succeeded", "Normalized JSON saved")

            self._set_node(job, "context", "running", job.request.context_mode)
            self._set_node(job, "context", "succeeded", "Context attached")
            self._set_node(job, "export", "running", "Materializing output")
            path = self._materialize(job, result)
            self._set_node(job, "export", "succeeded", path.name)
            job.status = "succeeded"
            job.finished_at = utc_now()
            job.error = None
            self._save(job)
            self._append_log(job, f"Output ready: {path.name}.")
        except (ProviderError, httpx.HTTPError) as error:
            self._fail(job, str(error))
        except Exception as error:  # noqa: BLE001 - persist unexpected worker failures.
            self._fail(job, f"Crawl failed: {error}")
        finally:
            self.tasks.pop(job_id, None)

    def _fail(self, job: JobRecord, message: str) -> None:
        job.status = "failed"
        job.error = message
        job.finished_at = utc_now()
        for node in job.nodes:
            if node.status == "running":
                node.status = "failed"
        self._append_log(job, message, "error")
        self._save(job)

    def _write_raw(self, job: JobRecord, result: CrawlResult) -> Path:
        job_dir = JOBS_DIR / job.id
        job_dir.mkdir(parents=True, exist_ok=True)
        path = job_dir / "raw_comments.json"
        path.write_text(
            json.dumps(
                {
                    "source": job.request.source,
                    "item_id": result.item_id,
                    "context": result.context,
                    "comments": result.comments,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return path

    def _read_result(self, job: JobRecord) -> CrawlResult:
        if not job.raw_path:
            raise ValueError("This job does not have normalized records yet.")
        raw = json.loads((PROJECT_ROOT / job.raw_path).read_text(encoding="utf-8"))
        return CrawlResult(
            item_id=raw["item_id"],
            comments=raw["comments"],
            context=raw.get("context") or {},
        )

    def _context(self, job: JobRecord, result: CrawlResult) -> dict[str, Any]:
        return {**result.context, **job.request.metadata}

    def _materialize(self, job: JobRecord, result: CrawlResult | None = None) -> Path:
        result = result or self._read_result(job)
        context = self._context(job, result)
        if job.request.context_mode == "global":
            output: Any = [
                {
                    "id": result.item_id,
                    "source": job.request.source,
                    "context": context,
                    "comments": [
                        {**comment, "labels": comment.get("labels", [])}
                        for comment in result.comments
                    ],
                }
            ]
        else:
            output = [
                {
                    "id": comment.get("id", ""),
                    "source": job.request.source,
                    "context": context,
                    "comment": comment.get("text", ""),
                    "comment_metadata": {
                        key: value for key, value in comment.items() if key not in {"id", "text"}
                    },
                    "labels": comment.get("labels", []),
                }
                for comment in result.comments
            ]
        path = JOBS_DIR / job.id / f"comments_{job.request.context_mode}.json"
        path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        relative = str(path.relative_to(PROJECT_ROOT))
        if relative not in job.output_files:
            job.output_files.append(relative)
        self._save(job)
        return path

    def update_metadata(self, job: JobRecord, update: MetadataUpdate) -> JobRecord:
        job.request.metadata = update.metadata
        if update.context_mode:
            job.request.context_mode = update.context_mode
        self._append_log(job, "Metadata context updated.")
        if job.status == "succeeded":
            path = self._materialize(job)
            self._append_log(job, f"Export rematerialized: {path.name}.")
        return job

    def output_path(self, job: JobRecord) -> Path | None:
        name = f"comments_{job.request.context_mode}.json"
        path = JOBS_DIR / job.id / name
        return path if path.exists() else None
manager = JobManager()
