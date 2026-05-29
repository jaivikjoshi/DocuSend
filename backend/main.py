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
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, List

# ── make sure the repo root is on PYTHONPATH so `src.*` imports work ──────────
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")

from fastapi import FastAPI, File, HTTPException, UploadFile, BackgroundTasks, Header
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
    expose_headers=["Content-Disposition"],
)

OUTPUT_DIR = REPO_ROOT / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tiff", ".tif"}
STORAGE_BUCKET = "documents"


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


class ProcessAsyncRequest(BaseModel):
    document_id: str
    storage_path: str


def _bearer_token(authorization: str | None) -> str:
    return authorization.replace("Bearer ", "", 1).strip() if authorization else ""


def _authed_supabase(token: str) -> Client:
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise RuntimeError("Supabase environment variables are not configured.")
    client: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    client.postgrest.auth(token)
    return client


def _fetch_owned_document(supabase: Client, document_id: str) -> dict | None:
    response = (
        supabase
        .table("documents")
        .select("*")
        .eq("id", document_id)
        .single()
        .execute()
    )
    return response.data


def _download_storage_object(storage_path: str, suffix: str, token: str) -> str:
    quoted_path = urllib.parse.quote(storage_path, safe="/")
    url = f"{SUPABASE_URL}/storage/v1/object/{STORAGE_BUCKET}/{quoted_path}"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "apikey": SUPABASE_ANON_KEY or "",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=OUTPUT_DIR) as tmp:
                shutil.copyfileobj(response, tmp)
                return tmp.name
    except urllib.error.HTTPError as exc:
        raise ValueError(f"Storage download failed with HTTP {exc.code}.") from exc


def process_worker(
    document_id: str,
    storage_path: str,
    jwt_token: str
):
    """Background worker to download a private upload, process it, and update Supabase."""
    logger.info("Starting background processing for document %s", document_id)
    tmp_path = None
    try:
        token = _bearer_token(jwt_token)
        supabase = _authed_supabase(token)
        existing = _fetch_owned_document(supabase, document_id)
        if not existing:
            raise ValueError("Document not found for this user.")
        if existing.get("storage_path") != storage_path:
            raise ValueError("Storage path does not match the document record.")
        if existing.get("status") in {"processed", "review"} and existing.get("raw_text"):
            logger.info("Skipping already processed document %s", document_id)
            return

        filename = existing.get("file_name") or Path(storage_path).name
        suffix = Path(filename).suffix.lower() or Path(storage_path).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise ValueError(f"Unsupported file type '{suffix}'.")

        tmp_path = _download_storage_object(storage_path, suffix, token)
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
        logger.info("Updating Supabase for document %s", document_id)
        safe_date = None
        if doc.date:
            raw_date = str(doc.date)[:10]
            if len(raw_date) == 10 and raw_date.count("-") == 2:
                safe_date = raw_date

        update_payload = {
            "status": doc.status or "processed",
            "document_type": doc.document_type or "unknown",
            "vendor": doc.vendor or None,
            "document_date": safe_date,
            "invoice_number": doc.invoice_number,
            "currency": doc.currency or "USD",
            "subtotal": float(doc.subtotal) if doc.subtotal is not None else None,
            "total": float(doc.total) if doc.total is not None else None,
            "tax": float(doc.tax) if doc.tax is not None else None,
            "tip": float(doc.tip) if doc.tip is not None else None,
            "discount": float(doc.discount) if doc.discount is not None else None,
            "payment_method": doc.payment_method,
            "raw_text": doc.raw_text or raw_text,
            "confidence": float(doc.confidence) if doc.confidence is not None else None,
            "warnings": doc.warnings or [],
            "source_mode": doc.source_mode if doc.source_mode in {"gemini", "regex"} else "regex",
        }
        
        res = supabase.table("documents").update(update_payload).eq("id", document_id).execute()
        
        if doc.line_items and len(doc.line_items) > 0 and len(res.data) > 0:
            user_id = res.data[0].get("user_id")
            supabase.table("line_items").delete().eq("document_id", document_id).execute()
            line_items_data = [
                {
                    "document_id": document_id,
                    "user_id": user_id,
                    "description": li.description,
                    "quantity": li.quantity,
                    "unit_price": li.unit_price,
                    "total": li.total,
                    "confidence": li.confidence,
                    "row_index": idx,
                }
                for idx, li in enumerate(doc.line_items)
            ]
            supabase.table("line_items").insert(line_items_data).execute()

        logger.info("Successfully processed and updated %s (ID: %s)", filename, document_id)

    except Exception as exc:
        logger.error("Worker failed for document %s: %s", document_id, exc)
        try:
            supabase = _authed_supabase(_bearer_token(jwt_token))
            supabase.table("documents").update({
                "status": "failed",
                "warnings": [f"Processing failed: {str(exc)}"]
            }).eq("id", document_id).execute()
        except Exception as update_exc:
            logger.error(f"Failed to update error status for {document_id}: {update_exc}")

    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


