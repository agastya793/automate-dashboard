-- ============================================================================
-- 00002_rls_policies.sql
-- Automated Business Reporting Dashboard — Row Level Security (RLS) & Roles
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Anti-Recursion Security Definer Helper Functions
-- ----------------------------------------------------------------------------
-- These functions execute with search_path locked to 'public' to prevent
-- search-path manipulation and infinite recursion within table RLS evaluation.

create or replace function public.is_workspace_member(ws_id uuid, u_id uuid)
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select exists (
    select 1
    from public.workspace_members
    where workspace_id = ws_id
      and user_id = u_id
  );
$$;

comment on function public.is_workspace_member is 'Safely checks whether a user belongs to a workspace without triggering RLS recursion.';

create or replace function public.has_workspace_role(ws_id uuid, u_id uuid, required_roles text[])
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select exists (
    select 1
    from public.workspace_members
    where workspace_id = ws_id
      and user_id = u_id
      and role = any(required_roles)
  );
$$;

comment on function public.has_workspace_role is 'Verifies whether a user has one of the required authorization roles in a workspace.';

-- Revoke default public execution privileges and grant explicitly to authenticated users
revoke all on function public.is_workspace_member(uuid, uuid) from public;
grant execute on function public.is_workspace_member(uuid, uuid) to authenticated, service_role;

revoke all on function public.has_workspace_role(uuid, uuid, text[]) from public;
grant execute on function public.has_workspace_role(uuid, uuid, text[]) to authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 2. Enable Row Level Security (RLS) on All Application Tables
-- ----------------------------------------------------------------------------
alter table public.profiles enable row level security;
alter table public.workspaces enable row level security;
alter table public.workspace_members enable row level security;
alter table public.datasets enable row level security;
alter table public.reports enable row level security;

-- ----------------------------------------------------------------------------
-- 3. Profiles RLS Policies
-- ----------------------------------------------------------------------------
drop policy if exists "Users can read own profile" on public.profiles;
create policy "Users can read own profile"
    on public.profiles
    for select
    to authenticated
    using (auth.uid() = id);

drop policy if exists "Users can update own profile" on public.profiles;
create policy "Users can update own profile"
    on public.profiles
    for update
    to authenticated
    using (auth.uid() = id)
    with check (auth.uid() = id);

-- ----------------------------------------------------------------------------
-- 4. Workspaces RLS Policies
-- ----------------------------------------------------------------------------
drop policy if exists "Members can read their workspaces" on public.workspaces;
create policy "Members can read their workspaces"
    on public.workspaces
    for select
    to authenticated
    using (public.is_workspace_member(id, auth.uid()));

drop policy if exists "Authenticated users can create workspaces" on public.workspaces;
create policy "Authenticated users can create workspaces"
    on public.workspaces
    for insert
    to authenticated
    with check (auth.uid() = created_by);

drop policy if exists "Workspace owners and editors can update workspace" on public.workspaces;
create policy "Workspace owners and editors can update workspace"
    on public.workspaces
    for update
    to authenticated
    using (public.has_workspace_role(id, auth.uid(), array['owner', 'editor']))
    with check (public.has_workspace_role(id, auth.uid(), array['owner', 'editor']));

drop policy if exists "Only workspace owners can delete workspace" on public.workspaces;
create policy "Only workspace owners can delete workspace"
    on public.workspaces
    for delete
    to authenticated
    using (public.has_workspace_role(id, auth.uid(), array['owner']));

-- ----------------------------------------------------------------------------
-- 5. Workspace Members RLS Policies
-- ----------------------------------------------------------------------------
drop policy if exists "Members can view workspace member directory" on public.workspace_members;
create policy "Members can view workspace member directory"
    on public.workspace_members
    for select
    to authenticated
    using (public.is_workspace_member(workspace_id, auth.uid()));

drop policy if exists "Workspace owners can add members" on public.workspace_members;
create policy "Workspace owners can add members"
    on public.workspace_members
    for insert
    to authenticated
    with check (public.has_workspace_role(workspace_id, auth.uid(), array['owner']));

drop policy if exists "Workspace owners can update member roles" on public.workspace_members;
create policy "Workspace owners can update member roles"
    on public.workspace_members
    for update
    to authenticated
    using (public.has_workspace_role(workspace_id, auth.uid(), array['owner']))
    with check (public.has_workspace_role(workspace_id, auth.uid(), array['owner']));

drop policy if exists "Workspace owners can remove members" on public.workspace_members;
create policy "Workspace owners can remove members"
    on public.workspace_members
    for delete
    to authenticated
    using (public.has_workspace_role(workspace_id, auth.uid(), array['owner']));

-- ----------------------------------------------------------------------------
-- 6. Datasets RLS Policies
-- ----------------------------------------------------------------------------
drop policy if exists "Workspace members can view dataset metadata" on public.datasets;
create policy "Workspace members can view dataset metadata"
    on public.datasets
    for select
    to authenticated
    using (public.is_workspace_member(workspace_id, auth.uid()));

drop policy if exists "Owners and editors can insert datasets" on public.datasets;
create policy "Owners and editors can insert datasets"
    on public.datasets
    for insert
    to authenticated
    with check (
        public.has_workspace_role(workspace_id, auth.uid(), array['owner', 'editor'])
        and auth.uid() = created_by
    );

drop policy if exists "Owners and editors can delete datasets" on public.datasets;
create policy "Owners and editors can delete datasets"
    on public.datasets
    for delete
    to authenticated
    using (public.has_workspace_role(workspace_id, auth.uid(), array['owner', 'editor']));

-- ----------------------------------------------------------------------------
-- 7. Reports RLS Policies
-- ----------------------------------------------------------------------------
drop policy if exists "Workspace members can view reports" on public.reports;
create policy "Workspace members can view reports"
    on public.reports
    for select
    to authenticated
    using (public.is_workspace_member(workspace_id, auth.uid()));

drop policy if exists "Owners and editors can create reports" on public.reports;
create policy "Owners and editors can create reports"
    on public.reports
    for insert
    to authenticated
    with check (
        public.has_workspace_role(workspace_id, auth.uid(), array['owner', 'editor'])
        and auth.uid() = created_by
    );

drop policy if exists "Owners and editors can update reports" on public.reports;
create policy "Owners and editors can update reports"
    on public.reports
    for update
    to authenticated
    using (public.has_workspace_role(workspace_id, auth.uid(), array['owner', 'editor']))
    with check (public.has_workspace_role(workspace_id, auth.uid(), array['owner', 'editor']));

drop policy if exists "Owners and editors can delete reports" on public.reports;
create policy "Owners and editors can delete reports"
    on public.reports
    for delete
    to authenticated
    using (public.has_workspace_role(workspace_id, auth.uid(), array['owner', 'editor']));
