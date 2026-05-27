from pathlib import Path
from html import escape
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

.app-shell {
    display: grid;
    grid-template-columns: 280px minmax(0, 1fr);
    min-height: 100vh;
}

.sidebar {
    border-right: 1px solid var(--line);
    padding: 32px 22px;
    display: flex;
    flex-direction: column;
    gap: 28px;
    min-height: 100vh;
    background: rgba(246, 250, 248, 0.55);
}

.sidebar-wrap {
    padding: 0 !important;
}

.brand {
    align-items: center;
    display: flex;
    gap: 14px;
    font-size: 28px;
    font-weight: 750;
    letter-spacing: 0;
}

.brand-mark {
    align-items: center;
    background: var(--pine);
    border-radius: 7px;
    color: white;
    display: inline-flex;
    height: 36px;
    justify-content: center;
    width: 36px;
}

.nav-stack {
    display: grid;
    gap: 10px;
    margin-top: 22px;
}

.nav-item {
    align-items: center;
    border-radius: 8px;
    color: var(--ink);
    display: flex;
    gap: 14px;
    padding: 14px 18px;
}

.nav-item.active {
    background: #EAF3EF;
    color: var(--pine);
    font-weight: 700;
}

.usage-card {
    margin-top: auto;
    padding: 18px;
}

.usage-meter {
    background: #E6EBE9;
    border-radius: 999px;
    height: 9px;
    margin: 14px 0 18px;
    overflow: hidden;
}

.usage-meter span {
    background: var(--pine);
    border-radius: inherit;
    display: block;
    height: 100%;
    width: 36%;
}

.profile-chip {
    align-items: center;
    display: flex;
    gap: 12px;
    margin-top: 28px;
}

.avatar {
    align-items: center;
    background: var(--ink);
    border-radius: 999px;
    color: white;
    display: inline-flex;
    font-size: 13px;
    font-weight: 800;
    height: 38px;
    justify-content: center;
    width: 38px;
}

.main-panel {
    padding: 30px 30px 38px;
}

.topbar {
    align-items: start;
    display: flex;
    justify-content: space-between;
    margin-bottom: 30px;
}

.topbar h1 {
    font-size: 30px;
    line-height: 1.1;
    margin: 0 0 8px;
}

.topbar p {
    color: var(--muted);
    font-size: 16px;
    margin: 0;
}

.top-actions {
    display: flex;
    gap: 12px;
}

.ghost-action {
    align-items: center;
    border: 1px solid var(--line);
    border-radius: 8px;
    color: var(--ink);
    display: inline-flex;
    font-weight: 700;
    gap: 10px;
    padding: 12px 18px;
}

.upload-card {
    padding: 28px;
}

.upload-grid {
    align-items: stretch;
    display: grid;
    gap: 28px;
    grid-template-columns: minmax(0, 1.6fr) minmax(320px, 0.9fr);
}

.upload-card h2 {
    font-size: 19px;
    margin: 0 0 14px;
}

.section-title {
    font-size: 18px;
    margin: 0 0 16px;
}

.recent-card {
    overflow: hidden;
}

.dashboard-table {
    border-collapse: collapse;
    width: 100%;
}

.dashboard-table th,
.dashboard-table td {
    border-bottom: 1px solid var(--line);
    font-size: 14px;
    padding: 13px 18px;
    text-align: left;
    vertical-align: middle;
}

.dashboard-table th {
    color: #31413D;
    font-size: 13px;
    font-weight: 650;
    background: #FBFCFC;
}

.dashboard-table tr:last-child td {
    border-bottom: 0;
}

.badge {
    border-radius: 7px;
    display: inline-flex;
    font-size: 12px;
    font-weight: 700;
    padding: 5px 10px;
}

.badge.green {
    background: #E8F4EE;
    color: var(--pine);
}

.badge.amber {
    background: #FFF4DB;
    color: var(--warning);
}

