from pathlib import Path
from typing import List, Optional

import gradio as gr
import pandas as pd

from src.export import documents_to_rows, line_items_to_rows, write_export_files
from src.ocr import extract_text
from src.parser import parse_document
from src.schema import EDITABLE_DOCUMENT_COLUMNS, LINE_ITEM_COLUMNS, ExtractedDocument, LineItem
from src.utils import confidence_label, is_supported_file, safe_float
from src.validation import validate_document


MAX_BATCH_FILES = 20

DOCUSEND_CSS = """
:root {
    --ink: #091413;
    --pine: #285A48;
    --sage: #408A71;
    --mint: #B0E4CC;
    --surface: #FFFFFF;
    --soft: #F6FAF8;
    --line: #E4EBE8;
    --muted: #60706C;
    --warning: #C98A05;
}

body,
.gradio-container {
    background: var(--surface) !important;
    color: var(--ink) !important;
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
}

.gradio-container {
    max-width: none !important;
}

button.primary,
.primary {
    background: var(--pine) !important;
    border-color: var(--pine) !important;
    color: white !important;
}

button.secondary {
    border-color: var(--line) !important;
    color: var(--ink) !important;
}

.docs-card {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 8px;
    box-shadow: 0 10px 28px rgba(9, 20, 19, 0.06);
}

.docs-muted {
    color: var(--muted);
}
"""


def _empty_documents_df() -> pd.DataFrame:
    return pd.DataFrame(columns=EDITABLE_DOCUMENT_COLUMNS)


def _empty_line_items_df() -> pd.DataFrame:
    return pd.DataFrame(columns=LINE_ITEM_COLUMNS)


def _warning_markdown(documents: List[ExtractedDocument]) -> str:
    if not documents:
        return "No documents processed yet."

    sections = []
    for document in documents:
        label = confidence_label(document.confidence)
        if document.warnings:
            warning_lines = "\n".join(f"- {warning}" for warning in document.warnings)
        else:
            warning_lines = "- No warnings."
        sections.append(f"### {document.file_name} - {label} confidence ({document.confidence:.0f}%)\n{warning_lines}")
    return "\n\n".join(sections)


def _raw_text_bundle(documents: List[ExtractedDocument]) -> str:
    if not documents:
        return ""

    chunks = []
    for document in documents:
        text = document.raw_text.strip() or "No raw text available."
        chunks.append(f"===== {document.file_name} =====\n{text}")
    return "\n\n".join(chunks)


def _failed_document(file_path: str, message: str) -> ExtractedDocument:
    return validate_document(
        ExtractedDocument(
            file_name=Path(file_path).name,
            status="failed",
            raw_text="",
            warnings=[message],
        )
    )


def _tables_and_exports(documents: List[ExtractedDocument]):
    json_path, csv_zip_path = write_export_files(documents)
    return (
        documents,
        pd.DataFrame(documents_to_rows(documents), columns=EDITABLE_DOCUMENT_COLUMNS),
        pd.DataFrame(line_items_to_rows(documents), columns=LINE_ITEM_COLUMNS),
        _warning_markdown(documents),
        _raw_text_bundle(documents),
        [document.model_dump(mode="json") for document in documents],
        json_path,
        csv_zip_path,
    )


def process_files(files: Optional[List[str]]):
    if not files:
        return (
            [],
            _empty_documents_df(),
            _empty_line_items_df(),
            "Upload at least one receipt or invoice to start.",
            "",
            {},
            None,
            None,
        )

    files = files[:MAX_BATCH_FILES]
    documents: List[ExtractedDocument] = []

    for file_path in files:
        if not is_supported_file(file_path):
            documents.append(_failed_document(file_path, "Unsupported file type. Upload JPG, PNG, or PDF."))
            continue

        raw_text, ocr_warnings = extract_text(file_path)
        try:
            document = parse_document(file_path, raw_text, ocr_warnings)
            documents.append(validate_document(document))
        except Exception as exc:
            documents.append(_failed_document(file_path, f"Could not process this file: {exc}"))

    return _tables_and_exports(documents)


def _as_dataframe(value, columns: List[str]) -> pd.DataFrame:
    if value is None:
        return pd.DataFrame(columns=columns)
    if isinstance(value, pd.DataFrame):
        return value.reindex(columns=columns)
    return pd.DataFrame(value, columns=columns)


