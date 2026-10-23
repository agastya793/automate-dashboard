-- ============================================================================
-- 00003_storage_setup.sql
-- Automated Business Reporting Dashboard — Private Storage Bucket & RLS
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Create Private Storage Bucket
-- ----------------------------------------------------------------------------
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
    'business-datasets',
    'business-datasets',
    false, -- Non-public private bucket
    10485760, -- 10 MiB limit (matches MAX_UPLOAD_BYTES)
    array[
        'text/csv',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-excel',
        'application/octet-stream'
    ]
)
on conflict (id) do update set
    public = false,
    file_size_limit = 10485760,
    allowed_mime_types = array[
        'text/csv',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-excel',
        'application/octet-stream'
    ];

-- ----------------------------------------------------------------------------
-- 2. Storage RLS Policies for business-datasets
-- ----------------------------------------------------------------------------
-- Expected object path hierarchy:
--   <workspace_id>/<user_id>/<dataset_id>/<sanitized_filename>
--
-- Path parsing with storage.foldername(name):
--   (storage.foldername(name))[1] = workspace_id
--   (storage.foldername(name))[2] = user_id
--   (storage.foldername(name))[3] = dataset_id

-- A. SELECT / Download
-- Allowed for any member belonging to the workspace indicated in the path.
drop policy if exists "Workspace members can download datasets" on storage.objects;
create policy "Workspace members can download datasets"
    on storage.objects
    for select
    to authenticated
    using (
        bucket_id = 'business-datasets'
        and public.is_workspace_member(
            (storage.foldername(name))[1]::uuid,
            auth.uid()
        )
    );

-- B. INSERT / Upload
-- Allowed for owners and editors of the workspace, uploading to their own user directory segment.
drop policy if exists "Workspace editors can upload datasets" on storage.objects;
create policy "Workspace editors can upload datasets"
    on storage.objects
    for insert
    to authenticated
    with check (
        bucket_id = 'business-datasets'
        and public.has_workspace_role(
            (storage.foldername(name))[1]::uuid,
            auth.uid(),
            array['owner', 'editor']
        )
        and (storage.foldername(name))[2]::uuid = auth.uid()
    );

-- C. DELETE / Cleanup
-- Allowed for owners and editors of the workspace.
drop policy if exists "Workspace editors can delete datasets" on storage.objects;
create policy "Workspace editors can delete datasets"
    on storage.objects
    for delete
    to authenticated
    using (
        bucket_id = 'business-datasets'
        and public.has_workspace_role(
            (storage.foldername(name))[1]::uuid,
            auth.uid(),
            array['owner', 'editor']
        )
    );
