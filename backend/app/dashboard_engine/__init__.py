"""
Dashboard Engine package — validated dashboard spec generation from detected blocks.

Public surface:
    recommend_dashboard(blocks: list[BlockResult], dataset_keys: dict[str, pd.DataFrame])
        -> DashboardSpec
    run_widget(spec: WidgetSpec, tables: dict[str, pd.DataFrame]) -> pd.DataFrame
"""

from app.dashboard_engine.recommender import (
    DashboardSpec,
    WidgetSpec,
    recommend_dashboard,
    run_widget,
)
from app.dashboard_engine.manufacturing_templates import (
    BLUEPRINT_REFERENCE_PPM_2026,
    KNOWN_MANUFACTURING_MODELS,
    ManufacturingDashboardSpec,
    ManufacturingWidgetSpec,
    GlobalFilterInput as ManufacturingGlobalFilter,
    ProvenanceMetadata,
    ReconciliationReport,
    build_manufacturing_dashboard_spec,
    compute_ppm_reconciliation,
    compute_pareto_cumulative,
    execute_manufacturing_widget,
)

__all__ = [
    "DashboardSpec",
    "WidgetSpec",
    "recommend_dashboard",
    "run_widget",
    "BLUEPRINT_REFERENCE_PPM_2026",
    "KNOWN_MANUFACTURING_MODELS",
    "ManufacturingDashboardSpec",
    "ManufacturingWidgetSpec",
    "ManufacturingGlobalFilter",
    "ProvenanceMetadata",
    "ReconciliationReport",
    "build_manufacturing_dashboard_spec",
    "compute_ppm_reconciliation",
    "compute_pareto_cumulative",
    "execute_manufacturing_widget",
]

