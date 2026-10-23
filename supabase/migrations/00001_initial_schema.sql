-- ============================================================================
-- 00001_initial_schema.sql
-- Automated Business Reporting Dashboard — Core Schema & Initial Provisioning
-- ============================================================================

-- Ensure pgcrypto extension for gen_random_uuid()
create extension if not exists "pgcrypto";

-- ----------------------------------------------------------------------------
-- 1. Profiles Table
-- ----------------------------------------------------------------------------
create table if not exists public.profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    display_name text,
    created_at timestamptz not null default now()
);

comment on table public.profiles is 'Public user profile information linked to Supabase auth.users.';

-- ----------------------------------------------------------------------------
-- 2. Workspaces Table
-- ----------------------------------------------------------------------------
create table if not exists public.workspaces (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    created_by uuid not null references auth.users(id) on delete cascade,
    created_at timestamptz not null default now()
);

comment on table public.workspaces is 'Tenancy and collaboration boundary for datasets and reports.';

-- ----------------------------------------------------------------------------
-- 3. Workspace Members Table
-- ----------------------------------------------------------------------------
create table if not exists public.workspace_members (
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    role text not null check (role in ('owner', 'editor', 'viewer')),
    created_at timestamptz not null default now(),
    primary key (workspace_id, user_id)
);

comment on table public.workspace_members is 'Membership mapping and role assignments within workspaces.';

-- ----------------------------------------------------------------------------
-- 4. Automatic User Provisioning Trigger (Default Workspace + Profile)
-- ----------------------------------------------------------------------------
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
    default_ws_id uuid;
    resolved_name text;
begin
    -- Determine user display name from auth metadata or email prefix
    resolved_name := coalesce(
        new.raw_user_meta_data->>'full_name',
        new.raw_user_meta_data->>'display_name',
        split_part(new.email, '@', 1),
        'User'
    );

    -- 1. Create Profile
    insert into public.profiles (id, display_name, created_at)
    values (new.id, resolved_name, now())
    on conflict (id) do update set display_name = excluded.display_name;

    -- 2. Create Initial Private Workspace
    insert into public.workspaces (name, created_by, created_at)
    values (resolved_name || '''s Workspace', new.id, now())
    returning id into default_ws_id;

    -- 3. Make user the Owner of their default workspace
    insert into public.workspace_members (workspace_id, user_id, role, created_at)
    values (default_ws_id, new.id, 'owner', now());

    return new;
end;
$$;

-- Trigger execution on auth.users creation
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();

-- ----------------------------------------------------------------------------
-- 5. Datasets Table
-- ----------------------------------------------------------------------------
create table if not exists public.datasets (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    created_by uuid not null references auth.users(id) on delete cascade,
    original_filename text not null,
    storage_path text not null,
    file_size_bytes bigint not null,
    file_mime_type text not null,
    sheet_names jsonb not null default '[]'::jsonb,
    selected_sheet text,
    row_count integer,
    column_count integer,
    created_at timestamptz not null default now()
);

comment on table public.datasets is 'Metadata catalog for uploaded Excel and CSV datasets stored in private storage.';

-- ----------------------------------------------------------------------------
-- 6. Reports Table
-- ----------------------------------------------------------------------------
create table if not exists public.reports (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    dataset_id uuid not null references public.datasets(id) on delete cascade,
    created_by uuid not null references auth.users(id) on delete cascade,
    name text not null,
    chart_configs jsonb not null default '[]'::jsonb,
    filter_config jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

comment on table public.reports is 'Saved reporting configurations referencing private datasets.';

-- ----------------------------------------------------------------------------
-- 7. Performance & Query Indexes
-- ----------------------------------------------------------------------------
create index if not exists idx_workspace_members_user on public.workspace_members(user_id);
create index if not exists idx_workspaces_created_by on public.workspaces(created_by);
create index if not exists idx_datasets_workspace on public.datasets(workspace_id);
create index if not exists idx_datasets_created_by on public.datasets(created_by);
create index if not exists idx_reports_workspace on public.reports(workspace_id);
create index if not exists idx_reports_dataset on public.reports(dataset_id);
create index if not exists idx_reports_created_by on public.reports(created_by);
create index if not exists idx_reports_created_at on public.reports(created_at desc);
