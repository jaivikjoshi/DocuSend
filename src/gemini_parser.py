"""
src/gemini_parser.py
──────────────────────────────────────────────────────────────────────────────
Tier-2 extraction engine: uses Gemini Flash multimodal structured output
to parse receipts and invoices directly from their visual representation.

Uses the modern `google-genai` SDK (v2+).

Strategy
--------
1. PDFs   → rendered to per-page PIL images via pypdfium2
2. Images → loaded directly as PIL images
3. All pages are passed as inline image parts to Gemini Flash
4. Gemini returns a JSON payload constrained to our extraction schema
5. On any failure the caller falls back to the legacy regex parser
"""
from __future__ import annotations

import io
import json
import logging
import os
from pathlib import Path
from typing import List, Optional

from PIL import Image

from .schema import ExtractedDocument, LineItem

logger = logging.getLogger(__name__)

# ── Gemini availability ────────────────────────────────────────────────────────
_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("Gemini_API_KEY")

GEMINI_AVAILABLE = False
_client = None

if _GEMINI_API_KEY:
    try:
        from google import genai  # type: ignore
        from google.genai import types as genai_types  # type: ignore

        _client = genai.Client(api_key=_GEMINI_API_KEY)
        GEMINI_AVAILABLE = True
        logger.info("Gemini AI (google-genai SDK) is available — Tier-2 parsing enabled.")
    except ImportError:
        logger.warning("google-genai not installed — falling back to regex parser.")
    except Exception as exc:
        logger.warning("Gemini configuration failed (%s) — falling back to regex parser.", exc)
else:
    logger.info("GEMINI_API_KEY not set — falling back to regex parser.")

# ── Constants ──────────────────────────────────────────────────────────────────
_MODEL_NAME = "gemini-2.0-flash"
_MAX_PDF_PAGES = 10
_PDF_RENDER_SCALE = 2.0  # ~150 DPI, good balance of quality vs token cost

_EXTRACTION_PROMPT = """You are a document data extraction API specializing in receipts and invoices.

Analyze the provided document image(s) and extract ALL available fields.

Rules:
- Return ONLY valid JSON — no markdown fences, no commentary, nothing outside the JSON object
- Use null for any field that is genuinely absent or unreadable
- For `date`, use ISO format YYYY-MM-DD when possible
- For `document_type`, use exactly "invoice", "receipt", or "unknown"
- For monetary amounts, return raw numbers (e.g. 12.50) not strings
- For `line_items`, extract every individual product/service line you can see
- For `confidence`, return a float 0-100 reflecting your overall extraction confidence
- For `warnings`, list any ambiguities, low-quality areas, or unclear fields as strings

Return a JSON object with this exact structure:
{
  "document_type": "invoice" | "receipt" | "unknown",
  "vendor": string | null,
  "date": string | null,
  "invoice_number": string | null,
  "currency": string,
  "subtotal": number | null,
  "tax": number | null,
  "tip": number | null,
  "discount": number | null,
  "total": number | null,
  "payment_method": string | null,
  "confidence": number,
  "warnings": [string],
  "line_items": [
    {
      "description": string,
      "quantity": number | null,
      "unit_price": number | null,
      "total": number | null,
      "confidence": number
    }
  ]
}"""


# ── Image helpers ──────────────────────────────────────────────────────────────

def _pil_to_bytes(image: Image.Image) -> bytes:
    """Convert a PIL image to JPEG bytes for the Gemini API."""
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _pdf_to_images(file_path: str) -> List[Image.Image]:
    """Render each PDF page to a PIL image using pypdfium2."""
    try:
        import pypdfium2 as pdfium  # type: ignore
    except ImportError:
        logger.warning("pypdfium2 not available — cannot render PDF for Gemini.")
        return []

    images: List[Image.Image] = []
    try:
        pdf = pdfium.PdfDocument(file_path)
        total = len(pdf)
        pages_to_render = min(total, _MAX_PDF_PAGES)
        if total > _MAX_PDF_PAGES:
            logger.info("PDF has %d pages; rendering first %d for Gemini.", total, _MAX_PDF_PAGES)

        for i in range(pages_to_render):
            try:
                page = pdf[i]
                bitmap = page.render(scale=_PDF_RENDER_SCALE)
                images.append(bitmap.to_pil())
                page.close()
            except Exception as exc:
                logger.warning("Failed to render PDF page %d: %s", i + 1, exc)
        pdf.close()
    except Exception as exc:
        logger.warning("Failed to open PDF for rendering: %s", exc)

    return images


def _load_images(file_path: str) -> List[Image.Image]:
    """Return a list of PIL images representing the document."""
    path = Path(file_path)
    if path.suffix.lower() == ".pdf":
        return _pdf_to_images(file_path)
    try:
        img = Image.open(file_path)
        img.load()
        return [img]
    except Exception as exc:
        logger.warning("Failed to open image file: %s", exc)
        return []


# ── Core Gemini call ───────────────────────────────────────────────────────────

def _call_gemini(
    file_name: str,
    images: List[Image.Image],
    raw_text: str,
) -> ExtractedDocument:
    """Call Gemini Flash and parse the structured JSON response."""
    assert _client is not None, "Gemini client not initialised"
    from google.genai import types as genai_types  # type: ignore

    # Build content parts
    content_parts: list = [_EXTRACTION_PROMPT]

    # Include OCR text as additional context for digital PDFs
    if raw_text and raw_text.strip():
        content_parts.append(
            f"\n\n--- OCR/extracted text (use as additional context) ---\n{raw_text[:8000]}\n---"
        )

    # Add image parts
    for img in images:
        content_parts.append(
            genai_types.Part.from_bytes(
                data=_pil_to_bytes(img),
                mime_type="image/jpeg",
            )
        )

    content_parts.append(
        f'\n\nExtract all fields from the above document. The file name is "{file_name}".'
    )

    response = _client.models.generate_content(
        model=_MODEL_NAME,
        contents=content_parts,
        config=genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        ),
    )

    raw_json = response.text.strip()

    # Strip accidental markdown fences just in case
    if raw_json.startswith("```"):
        lines = raw_json.split("\n")
        # Remove first and last lines (the fences)
        raw_json = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    parsed: dict = json.loads(raw_json)
    parsed["file_name"] = file_name

    # Coerce line_items
    raw_items = parsed.pop("line_items", []) or []
    line_items = []
    for item in raw_items:
        try:
            line_items.append(LineItem(**item))
        except Exception:
            pass

    doc = ExtractedDocument(line_items=line_items, source_mode="gemini", **parsed)
    return doc


# ── Public API ─────────────────────────────────────────────────────────────────

def parse_document_gemini(
    file_path: str,
    raw_text: str,
    ocr_warnings: Optional[List[str]] = None,
) -> ExtractedDocument:
    """
    Parse a receipt/invoice with Gemini Flash multimodal structured output.

    Raises RuntimeError if GEMINI_AVAILABLE is False.
    Raises on Gemini API / JSON parse errors (let caller decide to fall back).
    """
    if not GEMINI_AVAILABLE:
        raise RuntimeError("Gemini is not available (missing API key or package).")

    file_name = Path(file_path).name
    images = _load_images(file_path)

    if not images:
        raise ValueError(f"Could not load any images from '{file_name}'.")

    doc = _call_gemini(file_name, images, raw_text or "")

    # Merge upstream OCR warnings
    if ocr_warnings:
        existing = set(doc.warnings)
        for w in ocr_warnings:
            if w not in existing:
                doc.warnings.append(w)

    return doc
