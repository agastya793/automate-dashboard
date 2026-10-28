"""Initial schema for users, uploads, datasets, templates, dashboards, and exports

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-10-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# JSONB on PostgreSQL, JSON on SQLite
JSONType = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


def upgrade() -> None:
    # 1. users
    op.create_table(
        'users',
        sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('display_name', sa.String(255), nullable=True),
        sa.Column('role', sa.String(50), nullable=False, server_default='viewer'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    # 2. uploads
    op.create_table(
        'uploads',
        sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column('user_id', sa.Uuid(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('original_filename', sa.String(512), nullable=False),
        sa.Column('sanitized_filename', sa.String(512), nullable=False),
        sa.Column('storage_key', sa.String(1024), nullable=False, unique=True),
        sa.Column('file_size_bytes', sa.Integer(), nullable=False),
        sa.Column('file_type', sa.String(50), nullable=False),
        sa.Column('sha256_hash', sa.String(64), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='queued'),
        sa.Column('stage', sa.String(100), nullable=True),
        sa.Column('progress', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('error_code', sa.String(100), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'scanning', 'needs_mapping', 'ready', 'failed')",
            name='valid_upload_status',
        ),
    )
    op.create_index('ix_uploads_status', 'uploads', ['status'])
    op.create_index('ix_uploads_sha256', 'uploads', ['sha256_hash'])

    # 3. datasets
    op.create_table(
        'datasets',
        sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column('upload_id', sa.Uuid(as_uuid=True), sa.ForeignKey('uploads.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sheet_name', sa.String(255), nullable=False),
        sa.Column('cell_range', sa.String(100), nullable=False),
        sa.Column('kind', sa.String(50), nullable=False, server_default='tidy'),
        sa.Column('column_metadata', JSONType, nullable=False),
        sa.Column('normalization_status', sa.String(50), nullable=False, server_default='raw'),
        sa.Column('parquet_storage_key', sa.String(1024), nullable=True),
        sa.Column('row_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('column_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('summary_metadata', JSONType, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('tidy', 'wide', 'records', 'form', 'unknown')",
            name='valid_dataset_kind',
        ),
    )
    op.create_index('ix_datasets_upload_id', 'datasets', ['upload_id'])
    op.create_index('idx_dataset_upload_sheet', 'datasets', ['upload_id', 'sheet_name'])

    # 4. templates
    op.create_table(
        'templates',
        sa.Column('id', sa.String(128), primary_key=True),
        sa.Column('user_id', sa.Uuid(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('matching_rules', JSONType, nullable=False),
        sa.Column('column_mapping', JSONType, nullable=False),
        sa.Column('normalization_decisions', JSONType, nullable=False),
        sa.Column('dashboard_spec', JSONType, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # 5. dashboards
    op.create_table(
        'dashboards',
        sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column('upload_id', sa.Uuid(as_uuid=True), sa.ForeignKey('uploads.id', ondelete='CASCADE'), nullable=False),
        sa.Column('template_id', sa.String(128), sa.ForeignKey('templates.id', ondelete='SET NULL'), nullable=True),
        sa.Column('user_id', sa.Uuid(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('spec', JSONType, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_dashboards_upload_id', 'dashboards', ['upload_id'])

    # 6. exports
    op.create_table(
        'exports',
        sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column('dashboard_id', sa.Uuid(as_uuid=True), sa.ForeignKey('dashboards.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Uuid(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('format', sa.String(20), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('output_storage_key', sa.String(1024), nullable=True),
        sa.Column('error_info', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "format IN ('pdf', 'xlsx', 'png', 'pptx')",
            name='valid_export_format',
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name='valid_export_status',
        ),
    )
    op.create_index('ix_exports_dashboard_id', 'exports', ['dashboard_id'])


def downgrade() -> None:
    op.drop_table('exports')
    op.drop_table('dashboards')
    op.drop_table('templates')
    op.drop_table('datasets')
    op.drop_table('uploads')
    op.drop_table('users')
