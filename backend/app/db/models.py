"""
SQLAlchemy 2.x Declarative Models (Milestones 3, 4, 5)

Models for:
- users
- sessions
- workspaces
- workspace_members
- uploads
- datasets
- templates
- dashboards
- exports
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    JSON,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.db.session import Base

# Dialect-agnostic JSON type that uses native JSONB on PostgreSQL and JSON on SQLite
JSONType = JSON().with_variant(JSONB, "postgresql")


class User(Base):
    __tablename__ = "users"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=True)
    display_name = Column(String(255), nullable=True)
    role = Column(String(50), nullable=False, default="user")
    status = Column(String(50), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), onupdate=lambda: dt.datetime.now(dt.timezone.utc), nullable=False)

    uploads = relationship("Upload", back_populates="user", cascade="all, delete-orphan")
    templates = relationship("Template", back_populates="user")
    dashboards = relationship("Dashboard", back_populates="user")
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    workspace_memberships = relationship("WorkspaceMember", back_populates="user", cascade="all, delete-orphan")


class Session(Base):
    __tablename__ = "sessions"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False)
    last_used_at = Column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(255), nullable=True)

    user = relationship("User", back_populates="sessions")


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    created_by_id = Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), onupdate=lambda: dt.datetime.now(dt.timezone.utc), nullable=False)

    members = relationship("WorkspaceMember", back_populates="workspace", cascade="all, delete-orphan")
    uploads = relationship("Upload", back_populates="workspace")
    templates = relationship("Template", back_populates="workspace")
    dashboards = relationship("Dashboard", back_populates="workspace")


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(50), nullable=False, default="viewer")
    created_at = Column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False)

    workspace = relationship("Workspace", back_populates="members")
    user = relationship("User", back_populates="workspace_memberships")

    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),
        CheckConstraint(
            role.in_(["admin", "editor", "viewer"]),
            name="valid_workspace_role",
        ),
    )


class Upload(Base):
    __tablename__ = "uploads"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    workspace_id = Column(Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True)
    original_filename = Column(String(512), nullable=False)
    sanitized_filename = Column(String(512), nullable=False)
    storage_key = Column(String(1024), nullable=False, unique=True)
    file_size_bytes = Column(Integer, nullable=False)
    file_type = Column(String(50), nullable=False)
    sha256_hash = Column(String(64), nullable=False, index=True)
    status = Column(String(50), nullable=False, default="queued", index=True)
    stage = Column(String(100), nullable=True)
    progress = Column(Integer, nullable=True, default=0)
    error_code = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), onupdate=lambda: dt.datetime.now(dt.timezone.utc), nullable=False)

    user = relationship("User", back_populates="uploads")
    workspace = relationship("Workspace", back_populates="uploads")
    datasets = relationship("Dataset", back_populates="upload", cascade="all, delete-orphan")
    dashboards = relationship("Dashboard", back_populates="upload", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            status.in_(["queued", "scanning", "needs_mapping", "ready", "failed"]),
            name="valid_upload_status",
        ),
    )


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    upload_id = Column(Uuid(as_uuid=True), ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False, index=True)
    sheet_name = Column(String(255), nullable=False)
    cell_range = Column(String(100), nullable=False)
    kind = Column(String(50), nullable=False, default="tidy")
    column_metadata = Column(JSONType, nullable=False, default=list)
    normalization_status = Column(String(50), nullable=False, default="raw")
    parquet_storage_key = Column(String(1024), nullable=True)
    row_count = Column(Integer, nullable=False, default=0)
    column_count = Column(Integer, nullable=False, default=0)
    summary_metadata = Column(JSONType, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), onupdate=lambda: dt.datetime.now(dt.timezone.utc), nullable=False)

    upload = relationship("Upload", back_populates="datasets")

    __table_args__ = (
        CheckConstraint(
            kind.in_(["tidy", "wide", "records", "form", "unknown"]),
            name="valid_dataset_kind",
        ),
        Index("idx_dataset_upload_sheet", "upload_id", "sheet_name"),
    )


class Template(Base):
    __tablename__ = "templates"

    id = Column(String(128), primary_key=True)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    workspace_id = Column(Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    description = Column(Text, nullable=True)
    matching_rules = Column(JSONType, nullable=False, default=dict)
    column_mapping = Column(JSONType, nullable=False, default=dict)
    normalization_decisions = Column(JSONType, nullable=False, default=dict)
    dashboard_spec = Column(JSONType, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), onupdate=lambda: dt.datetime.now(dt.timezone.utc), nullable=False)

    user = relationship("User", back_populates="templates")
    workspace = relationship("Workspace", back_populates="templates")
    dashboards = relationship("Dashboard", back_populates="template")


class Dashboard(Base):
    __tablename__ = "dashboards"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    upload_id = Column(Uuid(as_uuid=True), ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False, index=True)
    template_id = Column(String(128), ForeignKey("templates.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    workspace_id = Column(Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    spec = Column(JSONType, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), onupdate=lambda: dt.datetime.now(dt.timezone.utc), nullable=False)

    upload = relationship("Upload", back_populates="dashboards")
    template = relationship("Template", back_populates="dashboards")
    user = relationship("User", back_populates="dashboards")
    workspace = relationship("Workspace", back_populates="dashboards")
    exports = relationship("Export", back_populates="dashboard", cascade="all, delete-orphan")


class Export(Base):
    __tablename__ = "exports"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    dashboard_id = Column(Uuid(as_uuid=True), ForeignKey("dashboards.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    format = Column(String(20), nullable=False)
    status = Column(String(50), nullable=False, default="queued", index=True)
    output_storage_key = Column(String(1024), nullable=True)
    file_size_bytes = Column(BigInteger, nullable=True)
    options = Column(JSONType, nullable=True, default=dict)
    error_code = Column(String(100), nullable=True)
    error_info = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), onupdate=lambda: dt.datetime.now(dt.timezone.utc), nullable=False)

    dashboard = relationship("Dashboard", back_populates="exports")
    workspace = relationship("Workspace")
    user = relationship("User")

    @property
    def storage_key(self) -> Optional[str]:
        return self.output_storage_key

    @storage_key.setter
    def storage_key(self, val: Optional[str]) -> None:
        self.output_storage_key = val

    @property
    def error_message(self) -> Optional[str]:
        return self.error_info

    @error_message.setter
    def error_message(self, val: Optional[str]) -> None:
        self.error_info = val

    __table_args__ = (
        CheckConstraint(
            format.in_(["pdf", "xlsx", "png", "csv", "pptx"]),
            name="valid_export_format",
        ),
        CheckConstraint(
            status.in_(["queued", "pending", "processing", "ready", "completed", "failed"]),
            name="valid_export_status",
        ),
    )
