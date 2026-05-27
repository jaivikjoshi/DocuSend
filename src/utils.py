import re
from pathlib import Path
from typing import Iterable, Optional

from dateutil import parser as date_parser


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
KNOWN_CURRENCIES = {"USD", "CAD", "EUR", "GBP", "INR", "AUD", "NZD"}

CURRENCY_SYMBOLS = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "₹": "INR",
}


def is_supported_file(file_path: str) -> bool:
    return Path(file_path).suffix.lower() in SUPPORTED_EXTENSIONS


def safe_float(value: object) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, float):
        return value
    if isinstance(value, int):
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    text = text.replace(",", "")
    match = re.search(r"-?\d+(?:\.\d{1,2})?", text)
    if not match:
        return None

    try:
        return round(float(match.group(0)), 2)
    except ValueError:
        return None


def money_from_match(text: str) -> Optional[float]:
    match = re.search(r"-?\$?\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})|-?\$?\s?\d+(?:\.\d{2})", text)
    if not match:
        return None
    return safe_float(match.group(0))


def normalize_date(value: str) -> tuple[str, Optional[str]]:
    if not value:
        return "", None

    try:
        parsed = date_parser.parse(value, fuzzy=True, dayfirst=False)
    except (ValueError, OverflowError):
        return "", "Date could not be normalized."

    warning = None
    if re.search(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", value):
        warning = "Date format may be ambiguous."

    return parsed.date().isoformat(), warning


def detect_currency(text: str) -> tuple[str, Optional[str]]:
    upper_text = text.upper()
    for currency in KNOWN_CURRENCIES:
        if re.search(rf"\b{currency}\b", upper_text):
            return currency, None

    for symbol, currency in CURRENCY_SYMBOLS.items():
        if symbol in text:
            return currency, None

    return "USD", "Currency was not detected; defaulted to USD."


def first_non_empty(lines: Iterable[str]) -> str:
    for line in lines:
        cleaned = line.strip()
        if cleaned:
            return cleaned
    return ""


def confidence_label(score: float) -> str:
    if score >= 80:
        return "High"
    if score >= 50:
        return "Medium"
    return "Low"
