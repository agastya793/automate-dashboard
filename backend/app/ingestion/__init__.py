"""
Ingestion package — workbook scanning, block detection, classification,
normalisation and label-merge suggestions.

Public surface:
    scan_workbook(raw: bytes, filename: str, ...) -> ScanResult
"""

from app.ingestion.scanner import ScanResult, BlockResult, scan_workbook
from app.ingestion.mapping import (
    MappingTemplate,
    MappingTemplateSummary,
    BlockMapping,
    ColumnRoleMapping,
    UnpivotConfig,
    AmbiguousRowDecision,
    CellColourStatusMap,
    ValueMergeDecision,
    SourceOfTruthConfirmation,
    NormalizationResult,
    NormalizedTable,
    template_storage,
    normalize_workbook,
)

__all__ = [
    "ScanResult",
    "BlockResult",
    "scan_workbook",
    "MappingTemplate",
    "MappingTemplateSummary",
    "BlockMapping",
    "ColumnRoleMapping",
    "UnpivotConfig",
    "AmbiguousRowDecision",
    "CellColourStatusMap",
    "ValueMergeDecision",
    "SourceOfTruthConfirmation",
    "NormalizationResult",
    "NormalizedTable",
    "template_storage",
    "normalize_workbook",
]
