-- ============================================================
-- DocuSend: Align async processing contract
--
-- Fixes frontend/backend/schema drift:
--   - documents.status supports the async "processing" state
--   - documents.source_mode stores parser source: "gemini" | "regex"
--   - uploaded object metadata is tracked on documents
-- ============================================================

alter table public.documents
  add column if not exists file_size bigint,
  add column if not exists storage_path text;

alter table public.documents
  alter column source_mode set default 'regex';

update public.documents
set source_mode = 'regex'
where source_mode not in ('gemini', 'regex');

alter table public.documents
  drop constraint if exists documents_status_check,
  add constraint documents_status_check
    check (status in ('processing', 'processed', 'review', 'failed'));

alter table public.documents
  drop constraint if exists documents_source_mode_check,
  add constraint documents_source_mode_check
    check (source_mode in ('gemini', 'regex'));

create index if not exists idx_documents_user_status
  on public.documents (user_id, status, created_at desc);

create index if not exists idx_documents_storage_path
  on public.documents (storage_path)
  where storage_path is not null;
