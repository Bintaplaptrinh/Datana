from pathlib import Path

from app.models import CrawlRequest, MetadataUpdate
from app.providers.base import CrawlResult
from app.service import JobManager


def test_global_and_pairwise_exports(tmp_path: Path, monkeypatch) -> None:
    import app.service as service

    monkeypatch.setattr(service, "STATUS_DIR", tmp_path / "status")
    monkeypatch.setattr(service, "JOBS_DIR", tmp_path / "storage" / "jobs")
    monkeypatch.setattr(service, "PROJECT_ROOT", tmp_path)
    local = JobManager()
    job = local.create(
        CrawlRequest(
            source="tiktok",
            target_url="https://www.tiktok.com/@user/video/123",
            metadata={"desc": "Launch"},
        )
    )
    result = CrawlResult(item_id="123", comments=[{"id": "1", "text": "Nice work"}])
    job.raw_path = str(local._write_raw(job, result).relative_to(tmp_path))
    global_path = local._materialize(job, result)
    assert '"desc": "Launch"' in global_path.read_text(encoding="utf-8")

    job.status = "succeeded"
    local.update_metadata(job, MetadataUpdate(metadata={"topic": "etl"}, context_mode="pairwise"))
    pairwise = local.output_path(job)
    assert pairwise is not None
    assert '"comment": "Nice work"' in pairwise.read_text(encoding="utf-8")
