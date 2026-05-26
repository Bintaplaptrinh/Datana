from __future__ import annotations

import base64
import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .models import (
    DataFormat,
    FileOrigin,
    WranglerEditRequest,
    WranglerFileContent,
    WranglerFileRecord,
    WranglerUploadRequest,
)
from .service import JOBS_DIR, PROJECT_ROOT, STORAGE_DIR


WRANGLER_DIR = STORAGE_DIR / "wrangler"
UPLOADS_DIR = WRANGLER_DIR / "uploads"
EDITS_DIR = WRANGLER_DIR / "edited"
FORMATS: dict[str, DataFormat] = {
    ".csv": "csv",
    ".json": "json",
    ".jsonl": "jsonl",
    ".txt": "text",
}


class WranglerError(ValueError):
    """Invalid file or content submitted to the Wrangler workspace."""


class DataWranglerManager:
    def __init__(self) -> None:
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        EDITS_DIR.mkdir(parents=True, exist_ok=True)

    def _supported_format(self, path: Path) -> DataFormat:
        file_format = FORMATS.get(path.suffix.lower())
        if not file_format:
            raise WranglerError("Only CSV, JSON, JSONL, and TXT files are supported.")
        return file_format

    def _safe_name(self, name: str) -> str:
        safe = Path(name).name.strip()
        if not safe or safe != name.strip():
            raise WranglerError("Please use a plain file name without folders.")
        self._supported_format(Path(safe))
        return safe

    def _validate_content(self, file_format: DataFormat, content: str) -> None:
        try:
            if file_format == "json":
                json.loads(content)
            elif file_format == "jsonl":
                for number, line in enumerate(content.splitlines(), start=1):
                    if line.strip():
                        json.loads(line)
            elif file_format == "csv":
                list(csv.reader(io.StringIO(content)))
        except (json.JSONDecodeError, csv.Error) as error:
            raise WranglerError(f"Invalid {file_format.upper()} content: {error}") from error

    def _unique_path(self, directory: Path, name: str) -> Path:
        target = directory / name
        if not target.exists():
            return target
        return directory / f"{target.stem}_{uuid4().hex[:6]}{target.suffix}"

    def _id_for(self, path: Path) -> str:
        relative = str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
        return base64.urlsafe_b64encode(relative.encode("utf-8")).decode("ascii").rstrip("=")

    def _record(self, path: Path, origin: FileOrigin) -> WranglerFileRecord:
        modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        return WranglerFileRecord(
            id=self._id_for(path),
            name=path.name,
            format=self._supported_format(path),
            origin=origin,
            size=path.stat().st_size,
            modified_at=modified,
            relative_path=str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        )

    def _paths(self) -> list[tuple[Path, FileOrigin]]:
        paths: list[tuple[Path, FileOrigin]] = []
        for directory, origin in (
            (JOBS_DIR, "crawled"),
            (UPLOADS_DIR, "uploaded"),
            (EDITS_DIR, "edited"),
        ):
            if not directory.exists():
                continue
            for path in directory.rglob("*"):
                if path.is_file() and path.suffix.lower() in FORMATS:
                    paths.append((path, origin))
        return paths

    def list_files(self) -> list[WranglerFileRecord]:
        records = [self._record(path, origin) for path, origin in self._paths()]
        return sorted(records, key=lambda item: item.modified_at, reverse=True)

    def _find(self, file_id: str) -> tuple[Path, FileOrigin] | None:
        for path, origin in self._paths():
            if self._id_for(path) == file_id:
                return path, origin
        return None

    def read(self, file_id: str) -> WranglerFileContent | None:
        found = self._find(file_id)
        if not found:
            return None
        path, origin = found
        return WranglerFileContent(
            file=self._record(path, origin),
            content=path.read_text(encoding="utf-8-sig"),
        )

    def upload(self, request: WranglerUploadRequest) -> WranglerFileContent:
        name = self._safe_name(request.name)
        file_format = self._supported_format(Path(name))
        self._validate_content(file_format, request.content)
        path = self._unique_path(UPLOADS_DIR, name)
        path.write_text(request.content, encoding="utf-8")
        return WranglerFileContent(file=self._record(path, "uploaded"), content=request.content)

    def save_edit(self, file_id: str, request: WranglerEditRequest) -> WranglerFileContent | None:
        found = self._find(file_id)
        if not found:
            return None
        name = self._safe_name(request.name)
        file_format = self._supported_format(Path(name))
        source_format = self._supported_format(found[0])
        if file_format != source_format:
            raise WranglerError("Edited files must keep the source file format.")
        self._validate_content(file_format, request.content)
        path = self._unique_path(EDITS_DIR, name)
        path.write_text(request.content, encoding="utf-8")
        return WranglerFileContent(file=self._record(path, "edited"), content=request.content)


wrangler = DataWranglerManager()
