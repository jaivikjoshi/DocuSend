import csv
import json
import unittest
import zipfile
from pathlib import Path

from src.export import write_export_files
from src.parser import parse_document
from src.validation import validate_document


SAMPLE_TEXT = """Costco
Receipt # R-100
Date: May 22, 2024
Printer paper 2 x 12.99 25.98
Pens 1 4.50 4.50
Subtotal 30.48
Tax 2.44
Total $32.92
Visa
"""


class Phase2PipelineTest(unittest.TestCase):
    def test_parser_extracts_quantity_unit_price_line_items(self):
        document = validate_document(parse_document("sample_receipt.jpg", SAMPLE_TEXT, []))

        self.assertEqual(document.document_type, "receipt")
        self.assertEqual(document.vendor, "Costco")
        self.assertEqual(document.date, "2024-05-22")
        self.assertEqual(document.total, 32.92)
        self.assertEqual(len(document.line_items), 2)
        self.assertEqual(document.line_items[0].description, "Printer paper")
        self.assertEqual(document.line_items[0].quantity, 2.0)
        self.assertEqual(document.line_items[0].unit_price, 12.99)
        self.assertEqual(document.status, "processed")

    def test_validation_marks_inconsistent_totals_for_review(self):
        text = SAMPLE_TEXT.replace("Total $32.92", "Total $42.92")
        document = validate_document(parse_document("bad_receipt.jpg", text, []))

        self.assertEqual(document.status, "review")
        self.assertIn("Subtotal, tax, tip, and discount do not reconcile with total.", document.warnings)

    def test_export_writes_json_and_csv_zip_with_headers(self):
        document = validate_document(parse_document("sample_receipt.jpg", SAMPLE_TEXT, []))
        json_path, csv_zip_path = write_export_files([document])

        payload = json.loads(Path(json_path).read_text(encoding="utf-8"))
        self.assertEqual(payload[0]["vendor"], "Costco")

        with zipfile.ZipFile(csv_zip_path) as archive:
            document_rows = list(csv.DictReader(archive.read("documents.csv").decode("utf-8").splitlines()))
            line_rows = list(csv.DictReader(archive.read("line_items.csv").decode("utf-8").splitlines()))

        self.assertEqual(document_rows[0]["vendor"], "Costco")
        self.assertEqual(line_rows[0]["description"], "Printer paper")


if __name__ == "__main__":
    unittest.main()
