from typing import Iterable, List

from .schema import ExtractedDocument
from .utils import KNOWN_CURRENCIES, safe_float


TOTAL_TOLERANCE = 0.03


def _dedupe_warnings(warnings: Iterable[str]) -> List[str]:
    seen = set()
    deduped = []
    for warning in warnings:
        if warning and warning not in seen:
            seen.add(warning)
            deduped.append(warning)
    return deduped


def validate_document(document: ExtractedDocument) -> ExtractedDocument:
    warnings = list(document.warnings)

    document.subtotal = safe_float(document.subtotal)
    document.tax = safe_float(document.tax)
    document.tip = safe_float(document.tip)
    document.discount = safe_float(document.discount)
    document.total = safe_float(document.total)

    if not document.raw_text.strip():
        warnings.append("No raw text was extracted from this document.")
    if not document.vendor:
        warnings.append("Vendor could not be detected.")
    if not document.date:
        warnings.append("Date could not be detected.")
    if document.total is None:
        warnings.append("Total could not be detected.")
    if document.currency not in KNOWN_CURRENCIES:
        warnings.append("Currency is unknown.")

    money_fields = {
        "subtotal": document.subtotal,
        "tax": document.tax,
        "tip": document.tip,
        "discount": document.discount,
        "total": document.total,
    }
    for field, value in money_fields.items():
        if value is not None and value < 0:
            warnings.append(f"{field.replace('_', ' ').title()} is negative.")

    if document.total is not None and document.total > 10000:
        warnings.append("Total looks unusually high. Please review.")

    if document.subtotal is not None and document.total is not None:
        expected = document.subtotal + (document.tax or 0) + (document.tip or 0) - (document.discount or 0)
        if abs(expected - document.total) > TOTAL_TOLERANCE:
            warnings.append("Subtotal, tax, tip, and discount do not reconcile with total.")

    score = 0
    if document.vendor:
        score += 20
    if document.date:
        score += 20
    if document.total is not None:
        score += 25
    if document.subtotal is not None or document.tax is not None:
        score += 15
    if document.line_items:
        score += 10
    if not warnings:
        score += 10

    document.confidence = float(min(score, 100))
    document.warnings = _dedupe_warnings(warnings)
    return document
