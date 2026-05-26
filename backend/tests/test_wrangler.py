from pathlib import Path

from fastapi.testclient import TestClient

from app import main
from app.wrangler import DataWranglerManager


def test_wrangler_upload_read_save_and_list(tmp_path: Path, monkeypatch) -> None:
    import app.wrangler as wrangler_service

    monkeypatch.setattr(wrangler_service, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(wrangler_service, "JOBS_DIR", tmp_path / "storage" / "jobs")
    monkeypatch.setattr(wrangler_service, "UPLOADS_DIR", tmp_path / "storage" / "wrangler" / "uploads")
    monkeypatch.setattr(wrangler_service, "EDITS_DIR", tmp_path / "storage" / "wrangler" / "edited")
    local = DataWranglerManager()
    monkeypatch.setattr(main, "wrangler", local)

    with TestClient(main.app) as client:
        uploaded = client.post(
            "/api/wrangler/uploads",
            json={"name": "sample.csv", "content": "name,score\nalpha,1\n"},
        )
        assert uploaded.status_code == 201
        file_id = uploaded.json()["file"]["id"]

        loaded = client.get(f"/api/wrangler/files/{file_id}")
        assert loaded.json()["content"] == "name,score\nalpha,1\n"

        edited = client.post(
            f"/api/wrangler/files/{file_id}/edits",
            json={"name": "sample_clean.csv", "content": "name,score\nalpha,2\n"},
        )
        assert edited.status_code == 201
        assert edited.json()["file"]["origin"] == "edited"

        listed = client.get("/api/wrangler/files").json()
        assert {entry["origin"] for entry in listed} == {"uploaded", "edited"}


def test_wrangler_rejects_unsupported_and_malformed_files(tmp_path: Path, monkeypatch) -> None:
    import app.wrangler as wrangler_service

    monkeypatch.setattr(wrangler_service, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(wrangler_service, "JOBS_DIR", tmp_path / "storage" / "jobs")
    monkeypatch.setattr(wrangler_service, "UPLOADS_DIR", tmp_path / "storage" / "wrangler" / "uploads")
    monkeypatch.setattr(wrangler_service, "EDITS_DIR", tmp_path / "storage" / "wrangler" / "edited")
    local = DataWranglerManager()
    monkeypatch.setattr(main, "wrangler", local)

    with TestClient(main.app) as client:
        assert (
            client.post("/api/wrangler/uploads", json={"name": "sheet.xlsx", "content": "x"}).status_code
            == 400
        )
        assert (
            client.post("/api/wrangler/uploads", json={"name": "bad.json", "content": "{"}).status_code
            == 400
        )
