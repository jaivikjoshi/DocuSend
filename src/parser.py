import re
from pathlib import Path
from typing import List, Optional

from .schema import ExtractedDocument, LineItem
from .utils import detect_currency, money_from_match, normalize_date


DATE_PATTERNS = [
    r"\b\d{4}-\d{1,2}-\d{1,2}\b",
    r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
    r"\b\d{1,2}-\d{1,2}-\d{2,4}\b",
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+\d{2,4}\b",
    r"\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{2,4}\b",
]

FIELD_LABELS = {
    "subtotal": [r"\bsubtotal\b", r"\bsub\s+total\b"],
    "tax": [r"\btax\b", r"\bvat\b", r"\bgst\b", r"\bhst\b"],
    "tip": [r"\btip\b", r"\bgratuity\b"],
    "discount": [r"\bdiscount\b", r"\bcoupon\b"],
    "total": [r"\bgrand\s+total\b", r"\bamount\s+due\b", r"\bbalance\s+due\b", r"\btotal\s+due\b", r"\btotal\b"],
}

PAYMENT_PATTERNS = [
    (r"\bvisa\b", "Visa"),
    (r"\bmaster\s?card\b", "Mastercard"),
    (r"\bamex\b|\bamerican express\b", "Amex"),
    (r"\bdiscover\b", "Discover"),
    (r"\bcash\b", "Cash"),
    (r"\bdebit\b", "Debit"),
    (r"\bcredit\b", "Credit Card"),
]


def _clean_lines(raw_text: str) -> List[str]:
    return [line.strip() for line in raw_text.splitlines() if line.strip()]


def _extract_labeled_amount(lines: List[str], field: str) -> Optional[float]:
    patterns = FIELD_LABELS[field]

    for line in reversed(lines):
        lower = line.lower()
        if field == "total" and re.search(r"\bsub\s*total\b", lower):
            continue

        if any(re.search(pattern, lower) for pattern in patterns):
            amount = money_from_match(line)
            if amount is not None:
                return amount

    return None


def _extract_date(raw_text: str) -> tuple[str, Optional[str]]:
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, raw_text, flags=re.IGNORECASE)
        if match:
            return normalize_date(match.group(0))
    return "", None


def _extract_invoice_number(raw_text: str) -> Optional[str]:
    patterns = [
        r"\b(?:invoice|inv)\s*(?:number|no|#)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9-]{2,})\b",
        r"\b(?:receipt|rcpt)\s*(?:number|no|#)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9-]{2,})\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, raw_text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _extract_payment_method(raw_text: str) -> Optional[str]:
    for pattern, label in PAYMENT_PATTERNS:
        if re.search(pattern, raw_text, flags=re.IGNORECASE):
            return label
    return None


def _detect_document_type(raw_text: str) -> str:
    lower = raw_text.lower()
    if "invoice" in lower or "amount due" in lower or "balance due" in lower:
        return "invoice"
    if "receipt" in lower or "cashier" in lower or "change" in lower:
        return "receipt"
    return "unknown"


def _extract_vendor(lines: List[str]) -> str:
    skipped_patterns = [
        r"\binvoice\b",
        r"\breceipt\b",
        r"\bdate\b",
        r"\btotal\b",
        r"\btax\b",
        r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
        r"\$\s?\d",
    ]

    for line in lines[:8]:
        if len(line) < 2:
            continue
        lower = line.lower()
        if any(re.search(pattern, lower) for pattern in skipped_patterns):
            continue
        return line[:80]

    return lines[0][:80] if lines else ""


def _extract_line_items(lines: List[str]) -> List[LineItem]:
    items: List[LineItem] = []
    label_words = ("subtotal", "total", "tax", "tip", "discount", "amount due", "balance due", "change")

    for line in lines:
        lower = line.lower()
        if any(word in lower for word in label_words):
            continue

        match = re.search(r"(.+?)\s+(-?\$?\s?\d+(?:\.\d{2}))\s*$", line)
        if not match:
            continue

        description = re.sub(r"\s{2,}", " ", match.group(1)).strip(" -")
        amount = money_from_match(match.group(2))

        if not description or amount is None:
            continue
        if len(description) < 3 or re.fullmatch(r"[\d\s./-]+", description):
            continue

        items.append(LineItem(description=description[:120], total=amount, confidence=45.0))

        if len(items) >= 40:
            break

    return items


def _count_total_candidates(lines: List[str]) -> int:
    count = 0
    for line in lines:
        lower = line.lower()
        if "subtotal" in lower:
            continue
        if re.search(r"\b(total|amount due|balance due|total due|grand total)\b", lower):
            if money_from_match(line) is not None:
                count += 1
    return count


def parse_document(file_path: str, raw_text: str, ocr_warnings: Optional[List[str]] = None) -> ExtractedDocument:
    lines = _clean_lines(raw_text)
    warnings = list(ocr_warnings or [])

    currency, currency_warning = detect_currency(raw_text)
    if currency_warning:
        warnings.append(currency_warning)

    date, date_warning = _extract_date(raw_text)
    if date_warning:
        warnings.append(date_warning)

    total_candidate_count = _count_total_candidates(lines)
    if total_candidate_count > 1:
        warnings.append("Multiple total-like amounts were found; please review the selected total.")

    return ExtractedDocument(
        file_name=Path(file_path).name,
        document_type=_detect_document_type(raw_text),
        vendor=_extract_vendor(lines),
        date=date,
        invoice_number=_extract_invoice_number(raw_text),
        currency=currency,
        subtotal=_extract_labeled_amount(lines, "subtotal"),
        tax=_extract_labeled_amount(lines, "tax"),
        tip=_extract_labeled_amount(lines, "tip"),
        discount=_extract_labeled_amount(lines, "discount"),
        total=_extract_labeled_amount(lines, "total"),
        payment_method=_extract_payment_method(raw_text),
        line_items=_extract_line_items(lines),
        raw_text=raw_text,
        warnings=warnings,
    )
