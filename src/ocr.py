from pathlib import Path
from typing import Dict, List, Tuple

import pdfplumber
import pypdfium2 as pdfium
import pytesseract
from PIL import Image, ImageEnhance, ImageOps

from .utils import is_supported_file


MAX_OCR_PDF_PAGES = 12
PDF_RENDER_SCALE = 2.5


def _prepare_pil_image(image: Image.Image) -> Image.Image:
    image = image.convert("RGB")
    image = ImageOps.exif_transpose(image)
    image = ImageOps.grayscale(image)
    image = ImageEnhance.Contrast(image).enhance(1.4)
    return image


def _ocr_pil_image(image: Image.Image) -> str:
    prepared = _prepare_pil_image(image)
    return pytesseract.image_to_string(prepared)


def _extract_image_text(path: str) -> Tuple[str, List[str]]:
    warnings: List[str] = []
    try:
        text = _ocr_pil_image(Image.open(path))
    except pytesseract.TesseractNotFoundError:
        return "", ["Tesseract is not installed or not available in this environment."]
    except Exception as exc:
        return "", [f"OCR failed for image: {exc}"]

    if not text.strip():
        warnings.append("No readable text was found in the image.")

    return text, warnings


def _ocr_pdf_pages(path: str, page_numbers: List[int]) -> Tuple[Dict[int, str], List[str]]:
    warnings: List[str] = []
    page_texts: Dict[int, str] = {}

    if not page_numbers:
        return page_texts, warnings

    if len(page_numbers) > MAX_OCR_PDF_PAGES:
        skipped_count = len(page_numbers) - MAX_OCR_PDF_PAGES
        warnings.append(f"OCR fallback was limited to the first {MAX_OCR_PDF_PAGES} scanned PDF pages.")
        warnings.append(f"{skipped_count} scanned PDF pages were skipped to avoid a long OCR run.")
        page_numbers = page_numbers[:MAX_OCR_PDF_PAGES]

    try:
        pdf = pdfium.PdfDocument(path)
    except Exception as exc:
        return page_texts, [f"Could not render scanned PDF pages for OCR: {exc}"]

    try:
        for page_number in page_numbers:
            try:
                page = pdf[page_number - 1]
                bitmap = page.render(scale=PDF_RENDER_SCALE)
                image = bitmap.to_pil()
                page_text = _ocr_pil_image(image).strip()
                if page_text:
                    page_texts[page_number] = page_text
                else:
                    warnings.append(f"OCR fallback found no readable text on PDF page {page_number}.")
            except pytesseract.TesseractNotFoundError:
                return page_texts, ["Tesseract is not installed or not available in this environment."]
            except Exception as exc:
                warnings.append(f"OCR fallback failed on PDF page {page_number}: {exc}")
            finally:
                try:
                    page.close()
                except Exception:
                    pass
    finally:
        try:
            pdf.close()
        except Exception:
            pass

    return page_texts, warnings


def _extract_pdf_text(path: str) -> Tuple[str, List[str]]:
    warnings: List[str] = []
    page_texts: Dict[int, str] = {}
    scanned_pages: List[int] = []
    total_pages = 0

    try:
        with pdfplumber.open(path) as pdf:
            total_pages = len(pdf.pages)
            for page_number, page in enumerate(pdf.pages, start=1):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    page_texts[page_number] = page_text.strip()
                else:
                    scanned_pages.append(page_number)
    except Exception as exc:
        return "", [f"PDF text extraction failed: {exc}"]

    if scanned_pages:
        warnings.append("Some PDF pages did not contain selectable text; OCR fallback was used.")
        ocr_page_texts, ocr_warnings = _ocr_pdf_pages(path, scanned_pages)
        page_texts.update(ocr_page_texts)
        warnings.extend(ocr_warnings)

    text = "\n\n".join(page_texts[page_number] for page_number in range(1, total_pages + 1) if page_texts.get(page_number))
    if not text.strip():
        warnings.append("No readable PDF text was found.")

    return text, warnings


def extract_text(file_path: str) -> Tuple[str, List[str]]:
    path = Path(file_path)
    if not is_supported_file(file_path):
        return "", [f"Unsupported file type: {path.suffix or 'unknown'}"]

    if path.suffix.lower() == ".pdf":
        return _extract_pdf_text(file_path)

    return _extract_image_text(file_path)
