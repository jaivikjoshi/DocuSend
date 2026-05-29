-- ============================================================
-- DocuSend: Core Schema Migration
-- Tables: profiles, documents, line_items, exports
-- Includes: triggers, indexes, check constraints, grants
-- ============================================================

-- ----------------------------------------------------------------
-- 1. profiles
--    One row per auth user; created automatically via trigger.
-- ----------------------------------------------------------------
create table public.profiles (
  id          uuid primary key references auth.users(id) on delete cascade,
  email       text,
  full_name   text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

-- ----------------------------------------------------------------
-- 2. documents
--    One row per uploaded receipt/invoice.
--    user_id is nullable so guest extractions that are later
--    saved by a signing-in user can be inserted correctly.
-- ----------------------------------------------------------------
create table public.documents (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid references auth.users(id) on delete cascade,
  file_name       text not null,
  file_type       text,
  document_type   text not null default 'unknown',
  vendor          text,
  document_date   date,
  invoice_number  text,
  currency        text not null default 'USD',
  subtotal        numeric(12,2),
  tax             numeric(12,2),
  tip             numeric(12,2),
  discount        numeric(12,2),
  total           numeric(12,2),
  payment_method  text,
  raw_text        text,
  confidence      numeric(5,2),
  status          text not null default 'review',
  warnings        jsonb not null default '[]'::jsonb,
  source_mode     text not null default 'authenticated',
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),

  constraint documents_status_check
    check (status in ('processed', 'review', 'failed')),
  constraint documents_document_type_check
    check (document_type in ('receipt', 'invoice', 'unknown')),
  constraint documents_source_mode_check
    check (source_mode in ('authenticated', 'guest_import')),
  constraint documents_subtotal_check
    check (subtotal is null or subtotal >= 0),
  constraint documents_tax_check
    check (tax is null or tax >= 0),
  constraint documents_tip_check
    check (tip is null or tip >= 0),
  constraint documents_discount_check
    check (discount is null or discount >= 0),
  constraint documents_total_check
    check (total is null or total >= 0),
  constraint documents_confidence_check
    check (confidence is null or (confidence >= 0 and confidence <= 100)),
  constraint documents_currency_check
    check (currency ~ '^[A-Z]{3}$')
);

-- ----------------------------------------------------------------
-- 3. line_items
--    Extracted line items belonging to a document.
--    user_id is duplicated for efficient RLS without a JOIN.
-- ----------------------------------------------------------------
create table public.line_items (
  id           uuid primary key default gen_random_uuid(),
  document_id  uuid not null references public.documents(id) on delete cascade,
  user_id      uuid references auth.users(id) on delete cascade,
  description  text not null,
  quantity     numeric(12,3),
  unit_price   numeric(12,2),
  total        numeric(12,2),
  confidence   numeric(5,2),
  row_index    integer,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),

  constraint line_items_confidence_check
    check (confidence is null or (confidence >= 0 and confidence <= 100)),
  constraint line_items_quantity_check
    check (quantity is null or quantity >= 0),
  constraint line_items_unit_price_check
    check (unit_price is null or unit_price >= 0),
  constraint line_items_total_check
    check (total is null or total >= 0)
);

-- ----------------------------------------------------------------
-- 4. exports
--    Optional audit log of generated export files.
-- ----------------------------------------------------------------
create table public.exports (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid references auth.users(id) on delete cascade,
  export_type     text not null,
  document_count  integer not null default 0,
  file_path       text,
  created_at      timestamptz not null default now(),

  constraint exports_export_type_check
    check (export_type in ('json', 'csv', 'csv_zip')),
  constraint exports_document_count_check
    check (document_count >= 0)
);

-- ----------------------------------------------------------------
-- 5. updated_at trigger
--    SECURITY INVOKER: runs with calling user's privileges (safe).
-- ----------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger trg_profiles_updated_at
  before update on public.profiles
  for each row execute function public.set_updated_at();

create trigger trg_documents_updated_at
  before update on public.documents
  for each row execute function public.set_updated_at();

create trigger trg_line_items_updated_at
  before update on public.line_items
  for each row execute function public.set_updated_at();

-- ----------------------------------------------------------------
-- 6. Auto-create profile on new auth user sign-up
--    SECURITY DEFINER is required here to write into public.profiles
--    from the auth schema trigger context.
--    Execute privilege is revoked from all public roles.
-- ----------------------------------------------------------------
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, email, full_name)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data->>'full_name', '')
  );
  return new;
end;
$$;

-- Only the trigger should invoke this function
revoke execute on function public.handle_new_user() from public, anon, authenticated;

create trigger trg_on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ----------------------------------------------------------------
-- 7. Indexes
-- ----------------------------------------------------------------
create index idx_documents_user_created  on public.documents (user_id, created_at desc);
create index idx_documents_user_date     on public.documents (user_id, document_date desc);
create index idx_documents_user_vendor   on public.documents (user_id, vendor);
create index idx_documents_status        on public.documents (status);
create index idx_line_items_document_id  on public.line_items (document_id);
create index idx_line_items_user_id      on public.line_items (user_id);
create index idx_exports_user_created    on public.exports (user_id, created_at desc);

-- ----------------------------------------------------------------
-- 8. Grant Data API access (RLS governs which rows are visible)
-- ----------------------------------------------------------------
grant select, insert, update, delete on public.profiles   to authenticated;
grant select, insert, update, delete on public.documents  to authenticated;
grant select, insert, update, delete on public.line_items to authenticated;
grant select, insert                 on public.exports     to authenticated;
