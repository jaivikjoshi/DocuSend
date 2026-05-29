"""
DocuSend FastAPI Backend
Exposes the existing Python OCR/parsing logic as a REST API.
"""
from __future__ import annotations

import os
import sys
import tempfile
import shutil
from pathlib import Path
from typing import Any, Dict, List

# ── make sure the repo root is on PYTHONPATH so `src.*` imports work ──────────
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from src.ocr import extract_text
from src.parser import parse_document
from src.export import write_export_files
from src.schema import ExtractedDocument
from src.utils import is_supported_file

# ── App Setup ─────────────────────────────────────────────────────────────────
app = FastAPI(title="DocuSend API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTPUT_DIR = REPO_ROOT / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tiff", ".tif"}


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "DocuSend API"}


@app.post("/api/process")
async def process_document(file: UploadFile = File(...)):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=OUTPUT_DIR) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        raw_text, ocr_warnings = extract_text(tmp_path)
        doc = parse_document(tmp_path, raw_text, ocr_warnings)
        doc.file_name = file.filename

        populated = sum(
            1 for field in [doc.vendor, doc.date, doc.total, doc.document_type]
            if field and field != "unknown"
        )
        doc.confidence = round((populated / 4) * 100, 1)

        return JSONResponse(content=doc.model_dump(mode="json"))
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


class ExportRequest(BaseModel):
    documents: List[Dict[str, Any]]
    format: str = "csv_zip"


@app.post("/api/export")
async def export_documents(request: ExportRequest):
    if not request.documents:
        raise HTTPException(status_code=400, detail="No documents provided for export.")
    if request.format not in ("json", "csv_zip"):
        raise HTTPException(status_code=400, detail="format must be 'json' or 'csv_zip'.")

    docs: List[ExtractedDocument] = []
    for raw in request.documents:
        try:
            docs.append(ExtractedDocument(**raw))
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Invalid document data: {exc}") from exc

    json_path, zip_path = write_export_files(docs)

    if request.format == "json":
        return FileResponse(path=json_path, media_type="application/json", filename=Path(json_path).name)
    else:
        return FileResponse(path=zip_path, media_type="application/zip", filename=Path(zip_path).name)
