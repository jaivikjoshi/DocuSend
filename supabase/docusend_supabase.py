"""
DocuSend — Supabase integration helpers
=======================================
Install:  pip install supabase python-dotenv
Env vars: SUPABASE_URL, SUPABASE_ANON_KEY

SECURITY NOTES
--------------
- Never expose SUPABASE_SERVICE_ROLE_KEY to the browser or Gradio frontend.
  It bypasses RLS entirely and has full database access.
- Use the anon key for all client-side / Gradio operations.
- SUPABASE_SERVICE_ROLE_KEY is only for trusted server-side admin tasks
  (e.g., a background migration script) and should never be in source control.
- Always validate user ownership before server-side operations.
- Inform users of your data retention policy before storing their receipts.
"""

from __future__ import annotations

import os
import json
from datetime import date
from typing import Any

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL: str = os.environ["SUPABASE_URL"]
SUPABASE_ANON_KEY: str = os.environ["SUPABASE_ANON_KEY"]

# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

def get_client() -> Client:
    """Return a Supabase client using the publishable anon key.

    The anon key is safe to use in Gradio (server-side Python) as long as
    you set the user's JWT via client.auth.set_session() after login.
    RLS enforces per-user row visibility.
    """
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def sign_up(email: str, password: str, full_name: str = "") -> dict:
    """Create a new account. A profile row is created automatically via trigger."""
    client = get_client()
    response = client.auth.sign_up({
        "email": email,
        "password": password,
        "options": {
            "data": {"full_name": full_name}  # stored in raw_user_meta_data
        }
    })
    return response.model_dump()


def sign_in(email: str, password: str) -> dict:
    """Sign in with email + password. Returns session with access_token."""
    client = get_client()
    response = client.auth.sign_in_with_password({
        "email": email,
        "password": password,
    })
    return response.model_dump()


def get_current_user(access_token: str, refresh_token: str) -> dict | None:
    """Return the currently signed-in user or None if not authenticated.

    Always use get_user() (server-validated) rather than reading the JWT
    payload locally — the JWT can be expired or tampered with.
    """
    client = get_client()
    client.auth.set_session(access_token, refresh_token)
    response = client.auth.get_user()
    return response.user.model_dump() if response.user else None


def sign_out(access_token: str, refresh_token: str) -> None:
    """Invalidate the current session."""
    client = get_client()
    client.auth.set_session(access_token, refresh_token)
    client.auth.sign_out()


def get_authed_client(access_token: str, refresh_token: str) -> Client:
    """Return a client pre-loaded with the user's session.

    Use this before any data operation so RLS policies see the correct uid.
    """
    client = get_client()
    client.auth.set_session(access_token, refresh_token)
    return client


# ---------------------------------------------------------------------------
# Mapping: extracted JSON → database row
# ---------------------------------------------------------------------------

def extraction_to_document_row(
    extraction: dict,
    user_id: str,
    source_mode: str = "regex",
) -> dict:
    """Map the app's extracted document dict to a documents table row.

    The app uses "date" as a key; the DB column is "document_date".
    null tips/discounts from the extractor are stored as NULL.
    """
    warnings = extraction.get("warnings", [])
    return {
        "user_id": user_id,
        "file_name": extraction["file_name"],
        "file_type": extraction.get("file_type"),
        "document_type": extraction.get("document_type", "unknown"),
        "vendor": extraction.get("vendor"),
        "document_date": extraction.get("date"),      # key rename
        "invoice_number": extraction.get("invoice_number"),
        "currency": extraction.get("currency", "USD"),
        "subtotal": extraction.get("subtotal"),
        "tax": extraction.get("tax"),
        "tip": extraction.get("tip"),
        "discount": extraction.get("discount"),
        "total": extraction.get("total"),
        "payment_method": extraction.get("payment_method"),
        "raw_text": extraction.get("raw_text"),
        "confidence": extraction.get("confidence"),
        "status": extraction.get("status", "review"),
        "warnings": warnings if isinstance(warnings, list) else [],
        "source_mode": source_mode,
    }


def extraction_to_line_item_rows(
    line_items: list[dict],
    document_id: str,
    user_id: str,
) -> list[dict]:
    """Map extracted line items to line_items table rows."""
    rows = []
    for idx, item in enumerate(line_items):
        rows.append({
            "document_id": document_id,
            "user_id": user_id,
            "description": item.get("description", ""),
            "quantity": item.get("quantity"),
            "unit_price": item.get("unit_price"),
            "total": item.get("total"),
            "confidence": item.get("confidence"),
            "row_index": item.get("row_index", idx),
        })
    return rows


# ---------------------------------------------------------------------------
# Document CRUD
# ---------------------------------------------------------------------------

def insert_document(
    client: Client,
    extraction: dict,
    user_id: str,
    source_mode: str = "regex",
) -> dict:
    """Insert one document and its line items. Returns the saved document row."""
    doc_row = extraction_to_document_row(extraction, user_id, source_mode)

    # Insert document first to get its generated id
    doc_response = (
        client.table("documents")
        .insert(doc_row)
        .execute()
    )
    saved_doc = doc_response.data[0]
    document_id = saved_doc["id"]

    # Insert line items if present
    line_items = extraction.get("line_items", [])
    if line_items:
        li_rows = extraction_to_line_item_rows(line_items, document_id, user_id)
        client.table("line_items").insert(li_rows).execute()

    return saved_doc


