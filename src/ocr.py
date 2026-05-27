from pathlib import Path
from typing import List, Tuple

import pdfplumber
import pytesseract
from PIL import Image, ImageEnhance, ImageOps

from .utils import is_supported_file


def _prepare_image(path: str) -> Image.Image:
    image = Image.open(path).convert("RGB")
    image = ImageOps.exif_transpose(image)
    image = ImageOps.grayscale(image)
    image = ImageEnhance.Contrast(image).enhance(1.4)
    return image


def _extract_image_text(path: str) -> Tuple[str, List[str]]:
    warnings: List[str] = []
    try:
        image = _prepare_image(path)
        text = pytesseract.image_to_string(image)
    except pytesseract.TesseractNotFoundError:
        return "", ["Tesseract is not installed or not available in this environment."]
    except Exception as exc:
        return "", [f"OCR failed for image: {exc}"]

    if not text.strip():
        warnings.append("No readable text was found in the image.")

    return text, warnings


def _extract_pdf_text(path: str) -> Tuple[str, List[str]]:
    warnings: List[str] = []
    page_texts: List[str] = []

    try:
        with pdfplumber.open(path) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    page_texts.append(page_text)
                else:
                    warnings.append(f"Page {page_number} did not contain selectable text.")
    except Exception as exc:
        return "", [f"PDF text extraction failed: {exc}"]

    text = "\n\n".join(page_texts)
    if not text.strip():
        warnings.append("No readable PDF text was found. Scanned PDFs need OCR rendering support.")

    return text, warnings


def extract_text(file_path: str) -> Tuple[str, List[str]]:
    path = Path(file_path)
    if not is_supported_file(file_path):
        return "", [f"Unsupported file type: {path.suffix or 'unknown'}"]

    if path.suffix.lower() == ".pdf":
        return _extract_pdf_text(file_path)

    return _extract_image_text(file_path)
