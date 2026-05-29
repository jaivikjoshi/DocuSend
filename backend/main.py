"""
DocuSend FastAPI Backend
Exposes the existing Python OCR/parsing logic as a REST API.
Tier-2: Uses Gemini Flash for structured parsing when available,
        falls back to the legacy regex parser otherwise.
"""
from __future__ import annotations

import logging
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

from fastapi import FastAPI, File, HTTPException, UploadFile, BackgroundTasks, Form, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from supabase import create_client, Client

from src.ocr import extract_text
from src.parser import parse_document
from src.export import write_export_files
from src.schema import ExtractedDocument
from src.utils import is_supported_file

# Tier-2: import Gemini parser (won't raise even if key is missing)
from src.gemini_parser import parse_document_gemini, GEMINI_AVAILABLE

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    logger.warning("Supabase environment variables missing. Database updates will fail.")

# ── App Setup ─────────────────────────────────────────────────────────────────
app = FastAPI(title="DocuSend API", version="2.0.0")

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
    return {
        "status": "ok",
        "service": "DocuSend API",
        "version": "2.0.0",
        "gemini_available": GEMINI_AVAILABLE,
        "parser": "gemini" if GEMINI_AVAILABLE else "regex",
    }


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
        # Always run OCR first — provides raw_text as context to Gemini
        # and serves as the full extraction on fallback path
        raw_text, ocr_warnings = extract_text(tmp_path)

        doc: ExtractedDocument

        # ── Tier-2: Try Gemini first ───────────────────────────────────────────
        if GEMINI_AVAILABLE:
            try:
                logger.info("Attempting Gemini extraction for: %s", file.filename)
                doc = parse_document_gemini(tmp_path, raw_text, ocr_warnings)

                # Calculate confidence from populated fields
                populated = sum(
                    1 for field in [doc.vendor, doc.date, doc.total, doc.document_type]
                    if field and field not in ("", "unknown", None)
                )
                # Gemini gets a confidence boost since it has richer context
                base_confidence = round((populated / 4) * 100, 1)
                if doc.confidence == 0.0:
                    doc.confidence = min(base_confidence + 15, 99.0)

                doc.file_name = file.filename
                logger.info(
                    "Gemini extraction succeeded for %s (confidence: %.1f%%)",
                    file.filename, doc.confidence
                )

            except Exception as exc:
                logger.warning(
                    "Gemini extraction failed for %s: %s — falling back to regex",
                    file.filename, exc
                )
                doc = _regex_parse(tmp_path, file.filename, raw_text, ocr_warnings)
        else:
            # ── Fallback: regex parser ─────────────────────────────────────────
            doc = _regex_parse(tmp_path, file.filename, raw_text, ocr_warnings)

        return JSONResponse(content=doc.model_dump(mode="json"))

    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def process_worker(
    tmp_path: str,
    filename: str,
    document_id: str,
    jwt_token: str
):
    """Background worker to process the document and update Supabase."""
    logger.info(f"Starting background processing for {filename} (ID: {document_id})")
    try:
        raw_text, ocr_warnings = extract_text(tmp_path)
        doc: ExtractedDocument

        # ── Try Gemini first ───────────────────────────────────────────
        if GEMINI_AVAILABLE:
            try:
                doc = parse_document_gemini(tmp_path, raw_text, ocr_warnings)
                populated = sum(
                    1 for field in [doc.vendor, doc.date, doc.total, doc.document_type]
                    if field and field not in ("", "unknown", None)
                )
                base_confidence = round((populated / 4) * 100, 1)
                if doc.confidence == 0.0:
                    doc.confidence = min(base_confidence + 15, 99.0)

                doc.file_name = filename
                logger.info(f"Gemini extraction succeeded for {filename}")
            except Exception as exc:
                logger.warning(f"Gemini failed for {filename}: {exc} — falling back to regex")
                doc = _regex_parse(tmp_path, filename, raw_text, ocr_warnings)
        else:
            doc = _regex_parse(tmp_path, filename, raw_text, ocr_warnings)

        # ── Update Supabase ────────────────────────────────────────────
        logger.info(f"Updating Supabase for document {document_id}")
        
        # Initialize client with user's JWT to pass RLS
        token = jwt_token.replace("Bearer ", "") if jwt_token else ""
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        
        # Use auth to bypass RLS safely
        # Note: If RLS is strict, we might need a service role key. We'll try user JWT first.
        supabase.postgrest.auth(token)
        
        # Convert date safely
        safe_date = None
        if doc.date:
            raw_date = str(doc.date)[:10]
            if len(raw_date) == 10 and raw_date.count("-") == 2:
                safe_date = raw_date

        update_payload = {
            "status": "processed",
            "document_type": doc.document_type or "unknown",
            "vendor": doc.vendor or None,
            "date": safe_date,
            "total": float(doc.total) if doc.total is not None else None,
            "tax": float(doc.tax) if doc.tax is not None else None,
            "confidence": float(doc.confidence) if doc.confidence is not None else None,
            "warnings": doc.warnings or [],
            "source_mode": doc.source_mode or "regex"
        }
        
        # Update Document
        res = supabase.table("documents").update(update_payload).eq("id", document_id).execute()
        
        # Insert Line Items
        if doc.line_items and len(doc.line_items) > 0 and len(res.data) > 0:
            user_id = res.data[0].get("user_id")
            line_items_data = [
                {
                    "document_id": document_id,
                    "user_id": user_id,
                    "description": li.description,
                    "quantity": li.quantity,
                    "unit_price": li.unit_price,
                    "total": li.total,
                    "confidence": li.confidence
                }
                for li in doc.line_items
            ]
            supabase.table("line_items").insert(line_items_data).execute()

        logger.info(f"Successfully processed and updated {filename} (ID: {document_id})")

    except Exception as exc:
        logger.error(f"Worker failed for {filename}: {exc}")
        # Mark as failed in DB
        try:
            token = jwt_token.replace("Bearer ", "") if jwt_token else ""
            supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
            supabase.postgrest.auth(token)
            supabase.table("documents").update({
                "status": "failed",
                "warnings": [f"Processing failed: {str(exc)}"]
            }).eq("id", document_id).execute()
        except Exception as update_exc:
            logger.error(f"Failed to update error status for {document_id}: {update_exc}")

    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@app.post("/api/process_async")
async def process_document_async(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    document_id: str = Form(...),
    authorization: str = Header(None)
):
    """
    Async endpoint. Accepts file, immediately returns 202 Accepted,
    and runs the extraction in the background.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=OUTPUT_DIR) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    background_tasks.add_task(
        process_worker,
        tmp_path=tmp_path,
        filename=file.filename,
        document_id=document_id,
        jwt_token=authorization
    )

    return JSONResponse(
        status_code=202,
        content={"message": "Accepted", "document_id": document_id, "status": "processing"}
    )


def _regex_parse(
    tmp_path: str,
    filename: str,
    raw_text: str,
    ocr_warnings: list,
) -> ExtractedDocument:
    """Run the legacy regex-based parser and stamp source_mode = 'regex'."""
    doc = parse_document(tmp_path, raw_text, ocr_warnings)
    doc.file_name = filename
    doc.source_mode = "regex"

    populated = sum(
        1 for field in [doc.vendor, doc.date, doc.total, doc.document_type]
        if field and field not in ("", "unknown", None)
    )
    doc.confidence = round((populated / 4) * 100, 1)
    return doc


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
