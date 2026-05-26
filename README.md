# Datana

A Next.js and FastAPI workspace for crawling social comment data and shaping stored files
for further analysis. It implements TikTok and Reddit comment collection, preserves the
JSON lineage of the supplied TikTok workflow, and leaves authenticated connectors for
Facebook and X as visible expansion points.

## Features

- Data Wrangler with an upper data editor and lower file/control tray.
- CSV table editing plus raw JSON, JSONL, and text editing.
- Upload supported source files or reopen crawl and edited output stored by the system.
- Configurable metadata with `global` and `pairwise` context output modes.
- Persistent run state in `status/` and generated data/logs in `storage/jobs/<job_id>/`.

## Project Layout

```text
backend/                 FastAPI application and provider adapters
frontend/                Next.js App Router dashboard
status/                  Latest persisted JSON state for each job
storage/jobs/<job_id>/   Raw data, exports, and pipeline.log
storage/wrangler/uploads/ Uploaded CSV, JSON, JSONL, and TXT source files
storage/wrangler/edited/ Saved edited copies from Data Wrangler
```

## Run Locally

Backend:

```powershell
cd backend
python -m pip install -r requirements-dev.txt
python -m uvicorn app.main:app --reload --port 8000
```

Frontend, in another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. The frontend defaults to
`http://localhost:8000/api`; set `NEXT_PUBLIC_API_URL` using
`frontend/.env.local.example` if that address changes.

## Data Wrangler

Open the `Wrangler` view to work with system files. CSV sources are displayed as an
editable table; JSON, JSONL, and text sources use a raw editor. Uploaded originals are
kept in `storage/wrangler/uploads/`, while saves create a new copy in
`storage/wrangler/edited/`. Crawl results from `storage/jobs/` are available in the same
source selector.

## Output Modes

`global` produces one item with a single editable `context` object and a `comments`
array, matching the original TikTok crawler structure.

`pairwise` produces one record per comment, attaching the editable `context` object to
every record for notebook/model workflows.