.confidence-cell {
    align-items: center;
    display: flex;
    gap: 10px;
}

.confidence-track {
    background: #E5E9E7;
    border-radius: 999px;
    height: 7px;
    overflow: hidden;
    width: 72px;
}

.confidence-fill {
    background: var(--sage);
    border-radius: inherit;
    display: block;
    height: 100%;
}

.confidence-fill.review {
    background: #D9A500;
}

.lower-grid {
    display: grid;
    gap: 22px;
    grid-template-columns: minmax(0, 0.95fr) minmax(0, 1.05fr);
    margin-top: 22px;
}

.quick-actions,
.summary-card {
    padding: 22px;
}

.action-grid {
    display: grid;
    gap: 16px;
    grid-template-columns: repeat(3, minmax(0, 1fr));
}

.action-card {
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 18px;
}

.action-icon {
    color: var(--pine);
    font-size: 28px;
    margin-bottom: 16px;
}

.action-card strong {
    display: block;
    font-size: 15px;
    margin-bottom: 6px;
}

.action-card span {
    color: var(--muted);
    display: block;
    font-size: 13px;
}

.summary-grid {
    border-top: 1px solid var(--line);
    display: grid;
    gap: 22px;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    padding-top: 22px;
}

.summary-number {
    color: var(--pine);
    font-size: 30px;
    font-weight: 800;
    line-height: 1;
    margin-bottom: 12px;
}

.summary-label {
    font-size: 14px;
    font-weight: 750;
}

.summary-note {
    color: var(--muted);
    font-size: 13px;
    margin-top: 6px;
}

.feature-panel {
    background: var(--soft);
    border-radius: 8px;
    display: grid;
    gap: 30px;
    padding: 34px;
}

.feature-item {
    align-items: center;
    display: grid;
    gap: 8px 20px;
    grid-template-columns: 40px 1fr;
}

.feature-icon {
    color: var(--pine);
    font-size: 27px;
    grid-row: span 2;
}

.feature-item strong {
    font-size: 16px;
}

.feature-item span {
    color: var(--muted);
    font-size: 14px;
}

#upload-zone {
    border: 1.5px dashed #CBD8D3 !important;
    border-radius: 8px !important;
    min-height: 270px;
}

#upload-zone .wrap {
    min-height: 240px;
}

