-- ============================================================
-- DocuSend: Durable processing, review workflow, export formats
-- ============================================================

alter table public.documents
  add column if not exists retry_count integer not null default 0,
  add column if not exists last_error text,
  add column if not exists processing_started_at timestamptz,
  add column if not exists processed_at timestamptz,
  add column if not exists processing_duration_ms integer,
  add column if not exists parser_version text,
  add column if not exists reviewed_at timestamptz,
  add column if not exists reviewed_by uuid references auth.users(id) on delete set null,
  add column if not exists review_notes text;

alter table public.documents
  drop constraint if exists documents_status_check,
  add constraint documents_status_check
    check (status in ('queued', 'processing', 'processed', 'review', 'failed'));

alter table public.documents
  drop constraint if exists documents_retry_count_check,
  add constraint documents_retry_count_check
    check (retry_count >= 0);

alter table public.documents
  drop constraint if exists documents_processing_duration_check,
  add constraint documents_processing_duration_check
    check (processing_duration_ms is null or processing_duration_ms >= 0);

create index if not exists idx_documents_queue
  on public.documents (status, retry_count, created_at)
  where status = 'queued';

create index if not exists idx_documents_user_review
  on public.documents (user_id, status, confidence, created_at desc);

create index if not exists idx_documents_reviewed_at
  on public.documents (user_id, reviewed_at desc)
  where reviewed_at is not null;

alter table public.exports
  drop constraint if exists exports_export_type_check,
  add constraint exports_export_type_check
    check (export_type in ('json', 'csv', 'csv_zip', 'accounting_csv'));
