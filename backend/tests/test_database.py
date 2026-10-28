"""
Tests for PostgreSQL Metadata Layer and Repositories (Milestone 3).

Uses SQLite in-memory database to test models and repositories in isolation
without requiring an external PostgreSQL server.
"""

import json
import tempfile
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Dashboard, Dataset, Template, Upload, User
from app.db.repositories import (
    DashboardRepository,
    DatasetRepository,
    TemplateRepository,
    UploadRepository,
)
from scripts.migrate_templates_to_pg import migrate_json_templates


@pytest.fixture
def db_session():
    """Create an isolated in-memory SQLite database session."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


class TestUploadRepository:

    def test_create_and_get_upload(self, db_session):
        repo = UploadRepository(db_session)
        upload = repo.create(
            original_filename="Q1_Report.xlsx",
            sanitized_filename="Q1_Report.xlsx",
            storage_key="uploads/u-1/original.xlsx",
            file_size_bytes=10240,
            file_type="xlsx",
            sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )

        assert upload.id is not None
        assert upload.status == "queued"
        assert upload.stage == "queued"
        assert upload.original_filename == "Q1_Report.xlsx"

        retrieved = repo.get(upload.id)
        assert retrieved is not None
        assert retrieved.storage_key == "uploads/u-1/original.xlsx"

    def test_update_upload_status(self, db_session):
        repo = UploadRepository(db_session)
        upload = repo.create(
            original_filename="Data.csv",
            sanitized_filename="Data.csv",
            storage_key="uploads/u-2/original.csv",
            file_size_bytes=2048,
            file_type="csv",
            sha256_hash="abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        )

        updated = repo.update_status(
            upload.id,
            status="scanning",
            stage="detecting_blocks",
            progress=25,
        )
        assert updated.status == "scanning"
        assert updated.stage == "detecting_blocks"
        assert updated.progress == 25

        # Fail status
        failed = repo.update_status(
            upload.id,
            status="failed",
            error_code="INVALID_ARCHIVE",
            error_message="Workbook archive is corrupted.",
        )
        assert failed.status == "failed"
        assert failed.error_code == "INVALID_ARCHIVE"


class TestDatasetRepository:

    def test_create_and_list_datasets(self, db_session):
        upload_repo = UploadRepository(db_session)
        upload = upload_repo.create(
            original_filename="Multi.xlsx",
            sanitized_filename="Multi.xlsx",
            storage_key="uploads/u-3/original.xlsx",
            file_size_bytes=5000,
            file_type="xlsx",
            sha256_hash="1234567890123456789012345678901234567890123456789012345678901234",
        )

        repo = DatasetRepository(db_session)
        ds1 = repo.create(
            upload_id=upload.id,
            sheet_name="Defects",
            cell_range="A1:E20",
            kind="tidy",
            column_metadata=[{"name": "Defect", "role": "category"}],
            row_count=19,
            column_count=5,
        )

        ds2 = repo.create(
            upload_id=upload.id,
            sheet_name="Summary",
            cell_range="A1:C5",
            kind="form",
            column_metadata=[],
        )

        datasets = repo.list_by_upload(upload.id)
        assert len(datasets) == 2
        sheet_names = [d.sheet_name for d in datasets]
        assert "Defects" in sheet_names
        assert "Summary" in sheet_names

    def test_update_parquet_storage_key(self, db_session):
        upload_repo = UploadRepository(db_session)
        upload = upload_repo.create(
            original_filename="Tidy.csv",
            sanitized_filename="Tidy.csv",
            storage_key="uploads/u-4/original.csv",
            file_size_bytes=1000,
            file_type="csv",
            sha256_hash="0000000000000000000000000000000000000000000000000000000000000000",
        )

        repo = DatasetRepository(db_session)
        ds = repo.create(
            upload_id=upload.id,
            sheet_name="Sheet1",
            cell_range="A1:B10",
            kind="tidy",
            column_metadata=[],
        )

        updated = repo.update_parquet_key(
            ds.id,
            parquet_storage_key="datasets/ds-1/normalized.parquet",
            row_count=9,
            column_count=2,
            normalization_status="normalized",
        )
        assert updated.parquet_storage_key == "datasets/ds-1/normalized.parquet"
        assert updated.normalization_status == "normalized"
        assert updated.row_count == 9


class TestTemplateRepository:

    def test_save_and_version_template(self, db_session):
        repo = TemplateRepository(db_session)
        t_id = "test-tpl-001"

        saved1 = repo.save(
            template_id=t_id,
            name="Alpha Template",
            blocks_data=[{"sheet": "Defects", "range": "A1:D10"}],
            description="First version",
        )
        assert saved1.id == t_id
        assert saved1.version == 1
        assert saved1.name == "Alpha Template"

        # Update increments version
        saved2 = repo.save(
            template_id=t_id,
            name="Alpha Template Updated",
            blocks_data=[{"sheet": "Defects", "range": "A1:D15"}],
            description="Second version",
        )
        assert saved2.id == t_id
        assert saved2.version == 2
        assert saved2.name == "Alpha Template Updated"

    def test_list_and_delete_template(self, db_session):
        repo = TemplateRepository(db_session)
        repo.save("tpl-1", "Template 1", [])
        repo.save("tpl-2", "Template 2", [])

        templates = repo.list_all()
        assert len(templates) >= 2

        deleted = repo.delete("tpl-1")
        assert deleted is True
        assert repo.get("tpl-1") is None


class TestTemplateJSONMigration:

    def test_migrate_json_templates_idempotent(self, monkeypatch):
        # Create temp folder with sample JSON mapping
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            sample_template = {
                "id": "migrated-tpl-01",
                "name": "Migrated Q1 Template",
                "description": "Imported from Milestone 2 JSON",
                "version": 1,
                "blocks": [{"block_index": 0, "sheet": "Sheet1", "range": "A1:C10"}],
                "source_of_truth": {"confirmed": True},
            }
            (tmp_path / "migrated-tpl-01.json").write_text(json.dumps(sample_template), encoding="utf-8")

            # Setup in-memory DB for migrate_json_templates
            engine = create_engine("sqlite:///:memory:", echo=False)
            Base.metadata.create_all(bind=engine)
            TestingSession = sessionmaker(bind=engine)

            import scripts.migrate_templates_to_pg as migrator
            monkeypatch.setattr(migrator, "SessionLocal", TestingSession)

            # First run: imports 1 template
            count1 = migrator.migrate_json_templates(tmp_path)
            assert count1 == 1

            # Second run: idempotent update
            count2 = migrator.migrate_json_templates(tmp_path)
            assert count2 == 1
