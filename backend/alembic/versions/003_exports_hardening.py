"""Exports hardening schema

Revision ID: 003_exports_hardening
Revises: 002_auth_workspaces
Create Date: 2026-10-25 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '003_exports_hardening'
down_revision: Union[str, None] = '002_auth_workspaces'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add workspace_id to exports
    op.add_column('exports', sa.Column('workspace_id', sa.Uuid(as_uuid=True), sa.ForeignKey('workspaces.id', ondelete='CASCADE'), nullable=True))
    op.create_index('ix_exports_workspace_id', 'exports', ['workspace_id'])

    # 2. Add file_size_bytes, options, error_code, completed_at
    op.add_column('exports', sa.Column('file_size_bytes', sa.BigInteger(), nullable=True))
    op.add_column('exports', sa.Column('options', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True))
    op.add_column('exports', sa.Column('error_code', sa.String(100), nullable=True))
    op.add_column('exports', sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True))

    # 3. Update check constraints on exports
    try:
        op.drop_constraint('valid_export_format', 'exports', type_='check')
    except Exception:
        pass
    op.create_check_constraint(
        'valid_export_format',
        'exports',
        "format IN ('pdf', 'xlsx', 'png', 'csv', 'pptx')"
    )

    try:
        op.drop_constraint('valid_export_status', 'exports', type_='check')
    except Exception:
        pass
    op.create_check_constraint(
        'valid_export_status',
        'exports',
        "status IN ('queued', 'pending', 'processing', 'ready', 'completed', 'failed')"
    )


def downgrade() -> None:
    try:
        op.drop_constraint('valid_export_status', 'exports', type_='check')
        op.create_check_constraint(
            'valid_export_status',
            'exports',
            "status IN ('pending', 'processing', 'completed', 'failed')"
        )
    except Exception:
        pass

    try:
        op.drop_constraint('valid_export_format', 'exports', type_='check')
        op.create_check_constraint(
            'valid_export_format',
            'exports',
            "format IN ('pdf', 'xlsx', 'png', 'pptx')"
        )
    except Exception:
        pass

    op.drop_column('exports', 'completed_at')
    op.drop_column('exports', 'error_code')
    op.drop_column('exports', 'options')
    op.drop_column('exports', 'file_size_bytes')

    op.drop_index('ix_exports_workspace_id', table_name='exports')
    op.drop_column('exports', 'workspace_id')
