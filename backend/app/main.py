from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .models import (
    CrawlRequest,
    JobRecord,
    MetadataUpdate,
    ProviderInfo,
    WranglerAnalysis,
    WranglerEditRequest,
    WranglerFileContent,
    WranglerFileRecord,
    WranglerMergeRequest,
    WranglerUploadRequest,
)
from .service import PROVIDER_INFO, manager
from .wrangler import WranglerError, wrangler


app = FastAPI(
    title="Data Engineer Tool API",
    version="0.1.0",
    description="Persisted social comment crawl pipelines and metadata exports.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_job(job_id: str) -> JobRecord:
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/providers", response_model=list[ProviderInfo])
def providers() -> list[ProviderInfo]:
    return PROVIDER_INFO


@app.get("/api/jobs", response_model=list[JobRecord])
def jobs() -> list[JobRecord]:
    return manager.list_jobs()


@app.get("/api/jobs/{job_id}", response_model=JobRecord)
def job(job_id: str) -> JobRecord:
    return require_job(job_id)


@app.post("/api/jobs", response_model=JobRecord, status_code=202)
async def create_job(request: CrawlRequest) -> JobRecord:
    created = manager.create(request)
    manager.schedule(created.id)
    return created


@app.post("/api/jobs/{job_id}/retry", response_model=JobRecord, status_code=202)
async def retry_job(job_id: str) -> JobRecord:
    previous = require_job(job_id)
    created = manager.create(previous.request.model_copy(deep=True), retry_of=previous.id)
    manager.schedule(created.id)
    return created


@app.patch("/api/jobs/{job_id}/metadata", response_model=JobRecord)
def change_metadata(job_id: str, update: MetadataUpdate) -> JobRecord:
    return manager.update_metadata(require_job(job_id), update)


@app.get("/api/jobs/{job_id}/output")
def output(job_id: str) -> JSONResponse:
    path = manager.output_path(require_job(job_id))
    if not path:
        raise HTTPException(status_code=404, detail="Output is not available yet.")
    return JSONResponse(json.loads(path.read_text(encoding="utf-8")))


@app.get("/api/jobs/{job_id}/download")
def download(job_id: str) -> FileResponse:
    path = manager.output_path(require_job(job_id))
    if not path:
        raise HTTPException(status_code=404, detail="Output is not available yet.")
    return FileResponse(path, media_type="application/json", filename=path.name)


@app.get("/api/wrangler/files", response_model=list[WranglerFileRecord])
def wrangler_files() -> list[WranglerFileRecord]:
    return wrangler.list_files()


@app.get("/api/wrangler/files/{file_id}", response_model=WranglerFileContent)
def wrangler_file(file_id: str) -> WranglerFileContent:
    content = wrangler.read(file_id)
    if not content:
        raise HTTPException(status_code=404, detail="Data file not found.")
    return content


@app.post("/api/wrangler/uploads", response_model=WranglerFileContent, status_code=201)
def upload_wrangler_file(request: WranglerUploadRequest) -> WranglerFileContent:
    try:
        return wrangler.upload(request)
    except WranglerError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/wrangler/files/{file_id}/edits", response_model=WranglerFileContent, status_code=201)
def save_wrangler_edit(file_id: str, request: WranglerEditRequest) -> WranglerFileContent:
    try:
        content = wrangler.save_edit(file_id, request)
    except WranglerError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if not content:
        raise HTTPException(status_code=404, detail="Data file not found.")
    return content


@app.post("/api/wrangler/merges", response_model=WranglerFileContent, status_code=201)
def merge_wrangler_files(request: WranglerMergeRequest) -> WranglerFileContent:
    try:
        return wrangler.merge(request)
    except WranglerError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/wrangler/files/{file_id}/analysis", response_model=WranglerAnalysis)
def analyze_wrangler_file(file_id: str) -> WranglerAnalysis:
    try:
        analysis = wrangler.analyze(file_id)
    except WranglerError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if not analysis:
        raise HTTPException(status_code=404, detail="Data file not found.")
    return analysis