def fetch_documents(client: Client) -> list[dict]:
    """Fetch all documents for the signed-in user, newest first."""
    response = (
        client.table("documents")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return response.data


def fetch_document_with_line_items(client: Client, document_id: str) -> dict | None:
    """Fetch a single document and its line items."""
    doc_response = (
        client.table("documents")
        .select("*")
        .eq("id", document_id)
        .single()
        .execute()
    )
    doc = doc_response.data
    if not doc:
        return None

    li_response = (
        client.table("line_items")
        .select("*")
        .eq("document_id", document_id)
        .order("row_index")
        .execute()
    )
    doc["line_items"] = li_response.data
    return doc


def update_document(
    client: Client,
    document_id: str,
    fields: dict,
) -> dict:
    """Update editable fields on an existing document.

    Only pass the fields the user changed. RLS ensures the row
    belongs to the signed-in user — the update silently returns
    0 rows if the user doesn't own it.
    """
    # Prevent accidentally overwriting immutable fields
    fields.pop("id", None)
    fields.pop("user_id", None)
    fields.pop("created_at", None)

    response = (
        client.table("documents")
        .update(fields)
        .eq("id", document_id)
        .execute()
    )
    return response.data[0] if response.data else {}


def delete_document(client: Client, document_id: str) -> None:
    """Delete a document. Line items are cascade-deleted by the DB."""
    client.table("documents").delete().eq("id", document_id).execute()


# ---------------------------------------------------------------------------
# Line item CRUD
# ---------------------------------------------------------------------------

def upsert_line_items(
    client: Client,
    document_id: str,
    user_id: str,
    line_items: list[dict],
) -> list[dict]:
    """Replace all line items for a document (delete + re-insert).

    This is simpler than tracking individual edits and correct for the
    DocuSend use-case where the user edits a table of items and saves.
    """
    client.table("line_items").delete().eq("document_id", document_id).execute()

    if not line_items:
        return []

    rows = extraction_to_line_item_rows(line_items, document_id, user_id)
    response = client.table("line_items").insert(rows).execute()
    return response.data


# ---------------------------------------------------------------------------
# Export tracking (optional)
# ---------------------------------------------------------------------------

def log_export(
    client: Client,
    user_id: str,
    export_type: str,
    document_count: int,
    file_path: str | None = None,
) -> dict:
    """Record that the user generated an export."""
    response = (
        client.table("exports")
        .insert({
            "user_id": user_id,
            "export_type": export_type,
            "document_count": document_count,
            "file_path": file_path,
        })
        .execute()
    )
    return response.data[0]


# ---------------------------------------------------------------------------
# Guest mode helpers
# ---------------------------------------------------------------------------

class GuestSession:
    """In-memory session for guest users (not signed in).

    Data lives only in this object for the duration of the Gradio session.
    Nothing is written to Supabase until the user signs in and explicitly
    chooses to save their data.
    """

    def __init__(self) -> None:
        self._documents: list[dict] = []

    def add_extraction(self, extraction: dict) -> None:
        """Store a single extraction result in memory."""
        self._documents.append(extraction)

    def get_documents(self) -> list[dict]:
        return list(self._documents)

    def clear(self) -> None:
        self._documents.clear()

    def save_to_account(
        self,
        client: Client,
        user_id: str,
    ) -> list[dict]:
        """Persist all in-memory guest extractions to Supabase.

        Call this after the user signs in and confirms they want to save.
        Each document keeps its parser source mode, defaulting to regex.
        """
        saved = []
        for extraction in self._documents:
            doc = insert_document(client, extraction, user_id, source_mode=extraction.get("source_mode", "regex"))
            saved.append(doc)
        self.clear()
        return saved


# ---------------------------------------------------------------------------
# Suggested Gradio app state pattern
# ---------------------------------------------------------------------------
# In your Gradio app, maintain state like this:
#
#   state = {
#       "access_token": None,       # str | None
#       "refresh_token": None,      # str | None
#       "user_id": None,            # str | None
#       "guest_session": GuestSession(),
#   }
#
# On upload+extract (guest or signed-in):
#   if state["user_id"]:
#       client = get_authed_client(state["access_token"], state["refresh_token"])
#       insert_document(client, extraction, state["user_id"])
#   else:
#       state["guest_session"].add_extraction(extraction)
#
# On sign-in:
#   result = sign_in(email, password)
#   state["access_token"]  = result["session"]["access_token"]
#   state["refresh_token"] = result["session"]["refresh_token"]
#   state["user_id"]       = result["user"]["id"]
#   # Offer to save guest data:
#   if state["guest_session"].get_documents():
#       # Show "Save X extractions to your account?" prompt
#       pass
#
# On "Save guest data" confirmation:
#   client = get_authed_client(state["access_token"], state["refresh_token"])
#   state["guest_session"].save_to_account(client, state["user_id"])
#
# On sign-out:
#   sign_out(state["access_token"], state["refresh_token"])
#   state["access_token"]  = None
#   state["refresh_token"] = None
#   state["user_id"]       = None
#   state["guest_session"].clear()
