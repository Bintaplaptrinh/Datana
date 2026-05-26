import time
from pathlib import Path

from fastapi.testclient import TestClient

from app import main
from app.providers.base import CrawlResult
from app.service import JobManager


class FakeProvider:
    async def crawl(self, request) -> CrawlResult:
        return CrawlResult(
            item_id="video-1",
            comments=[{"id": "comment-1", "text": "Clean comment"}],
            context={"source_url": request.target_url},
        )


def test_crawl_api_persists_and_rematerializes_output(tmp_path: Path, monkeypatch) -> None:
    import app.service as service

    monkeypatch.setattr(service, "STATUS_DIR", tmp_path / "status")
    monkeypatch.setattr(service, "JOBS_DIR", tmp_path / "storage" / "jobs")
    monkeypatch.setattr(service, "PROJECT_ROOT", tmp_path)
    local = JobManager()
    local.providers["tiktok"] = FakeProvider()
    monkeypatch.setattr(main, "manager", local)

    with TestClient(main.app) as client:
        created = client.post(
            "/api/jobs",
            json={
                "source": "tiktok",
                "target_url": "https://www.tiktok.com/@user/video/123",
                "metadata": {"desc": "First context"},
                "context_mode": "global",
            },
        )
        assert created.status_code == 202
        job_id = created.json()["id"]

        status = ""
        for _ in range(30):
            status = client.get(f"/api/jobs/{job_id}").json()["status"]
            if status == "succeeded":
                break
            time.sleep(0.01)
        assert status == "succeeded"
        assert (tmp_path / "status" / f"{job_id}.json").exists()
        assert client.get(f"/api/jobs/{job_id}/output").json()[0]["context"]["desc"] == "First context"

        updated = client.patch(
            f"/api/jobs/{job_id}/metadata",
            json={"metadata": {"topic": "pipelines"}, "context_mode": "pairwise"},
        )
        assert updated.status_code == 200
        output = client.get(f"/api/jobs/{job_id}/output").json()
        assert output[0]["comment"] == "Clean comment"
        assert output[0]["context"]["topic"] == "pipelines"
        assert client.get(f"/api/jobs/{job_id}/download").status_code == 200
