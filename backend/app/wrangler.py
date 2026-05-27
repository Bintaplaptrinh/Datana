from __future__ import annotations

import base64
import csv
import io
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any
from uuid import uuid4

from .models import (
    AnalysisBucket,
    AnalysisField,
    DataFormat,
    FileOrigin,
    WranglerAnalysis,
    WranglerEditRequest,
    WranglerFileContent,
    WranglerFileRecord,
    WranglerMergeRequest,
    WranglerUploadRequest,
)
from .service import JOBS_DIR, PROJECT_ROOT, STORAGE_DIR


WRANGLER_DIR = STORAGE_DIR / "wrangler"
UPLOADS_DIR = WRANGLER_DIR / "uploads"
EDITS_DIR = WRANGLER_DIR / "edited"
MERGES_DIR = WRANGLER_DIR / "merged"
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
        MERGES_DIR.mkdir(parents=True, exist_ok=True)

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
        try:
            job_relative = path.relative_to(JOBS_DIR)
            job_id = job_relative.parts[0] if len(job_relative.parts) > 1 else None
        except ValueError:
            job_id = None
        return WranglerFileRecord(
            id=self._id_for(path),
            name=path.name,
            format=self._supported_format(path),
            origin=origin,
            job_id=job_id,
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
            (MERGES_DIR, "merged"),
        ):
            if not directory.exists():
                continue
            for path in directory.rglob("*"):
                if path.is_file() and path.suffix.lower() in FORMATS:
                    paths.append((path, origin))
        return paths

    def list_files(self) -> list[WranglerFileRecord]:
        records = [self._record(path, origin) for path, origin in self._paths()]
        origin_order = {"crawled": 0, "merged": 1, "uploaded": 2, "edited": 3}
        return sorted(
            records,
            key=lambda item: (
                0 if item.job_id else 1,
                item.job_id or "",
                origin_order[item.origin],
                item.name.lower(),
                item.modified_at,
            ),
        )

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

    def merge(self, request: WranglerMergeRequest) -> WranglerFileContent:
        if len(set(request.file_ids)) != len(request.file_ids):
            raise WranglerError("Select distinct files to merge.")
        selected: list[WranglerFileContent] = []
        for file_id in request.file_ids:
            content = self.read(file_id)
            if not content:
                raise WranglerError("One or more selected files are no longer available.")
            selected.append(content)
        formats = {item.file.format for item in selected}
        if len(formats) != 1:
            raise WranglerError("Only files with the same format can be merged.")
        file_format = selected[0].file.format
        name = self._safe_name(request.name)
        if self._supported_format(Path(name)) != file_format:
            raise WranglerError("The merged output must keep the selected file format.")
        content = self._merge_content(file_format, [item.content for item in selected])
        self._validate_content(file_format, content)
        path = self._unique_path(MERGES_DIR, name)
        path.write_text(content, encoding="utf-8")
        return WranglerFileContent(file=self._record(path, "merged"), content=content)

    def _merge_content(self, file_format: DataFormat, contents: list[str]) -> str:
        if file_format == "csv":
            merged_rows: list[list[str]] = []
            header: list[str] | None = None
            for content in contents:
                rows = list(csv.reader(io.StringIO(content)))
                if not rows:
                    continue
                if header is None:
                    header = rows[0]
                    merged_rows.append(header)
                elif rows[0] != header:
                    raise WranglerError("CSV files must have identical headers to merge.")
                merged_rows.extend(rows[1:])
            output = io.StringIO()
            csv.writer(output, lineterminator="\n").writerows(merged_rows)
            return output.getvalue()
        if file_format == "json":
            values = [json.loads(content) for content in contents]
            if all(isinstance(value, list) for value in values):
                combined = [item for value in values for item in value]
            elif all(isinstance(value, dict) for value in values):
                combined = values
            else:
                raise WranglerError("JSON files must share an object or array top-level shape.")
            return f"{json.dumps(combined, ensure_ascii=False, indent=2)}\n"
        if file_format == "jsonl":
            records = [
                line.strip()
                for content in contents
                for line in content.splitlines()
                if line.strip()
            ]
            return f"{chr(10).join(records)}\n" if records else ""
        return "\n".join(content.rstrip("\n") for content in contents) + "\n"

    def analyze(self, file_id: str) -> WranglerAnalysis | None:
        content = self.read(file_id)
        if not content:
            return None
        if content.file.format == "text":
            raise WranglerError("EDA is available for CSV, JSON, and JSONL files.")
        rows = self._analysis_rows(content.file.format, content.content)
        fields = self._analyze_fields(rows)
        return WranglerAnalysis(
            file=content.file,
            record_count=len(rows),
            field_count=len(fields),
            missing_values=sum(field.missing for field in fields),
            numeric_fields=sum(field.kind == "number" for field in fields),
            fields=fields,
        )

    def _analysis_rows(self, file_format: DataFormat, content: str) -> list[dict[str, Any]]:
        if file_format == "csv":
            return [dict(row) for row in csv.DictReader(io.StringIO(content))]
        if file_format == "json":
            return self._json_rows(json.loads(content))
        rows: list[dict[str, Any]] = []
        for line in content.splitlines():
            if line.strip():
                rows.extend(self._json_rows(json.loads(line)))
        return rows

    def _json_rows(self, value: Any) -> list[dict[str, Any]]:
        values = value if isinstance(value, list) else [value]
        rows: list[dict[str, Any]] = []
        for item in values:
            if isinstance(item, dict) and isinstance(item.get("comments"), list):
                dataset = {
                    "dataset.id": item.get("id", item.get("item_id")),
                    "dataset.source": item.get("source"),
                    "context": item.get("context", {}),
                }
                rows.extend(
                    self._flatten({**dataset, **comment})
                    for comment in item["comments"]
                    if isinstance(comment, dict)
                )
            elif isinstance(item, dict):
                rows.append(self._flatten(item))
            else:
                rows.append({"value": item})
        return rows

    def _flatten(self, value: dict[str, Any], prefix: str = "") -> dict[str, Any]:
        flattened: dict[str, Any] = {}
        for key, item in value.items():
            name = f"{prefix}.{key}" if prefix else key
            if isinstance(item, dict):
                flattened.update(self._flatten(item, name))
            elif isinstance(item, list):
                flattened[name] = json.dumps(item, ensure_ascii=False)
            else:
                flattened[name] = item
        return flattened

    def _analyze_fields(self, rows: list[dict[str, Any]]) -> list[AnalysisField]:
        names: list[str] = []
        for row in rows:
            for name in row:
                if name not in names:
                    names.append(name)
        return [self._analyze_field(name, rows) for name in names]

    def _analyze_field(self, name: str, rows: list[dict[str, Any]]) -> AnalysisField:
        values = [row.get(name) for row in rows]
        populated = [value for value in values if value not in {None, ""}]
        numeric_values = [
            number
            for value in populated
            if (number := self._as_number(value, name)) is not None
        ]
        if populated and all(isinstance(value, bool) for value in populated):
            kind = "boolean"
        elif populated and len(numeric_values) == len(populated):
            kind = "number"
        elif populated and len({type(value) for value in populated}) > 1:
            kind = "mixed"
        else:
            kind = "text"
        distribution = (
            self._numeric_distribution(numeric_values)
            if kind == "number"
            else self._categorical_distribution(populated)
        )
        labels = {self._label(value) for value in populated}
        return AnalysisField(
            name=name,
            kind=kind,
            non_empty=len(populated),
            missing=len(values) - len(populated),
            unique=len(labels),
            minimum=min(numeric_values) if kind == "number" and numeric_values else None,
            maximum=max(numeric_values) if kind == "number" and numeric_values else None,
            average=fmean(numeric_values) if kind == "number" and numeric_values else None,
            distribution=distribution,
        )

    def _as_number(self, value: Any, name: str) -> float | None:
        if isinstance(value, bool) or name.lower().endswith("id"):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _label(self, value: Any) -> str:
        label = str(value)
        return label if len(label) <= 36 else f"{label[:33]}..."

    def _categorical_distribution(self, values: list[Any]) -> list[AnalysisBucket]:
        counts = Counter(self._label(value) for value in values)
        return [
            AnalysisBucket(label=label, count=count)
            for label, count in counts.most_common(8)
        ]

    def _numeric_distribution(self, values: list[float]) -> list[AnalysisBucket]:
        if not values:
            return []
        minimum, maximum = min(values), max(values)
        if minimum == maximum:
            return [AnalysisBucket(label=self._format_number(minimum), count=len(values))]
        count = min(8, max(3, round(len(values) ** 0.5)))
        width = (maximum - minimum) / count
        buckets = [0] * count
        for value in values:
            index = min(int((value - minimum) / width), count - 1)
            buckets[index] += 1
        return [
            AnalysisBucket(
                label=f"{self._format_number(minimum + index * width)} - "
                f"{self._format_number(minimum + (index + 1) * width)}",
                count=value,
            )
            for index, value in enumerate(buckets)
        ]

    def _format_number(self, value: float) -> str:
        return f"{value:,.2f}".rstrip("0").rstrip(".")


wrangler = DataWranglerManager()