def revalidate_edited(document_rows, line_item_rows, current_documents):
    if document_rows is None or len(document_rows) == 0:
        return process_files([])

    document_df = _as_dataframe(document_rows, EDITABLE_DOCUMENT_COLUMNS)
    line_df = _as_dataframe(line_item_rows, LINE_ITEM_COLUMNS)
    existing_by_file = {document.file_name: document for document in current_documents or []}

    documents: List[ExtractedDocument] = []
    for _, row in document_df.iterrows():
        file_name = str(row.get("file_name", "")).strip()
        original = existing_by_file.get(file_name)

        matching_items = line_df[line_df["file_name"] == file_name] if "file_name" in line_df else _empty_line_items_df()
        line_items = [
            LineItem(
                description=str(item.get("description", "") or ""),
                quantity=safe_float(item.get("quantity")),
                unit_price=safe_float(item.get("unit_price")),
                total=safe_float(item.get("total")),
                confidence=safe_float(item.get("confidence")) or 0.0,
            )
            for _, item in matching_items.iterrows()
        ]

        document = ExtractedDocument(
            file_name=file_name,
            status=str(row.get("status", "processed") or "processed"),
            document_type=str(row.get("document_type", "unknown") or "unknown"),
            vendor=str(row.get("vendor", "") or ""),
            date=str(row.get("date", "") or ""),
            invoice_number=str(row.get("invoice_number", "") or "") or None,
            currency=str(row.get("currency", "USD") or "USD").upper(),
            subtotal=safe_float(row.get("subtotal")),
            tax=safe_float(row.get("tax")),
            tip=safe_float(row.get("tip")),
            discount=safe_float(row.get("discount")),
            total=safe_float(row.get("total")),
            payment_method=str(row.get("payment_method", "") or "") or None,
            line_items=line_items,
            raw_text=original.raw_text if original else "",
            warnings=[],
        )
        documents.append(validate_document(document))

    return _tables_and_exports(documents)


with gr.Blocks(title="DocuSend") as demo:
    gr.Markdown(
        """
        # DocuSend
        """
    )

    document_state = gr.State([])

    with gr.Row():
        with gr.Column(scale=1):
            files_input = gr.Files(
                label="Receipts / Invoices",
                file_count="multiple",
                file_types=[".jpg", ".jpeg", ".png", ".pdf"],
                type="filepath",
            )
            with gr.Row():
                extract_button = gr.Button("Extract", variant="primary")
                revalidate_button = gr.Button("Revalidate Edits")

            json_download = gr.File(label="Download JSON")
            csv_download = gr.File(label="Download CSV ZIP")

        with gr.Column(scale=2):
            documents_table = gr.Dataframe(
                value=_empty_documents_df(),
                headers=EDITABLE_DOCUMENT_COLUMNS,
                datatype=["str"] * len(EDITABLE_DOCUMENT_COLUMNS),
                label="Editable Document Fields",
                interactive=True,
                wrap=True,
            )

    with gr.Tabs():
        with gr.Tab("Line Items"):
            line_items_table = gr.Dataframe(
                value=_empty_line_items_df(),
                headers=LINE_ITEM_COLUMNS,
                datatype=["str"] * len(LINE_ITEM_COLUMNS),
                label="Editable Line Items",
                interactive=True,
                wrap=True,
            )
        with gr.Tab("Warnings"):
            warnings_output = gr.Markdown("No documents processed yet.")
        with gr.Tab("Raw OCR Text"):
            raw_text_output = gr.Textbox(label="Raw OCR Text", lines=18, interactive=False)
        with gr.Tab("JSON Preview"):
            json_preview = gr.JSON(label="Structured Output")

    extract_button.click(
        process_files,
        inputs=[files_input],
        outputs=[
            document_state,
            documents_table,
            line_items_table,
            warnings_output,
            raw_text_output,
            json_preview,
            json_download,
            csv_download,
        ],
    )

    revalidate_button.click(
        revalidate_edited,
        inputs=[documents_table, line_items_table, document_state],
        outputs=[
            document_state,
            documents_table,
            line_items_table,
            warnings_output,
            raw_text_output,
            json_preview,
            json_download,
            csv_download,
        ],
    )


if __name__ == "__main__":
    demo.launch()
