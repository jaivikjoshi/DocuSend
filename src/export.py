import csv
import json
import uuid
import zipfile
from pathlib import Path
from typing import Iterable, List, Tuple

import pandas as pd

from .schema import EDITABLE_DOCUMENT_COLUMNS, LINE_ITEM_COLUMNS, ExtractedDocument


OUTPUT_DIR = Path("outputs")


def documents_to_rows(documents: Iterable[ExtractedDocument]) -> List[dict]:
    rows = []
    for document in documents:
        rows.append(
            {
                "file_name": document.file_name,
                "status": document.status,
                "document_type": document.document_type,
                "vendor": document.vendor,
                "date": document.date,
                "invoice_number": document.invoice_number,
                "currency": document.currency,
                "subtotal": document.subtotal,
                "tax": document.tax,
                "tip": document.tip,
                "discount": document.discount,
                "total": document.total,
                "payment_method": document.payment_method,
                "confidence": document.confidence,
                "warnings": " | ".join(document.warnings),
            }
        )
    return rows


def line_items_to_rows(documents: Iterable[ExtractedDocument]) -> List[dict]:
    rows = []
    for document in documents:
        for item in document.line_items:
            rows.append(
                {
                    "file_name": document.file_name,
                    "description": item.description,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "total": item.total,
                    "confidence": item.confidence,
                }
            )
    return rows


def accounting_to_rows(documents: Iterable[ExtractedDocument]) -> List[dict]:
    rows = []
    for document in documents:
        needs_review = document.status == "review" or bool(document.warnings)
        category = "Office Supplies" if document.document_type in {"invoice", "receipt"} else "Uncategorized"
        rows.append(
            {
                "Date": document.date,
                "Payee": document.vendor,
                "Description": document.invoice_number or document.file_name,
                "Category": category,
                "Amount": document.total,
                "Tax": document.tax,
                "Currency": document.currency,
                "Payment Method": document.payment_method,
                "Receipt File": document.file_name,
                "Review Required": "Yes" if needs_review else "No",
                "Warnings": " | ".join(document.warnings),
            }
        )
    return rows


def write_export_files(documents: List[ExtractedDocument]) -> Tuple[str, str]:
    OUTPUT_DIR.mkdir(exist_ok=True)
    export_id = uuid.uuid4().hex[:10]

    json_path = OUTPUT_DIR / f"docs_send_export_{export_id}.json"
    zip_path = OUTPUT_DIR / f"docs_send_csv_{export_id}.zip"
    documents_csv_path = OUTPUT_DIR / f"documents_{export_id}.csv"
    line_items_csv_path = OUTPUT_DIR / f"line_items_{export_id}.csv"

    payload = [document.model_dump(mode="json") for document in documents]
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    pd.DataFrame(documents_to_rows(documents), columns=EDITABLE_DOCUMENT_COLUMNS).to_csv(documents_csv_path, index=False)
    pd.DataFrame(line_items_to_rows(documents), columns=LINE_ITEM_COLUMNS).to_csv(line_items_csv_path, index=False)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(documents_csv_path, arcname="documents.csv")
        archive.write(line_items_csv_path, arcname="line_items.csv")

    return str(json_path), str(zip_path)


def write_accounting_csv(documents: List[ExtractedDocument]) -> str:
    OUTPUT_DIR.mkdir(exist_ok=True)
    export_id = uuid.uuid4().hex[:10]
    csv_path = OUTPUT_DIR / f"docusend_accounting_{export_id}.csv"
    rows = accounting_to_rows(documents)
    columns = [
        "Date",
        "Payee",
        "Description",
        "Category",
        "Amount",
        "Tax",
        "Currency",
        "Payment Method",
        "Receipt File",
        "Review Required",
        "Warnings",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return str(csv_path)
