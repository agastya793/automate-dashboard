"""
Migration Utility: Import JSON Mapping Templates into PostgreSQL (Milestone 3)

Scans `backend/data/mappings/` for JSON mapping templates created in Milestone 2
and idempotently imports or updates them in the PostgreSQL `templates` table.
Does not delete or alter the original JSON files.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.db.repositories import TemplateRepository
from app.db.session import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("template_migration")

DEFAULT_MAPPINGS_DIR = backend_dir / "data" / "mappings"


def migrate_json_templates(mappings_dir: Path | None = None) -> int:
    """
    Idempotently migrate all JSON templates from mappings_dir into the database.
    Returns the number of templates processed.
    """
    target_dir = mappings_dir or DEFAULT_MAPPINGS_DIR
    if not target_dir.exists():
        logger.info(f"Mappings directory {target_dir} does not exist. Nothing to migrate.")
        return 0

    json_files = list(target_dir.glob("*.json"))
    if not json_files:
        logger.info(f"No JSON template files found in {target_dir}.")
        return 0

    db = SessionLocal()
    repo = TemplateRepository(db)
    imported_count = 0

    try:
        for file_path in json_files:
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                template_id = data.get("id") or file_path.stem
                name = data.get("name") or "Imported Template"
                description = data.get("description")
                blocks = data.get("blocks", [])
                source_of_truth = data.get("source_of_truth")

                # Idempotent save/update
                repo.save(
                    template_id=template_id,
                    name=name,
                    blocks_data=blocks,
                    description=description,
                    source_of_truth=source_of_truth,
                )
                logger.info(f"Imported/Updated template '{name}' ({template_id}) from {file_path.name}")
                imported_count += 1
            except Exception as exc:
                logger.error(f"Error processing {file_path.name}: {exc}")
    finally:
        db.close()

    logger.info(f"Template migration complete: {imported_count} templates processed.")
    return imported_count


if __name__ == "__main__":
    count = migrate_json_templates()
    print(f"Successfully migrated {count} template(s) to database.")
