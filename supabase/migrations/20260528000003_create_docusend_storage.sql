-- ============================================================
-- DocuSend: Storage Bucket + Policies
--
-- Bucket: documents (private)
-- Path:   {user_id}/{document_id}/{original_filename}
--
-- Guest uploads are NOT stored here. Only authenticated users
-- who choose to save their files get objects in this bucket.
--
-- Storage upsert (file replacement) requires INSERT + SELECT +
-- UPDATE policies — all three are defined below.
-- ============================================================

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'documents',
  'documents',
  false,
  20971520,  -- 20 MB per file
  array[
    'image/jpeg',
    'image/png',
    'image/webp',
    'image/tiff',
    'application/pdf'
  ]
)
on conflict (id) do nothing;

-- Upload: user can only write under their own user_id/ prefix
create policy "storage: upload own files"
  on storage.objects
  for insert
  to authenticated
  with check (
    bucket_id = 'documents'
    and (select auth.uid())::text = (storage.foldername(name))[1]
  );

-- Download: user can only read under their own user_id/ prefix
create policy "storage: read own files"
  on storage.objects
  for select
  to authenticated
  using (
    bucket_id = 'documents'
    and (select auth.uid())::text = (storage.foldername(name))[1]
  );

-- Replace (upsert): user can only overwrite their own files
create policy "storage: replace own files"
  on storage.objects
  for update
  to authenticated
  using (
    bucket_id = 'documents'
    and (select auth.uid())::text = (storage.foldername(name))[1]
  )
  with check (
    bucket_id = 'documents'
    and (select auth.uid())::text = (storage.foldername(name))[1]
  );

-- Delete: user can only remove their own files
create policy "storage: delete own files"
  on storage.objects
  for delete
  to authenticated
  using (
    bucket_id = 'documents'
    and (select auth.uid())::text = (storage.foldername(name))[1]
  );
