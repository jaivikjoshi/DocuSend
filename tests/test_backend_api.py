import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import app


class FakeQuery:
    def __init__(self, data):
        self.data = data

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def single(self):
        return self

    def in_(self, *_args, **_kwargs):
        return self

    def execute(self):
        return type("Response", (), {"data": self.data})()


class FakeSupabase:
    def __init__(self, data):
        self.data = data

    def table(self, _name):
        return FakeQuery(self.data)


class BackendApiTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.auth = {"Authorization": "Bearer test-token"}

    @patch("backend.main.process_worker")
    @patch("backend.main._queue_document", return_value={"status": "queued"})
    def test_process_async_queues_document(self, queue_document, process_worker):
        response = self.client.post(
            "/api/process_async",
            json={"document_id": "doc-1", "storage_path": "user/doc/file.pdf"},
            headers=self.auth,
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "queued")
        queue_document.assert_called_once()
        process_worker.assert_called_once()

    @patch("backend.main.process_worker")
    @patch("backend.main._queue_document", return_value={"status": "queued"})
    @patch("backend.main._authed_supabase")
    def test_retry_endpoint_requeues_failed_document(self, authed_supabase, queue_document, process_worker):
        authed_supabase.return_value = FakeSupabase({
            "id": "doc-1",
            "status": "failed",
            "storage_path": "user/doc/file.pdf",
        })

        response = self.client.post("/api/documents/doc-1/retry", headers=self.auth)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["message"], "Queued for retry")
        queue_document.assert_called_once()
        process_worker.assert_called_once()

    @patch("backend.main._authed_supabase")
    def test_accounting_export_returns_csv(self, authed_supabase):
        rows = [{
            "id": "doc-1",
            "file_name": "receipt.pdf",
            "status": "processed",
            "document_type": "receipt",
            "vendor": "Acme",
            "document_date": "2026-06-01",
            "total": 42.5,
            "tax": 3.5,
            "currency": "USD",
            "warnings": [],
            "line_items": [],
        }]
        authed_supabase.return_value = FakeSupabase(rows)

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "accounting.csv"
            csv_path.write_text("Date,Payee,Amount\n2026-06-01,Acme,42.5\n", encoding="utf-8")
            with patch("backend.main.write_accounting_csv", return_value=str(csv_path)):
                response = self.client.post(
                    "/api/export",
                    json={"document_ids": ["doc-1"], "format": "accounting_csv"},
                    headers=self.auth,
                )

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers["content-type"])
        self.assertIn("Acme", response.text)


if __name__ == "__main__":
    unittest.main()
