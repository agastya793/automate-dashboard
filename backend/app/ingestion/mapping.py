"""
Workbook Mapping and Normalisation Engine (Milestone 2)

Allows users to:
1. Define, validate, version, and persist reusable mapping templates as JSON.
2. Override detected column roles (date, category, measure, id, text, derived).
3. Confirm unpivot operations for wide monthly tables.
4. Triage ambiguous summary rows (classify as summary, record, or discard).
5. Map raw RGB cell colours to semantic action statuses (e.g., #00B050 -> "Completed").
6. Review and apply category value merges (edit-distance suggestions).
7. Confirm production quantity source-of-truth conflicts (e.g., 37,111 vs 46,816).
8. Execute deterministic normalisation on scanned workbooks.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from pydantic import BaseModel, Field, field_validator

from app.ingestion.scanner import (
    BlockResult,
    ScanResult,
    scan_workbook,
    suggest_label_merges,
)


# ---------------------------------------------------------------------------
# Storage Directory Configuration
# ---------------------------------------------------------------------------

MAPPINGS_DIR = Path(os.getenv("MAPPINGS_DIR", Path(__file__).resolve().parent.parent.parent / "data" / "mappings"))


def get_mappings_dir() -> Path:
    """Ensure mappings directory exists and return its path."""
    MAPPINGS_DIR.mkdir(parents=True, exist_ok=True)
    return MAPPINGS_DIR


# ---------------------------------------------------------------------------
# Pydantic Schemas for Mapping Template
# ---------------------------------------------------------------------------

VALID_COLUMN_ROLES = {"date", "category", "measure", "id", "text", "derived"}
VALID_ROW_DECISIONS = {"summary", "record", "discard"}
SAFE_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-]+$")


class ColumnRoleMapping(BaseModel):
    column_name: str
    role: str = "text"
    original_role: Optional[str] = None
    data_type: Optional[str] = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        clean = (v or "").strip().lower()
        if clean not in VALID_COLUMN_ROLES:
            raise ValueError(f"Invalid column role '{v}'. Allowed roles: {sorted(VALID_COLUMN_ROLES)}")
        return clean


class UnpivotConfig(BaseModel):
    enabled: bool = False
    id_columns: List[str] = Field(default_factory=list)
    value_columns: List[str] = Field(default_factory=list)
    variable_name: str = "Month"
    value_name: str = "Value"
    measure_name: Optional[str] = None


class AmbiguousRowDecision(BaseModel):
    source_row: int
    sheet_row: int
    decision: str = "record"  # "summary" | "record" | "discard"
    reason: Optional[str] = None

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, v: str) -> str:
        clean = (v or "").strip().lower()
        if clean not in VALID_ROW_DECISIONS:
            raise ValueError(f"Invalid row decision '{v}'. Allowed decisions: {sorted(VALID_ROW_DECISIONS)}")
        return clean


class CellColourStatusMap(BaseModel):
    rgb: str
    status_label: str
    description: Optional[str] = None

    @field_validator("rgb")
    @classmethod
    def validate_rgb(cls, v: str) -> str:
        clean = (v or "").strip().upper()
        if not clean.startswith("#"):
            clean = f"#{clean}"
        if not re.match(r"^#[0-9A-F]{6}$", clean):
            raise ValueError(f"Invalid RGB hex code '{v}'. Expected format #RRGGBB.")
        return clean


class ValueMergeDecision(BaseModel):
    original_value: str
    target_value: str
    accepted: bool = True


class BlockMapping(BaseModel):
    block_index: int
    sheet: str
    range: str
    trimmed_range: Optional[str] = None
    included: bool = True
    kind: str = "tidy"
    column_roles: Dict[str, str] = Field(default_factory=dict)
    unpivot: Optional[UnpivotConfig] = None
    ambiguous_row_decisions: List[AmbiguousRowDecision] = Field(default_factory=list)
    colour_mappings: List[CellColourStatusMap] = Field(default_factory=list)
    value_merges: List[ValueMergeDecision] = Field(default_factory=list)


class SourceOfTruthConfirmation(BaseModel):
    confirmed: bool = False
    chosen_source: Optional[str] = None
    confirmed_quantity: Optional[float] = None
    notes: Optional[str] = None


class MappingTemplate(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Default Mapping Template"
    description: Optional[str] = None
    version: int = 1
    created_at: str = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat())
    filename_pattern: Optional[str] = None
    blocks: List[BlockMapping] = Field(default_factory=list)
    source_of_truth: Optional[SourceOfTruthConfirmation] = None
    global_warnings_acknowledged: bool = False

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        clean = (v or "").strip()
        if not clean or not SAFE_ID_REGEX.match(clean):
            raise ValueError(f"Invalid template ID '{v}'. Must be alphanumeric with hyphens/underscores.")
        return clean


class MappingTemplateSummary(BaseModel):
    id: str
    name: str
    version: int
    created_at: str
    updated_at: str
    block_count: int
    description: Optional[str] = None
    source_of_truth_confirmed: bool = False


# ---------------------------------------------------------------------------
# Template Repository (JSON File Storage with in-memory caching)
# ---------------------------------------------------------------------------

class TemplateStorage:
    """Manages file-based JSON storage of mapping templates."""

    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or get_mappings_dir()
        self._memory_cache: Dict[str, MappingTemplate] = {}
        self._load_all_from_disk()

    def _load_all_from_disk(self) -> None:
        """Scan storage directory and populate memory cache."""
        try:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            for file_path in self.storage_dir.glob("*.json"):
                try:
                    data = json.loads(file_path.read_text(encoding="utf-8"))
                    template = MappingTemplate.model_validate(data)
                    self._memory_cache[template.id] = template
                except Exception:
                    # Corrupt or incompatible template file, skip
                    pass
        except Exception:
            pass

    def save_template(self, template: MappingTemplate) -> MappingTemplate:
        """Save a template. If it already exists, increment the version number."""
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        if template.id in self._memory_cache:
            existing = self._memory_cache[template.id]
            template.version = existing.version + 1
            template.created_at = existing.created_at
        else:
            if not template.created_at:
                template.created_at = now

        template.updated_at = now

        # Persist to disk
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        file_path = self.storage_dir / f"{template.id}.json"
        file_path.write_text(template.model_dump_json(indent=2), encoding="utf-8")

        self._memory_cache[template.id] = template
        return template

    def get_template(self, template_id: str) -> Optional[MappingTemplate]:
        """Retrieve template by ID."""
        if not SAFE_ID_REGEX.match(template_id):
            return None
        if template_id in self._memory_cache:
            return self._memory_cache[template_id]

        file_path = self.storage_dir / f"{template_id}.json"
        if file_path.exists():
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                template = MappingTemplate.model_validate(data)
                self._memory_cache[template.id] = template
                return template
            except Exception:
                return None
        return None

    def list_templates(self) -> List[MappingTemplateSummary]:
        """Return list of template summaries."""
        summaries: List[MappingTemplateSummary] = []
        for t in self._memory_cache.values():
            sot_confirmed = t.source_of_truth.confirmed if t.source_of_truth else False
            summaries.append(
                MappingTemplateSummary(
                    id=t.id,
                    name=t.name,
                    version=t.version,
                    created_at=t.created_at,
                    updated_at=t.updated_at,
                    block_count=len(t.blocks),
                    description=t.description,
                    source_of_truth_confirmed=sot_confirmed,
                )
            )
        summaries.sort(key=lambda s: s.updated_at, reverse=True)
        return summaries

    def delete_template(self, template_id: str) -> bool:
        """Delete a template by ID."""
        if not SAFE_ID_REGEX.match(template_id):
            return False
        deleted = False
        if template_id in self._memory_cache:
            del self._memory_cache[template_id]
            deleted = True

        file_path = self.storage_dir / f"{template_id}.json"
        if file_path.exists():
            try:
                file_path.unlink()
                deleted = True
            except Exception:
                pass
        return deleted


# Global singleton instance
template_storage = TemplateStorage()


# ---------------------------------------------------------------------------
# Normalisation Engine
# ---------------------------------------------------------------------------

class NormalizedTable(BaseModel):
    table_key: str
    sheet: str
    range: str
    row_count: int
    column_count: int
    columns: List[Dict[str, Any]]
    column_roles: Dict[str, str]
    rows: List[List[Any]]
    summary_rows: List[List[Any]] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class NormalizationResult(BaseModel):
    filename: str
    template_id: Optional[str] = None
    template_version: Optional[int] = None
    tables: List[NormalizedTable] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    source_of_truth_status: Dict[str, Any] = Field(default_factory=dict)
    ppm_ready: bool = False


def _apply_value_merges(series: pd.Series, merges: List[ValueMergeDecision]) -> pd.Series:
    """Replace original category values with target values where accepted."""
    replacement_map = {m.original_value: m.target_value for m in merges if m.accepted}
    if not replacement_map:
        return series
    return series.map(lambda v: replacement_map.get(str(v).strip(), v) if pd.notna(v) else v)


def _apply_colour_status_mapping(
    df: pd.DataFrame,
    sheet: str,
    cell_colours: List[Any],
    colour_mappings: List[CellColourStatusMap],
    sheet_row_offset: int = 1,
) -> pd.DataFrame:
    """
    If colour mappings and cell colours are present, add an 'Action_Status' column
    derived from the cell fill colour of each row.
    """
    if not colour_mappings or not cell_colours:
        return df

    rgb_to_status = {m.rgb.upper(): m.status_label for m in colour_mappings}
    
    # Map row index to status
    row_status: Dict[int, str] = {}
    for c in cell_colours:
        rgb = getattr(c, "rgb", None) or (c.get("rgb") if isinstance(c, dict) else None)
        r = getattr(c, "row", None) or (c.get("row") if isinstance(c, dict) else None)
        if rgb and r is not None:
            clean_rgb = rgb.upper()
            if not clean_rgb.startswith("#"):
                clean_rgb = f"#{clean_rgb}"
            if clean_rgb in rgb_to_status:
                row_status[r] = rgb_to_status[clean_rgb]

    if not row_status:
        return df

    # Assign derived status based on DataFrame index or source row
    res_df = df.copy()
    statuses = []
    for idx in range(len(res_df)):
        sheet_row = sheet_row_offset + idx
        status_val = row_status.get(sheet_row) or row_status.get(idx, "Unknown")
        statuses.append(status_val)

    res_df["Action_Status"] = statuses
    return res_df


def _unpivot_dataframe(
    df: pd.DataFrame,
    id_cols: List[str],
    value_cols: List[str],
    var_name: str = "Month",
    val_name: str = "Value",
    measure_name: Optional[str] = None,
) -> pd.DataFrame:
    """Melt wide monthly columns into normalized long-form rows."""
    valid_id_cols = [c for c in id_cols if c in df.columns]
    valid_value_cols = [c for c in value_cols if c in df.columns]

    if not valid_value_cols:
        return df

    # If no ID columns remain, create a synthetic row index
    drop_index = False
    if not valid_id_cols:
        df = df.copy()
        df["_row_id"] = range(1, len(df) + 1)
        valid_id_cols = ["_row_id"]
        drop_index = True

    melted = pd.melt(
        df,
        id_vars=valid_id_cols,
        value_vars=valid_value_cols,
        var_name=var_name,
        value_name=val_name,
    )

    if drop_index and "_row_id" in melted.columns:
        melted = melted.drop(columns=["_row_id"])

    if measure_name:
        melted["Measure"] = measure_name

    # Drop rows with null values in value column
    melted = melted.dropna(subset=[val_name])
    return melted


def normalize_workbook(
    raw: bytes,
    filename: str,
    template: MappingTemplate,
    max_upload_bytes: int = 10 * 1024 * 1024,
) -> NormalizationResult:
    """
    Executes full normalisation of a workbook based on a MappingTemplate.
    """
    # 1. Scan workbook to detect sheets, blocks, and cell colours
    scan = scan_workbook(
        raw=raw,
        filename=filename,
        read_colours=True,
        max_upload_bytes=max_upload_bytes,
    )

    warnings: List[str] = list(scan.global_warnings)
    normalized_tables: List[NormalizedTable] = []

    # Map block mapping by block index
    block_map_by_idx: Dict[int, BlockMapping] = {b.block_index: b for b in template.blocks}

    # Evaluate Source of Truth conflict
    ppm_ready = False
    sot_status: Dict[str, Any] = {
        "has_conflict": False,
        "confirmed": False,
    }

    # Check if scan detected source-of-truth warnings
    sot_warning = any("37,111" in w or "conflict" in w.lower() for w in scan.global_warnings)
    if sot_warning:
        sot_status["has_conflict"] = True
        if template.source_of_truth and template.source_of_truth.confirmed:
            sot_status["confirmed"] = True
            sot_status["chosen_source"] = template.source_of_truth.chosen_source
            sot_status["confirmed_quantity"] = template.source_of_truth.confirmed_quantity
            ppm_ready = True
        else:
            warnings.append(
                "Source-of-truth production quantity conflict requires user confirmation before PPM widgets can be unlocked."
            )
    else:
        # If no conflict detected, PPM widgets are unlocked
        ppm_ready = True

    for idx, block in enumerate(scan.blocks):
        # Check if block is mapped
        mapping = block_map_by_idx.get(idx)

        # If mapping exists and block is explicitly excluded, skip
        if mapping and not mapping.included:
            continue

        # If block has no data frame, skip
        if block.df is None or block.df.empty:
            continue

        df = block.df.copy()
        column_roles = dict(block.column_roles)

        # 2. Apply range trim if specified
        table_range = block.range
        if mapping and mapping.trimmed_range:
            table_range = mapping.trimmed_range

        # 3. Apply Ambiguous Row Decisions
        summary_rows_list: List[List[Any]] = []
        if mapping and mapping.ambiguous_row_decisions:
            discard_indices = set()
            summary_indices = set()
            for dec in mapping.ambiguous_row_decisions:
                if dec.decision == "discard":
                    discard_indices.add(dec.source_row)
                elif dec.decision == "summary":
                    summary_indices.add(dec.source_row)

            if discard_indices:
                df = df.drop(index=[i for i in discard_indices if i in df.index], errors="ignore")

            if summary_indices:
                sum_df = df.loc[[i for i in summary_indices if i in df.index]]
                df = df.drop(index=[i for i in summary_indices if i in df.index], errors="ignore")
                summary_rows_list = sum_df.values.tolist()

        # 4. Apply Column Role Overrides
        if mapping and mapping.column_roles:
            for col, role in mapping.column_roles.items():
                if col in df.columns:
                    column_roles[col] = role

        # 5. Apply Value Merges
        if mapping and mapping.value_merges:
            for col in df.columns:
                if column_roles.get(col) == "category" or df[col].dtype == object:
                    df[col] = _apply_value_merges(df[col], mapping.value_merges)

        # 6. Apply Cell Colour Status Mapping
        if mapping and mapping.colour_mappings and block.cell_colours:
            offset = block.r0 + block.header_row_index + 1
            df = _apply_colour_status_mapping(
                df,
                block.sheet,
                block.cell_colours,
                mapping.colour_mappings,
                sheet_row_offset=offset,
            )
            column_roles["Action_Status"] = "category"

        # 7. Apply Unpivot if configured
        if mapping and mapping.unpivot and mapping.unpivot.enabled:
            df = _unpivot_dataframe(
                df=df,
                id_cols=mapping.unpivot.id_columns,
                value_cols=mapping.unpivot.value_columns,
                var_name=mapping.unpivot.variable_name,
                val_name=mapping.unpivot.value_name,
                measure_name=mapping.unpivot.measure_name,
            )
            column_roles[mapping.unpivot.variable_name] = "date"
            column_roles[mapping.unpivot.value_name] = "measure"
            if mapping.unpivot.measure_name:
                column_roles["Measure"] = "category"

        # Prepare bounded rows for output
        clean_rows: List[List[Any]] = []
        for _, r in df.head(1000).iterrows():
            clean_cells = []
            for v in r:
                if pd.isna(v) if not isinstance(v, str) else False:
                    clean_cells.append(None)
                elif isinstance(v, (dt.date, dt.datetime)):
                    clean_cells.append(v.isoformat())
                elif isinstance(v, float) and v == int(v):
                    clean_cells.append(int(v))
                else:
                    clean_cells.append(v)
            clean_rows.append(clean_cells)

        columns_meta = []
        for c in df.columns:
            columns_meta.append({
                "name": str(c),
                "role": column_roles.get(str(c), "text"),
                "dtype": str(df[c].dtype),
            })

        normalized_tables.append(
            NormalizedTable(
                table_key=f"{block.sheet}_block_{idx + 1}",
                sheet=block.sheet,
                range=table_range,
                row_count=len(df),
                column_count=len(df.columns),
                columns=columns_meta,
                column_roles=column_roles,
                rows=clean_rows,
                summary_rows=summary_rows_list,
                notes=block.notes,
            )
        )

    return NormalizationResult(
        filename=filename,
        template_id=template.id,
        template_version=template.version,
        tables=normalized_tables,
        warnings=warnings,
        source_of_truth_status=sot_status,
        ppm_ready=ppm_ready,
    )
