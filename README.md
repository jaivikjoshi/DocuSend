# DocuSend

DocuSend is a Gradio web app for extracting structured financial data from receipts and invoices.

Users upload receipt photos or invoice PDFs, review editable extracted fields, inspect validation warnings, and export clean JSON or CSV.

## Current Build Scope

- Batch upload for JPG, PNG, and PDF files
- OCR, selectable PDF text extraction, and scanned PDF OCR fallback
- Rule-based extraction for vendor, date, invoice number, subtotal, tax, tip, discount, total, currency, and payment method
- Draft line-item extraction with quantity and unit-price support for common rows
- Validation warnings and review status
- Editable review tables
- JSON export and CSV ZIP export with document and line-item files
- Example receipt/invoice files
- Hugging Face Spaces-ready dependency files

## Phase 2 Status

Phase 2 is the useful MVP layer. It adds practical PDF handling, better line items, validation status, export reliability, and sample files for testing.

Try these files in the app:

- `examples/sample_receipt.png`
- `examples/sample_invoice_scan.png`
- `examples/sample_scanned_invoice.pdf`

## How It Works

1. `app.py` builds the Gradio UI and coordinates the workflow.
2. `src/ocr.py` extracts raw text from uploaded files.
3. `src/parser.py` turns raw text into structured draft data.
4. `src/validation.py` adds warnings and confidence scores.
5. `src/export.py` writes JSON and CSV files for download.
6. `src/schema.py` defines the receipt/invoice data model used across the app.

## Run Locally

```bash
pip install -r requirements.txt
python app.py
```

For local OCR, install the Tesseract system package if it is not already available.

## Test

```bash
python -m unittest
```

## Privacy Note

Uploaded files are processed temporarily by the running app. Do not upload sensitive financial documents unless you trust the environment where the app is deployed.
