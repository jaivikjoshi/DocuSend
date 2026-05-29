-- ============================================================
-- DocuSend: Row Level Security Policies
--
-- Security design notes:
--   - Use TO authenticated (not auth.role()) — auth.role() is deprecated
--     and breaks when anonymous sign-ins are enabled.
--   - UPDATE policies always include both USING and WITH CHECK to
--     prevent user_id reassignment attacks.
--   - (select auth.uid()) pattern is used instead of auth.uid() directly
--     in USING/WITH CHECK for a small performance gain (evaluated once
--     per statement rather than once per row).
-- ============================================================

-- ----------------------------------------------------------------
-- Enable RLS on all app tables
-- ----------------------------------------------------------------
alter table public.profiles   enable row level security;
alter table public.documents  enable row level security;
alter table public.line_items enable row level security;
alter table public.exports    enable row level security;

-- ================================================================
-- profiles
-- ================================================================

create policy "profiles: select own"
  on public.profiles
  for select
  to authenticated
  using ( (select auth.uid()) = id );

create policy "profiles: update own"
  on public.profiles
  for update
  to authenticated
  using ( (select auth.uid()) = id )
  with check ( (select auth.uid()) = id );

-- ================================================================
-- documents
-- ================================================================

create policy "documents: select own"
  on public.documents
  for select
  to authenticated
  using ( (select auth.uid()) = user_id );

create policy "documents: insert own"
  on public.documents
  for insert
  to authenticated
  with check ( (select auth.uid()) = user_id );

create policy "documents: update own"
  on public.documents
  for update
  to authenticated
  using ( (select auth.uid()) = user_id )
  with check ( (select auth.uid()) = user_id );

create policy "documents: delete own"
  on public.documents
  for delete
  to authenticated
  using ( (select auth.uid()) = user_id );

-- ================================================================
-- line_items
-- ================================================================

create policy "line_items: select own"
  on public.line_items
  for select
  to authenticated
  using ( (select auth.uid()) = user_id );

create policy "line_items: insert own"
  on public.line_items
  for insert
  to authenticated
  with check ( (select auth.uid()) = user_id );

create policy "line_items: update own"
  on public.line_items
  for update
  to authenticated
  using ( (select auth.uid()) = user_id )
  with check ( (select auth.uid()) = user_id );

create policy "line_items: delete own"
  on public.line_items
  for delete
  to authenticated
  using ( (select auth.uid()) = user_id );

-- ================================================================
-- exports
-- ================================================================

create policy "exports: select own"
  on public.exports
  for select
  to authenticated
  using ( (select auth.uid()) = user_id );

create policy "exports: insert own"
  on public.exports
  for insert
  to authenticated
  with check ( (select auth.uid()) = user_id );