@media (max-width: 980px) {
    .app-shell {
        grid-template-columns: 1fr;
    }

    .sidebar {
        min-height: auto;
    }

    .upload-grid {
        grid-template-columns: 1fr;
    }

    .lower-grid,
    .summary-grid,
    .action-grid {
        grid-template-columns: 1fr;
    }
}
"""


def _empty_documents_df() -> pd.DataFrame:
    return pd.DataFrame(columns=EDITABLE_DOCUMENT_COLUMNS)


def _empty_line_items_df() -> pd.DataFrame:
    return pd.DataFrame(columns=LINE_ITEM_COLUMNS)


def _sidebar_html() -> str:
    return """
    <aside class="sidebar">
        <div>
            <div class="brand"><span class="brand-mark">▱</span><span>DocuSend</span></div>
            <nav class="nav-stack">
                <div class="nav-item active">⌂ <span>Dashboard</span></div>
                <div class="nav-item">□ <span>Documents</span></div>
                <div class="nav-item">⇧ <span>Exports</span></div>
                <div class="nav-item">⚙ <span>Settings</span></div>
            </nav>
        </div>
        <div>
            <div class="docs-card usage-card">
                <div class="docs-muted">Monthly usage</div>
                <div style="font-size: 28px; font-weight: 750; margin-top: 8px;">128 <span class="docs-muted" style="font-size: 16px; font-weight: 500;">/ 500</span></div>
                <div class="docs-muted" style="font-size: 13px;">documents</div>
                <div class="usage-meter"><span></span></div>
                <div class="ghost-action" style="justify-content: center; width: 100%;">↗ Upgrade Plan</div>
            </div>
            <div class="profile-chip">
                <span class="avatar">JD</span>
                <div>
                    <strong>Jane Doe</strong>
                    <div class="docs-muted" style="font-size: 13px;">janedoe@email.com</div>
                </div>
            </div>
        </div>
    </aside>
    """


def _header_html() -> str:
    return """
    <div class="topbar">
        <div>
            <h1>Dashboard</h1>
            <p>Extract. Review. Export.</p>
        </div>
        <div class="top-actions">
            <div class="ghost-action">□ Try an example</div>
            <div class="ghost-action">?</div>
        </div>
    </div>
    """


def _feature_panel_html() -> str:
    return """
    <section class="feature-panel">
        <div class="feature-item">
            <div class="feature-icon">◎</div>
            <strong>Accurate extraction</strong>
            <span>OCR + AI to extract structured data</span>
        </div>
        <div class="feature-item">
            <div class="feature-icon">♢</div>
            <strong>Review with confidence</strong>
            <span>Edit and validate extracted fields</span>
        </div>
        <div class="feature-item">
            <div class="feature-icon">⇩</div>
            <strong>Export anywhere</strong>
            <span>Download as JSON or CSV</span>
        </div>
    </section>
    """


def _money(value: Optional[float], currency: str) -> str:
    if value is None:
        return "—"
    symbol = "$" if currency in {"USD", "CAD", "AUD", "NZD"} else ""
    return f"{symbol}{value:,.2f}"


def _recent_documents_html(documents: List[ExtractedDocument]) -> str:
    rows = []
    for document in documents:
        warning_count = len(document.warnings)
        needs_review = warning_count > 0 or document.confidence < 75
        status_class = "amber" if needs_review else "green"
        status_label = "Review" if needs_review else "Processed"
        confidence_class = "review" if needs_review else ""
        type_label = document.document_type.title() if document.document_type != "unknown" else "Document"
        confidence_width = max(0, min(100, int(document.confidence)))

        rows.append(
            f"""
            <tr>
                <td>□ {escape(document.file_name)}</td>
                <td><span class="badge green">{escape(type_label)}</span></td>
                <td>{escape(document.date or "—")}</td>
                <td>{escape(document.vendor or "—")}</td>
                <td>{escape(_money(document.total, document.currency))}</td>
                <td><span class="badge {status_class}">{status_label}</span></td>
                <td>
                    <div class="confidence-cell">
                        <span>{document.confidence:.0f}%</span>
                        <span class="confidence-track"><span class="confidence-fill {confidence_class}" style="width: {confidence_width}%"></span></span>
                    </div>
                </td>
                <td>{'⚠ ' if warning_count else ''}{warning_count}</td>
                <td>›</td>
            </tr>
            """
        )

    if not rows:
        rows.append(
            """
            <tr>
                <td colspan="9" style="padding: 28px 18px; color: var(--muted);">Upload receipts or invoices to populate this dashboard.</td>
            </tr>
            """
        )

    return f"""
    <h2 class="section-title">Recent documents</h2>
    <section class="docs-card recent-card">
        <table class="dashboard-table">
            <thead>
                <tr>
                    <th>File name</th>
                    <th>Type</th>
                    <th>Date</th>
                    <th>Vendor</th>
                    <th>Total</th>
                    <th>Status</th>
                    <th>Confidence</th>
                    <th>Warnings</th>
                    <th></th>
                </tr>
            </thead>
            <tbody>{''.join(rows)}</tbody>
        </table>
    </section>
    """


def _quick_actions_html() -> str:
    return """
    <section class="docs-card quick-actions">
        <h2 class="section-title">Quick actions</h2>
        <div class="action-grid">
            <div class="action-card">
                <div class="action-icon">□</div>
                <strong>Export JSON</strong>
                <span>Download all data</span>
            </div>
            <div class="action-card">
                <div class="action-icon">▤</div>
                <strong>Export CSV</strong>
                <span>Documents & line items</span>
            </div>
            <div class="action-card">
                <div class="action-icon">♢</div>
                <strong>Revalidate all</strong>
                <span>Check for issues</span>
            </div>
        </div>
    </section>
    """


def _summary_html(documents: List[ExtractedDocument]) -> str:
    count = len(documents)
    warning_count = sum(len(document.warnings) for document in documents)
    success_count = sum(1 for document in documents if document.status == "processed" and document.total is not None)
    success_rate = round((success_count / count) * 100) if count else 0
    avg_confidence = round(sum(document.confidence for document in documents) / count) if count else 0

    return f"""
    <section class="docs-card summary-card">
        <h2 class="section-title">Extraction summary</h2>
        <div class="summary-grid">
            <div>
                <div class="summary-number">{count}</div>
                <div class="summary-label">Documents</div>
                <div class="summary-note">This batch</div>
            </div>
            <div>
                <div class="summary-number">{success_rate}%</div>
                <div class="summary-label">Success rate</div>
                <div class="summary-note">With detected total</div>
            </div>
            <div>
                <div class="summary-number">{warning_count}</div>
                <div class="summary-label">Warnings</div>
                <div class="summary-note">Require review</div>
            </div>
            <div>
                <div class="summary-number">{avg_confidence}%</div>
                <div class="summary-label">Avg. confidence</div>
                <div class="summary-note">Current batch</div>
            </div>
        </div>
    </section>
    """


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
        _recent_documents_html(documents),
        _summary_html(documents),
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
            _recent_documents_html([]),
            _summary_html([]),
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
    document_state = gr.State([])

    with gr.Row(elem_classes=["app-shell"]):
        with gr.Column(scale=0, min_width=280, elem_classes=["sidebar-wrap"]):
            gr.HTML(_sidebar_html())

        with gr.Column(scale=1, elem_classes=["main-panel"]):
            gr.HTML(_header_html())

            with gr.Column(elem_classes=["docs-card", "upload-card"]):
                with gr.Row(elem_classes=["upload-grid"]):
                    with gr.Column(scale=2):
                        gr.HTML("<h2>Upload receipts or invoices</h2>")
                        files_input = gr.Files(
                            label="Receipts / Invoices",
                            file_count="multiple",
                            file_types=[".jpg", ".jpeg", ".png", ".pdf"],
                            type="filepath",
                            elem_id="upload-zone",
                        )
                        with gr.Row():
                            extract_button = gr.Button("Extract", variant="primary")
                            revalidate_button = gr.Button("Revalidate Edits")
                    with gr.Column(scale=1):
                        gr.HTML(_feature_panel_html())

            gr.HTML('<div style="height: 28px;"></div>')

            recent_documents = gr.HTML(_recent_documents_html([]))

            with gr.Row(elem_classes=["lower-grid"]):
                gr.HTML(_quick_actions_html())
                summary_panel = gr.HTML(_summary_html([]))

            with gr.Tabs():
                with gr.Tab("Review Fields"):
                    documents_table = gr.Dataframe(
                        value=_empty_documents_df(),
                        headers=EDITABLE_DOCUMENT_COLUMNS,
                        datatype=["str"] * len(EDITABLE_DOCUMENT_COLUMNS),
                        label="Editable document fields",
                        interactive=True,
                        wrap=True,
                    )
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
                with gr.Tab("Exports"):
                    with gr.Row():
                        json_download = gr.File(label="Download JSON")
                        csv_download = gr.File(label="Download CSV ZIP")

    extract_button.click(
        process_files,
        inputs=[files_input],
        outputs=[
            document_state,
            recent_documents,
            summary_panel,
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
            recent_documents,
            summary_panel,
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
    demo.launch(css=DOCUSEND_CSS)
