"""
Database Repositories (Milestones 3, 4, 5)

Provides clean, encapsulated data access interfaces for:
- Users
- Sessions
- Workspaces and Workspace Members
- Uploads
- Datasets
- Templates
- Dashboards
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, select
from sqlalchemy.orm import Session as DBSession

from app.db.models import (
    Dashboard,
    Dataset,
    Export,
    Session,
    Template,
    Upload,
    User,
    Workspace,
    WorkspaceMember,
)


def _to_uuid(val: uuid.UUID | str | None) -> Optional[uuid.UUID]:
    if val is None:
        return None
    return uuid.UUID(str(val)) if not isinstance(val, uuid.UUID) else val


class UserRepository:
    """Repository for User identity entity."""

    def __init__(self, db: DBSession):
        self.db = db

    def create(
        self,
        email: str,
        password_hash: Optional[str] = None,
        display_name: Optional[str] = None,
        role: str = "user",
        status: str = "active",
        user_id: Optional[uuid.UUID | str] = None,
    ) -> User:
        user = User(
            id=_to_uuid(user_id) or uuid.uuid4(),
            email=email.strip().lower(),
            password_hash=password_hash,
            display_name=display_name.strip() if display_name else None,
            role=role,
            status=status,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def get_by_id(self, user_id: uuid.UUID | str) -> Optional[User]:
        uid = _to_uuid(user_id)
        return self.db.get(User, uid) if uid else None

    def get_by_email(self, email: str) -> Optional[User]:
        stmt = select(User).where(User.email == email.strip().lower())
        return self.db.scalars(stmt).first()

    def update_password(self, user_id: uuid.UUID | str, password_hash: str) -> Optional[User]:
        user = self.get_by_id(user_id)
        if not user:
            return None
        user.password_hash = password_hash
        user.updated_at = dt.datetime.now(dt.timezone.utc)
        self.db.commit()
        self.db.refresh(user)
        return user

    def update_status(self, user_id: uuid.UUID | str, status: str) -> Optional[User]:
        user = self.get_by_id(user_id)
        if not user:
            return None
        user.status = status
        user.updated_at = dt.datetime.now(dt.timezone.utc)
        self.db.commit()
        self.db.refresh(user)
        return user


class SessionRepository:
    """Repository for server-side Sessions."""

    def __init__(self, db: DBSession):
        self.db = db

    def create(
        self,
        user_id: uuid.UUID | str,
        token_hash: str,
        expires_at: dt.datetime,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Session:
        session = Session(
            id=uuid.uuid4(),
            user_id=_to_uuid(user_id),
            token_hash=token_hash,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_valid_session(self, token_hash: str) -> Optional[Session]:
        now = dt.datetime.now(dt.timezone.utc)
        stmt = (
            select(Session)
            .where(
                and_(
                    Session.token_hash == token_hash,
                    Session.revoked_at.is_(None),
                    Session.expires_at > now,
                )
            )
        )
        return self.db.scalars(stmt).first()

    def touch(self, session_id: uuid.UUID | str) -> None:
        sid = _to_uuid(session_id)
        session = self.db.get(Session, sid)
        if session:
            session.last_used_at = dt.datetime.now(dt.timezone.utc)
            self.db.commit()

    def revoke(self, session_id: uuid.UUID | str) -> bool:
        sid = _to_uuid(session_id)
        session = self.db.get(Session, sid)
        if not session or session.revoked_at is not None:
            return False
        session.revoked_at = dt.datetime.now(dt.timezone.utc)
        self.db.commit()
        return True

    def revoke_by_token_hash(self, token_hash: str) -> bool:
        stmt = select(Session).where(Session.token_hash == token_hash)
        session = self.db.scalars(stmt).first()
        if not session or session.revoked_at is not None:
            return False
        session.revoked_at = dt.datetime.now(dt.timezone.utc)
        self.db.commit()
        return True

    def revoke_all_for_user(self, user_id: uuid.UUID | str) -> int:
        uid = _to_uuid(user_id)
        now = dt.datetime.now(dt.timezone.utc)
        stmt = select(Session).where(
            and_(
                Session.user_id == uid,
                Session.revoked_at.is_(None),
            )
        )
        sessions = list(self.db.scalars(stmt).all())
        for s in sessions:
            s.revoked_at = now
        self.db.commit()
        return len(sessions)

    def cleanup_expired(self) -> int:
        now = dt.datetime.now(dt.timezone.utc)
        stmt = select(Session).where(Session.expires_at <= now)
        expired = list(self.db.scalars(stmt).all())
        for s in expired:
            self.db.delete(s)
        self.db.commit()
        return len(expired)


class WorkspaceRepository:
    """Repository for Workspaces and Workspace Memberships."""

    def __init__(self, db: DBSession):
        self.db = db

    def create(
        self,
        name: str,
        created_by_id: Optional[uuid.UUID | str] = None,
        workspace_id: Optional[uuid.UUID | str] = None,
    ) -> Workspace:
        ws = Workspace(
            id=_to_uuid(workspace_id) or uuid.uuid4(),
            name=name.strip(),
            created_by_id=_to_uuid(created_by_id),
        )
        self.db.add(ws)
        self.db.commit()
        self.db.refresh(ws)
        return ws

    def get(self, workspace_id: uuid.UUID | str) -> Optional[Workspace]:
        wid = _to_uuid(workspace_id)
        return self.db.get(Workspace, wid) if wid else None

    def add_member(
        self,
        workspace_id: uuid.UUID | str,
        user_id: uuid.UUID | str,
        role: str = "viewer",
    ) -> WorkspaceMember:
        wid = _to_uuid(workspace_id)
        uid = _to_uuid(user_id)
        existing = self.get_member(wid, uid)
        if existing:
            existing.role = role
            self.db.commit()
            self.db.refresh(existing)
            return existing

        member = WorkspaceMember(
            id=uuid.uuid4(),
            workspace_id=wid,
            user_id=uid,
            role=role,
        )
        self.db.add(member)
        self.db.commit()
        self.db.refresh(member)
        return member

    def get_member(
        self,
        workspace_id: uuid.UUID | str,
        user_id: uuid.UUID | str,
    ) -> Optional[WorkspaceMember]:
        wid = _to_uuid(workspace_id)
        uid = _to_uuid(user_id)
        stmt = select(WorkspaceMember).where(
            and_(
                WorkspaceMember.workspace_id == wid,
                WorkspaceMember.user_id == uid,
            )
        )
        return self.db.scalars(stmt).first()

    def update_member_role(
        self,
        workspace_id: uuid.UUID | str,
        user_id: uuid.UUID | str,
        role: str,
    ) -> Optional[WorkspaceMember]:
        member = self.get_member(workspace_id, user_id)
        if not member:
            return None
        member.role = role
        self.db.commit()
        self.db.refresh(member)
        return member

    def remove_member(
        self,
        workspace_id: uuid.UUID | str,
        user_id: uuid.UUID | str,
    ) -> bool:
        member = self.get_member(workspace_id, user_id)
        if not member:
            return False
        self.db.delete(member)
        self.db.commit()
        return True

    def list_user_workspaces(self, user_id: uuid.UUID | str) -> List[Dict[str, Any]]:
        uid = _to_uuid(user_id)
        stmt = (
            select(Workspace, WorkspaceMember.role)
            .join(WorkspaceMember, Workspace.id == WorkspaceMember.workspace_id)
            .where(WorkspaceMember.user_id == uid)
            .order_by(desc(Workspace.created_at))
        )
        results = self.db.execute(stmt).all()
        return [
            {
                "id": str(ws.id),
                "name": ws.name,
                "role": role,
                "created_by_id": str(ws.created_by_id) if ws.created_by_id else None,
                "created_at": ws.created_at.isoformat() if ws.created_at else "",
            }
            for ws, role in results
        ]

    def list_members(self, workspace_id: uuid.UUID | str) -> List[WorkspaceMember]:
        wid = _to_uuid(workspace_id)
        stmt = (
            select(WorkspaceMember)
            .where(WorkspaceMember.workspace_id == wid)
            .order_by(WorkspaceMember.created_at)
        )
        return list(self.db.scalars(stmt).all())


class UploadRepository:
    """Repository for Upload metadata entity."""

    def __init__(self, db: DBSession):
        self.db = db

    def create(
        self,
        original_filename: str,
        sanitized_filename: str,
        storage_key: str,
        file_size_bytes: int,
        file_type: str,
        sha256_hash: str,
        user_id: Optional[uuid.UUID | str] = None,
        workspace_id: Optional[uuid.UUID | str] = None,
        upload_id: Optional[uuid.UUID | str] = None,
    ) -> Upload:
        upload = Upload(
            id=_to_uuid(upload_id) or uuid.uuid4(),
            user_id=_to_uuid(user_id),
            workspace_id=_to_uuid(workspace_id),
            original_filename=original_filename,
            sanitized_filename=sanitized_filename,
            storage_key=storage_key,
            file_size_bytes=file_size_bytes,
            file_type=file_type,
            sha256_hash=sha256_hash,
            status="queued",
            stage="queued",
            progress=0,
        )
        self.db.add(upload)
        self.db.commit()
        self.db.refresh(upload)
        return upload

    def get(self, upload_id: uuid.UUID | str) -> Optional[Upload]:
        uid = _to_uuid(upload_id)
        return self.db.get(Upload, uid) if uid else None

    def list_recent(
        self,
        limit: int = 50,
        offset: int = 0,
        workspace_id: Optional[uuid.UUID | str] = None,
        user_id: Optional[uuid.UUID | str] = None,
    ) -> List[Upload]:
        stmt = select(Upload)
        wid = _to_uuid(workspace_id)
        uid = _to_uuid(user_id)
        if wid:
            stmt = stmt.where(Upload.workspace_id == wid)
        elif uid:
            stmt = stmt.where(Upload.user_id == uid)

        stmt = stmt.order_by(desc(Upload.created_at)).limit(limit).offset(offset)
        return list(self.db.scalars(stmt).all())

    def count(
        self,
        workspace_id: Optional[uuid.UUID | str] = None,
        user_id: Optional[uuid.UUID | str] = None,
    ) -> int:
        from sqlalchemy import func
        stmt = select(func.count(Upload.id))
        wid = _to_uuid(workspace_id)
        uid = _to_uuid(user_id)
        if wid:
            stmt = stmt.where(Upload.workspace_id == wid)
        elif uid:
            stmt = stmt.where(Upload.user_id == uid)
        return self.db.scalar(stmt) or 0

    def update_status(
        self,
        upload_id: uuid.UUID | str,
        status: str,
        stage: Optional[str] = None,
        progress: Optional[int] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> Optional[Upload]:
        upload = self.get(upload_id)
        if not upload:
            return None

        upload.status = status
        if stage is not None:
            upload.stage = stage
        if progress is not None:
            upload.progress = progress
        if error_code is not None:
            upload.error_code = error_code
        if error_message is not None:
            upload.error_message = error_message

        upload.updated_at = dt.datetime.now(dt.timezone.utc)
        self.db.commit()
        self.db.refresh(upload)
        return upload


class DatasetRepository:
    """Repository for detected and normalized Dataset entities."""

    def __init__(self, db: DBSession):
        self.db = db

    def create(
        self,
        upload_id: uuid.UUID | str,
        sheet_name: str,
        cell_range: str,
        kind: str,
        column_metadata: List[Dict[str, Any]],
        normalization_status: str = "raw",
        row_count: int = 0,
        column_count: int = 0,
        parquet_storage_key: Optional[str] = None,
        summary_metadata: Optional[Dict[str, Any]] = None,
        dataset_id: Optional[uuid.UUID | str] = None,
    ) -> Dataset:
        uid = _to_uuid(upload_id)
        dataset = Dataset(
            id=_to_uuid(dataset_id) or uuid.uuid4(),
            upload_id=uid,
            sheet_name=sheet_name,
            cell_range=cell_range,
            kind=kind,
            column_metadata=column_metadata,
            normalization_status=normalization_status,
            row_count=row_count,
            column_count=column_count,
            parquet_storage_key=parquet_storage_key,
            summary_metadata=summary_metadata or {},
        )
        self.db.add(dataset)
        self.db.commit()
        self.db.refresh(dataset)
        return dataset

    def get(self, dataset_id: uuid.UUID | str) -> Optional[Dataset]:
        did = _to_uuid(dataset_id)
        return self.db.get(Dataset, did) if did else None

    def list_by_upload(self, upload_id: uuid.UUID | str) -> List[Dataset]:
        uid = _to_uuid(upload_id)
        stmt = select(Dataset).where(Dataset.upload_id == uid).order_by(Dataset.sheet_name, Dataset.cell_range)
        return list(self.db.scalars(stmt).all())

    def count_by_upload(self, upload_id: uuid.UUID | str) -> int:
        from sqlalchemy import func
        uid = _to_uuid(upload_id)
        return self.db.scalar(select(func.count(Dataset.id)).where(Dataset.upload_id == uid)) or 0

    def update_parquet_key(
        self,
        dataset_id: uuid.UUID | str,
        parquet_storage_key: str,
        row_count: int,
        column_count: int,
        normalization_status: str = "normalized",
    ) -> Optional[Dataset]:
        dataset = self.get(dataset_id)
        if not dataset:
            return None

        dataset.parquet_storage_key = parquet_storage_key
        dataset.row_count = row_count
        dataset.column_count = column_count
        dataset.normalization_status = normalization_status
        dataset.updated_at = dt.datetime.now(dt.timezone.utc)

        self.db.commit()
        self.db.refresh(dataset)
        return dataset

    def delete_by_upload(self, upload_id: uuid.UUID | str) -> int:
        """Deletes all datasets for an upload. Returns count of deleted rows."""
        datasets = self.list_by_upload(upload_id)
        count = len(datasets)
        for d in datasets:
            self.db.delete(d)
        self.db.commit()
        return count


class TemplateRepository:
    """Repository for reusable MappingTemplate entities in PostgreSQL."""

    def __init__(self, db: DBSession):
        self.db = db

    def save(
        self,
        template_id: str,
        name: str,
        blocks_data: List[Dict[str, Any]],
        description: Optional[str] = None,
        source_of_truth: Optional[Dict[str, Any]] = None,
        user_id: Optional[uuid.UUID | str] = None,
        workspace_id: Optional[uuid.UUID | str] = None,
    ) -> Template:
        existing = self.db.get(Template, template_id)
        now = dt.datetime.now(dt.timezone.utc)

        if existing:
            existing.name = name
            existing.version = existing.version + 1
            existing.description = description
            existing.column_mapping = {"blocks": blocks_data}
            existing.normalization_decisions = source_of_truth or {}
            existing.updated_at = now
            if workspace_id:
                existing.workspace_id = _to_uuid(workspace_id)
            self.db.commit()
            self.db.refresh(existing)
            return existing
        else:
            template = Template(
                id=template_id,
                user_id=_to_uuid(user_id),
                workspace_id=_to_uuid(workspace_id),
                name=name,
                version=1,
                description=description,
                matching_rules={},
                column_mapping={"blocks": blocks_data},
                normalization_decisions=source_of_truth or {},
                dashboard_spec=None,
                created_at=now,
                updated_at=now,
            )
            self.db.add(template)
            self.db.commit()
            self.db.refresh(template)
            return template

    def get(self, template_id: str) -> Optional[Template]:
        return self.db.get(Template, template_id)

    def list_all(
        self,
        workspace_id: Optional[uuid.UUID | str] = None,
        user_id: Optional[uuid.UUID | str] = None,
    ) -> List[Template]:
        stmt = select(Template)
        wid = _to_uuid(workspace_id)
        uid = _to_uuid(user_id)
        if wid:
            stmt = stmt.where(Template.workspace_id == wid)
        elif uid:
            stmt = stmt.where(Template.user_id == uid)

        stmt = stmt.order_by(desc(Template.updated_at))
        return list(self.db.scalars(stmt).all())

    def delete(self, template_id: str) -> bool:
        template = self.get(template_id)
        if not template:
            return False
        self.db.delete(template)
        self.db.commit()
        return True


class DashboardRepository:
    """Repository for Dashboard entities."""

    def __init__(self, db: DBSession):
        self.db = db

    def create(
        self,
        upload_id: uuid.UUID | str,
        title: str,
        spec: Dict[str, Any],
        template_id: Optional[str] = None,
        user_id: Optional[uuid.UUID | str] = None,
        workspace_id: Optional[uuid.UUID | str] = None,
    ) -> Dashboard:
        uid = _to_uuid(upload_id)
        dashboard = Dashboard(
            id=uuid.uuid4(),
            upload_id=uid,
            template_id=template_id,
            user_id=_to_uuid(user_id),
            workspace_id=_to_uuid(workspace_id),
            title=title,
            spec=spec,
        )
        self.db.add(dashboard)
        self.db.commit()
        self.db.refresh(dashboard)
        return dashboard

    def get(self, dashboard_id: uuid.UUID | str) -> Optional[Dashboard]:
        did = _to_uuid(dashboard_id)
        return self.db.get(Dashboard, did) if did else None

    def list_recent(
        self,
        limit: int = 50,
        workspace_id: Optional[uuid.UUID | str] = None,
        user_id: Optional[uuid.UUID | str] = None,
    ) -> List[Dashboard]:
        stmt = select(Dashboard)
        wid = _to_uuid(workspace_id)
        uid = _to_uuid(user_id)
        if wid:
            stmt = stmt.where(Dashboard.workspace_id == wid)
        elif uid:
            stmt = stmt.where(Dashboard.user_id == uid)

        stmt = stmt.order_by(desc(Dashboard.created_at)).limit(limit)
        return list(self.db.scalars(stmt).all())

    def list_by_upload(self, upload_id: uuid.UUID | str) -> List[Dashboard]:
        uid = _to_uuid(upload_id)
        stmt = select(Dashboard).where(Dashboard.upload_id == uid).order_by(desc(Dashboard.created_at))
        return list(self.db.scalars(stmt).all())

    def update(
        self,
        dashboard_id: uuid.UUID | str,
        title: Optional[str] = None,
        spec: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dashboard]:
        dashboard = self.get(dashboard_id)
        if not dashboard:
            return None
        if title is not None:
            dashboard.title = title
        if spec is not None:
            dashboard.spec = spec
        dashboard.updated_at = dt.datetime.now(dt.timezone.utc)
        self.db.commit()
        self.db.refresh(dashboard)
        return dashboard

    def duplicate(
        self,
        dashboard_id: uuid.UUID | str,
        new_title: str,
        user_id: Optional[uuid.UUID | str] = None,
        workspace_id: Optional[uuid.UUID | str] = None,
    ) -> Optional[Dashboard]:
        source = self.get(dashboard_id)
        if not source:
            return None
        import copy
        new_spec = copy.deepcopy(source.spec) if source.spec else {}
        dup = Dashboard(
            id=uuid.uuid4(),
            upload_id=source.upload_id,
            template_id=source.template_id,
            user_id=_to_uuid(user_id) or source.user_id,
            workspace_id=_to_uuid(workspace_id) or source.workspace_id,
            title=new_title,
            spec=new_spec,
        )
        self.db.add(dup)
        self.db.commit()
        self.db.refresh(dup)
        return dup

    def delete(self, dashboard_id: uuid.UUID | str) -> bool:
        dashboard = self.get(dashboard_id)
        if not dashboard:
            return False
        self.db.delete(dashboard)
        self.db.commit()
        return True


class ExportRepository:
    """Repository for Export entities."""

    def __init__(self, db: DBSession):
        self.db = db

    def create(
        self,
        dashboard_id: uuid.UUID | str,
        format: str,
        user_id: Optional[uuid.UUID | str] = None,
        workspace_id: Optional[uuid.UUID | str] = None,
        storage_key: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
        status: str = "queued",
    ) -> Export:
        export = Export(
            id=uuid.uuid4(),
            dashboard_id=_to_uuid(dashboard_id),
            user_id=_to_uuid(user_id),
            workspace_id=_to_uuid(workspace_id),
            format=format,
            output_storage_key=storage_key,
            status=status,
            options=options or {},
        )
        self.db.add(export)
        self.db.commit()
        self.db.refresh(export)
        return export

    def get(self, export_id: uuid.UUID | str) -> Optional[Export]:
        eid = _to_uuid(export_id)
        return self.db.get(Export, eid) if eid else None

    def list_by_dashboard(
        self,
        dashboard_id: uuid.UUID | str,
        limit: int = 50,
    ) -> List[Export]:
        did = _to_uuid(dashboard_id)
        stmt = (
            select(Export)
            .where(Export.dashboard_id == did)
            .order_by(desc(Export.created_at))
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def list_by_workspace(
        self,
        workspace_id: uuid.UUID | str,
        limit: int = 50,
    ) -> List[Export]:
        wid = _to_uuid(workspace_id)
        stmt = (
            select(Export)
            .where(Export.workspace_id == wid)
            .order_by(desc(Export.created_at))
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def update_status(
        self,
        export_id: uuid.UUID | str,
        status: str,
        output_storage_key: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
        error_code: Optional[str] = None,
        error_info: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> Optional[Export]:
        export = self.get(export_id)
        if not export:
            return None
        export.status = status
        if output_storage_key is not None:
            export.output_storage_key = output_storage_key
        if file_size_bytes is not None:
            export.file_size_bytes = file_size_bytes
        if error_code is not None:
            export.error_code = error_code
        err_text = error_message if error_message is not None else error_info
        if err_text is not None:
            export.error_info = err_text
        if status in ("ready", "completed", "failed"):
            export.completed_at = dt.datetime.now(dt.timezone.utc)
        export.updated_at = dt.datetime.now(dt.timezone.utc)
        self.db.commit()
        self.db.refresh(export)
        return export

    def delete(self, export_id: uuid.UUID | str) -> bool:
        export = self.get(export_id)
        if not export:
            return False
        self.db.delete(export)
        self.db.commit()
        return True

