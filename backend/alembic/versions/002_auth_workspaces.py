"""Auth and Workspaces schema

Revision ID: 002_auth_workspaces
Revises: 001_initial_schema
Create Date: 2026-10-25 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '002_auth_workspaces'
down_revision: Union[str, None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update users table with password_hash and status
    op.add_column('users', sa.Column('password_hash', sa.String(255), nullable=True))
    op.add_column('users', sa.Column('status', sa.String(50), nullable=False, server_default='active'))

    # 2. Create workspaces table
    op.create_table(
        'workspaces',
        sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('created_by_id', sa.Uuid(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_workspaces_created_by', 'workspaces', ['created_by_id'])

    # 3. Create workspace_members table
    op.create_table(
        'workspace_members',
        sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column('workspace_id', sa.Uuid(as_uuid=True), sa.ForeignKey('workspaces.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Uuid(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(50), nullable=False, server_default='viewer'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('workspace_id', 'user_id', name='uq_workspace_member'),
        sa.CheckConstraint("role IN ('admin', 'editor', 'viewer')", name='valid_workspace_role'),
    )
    op.create_index('ix_workspace_members_workspace_id', 'workspace_members', ['workspace_id'])
    op.create_index('ix_workspace_members_user_id', 'workspace_members', ['user_id'])

    # 4. Create sessions table
    op.create_table(
        'sessions',
        sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column('user_id', sa.Uuid(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ip_address', sa.String(64), nullable=True),
        sa.Column('user_agent', sa.String(255), nullable=True),
    )
    op.create_index('ix_sessions_user_id', 'sessions', ['user_id'])
    op.create_index('ix_sessions_token_hash', 'sessions', ['token_hash'], unique=True)
    op.create_index('ix_sessions_expires_at', 'sessions', ['expires_at'])

    # 5. Add workspace_id foreign keys to uploads, templates, and dashboards
    op.add_column('uploads', sa.Column('workspace_id', sa.Uuid(as_uuid=True), sa.ForeignKey('workspaces.id', ondelete='SET NULL'), nullable=True))
    op.create_index('ix_uploads_workspace_id', 'uploads', ['workspace_id'])

    op.add_column('templates', sa.Column('workspace_id', sa.Uuid(as_uuid=True), sa.ForeignKey('workspaces.id', ondelete='SET NULL'), nullable=True))
    op.create_index('ix_templates_workspace_id', 'templates', ['workspace_id'])

    op.add_column('dashboards', sa.Column('workspace_id', sa.Uuid(as_uuid=True), sa.ForeignKey('workspaces.id', ondelete='SET NULL'), nullable=True))
    op.create_index('ix_dashboards_workspace_id', 'dashboards', ['workspace_id'])


def downgrade() -> None:
    op.drop_index('ix_dashboards_workspace_id', table_name='dashboards')
    op.drop_column('dashboards', 'workspace_id')

    op.drop_index('ix_templates_workspace_id', table_name='templates')
    op.drop_column('templates', 'workspace_id')

    op.drop_index('ix_uploads_workspace_id', table_name='uploads')
    op.drop_column('uploads', 'workspace_id')

    op.drop_index('ix_sessions_expires_at', table_name='sessions')
    op.drop_index('ix_sessions_token_hash', table_name='sessions')
    op.drop_index('ix_sessions_user_id', table_name='sessions')
    op.drop_table('sessions')

    op.drop_index('ix_workspace_members_user_id', table_name='workspace_members')
    op.drop_index('ix_workspace_members_workspace_id', table_name='workspace_members')
    op.drop_table('workspace_members')

    op.drop_index('ix_workspaces_created_by', table_name='workspaces')
    op.drop_table('workspaces')

    op.drop_column('users', 'status')
    op.drop_column('users', 'password_hash')
