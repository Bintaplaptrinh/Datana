import json
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
    monkeypatch.setattr(wrangler_service, "MERGES_DIR", tmp_path / "storage" / "wrangler" / "merged")
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
    monkeypatch.setattr(wrangler_service, "MERGES_DIR", tmp_path / "storage" / "wrangler" / "merged")
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


def test_wrangler_lists_job_id_and_analyzes_crawl_json(tmp_path: Path, monkeypatch) -> None:
    import app.wrangler as wrangler_service

    monkeypatch.setattr(wrangler_service, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(wrangler_service, "JOBS_DIR", tmp_path / "storage" / "jobs")
    monkeypatch.setattr(wrangler_service, "UPLOADS_DIR", tmp_path / "storage" / "wrangler" / "uploads")
    monkeypatch.setattr(wrangler_service, "EDITS_DIR", tmp_path / "storage" / "wrangler" / "edited")
    monkeypatch.setattr(wrangler_service, "MERGES_DIR", tmp_path / "storage" / "wrangler" / "merged")
    job_dir = tmp_path / "storage" / "jobs" / "9a70f68c23c0"
    job_dir.mkdir(parents=True)
    (job_dir / "raw_comments.json").write_text(
        '{"source":"tiktok","item_id":"video-1","comments":'
        '[{"text":"Nice","likes":2},{"text":"Good","likes":4}]}',
        encoding="utf-8",
    )
    local = DataWranglerManager()
    monkeypatch.setattr(main, "wrangler", local)

    with TestClient(main.app) as client:
        listed = client.get("/api/wrangler/files").json()
        assert listed[0]["job_id"] == "9a70f68c23c0"
        analysis = client.get(f"/api/wrangler/files/{listed[0]['id']}/analysis").json()
        assert analysis["record_count"] == 2
        likes = next(field for field in analysis["fields"] if field["name"] == "likes")
        assert likes["kind"] == "number"
        assert likes["average"] == 3


def test_wrangler_merges_compatible_csv_and_rejects_mismatch(tmp_path: Path, monkeypatch) -> None:
    import app.wrangler as wrangler_service

    monkeypatch.setattr(wrangler_service, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(wrangler_service, "JOBS_DIR", tmp_path / "storage" / "jobs")
    monkeypatch.setattr(wrangler_service, "UPLOADS_DIR", tmp_path / "storage" / "wrangler" / "uploads")
    monkeypatch.setattr(wrangler_service, "EDITS_DIR", tmp_path / "storage" / "wrangler" / "edited")
    monkeypatch.setattr(wrangler_service, "MERGES_DIR", tmp_path / "storage" / "wrangler" / "merged")
    local = DataWranglerManager()
    monkeypatch.setattr(main, "wrangler", local)

    with TestClient(main.app) as client:
        one = client.post(
            "/api/wrangler/uploads",
            json={"name": "one.csv", "content": "name,score\nalpha,1\n"},
        ).json()
        two = client.post(
            "/api/wrangler/uploads",
            json={"name": "two.csv", "content": "name,score\nbeta,2\n"},
        ).json()
        mismatch = client.post(
            "/api/wrangler/uploads",
            json={"name": "bad.csv", "content": "label,value\ngamma,3\n"},
        ).json()

        merged = client.post(
            "/api/wrangler/merges",
            json={
                "name": "combined.csv",
                "file_ids": [one["file"]["id"], two["file"]["id"]],
            },
        )
        assert merged.status_code == 201
        assert merged.json()["file"]["origin"] == "merged"
        assert merged.json()["content"] == "name,score\nalpha,1\nbeta,2\n"
        summary = client.get(
            f"/api/wrangler/files/{merged.json()['file']['id']}/analysis"
        ).json()
        assert summary["record_count"] == 2

        rejected = client.post(
            "/api/wrangler/merges",
            json={
                "name": "invalid.csv",
                "file_ids": [one["file"]["id"], mismatch["file"]["id"]],
            },
        )
        assert rejected.status_code == 400


def test_wrangler_merges_json_records_for_analysis(tmp_path: Path, monkeypatch) -> None:
    import app.wrangler as wrangler_service

    monkeypatch.setattr(wrangler_service, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(wrangler_service, "JOBS_DIR", tmp_path / "storage" / "jobs")
    monkeypatch.setattr(wrangler_service, "UPLOADS_DIR", tmp_path / "storage" / "wrangler" / "uploads")
    monkeypatch.setattr(wrangler_service, "EDITS_DIR", tmp_path / "storage" / "wrangler" / "edited")
    monkeypatch.setattr(wrangler_service, "MERGES_DIR", tmp_path / "storage" / "wrangler" / "merged")
    local = DataWranglerManager()
    monkeypatch.setattr(main, "wrangler", local)

    with TestClient(main.app) as client:
        identifiers = []
        for name, content in (
            ("one.json", '[{"comment":"Nice","likes":3}]'),
            ("two.json", '[{"comment":"Useful","likes":5}]'),
        ):
            uploaded = client.post(
                "/api/wrangler/uploads",
                json={"name": name, "content": content},
            ).json()
            identifiers.append(uploaded["file"]["id"])
        merged = client.post(
            "/api/wrangler/merges",
            json={"name": "combined.json", "file_ids": identifiers},
        ).json()
        assert json.loads(merged["content"]) == [
            {"comment": "Nice", "likes": 3},
            {"comment": "Useful", "likes": 5},
        ]
        analysis = client.get(
            f"/api/wrangler/files/{merged['file']['id']}/analysis"
        ).json()
        assert analysis["record_count"] == 2
