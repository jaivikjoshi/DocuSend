# DocuSend

DocuSend is a full-stack document intelligence app for turning receipts and invoices into reviewed, exportable expense data.

Users upload PDFs or receipt images, DocuSend stores the source file privately, queues the document for OCR and AI extraction, highlights low-confidence results for human review, and exports clean data for spreadsheets or accounting workflows.

## What It Does

- Authenticated dashboard with Supabase Auth, private Storage, Postgres tables, and RLS policies
- Batch upload for PDF, PNG, JPG, WEBP, and TIFF documents
- Durable processing state with queued, processing, review, processed, and failed statuses
- Retryable extraction jobs with retry count, failure reason, processing duration, and parser version metadata
- OCR pipeline for images, selectable PDFs, and scanned PDF fallback pages
- Gemini multimodal extraction with regex fallback
- Editable review workflow for document fields and line items
- Warning and confidence indicators for human-in-the-loop validation
- CSV ZIP, JSON, and accounting-ready CSV exports
- React/Vite frontend, FastAPI backend, Supabase migrations, backend API tests, and Playwright E2E coverage

## Architecture

```text
React + Vite
  -> Supabase Auth / Storage / Realtime
  -> FastAPI API
  -> durable document queue in Postgres
  -> OCR + Gemini extraction worker
  -> reviewed exports
```

The source document remains in the private `documents` storage bucket. The `documents` table acts as the durable job record, so failed or interrupted jobs can be retried without losing the upload.

## Run Locally

Install Python dependencies:

```bash
cd /Users/jaivik/Documents/DocuSend
python3 -m pip install -r requirements.txt
```

Start the FastAPI backend:

```bash
cd /Users/jaivik/Documents/DocuSend
python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Start the frontend in another terminal:

```bash
cd /Users/jaivik/Documents/DocuSend/frontend
npm install
npm run dev
```

Open the Vite URL, usually `http://localhost:5173`.

## Environment

Root `.env`:

```bash
SUPABASE_URL=...
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=... # recommended for durable queue worker
GEMINI_API_KEY=...
```

Frontend `frontend/.env`:

```bash
VITE_SUPABASE_URL=...
VITE_SUPABASE_ANON_KEY=...
VITE_API_URL=http://localhost:8000
```

For local OCR, install the Tesseract system package if it is not already available.

## Database

Apply the migrations in `supabase/migrations` to create:

- `profiles`, `documents`, `line_items`, and `exports`
- row-level security policies
- private document storage bucket policies
- durable processing and review metadata

The latest migration adds queue/retry fields, review fields, and the accounting export type.

## Tests

```bash
cd /Users/jaivik/Documents/DocuSend
python3 -m unittest
```

Frontend lint:

```bash
cd /Users/jaivik/Documents/DocuSend/frontend
npm run lint
```

E2E flow:

```bash
cd /Users/jaivik/Documents/DocuSend/frontend
npm run test:e2e
```

## Resume Highlights

- Built a full-stack AI document-processing app with React, FastAPI, Supabase Auth, private object storage, RLS, and realtime updates.
- Implemented a durable Postgres-backed processing queue with retryable jobs, failure metadata, parser versioning, and processing time metrics.
- Designed a human review workflow for low-confidence OCR/LLM extraction results with editable structured fields and line items.
- Added accounting-ready exports for spreadsheet and finance workflows, alongside JSON and normalized CSV ZIP exports.