@app.post("/api/process_async")
async def process_document_async(
    background_tasks: BackgroundTasks,
    request: ProcessAsyncRequest,
    authorization: str = Header(None)
):
    """
    Async endpoint. Accepts a document row + storage path, immediately returns
    202 Accepted, and runs the extraction in the background.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    background_tasks.add_task(
        process_worker,
        document_id=request.document_id,
        storage_path=request.storage_path,
        jwt_token=authorization,
    )

    return JSONResponse(
        status_code=202,
        content={"message": "Accepted", "document_id": request.document_id, "status": "processing"}
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
    document_ids: List[str]
    format: str = "csv_zip"


@app.post("/api/export")
async def export_documents(request: ExportRequest, authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    if not request.document_ids:
        raise HTTPException(status_code=400, detail="No documents provided for export.")
    if request.format not in ("json", "csv_zip"):
        raise HTTPException(status_code=400, detail="format must be 'json' or 'csv_zip'.")

    supabase = _authed_supabase(_bearer_token(authorization))
    response = (
        supabase
        .table("documents")
        .select("*, line_items(*)")
        .in_("id", request.document_ids)
        .execute()
    )
    rows = response.data or []
    if len(rows) != len(set(request.document_ids)):
        raise HTTPException(status_code=404, detail="One or more documents were not found for this user.")

    docs = [_document_row_to_extracted(row) for row in rows]

    json_path, zip_path = write_export_files(docs)

    if request.format == "json":
        return FileResponse(path=json_path, media_type="application/json", filename=Path(json_path).name)
    else:
        return FileResponse(path=zip_path, media_type="application/zip", filename=Path(zip_path).name)


def _document_row_to_extracted(row: dict) -> ExtractedDocument:
    line_items = sorted(row.get("line_items") or [], key=lambda li: li.get("row_index") or 0)
    return ExtractedDocument(
        file_name=row.get("file_name") or "document",
        status=row.get("status") or "processed",
        document_type=row.get("document_type") or "unknown",
        vendor=row.get("vendor") or "",
        date=str(row.get("document_date") or ""),
        invoice_number=row.get("invoice_number"),
        currency=row.get("currency") or "USD",
        subtotal=_num(row.get("subtotal")),
        tax=_num(row.get("tax")),
        tip=_num(row.get("tip")),
        discount=_num(row.get("discount")),
        total=_num(row.get("total")),
        payment_method=row.get("payment_method"),
        raw_text=row.get("raw_text") or "",
        confidence=_num(row.get("confidence")) or 0.0,
        warnings=row.get("warnings") or [],
        source_mode=row.get("source_mode") or "regex",
        line_items=[
            {
                "description": item.get("description") or "",
                "quantity": _num(item.get("quantity")),
                "unit_price": _num(item.get("unit_price")),
                "total": _num(item.get("total")),
                "confidence": _num(item.get("confidence")) or 0.0,
            }
            for item in line_items
        ],
    )


def _num(value: Any) -> float | None:
    return float(value) if value is not None else None
