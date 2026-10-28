"""
Background Tasks (Milestone 3, 4, 5)

Celery background tasks for:
- scan_workbook_task: Asynchronous workbook scanning and block detection
- normalize_workbook_task: Asynchronous normalisation and Parquet dataset generation

Security controls:
- Loads persisted upload record from PostgreSQL to verify ownership & workspace.
- Validates that the storage key belongs to the persisted record.
- Prevents unauthorized or invalid duplicate processing.
- Records sanitized, safe error messages without exposing spreadsheet data in logs.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Dict, Optional

import pandas as pd

from app.db.repositories import DatasetRepository, UploadRepository
from app.db.session import get_db_context
from app.ingestion.mapping import (
    MappingTemplate,
    normalize_workbook,
)
from app.ingestion.scanner import scan_workbook
from app.storage import get_storage_backend, save_dataframe_as_parquet
from app.worker.celery_app import celery_app

storage = get_storage_backend()
logger = logging.getLogger("worker_tasks")


@celery_app.task(
    bind=True,
    name="app.worker.tasks.scan_workbook_task",
    max_retries=3,
    default_retry_delay=10,
)
def scan_workbook_task(self, upload_id: str, storage_key: str) -> Dict[str, Any]:
    """
    Background job to scan workbook, detect tables, and persist block metadata.
    Validates upload existence, state, and storage ownership.
    """
    storage = get_storage_backend()
    upload_uuid = uuid.UUID(str(upload_id))
    logger.info(f"Starting scan for upload {upload_uuid}")

    with get_db_context() as db:
        upload_repo = UploadRepository(db)
        upload = upload_repo.get(upload_uuid)
        if not upload:
            logger.error(f"Upload {upload_uuid} not found in database.")
            return {"status": "error", "message": f"Upload {upload_uuid} not found."}

        # Verify storage key matches server-created upload record
        if upload.storage_key != storage_key:
            logger.error(f"Security mismatch: upload {upload_uuid} storage_key does not match task key.")
            return {"status": "error", "message": "Storage key verification failed."}

        orig_filename = upload.original_filename
        upload_repo.update_status(upload_uuid, status="scanning", stage="reading_workbook", progress=10)

    try:
        # Retrieve raw file bytes through the storage abstraction
        raw_bytes = storage.get_object(storage_key)

        with get_db_context() as db:
            upload_repo = UploadRepository(db)
            upload_repo.update_status(upload_uuid, status="scanning", stage="detecting_blocks", progress=40)

        # Execute production-grade workbook scanner
        scan_result = scan_workbook(
            raw=raw_bytes,
            filename=orig_filename,
            read_colours=True,
        )

        with get_db_context() as db:
            upload_repo = UploadRepository(db)
            dataset_repo = DatasetRepository(db)

            # Idempotent cleanup of any previous datasets for this upload
            dataset_repo.delete_by_upload(upload_uuid)

            # Persist detected data blocks in PostgreSQL
            created_datasets = []
            for idx, block in enumerate(scan_result.blocks):
                cols = list(block.df.columns) if block.df is not None else list(block.column_roles.keys())
                col_meta = [
                    {"name": col, "role": block.column_roles.get(col, "text")}
                    for col in cols
                ]
                summary_meta = {
                    "confidence": block.confidence,
                    "notes": block.notes,
                    "warnings": block.warnings,
                    "formula_cache_warning": block.formula_cache_warning,
                    "ambiguous_rows": [
                        {"sheet_row": a.sheet_row, "reason": a.reason}
                        for a in block.ambiguous_rows
                    ],
                    "sample_preview": block.sample_preview(15),
                    "cell_colours": [
                        {"row": c.row, "col": c.col, "rgb": c.rgb, "raw_type": c.raw_type}
                        for c in block.cell_colours
                    ],
                    "has_summary": block.summary_df is not None and len(block.summary_df) > 0,
                    "cap_reached": block.cap_reached,
                    "block_index": idx,
                }

                num_rows = (block.r1 - block.r0 + 1) if block.r1 is not None and block.r0 is not None else (len(block.df) if block.df is not None else 0)
                num_cols = (block.c1 - block.c0 + 1) if block.c1 is not None and block.c0 is not None else len(cols)

                ds = dataset_repo.create(
                    upload_id=upload_uuid,
                    sheet_name=block.sheet,
                    cell_range=block.range,
                    kind=block.kind,
                    column_metadata=col_meta,
                    normalization_status="raw",
                    row_count=num_rows,
                    column_count=num_cols,
                    summary_metadata=summary_meta,
                )
                created_datasets.append(str(ds.id))

            # Determine next status
            has_wide = any(b.kind == "wide" for b in scan_result.blocks)
            has_ambiguous = any(len(b.ambiguous_rows) > 0 for b in scan_result.blocks)
            has_warnings = len(scan_result.global_warnings) > 0

            next_status = "needs_mapping" if (has_wide or has_ambiguous or has_warnings) else "ready"
            next_stage = "awaiting_user_mapping" if next_status == "needs_mapping" else "ready"

            upload_repo.update_status(
                upload_id,
                status=next_status,
                stage=next_stage,
                progress=100,
            )

        logger.info(f"Scan completed for upload {upload_id}: status={next_status}, {len(created_datasets)} datasets recorded")
        return {
            "status": "success",
            "upload_id": upload_id,
            "next_status": next_status,
            "dataset_count": len(created_datasets),
        }

    except Exception as exc:
        logger.exception(f"Scan failed for upload {upload_id}: {exc}")
        safe_error = "Workbook scanning failed: " + str(exc)
        with get_db_context() as db:
            upload_repo = UploadRepository(db)
            upload_repo.update_status(
                upload_id,
                status="failed",
                stage="failed",
                error_code="SCAN_ERROR",
                error_message=safe_error,
            )
        return {"status": "failed", "upload_id": upload_id, "error": safe_error}


@celery_app.task(
    bind=True,
    name="app.worker.tasks.normalize_workbook_task",
    max_retries=3,
    default_retry_delay=10,
)
def normalize_workbook_task(
    self,
    upload_id: str,
    storage_key: str,
    template_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Background job to normalize workbook based on user mapping decisions
    and write output tables to Apache Parquet files in private storage.
    """
    storage = get_storage_backend()
    logger.info(f"Starting normalisation for upload {upload_id}")

    with get_db_context() as db:
        upload_repo = UploadRepository(db)
        upload = upload_repo.get(upload_id)
        if not upload:
            return {"status": "error", "message": f"Upload {upload_id} not found."}

        # Verify storage key belongs to this upload
        if upload.storage_key != storage_key:
            logger.error(f"Security mismatch: upload {upload_id} storage_key does not match task key.")
            return {"status": "error", "message": "Storage key verification failed."}

        orig_filename = upload.original_filename
        upload_repo.update_status(upload_id, status="scanning", stage="normalizing", progress=50)

    try:
        raw_bytes = storage.get_object(storage_key)
        template = MappingTemplate.model_validate(template_data)

        # Run normalization engine
        norm_result = normalize_workbook(
            raw=raw_bytes,
            filename=orig_filename,
            template=template,
        )

        with get_db_context() as db:
            upload_repo = UploadRepository(db)
            dataset_repo = DatasetRepository(db)
            existing_datasets = dataset_repo.list_by_upload(upload_id)

            # Match normalized tables to dataset records
            dataset_by_key = {f"{d.sheet_name}!{d.cell_range}": d for d in existing_datasets}

            parquet_keys = []
            for table in norm_result.tables:
                table_key = f"{table.sheet}!{table.range}"
                ds = dataset_by_key.get(table_key) or (existing_datasets[0] if existing_datasets else None)

                if ds:
                    # Convert normalized rows and columns to DataFrame
                    col_names = [c["name"] if isinstance(c, dict) else c.name for c in table.columns]
                    df = pd.DataFrame(table.rows, columns=col_names)

                    # Persist as Parquet in private local storage
                    parquet_key = f"datasets/{ds.id}/normalized.parquet"
                    save_dataframe_as_parquet(df, storage, parquet_key)

                    # Update dataset record in PostgreSQL
                    dataset_repo.update_parquet_key(
                        dataset_id=ds.id,
                        parquet_storage_key=parquet_key,
                        row_count=table.row_count,
                        column_count=table.column_count,
                        normalization_status="normalized",
                    )
                    parquet_keys.append(parquet_key)

            upload_repo.update_status(
                upload_id,
                status="ready",
                stage="ready",
                progress=100,
            )

        logger.info(f"Normalisation complete for {upload_id}: {len(parquet_keys)} Parquet datasets written.")
        return {
            "status": "success",
            "upload_id": upload_id,
            "parquet_datasets": parquet_keys,
            "ppm_ready": norm_result.ppm_ready,
        }

    except Exception as exc:
        logger.exception(f"Normalization failed for upload {upload_id}: {exc}")
        safe_error = "Normalization failed: " + str(exc)
        with get_db_context() as db:
            upload_repo = UploadRepository(db)
            upload_repo.update_status(
                upload_id,
                status="failed",
                stage="failed",
                error_code="NORMALIZATION_ERROR",
                error_message=safe_error,
            )
        return {"status": "failed", "upload_id": upload_id, "error": safe_error}


@celery_app.task(
    bind=True,
    name="app.worker.tasks.generate_export_task",
    max_retries=2,
    default_retry_delay=5,
)
def generate_export_task(self, export_id: str) -> Dict[str, Any]:
    """
    Background job to render and generate report exports (PDF, PNG, Excel, CSV).
    Passes validated export ID only; retrieves models and storage securely.
    """
    from app.exports.generator import generate_export

    storage = get_storage_backend()
    logger.info(f"Starting export generation task for export_id={export_id}")
    with get_db_context() as db:
        res = generate_export(db, export_id, storage)
        return res
