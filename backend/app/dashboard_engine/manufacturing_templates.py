"""
Manufacturing Quality Dashboard Engine & Templates (Milestone 4)

Authoritative implementation for manufacturing BI dashboards based on
the Excel-to-Dashboard Platform Blueprint.

Supports 5 specialized manufacturing templates:
1. Monthly Rejection PPM versus Target (TrendLine with Target & Variance)
2. Defect Pareto Chart (Dual-Axis with 0-100% Cumulative Line & 80% Threshold)
3. Paynter Defect Heatmap (Months x Defects/Models Matrix, Missing-month Safe)
4. Corrective-Action Tracker (Status, Owner Breakdown, Due/Closure Dates, Colour Mapping)
5. Model-Level Rejection Comparison (Quantities & Confirmed PPM; No Cross-Model PPM Summing)

Reconciliation & Accuracy Guard:
- Compares calculated PPM against approved blueprint reference values (Jan-Aug 2026).
- Surfaces January production quantity conflict (37,111 in Target 2026 vs 46,816 in Paynter 2026).
- Blocks unconfirmed calculated PPM from authoritative publication.
- Retains complete KPI provenance for all metrics.
"""

from __future__ import annotations

import datetime as dt
import math
import uuid
from typing import Any, Dict, List, Literal, Optional, Tuple

import pandas as pd
from pydantic import BaseModel, Field

from app.dashboard_engine.duckdb_engine import (
    QueryFilter,
    QueryPlan,
    execute_query_plan,
    validate_identifier,
)
from app.db.models import Dataset
from app.storage.base import StorageBackend

# ---------------------------------------------------------------------------
# Blueprint Authoritative Reference PPM Values (Jan-Aug 2026)
# Source: Excel-to-Dashboard Platform Blueprint & Client Handover
# ---------------------------------------------------------------------------
BLUEPRINT_REFERENCE_PPM_2026: Dict[str, int] = {
    "Jan-26": 4229,
    "Feb-26": 2718,
    "Mar-26": 2514,
    "Apr-26": 1307,
    "May-26": 1618,
    "Jun-26": 2318,
    "Jul-26": 3565,
    "Aug-26": 7458,
}

# Standard manufacturing models present in client workbook
KNOWN_MANUFACTURING_MODELS = ["157 TY", "367 TY", "457 TY", "Milwaukee"]

# Allowed template types
MANUFACTURING_TEMPLATE_TYPE = "manufacturing_quality"


# ---------------------------------------------------------------------------
# Typed Models: Provenance, Filters & Widget Specifications
# ---------------------------------------------------------------------------

class ProvenanceMetadata(BaseModel):
    """Retains full data lineage for a displayed KPI or widget."""
    upload_id: str
    sheet_name: str
    cell_range: str
    source_column: str
    aggregation: str = "sum"
    calculation_applied: Optional[str] = None
    confirmation_status: str = "confirmed"  # "confirmed", "unconfirmed_conflict", "source_measure"
    caveats: List[str] = Field(default_factory=list)
    joined_tables: List[str] = Field(default_factory=list)


class GlobalFilterInput(BaseModel):
    """Global filters applicable across all dashboard widgets."""
    period: Optional[str] = None
    model: Optional[str] = None
    defect: Optional[str] = None
    action_owner: Optional[str] = None
    action_status: Optional[str] = None


class ManufacturingWidgetSpec(BaseModel):
    """Specification for a single manufacturing dashboard widget."""
    widget_id: str
    widget_type: Literal[
        "ppm_trend_target",
        "defect_pareto",
        "paynter_heatmap",
        "action_tracker",
        "model_comparison",
        "kpi_card",
    ]
    title: str
    dataset_id: str
    target_dataset_id: Optional[str] = None
    dimensions: List[str] = Field(default_factory=list)
    measures: List[str] = Field(default_factory=list)
    aggregations: Dict[str, str] = Field(default_factory=dict)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    provenance: ProvenanceMetadata
    warnings: List[str] = Field(default_factory=list)


class ReconciliationItem(BaseModel):
    period: str
    reference_ppm: int
    calculated_ppm: Optional[float] = None
    variance: Optional[float] = None
    status: Literal["match", "variance", "missing_actual", "conflict_blocked"]
    notes: Optional[str] = None


class ReconciliationReport(BaseModel):
    status: Literal["verified", "has_variances", "conflict_blocked", "synthetic_fixture", "unverified"]
    match_count: int = 0
    total_periods: int = 0
    max_variance: float = 0.0
    items: List[ReconciliationItem] = Field(default_factory=list)
    explanation: str = ""
    is_authoritative: bool = False


class ManufacturingDashboardSpec(BaseModel):
    """Versioned manufacturing dashboard specification."""
    template_type: str = MANUFACTURING_TEMPLATE_TYPE
    version: int = 1
    title: str
    upload_id: str
    source_of_truth_confirmed: bool = False
    source_of_truth_choice: Optional[str] = None  # "monthly_breakdown" (37,111) or "yearly_overview" (46,816)
    reconciliation: ReconciliationReport
    widgets: List[ManufacturingWidgetSpec] = Field(default_factory=list)
    available_filters: Dict[str, List[str]] = Field(default_factory=dict)
    global_warnings: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Reconciliation Engine
# ---------------------------------------------------------------------------

def compute_ppm_reconciliation(
    actual_ppm_by_period: Dict[str, float],
    source_of_truth_confirmed: bool,
    has_sot_conflict: bool = True,
    is_synthetic: bool = False,
) -> ReconciliationReport:
    """
    Compares actual or calculated PPM series against the blueprint reference values (Jan-Aug 2026).
    
    Guards:
    - If source-of-truth conflict is present and unconfirmed, flags as conflict_blocked.
    - Tolerates integer rounding differences (<= 1.5 PPM).
    - Identifies missing periods.
    """
    if has_sot_conflict and not source_of_truth_confirmed:
        items = []
        for period, ref_val in BLUEPRINT_REFERENCE_PPM_2026.items():
            items.append(
                ReconciliationItem(
                    period=period,
                    reference_ppm=ref_val,
                    calculated_ppm=None,
                    variance=None,
                    status="conflict_blocked",
                    notes="Publication blocked: Production quantity denominator (37,111 vs 46,816) unconfirmed.",
                )
            )
        return ReconciliationReport(
            status="conflict_blocked",
            match_count=0,
            total_periods=len(BLUEPRINT_REFERENCE_PPM_2026),
            max_variance=0.0,
            items=items,
            explanation=(
                "Source-of-truth conflict detected: January production count is reported as 37,111 in "
                "monthly breakdown and 46,816 in overview ledger. Calculated PPM cannot be published "
                "as authoritative until the denominator source is confirmed by the user."
            ),
            is_authoritative=False,
        )

    items: List[ReconciliationItem] = []
    match_count = 0
    max_var = 0.0

    for period, ref_val in BLUEPRINT_REFERENCE_PPM_2026.items():
        if period in actual_ppm_by_period and actual_ppm_by_period[period] is not None:
            actual = float(actual_ppm_by_period[period])
            var = round(actual - ref_val, 2)
            abs_var = abs(var)
            if abs_var > max_var:
                max_var = abs_var

            # Rounding tolerance of 1.5 PPM for formula float rounding
            if abs_var <= 1.5:
                status = "match"
                match_count += 1
                notes = "Exact match with blueprint reference" if abs_var == 0 else f"Within rounding tolerance ({var:+.1f})"
            else:
                status = "variance"
                notes = f"Variance of {var:+.1f} PPM vs reference ({ref_val})"

            items.append(
                ReconciliationItem(
                    period=period,
                    reference_ppm=ref_val,
                    calculated_ppm=actual,
                    variance=var,
                    status=status,
                    notes=notes,
                )
            )
        else:
            items.append(
                ReconciliationItem(
                    period=period,
                    reference_ppm=ref_val,
                    calculated_ppm=None,
                    variance=None,
                    status="missing_actual",
                    notes="Period missing from dataset or not yet reported.",
                )
            )

    total_periods = len(BLUEPRINT_REFERENCE_PPM_2026)
    if is_synthetic:
        rep_status = "synthetic_fixture"
        explanation = "Validated against synthetic test fixture replicating client workbook structure."
        is_auth = False
    elif match_count == total_periods:
        rep_status = "verified"
        explanation = f"All {total_periods} reporting periods match the approved reference PPM values within rounding limits."
        is_auth = True
    elif match_count > 0:
        rep_status = "has_variances"
        explanation = f"{match_count}/{total_periods} periods matched reference PPM. Max variance: {max_var:.1f} PPM."
        is_auth = False
    else:
        rep_status = "unverified"
        explanation = "No matching reporting periods found for Jan-Aug 2026 reference reconciliation."
        is_auth = False

    return ReconciliationReport(
        status=rep_status,
        match_count=match_count,
        total_periods=total_periods,
        max_variance=max_var,
        items=items,
        explanation=explanation,
        is_authoritative=is_auth,
    )


# ---------------------------------------------------------------------------
# Calculation Helpers
# ---------------------------------------------------------------------------

def calculate_ppm(rejection_qty: float, production_qty: float) -> Optional[float]:
    """
    Standard PPM calculation: (rejection_qty / production_qty) * 1,000,000
    Returns None if production_qty is 0 or negative.
    """
    if production_qty <= 0 or math.isnan(production_qty) or math.isinf(production_qty):
        return None
    if math.isnan(rejection_qty) or math.isinf(rejection_qty):
        return None
    return round((rejection_qty / production_qty) * 1_000_000.0, 2)


def compute_pareto_cumulative(
    items: List[Dict[str, Any]],
    measure_key: str,
) -> List[Dict[str, Any]]:
    """
    Takes grouped category items sorted descending by measure_key,
    computes cumulative running sum and cumulative percentage from 0.0% to 100.0%.
    
    Guards:
    - If total sum is 0, cumulative percentage is 0.0 (prevents ZeroDivisionError).
    - Sorts descending before calculating cumulative percentages.
    """
    sorted_items = sorted(
        items,
        key=lambda x: float(x.get(measure_key) or 0),
        reverse=True,
    )

    total_sum = sum(float(x.get(measure_key) or 0) for x in sorted_items)
    running_sum = 0.0
    result = []

    for item in sorted_items:
        val = float(item.get(measure_key) or 0)
        running_sum += val
        if total_sum > 0:
            cum_pct = round((running_sum / total_sum) * 100.0, 2)
        else:
            cum_pct = 0.0

        item_copy = dict(item)
        item_copy["cumulative_quantity"] = round(running_sum, 2)
        item_copy["cumulative_percentage"] = cum_pct
        result.append(item_copy)

    return result


# ---------------------------------------------------------------------------
# Template Generation from Normalized Datasets
# ---------------------------------------------------------------------------

def detect_manufacturing_roles(
    datasets: List[Dataset],
) -> Dict[str, Optional[Dataset]]:
    """
    Inspects normalized datasets for an upload and classifies them into
    manufacturing functional roles:
    - ppm_trend / rejection_dataset
    - pareto_defects
    - heatmap_paynter
    - action_tracker
    - model_breakdown
    """
    classified: Dict[str, Optional[Dataset]] = {
        "rejections": None,
        "actions": None,
        "targets": None,
        "general": None,
    }

    for ds in datasets:
        cols = {c.get("name", "").lower(): c.get("role", "") for c in (ds.column_metadata or []) if isinstance(c, dict)}
        sheet_l = ds.sheet_name.lower()

        # Check for action tracker
        if any(term in sheet_l for term in ["action", "countermeasure", "status"]) or any(
            term in cols for term in ["action", "champion", "owner", "due date", "closure date", "action_status"]
        ):
            if not classified["actions"]:
                classified["actions"] = ds
                continue

        # Check for target dataset
        if "target" in sheet_l or any(term in cols for term in ["target", "target ppm", "ppm target"]):
            if not classified["targets"]:
                classified["targets"] = ds

        # Check for rejections / defects
        if any(term in sheet_l for term in ["paynter", "defect", "rejection", "effect confirmation"]) or any(
            term in cols for term in ["defect", "ppm", "rejection", "rejection quantity", "model"]
        ):
            if not classified["rejections"]:
                classified["rejections"] = ds
                continue

        if not classified["general"]:
            classified["general"] = ds

    # Fallback: if no dedicated rejections dataset, use first available
    if not classified["rejections"] and datasets:
        classified["rejections"] = datasets[0]

    return classified


def build_manufacturing_dashboard_spec(
    upload_id: str,
    datasets: List[Dataset],
    template_name: str = "Manufacturing Quality Dashboard",
    source_of_truth_confirmed: bool = False,
    source_of_truth_choice: Optional[str] = None,
    confirmed_target_ppm: float = 2000.0,
) -> ManufacturingDashboardSpec:
    """
    Constructs a complete versioned ManufacturingDashboardSpec mapping the 5
    manufacturing templates to normalized datasets with explicit provenance.
    """
    classified = detect_manufacturing_roles(datasets)
    rejection_ds = classified["rejections"]
    action_ds = classified["actions"]
    target_ds = classified["targets"]

    widgets: List[ManufacturingWidgetSpec] = []
    global_warnings: List[str] = []

    # Detect available filter options from dataset columns
    available_filters: Dict[str, List[str]] = {
        "periods": [],
        "models": [],
        "defects": [],
        "action_owners": [],
        "action_statuses": [],
    }

    # 1. Widget A: Monthly Rejection PPM versus Target
    if rejection_ds:
        cols = [c.get("name") for c in (rejection_ds.column_metadata or []) if isinstance(c, dict)]
        period_col = next((c for c in cols if c and c.lower() in ["month", "period", "date"]), cols[0] if cols else "Month")
        
        # Look for explicit PPM column
        ppm_col = next((c for c in cols if c and "ppm" in c.lower()), None)
        qty_col = next((c for c in cols if c and any(k in c.lower() for k in ["quantity", "qty", "count", "rejection"])), cols[1] if len(cols) > 1 else None)

        measure_col = ppm_col or qty_col or "Value"
        is_source_ppm = bool(ppm_col)

        caveats = []
        if not source_of_truth_confirmed and not is_source_ppm:
            conf_status = "unconfirmed_conflict"
            caveats.append("Production denominator conflict (37,111 vs 46,816) pending user confirmation.")
        else:
            conf_status = "confirmed" if source_of_truth_confirmed else "source_measure"

        widgets.append(
            ManufacturingWidgetSpec(
                widget_id="widget_ppm_trend",
                widget_type="ppm_trend_target",
                title="Monthly Rejection PPM versus Target",
                dataset_id=str(rejection_ds.id),
                dimensions=[period_col] if period_col else [],
                measures=[measure_col],
                aggregations={measure_col: "sum" if not is_source_ppm else "avg"},
                parameters={
                    "target_ppm": confirmed_target_ppm,
                    "is_source_ppm": is_source_ppm,
                    "target_variance_alert": True,
                    "period_column": period_col,
                    "measure_column": measure_col,
                },
                provenance=ProvenanceMetadata(
                    upload_id=upload_id,
                    sheet_name=rejection_ds.sheet_name,
                    cell_range=rejection_ds.cell_range,
                    source_column=measure_col,
                    aggregation="avg" if is_source_ppm else "sum",
                    calculation_applied=None if is_source_ppm else "PPM = (rejection_qty / production_qty) * 1,000,000",
                    confirmation_status=conf_status,
                    caveats=caveats,
                ),
                warnings=caveats,
            )
        )

    # 2. Widget B: Defect Pareto Chart
    if rejection_ds:
        cols = [c.get("name") for c in (rejection_ds.column_metadata or []) if isinstance(c, dict)]
        defect_col = next((c for c in cols if c and any(k in c.lower() for k in ["defect", "issue", "failure", "category"])), None)
        qty_col = next((c for c in cols if c and any(k in c.lower() for k in ["quantity", "qty", "count"])), None)

        if defect_col and qty_col:
            widgets.append(
                ManufacturingWidgetSpec(
                    widget_id="widget_defect_pareto",
                    widget_type="defect_pareto",
                    title="Defect Pareto Analysis (Ranked with Cumulative %)",
                    dataset_id=str(rejection_ds.id),
                    dimensions=[defect_col],
                    measures=[qty_col],
                    aggregations={qty_col: "sum"},
                    parameters={
                        "top_n": 10,
                        "pareto_threshold": 80.0,
                        "category_column": defect_col,
                        "measure_column": qty_col,
                    },
                    provenance=ProvenanceMetadata(
                        upload_id=upload_id,
                        sheet_name=rejection_ds.sheet_name,
                        cell_range=rejection_ds.cell_range,
                        source_column=qty_col,
                        aggregation="sum",
                        calculation_applied="Cumulative % = (Running Sum / Total Sum) * 100",
                        confirmation_status="confirmed",
                    ),
                )
            )

    # 3. Widget C: Paynter Defect Heatmap
    if rejection_ds:
        cols = [c.get("name") for c in (rejection_ds.column_metadata or []) if isinstance(c, dict)]
        period_col = next((c for c in cols if c and c.lower() in ["month", "period", "date"]), None)
        defect_col = next((c for c in cols if c and any(k in c.lower() for k in ["defect", "issue", "category"])), None)
        model_col = next((c for c in cols if c and "model" in c.lower()), None)
        qty_col = next((c for c in cols if c and any(k in c.lower() for k in ["quantity", "qty", "count"])), None)

        y_axis_col = defect_col or model_col
        if period_col and y_axis_col and qty_col:
            widgets.append(
                ManufacturingWidgetSpec(
                    widget_id="widget_paynter_heatmap",
                    widget_type="paynter_heatmap",
                    title="Paynter Defect Heatmap (Recurring Defect Distribution)",
                    dataset_id=str(rejection_ds.id),
                    dimensions=[y_axis_col, period_col],
                    measures=[qty_col],
                    aggregations={qty_col: "sum"},
                    parameters={
                        "x_column": period_col,
                        "y_column": y_axis_col,
                        "measure_column": qty_col,
                        "secondary_model_column": model_col if model_col != y_axis_col else None,
                    },
                    provenance=ProvenanceMetadata(
                        upload_id=upload_id,
                        sheet_name=rejection_ds.sheet_name,
                        cell_range=rejection_ds.cell_range,
                        source_column=qty_col,
                        aggregation="sum",
                        calculation_applied="Matrix unpivot aggregation",
                        confirmation_status="confirmed",
                    ),
                )
            )

    # 4. Widget D: Corrective-Action Tracker
    target_action_ds = action_ds or rejection_ds
    if target_action_ds:
        cols = [c.get("name") for c in (target_action_ds.column_metadata or []) if isinstance(c, dict)]
        status_col = next((c for c in cols if c and any(k in c.lower() for k in ["action_status", "status", "stage"])), None)
        owner_col = next((c for c in cols if c and any(k in c.lower() for k in ["owner", "champion", "assigned"])), None)
        due_col = next((c for c in cols if c and any(k in c.lower() for k in ["due", "target date"])), None)
        close_col = next((c for c in cols if c and any(k in c.lower() for k in ["close", "closure", "completed date"])), None)

        item_col = next((c for c in cols if c and any(k in c.lower() for k in ["action_item", "action", "item", "task", "description", "countermeasure"])), None)
        action_dims = [c for c in [item_col, status_col, owner_col, due_col, close_col] if c]
        if not action_dims:
            action_dims = cols[:5] if cols else []

        widgets.append(
            ManufacturingWidgetSpec(
                widget_id="widget_action_tracker",
                widget_type="action_tracker",
                title="Corrective-Action & Countermeasure Tracker",
                dataset_id=str(target_action_ds.id),
                dimensions=action_dims,
                measures=[],
                parameters={
                    "item_column": item_col or "Action_Item",
                    "status_column": status_col or "Action_Status",
                    "owner_column": owner_col or "Champion",
                    "due_date_column": due_col or "Due_Date",
                    "closure_date_column": close_col or "Closure_Date",
                    "status_from_cell_colour": bool(status_col == "Action_Status"),
                },
                provenance=ProvenanceMetadata(
                    upload_id=upload_id,
                    sheet_name=target_action_ds.sheet_name,
                    cell_range=target_action_ds.cell_range,
                    source_column=status_col or "Action_Status",
                    aggregation="count",
                    calculation_applied="Derived from confirmed cell fill colors or status text",
                    confirmation_status="confirmed",
                    caveats=["Unmapped fill colours fall back to 'unknown' status."] if not status_col else [],
                ),
            )
        )

    # 5. Widget E: Model-Level Rejection Comparison
    if rejection_ds:
        cols = [c.get("name") for c in (rejection_ds.column_metadata or []) if isinstance(c, dict)]
        model_col = next((c for c in cols if c and "model" in c.lower()), None)
        period_col = next((c for c in cols if c and c.lower() in ["month", "period", "date"]), None)
        qty_col = next((c for c in cols if c and any(k in c.lower() for k in ["quantity", "qty", "count"])), None)

        if model_col and qty_col:
            widgets.append(
                ManufacturingWidgetSpec(
                    widget_id="widget_model_comparison",
                    widget_type="model_comparison",
                    title="Model-Level Rejection Comparison",
                    dataset_id=str(rejection_ds.id),
                    dimensions=[model_col] + ([period_col] if period_col else []),
                    measures=[qty_col],
                    aggregations={qty_col: "sum"},
                    parameters={
                        "model_column": model_col,
                        "period_column": period_col,
                        "measure_column": qty_col,
                        "known_models": KNOWN_MANUFACTURING_MODELS,
                        "disallow_ppm_sum": True,  # Non-negotiable architectural rule
                    },
                    provenance=ProvenanceMetadata(
                        upload_id=upload_id,
                        sheet_name=rejection_ds.sheet_name,
                        cell_range=rejection_ds.cell_range,
                        source_column=qty_col,
                        aggregation="sum",
                        calculation_applied="Direct sum of quantities. Cross-model PPM summing prohibited.",
                        confirmation_status="confirmed",
                    ),
                )
            )

    # Compute baseline reconciliation report
    recon_report = compute_ppm_reconciliation(
        actual_ppm_by_period={},
        source_of_truth_confirmed=source_of_truth_confirmed,
        has_sot_conflict=not source_of_truth_confirmed,
    )

    return ManufacturingDashboardSpec(
        template_type=MANUFACTURING_TEMPLATE_TYPE,
        version=1,
        title=template_name,
        upload_id=upload_id,
        source_of_truth_confirmed=source_of_truth_confirmed,
        source_of_truth_choice=source_of_truth_choice,
        reconciliation=recon_report,
        widgets=widgets,
        available_filters=available_filters,
        global_warnings=global_warnings,
    )


# ---------------------------------------------------------------------------
# Execution Engine: Execute Manufacturing Widgets with DuckDB
# ---------------------------------------------------------------------------

def execute_manufacturing_widget(
    widget: ManufacturingWidgetSpec,
    storage: StorageBackend,
    dataset: Dataset,
    filters: Optional[GlobalFilterInput] = None,
    source_of_truth_confirmed: bool = False,
) -> Dict[str, Any]:
    """
    Executes a single manufacturing widget spec using DuckDB over Parquet.
    Applies global filters consistently and transforms raw rows into ECharts-ready payload.
    """
    query_filters: List[QueryFilter] = []

    # Map global filters to widget query
    if filters:
        cols = {c.get("name", "").lower(): c.get("name", "") for c in (dataset.column_metadata or []) if isinstance(c, dict)}
        
        if filters.period and any(k in cols for k in ["month", "period", "date"]):
            col_match = next(cols[k] for k in ["month", "period", "date"] if k in cols)
            query_filters.append(QueryFilter(column=col_match, operator="==", value=filters.period))

        if filters.model and "model" in cols:
            query_filters.append(QueryFilter(column=cols["model"], operator="==", value=filters.model))

        if filters.defect and any(k in cols for k in ["defect", "issue", "category"]):
            col_match = next(cols[k] for k in ["defect", "issue", "category"] if k in cols)
            query_filters.append(QueryFilter(column=col_match, operator="==", value=filters.defect))

        if filters.action_owner and any(k in cols for k in ["owner", "champion", "assigned"]):
            col_match = next(cols[k] for k in ["owner", "champion", "assigned"] if k in cols)
            query_filters.append(QueryFilter(column=col_match, operator="==", value=filters.action_owner))

        if filters.action_status and any(k in cols for k in ["action_status", "status"]):
            col_match = next(cols[k] for k in ["action_status", "status"] if k in cols)
            query_filters.append(QueryFilter(column=col_match, operator="==", value=filters.action_status))

    # Construct DuckDB QueryPlan
    plan = QueryPlan(
        dataset_id=str(dataset.id),
        dimensions=widget.dimensions,
        measures=widget.measures,
        aggregations=widget.aggregations,
        filters=query_filters,
        limit=5000,
    )

    query_res = execute_query_plan(plan, storage, dataset)
    rows = query_res.get("rows", [])

    # Specialized widget formatting for Apache ECharts
    if widget.widget_type == "ppm_trend_target":
        return _format_ppm_trend_widget(widget, rows, source_of_truth_confirmed)

    elif widget.widget_type == "defect_pareto":
        return _format_defect_pareto_widget(widget, rows)

    elif widget.widget_type == "paynter_heatmap":
        return _format_paynter_heatmap_widget(widget, rows)

    elif widget.widget_type == "action_tracker":
        return _format_action_tracker_widget(widget, rows)

    elif widget.widget_type == "model_comparison":
        return _format_model_comparison_widget(widget, rows)

    return {
        "widget_id": widget.widget_id,
        "widget_type": widget.widget_type,
        "title": widget.title,
        "data": rows,
        "provenance": widget.provenance.model_dump(),
        "warnings": widget.warnings,
    }


def _format_ppm_trend_widget(
    widget: ManufacturingWidgetSpec,
    rows: List[Dict[str, Any]],
    source_of_truth_confirmed: bool,
) -> Dict[str, Any]:
    """Formats PPM trend rows with target line and variance calculations."""
    target_ppm = float(widget.parameters.get("target_ppm", 2000.0))
    is_source_ppm = bool(widget.parameters.get("is_source_ppm", False))
    period_col = widget.parameters.get("period_column", "Month")
    measure_col = widget.parameters.get("measure_column", "PPM")
    agg_key = f"{measure_col}_avg" if is_source_ppm else f"{measure_col}_sum"

    data_points = []
    actual_by_period = {}
    exceeded_count = 0
    warnings = list(widget.warnings)

    if not is_source_ppm and not source_of_truth_confirmed:
        warnings.append(
            "Conflict Warning: Jan production quantity conflict (37,111 vs 46,816) is unconfirmed. "
            "Calculated PPM blocked from publication."
        )

    for r in rows:
        period_val = str(r.get(period_col) or "")
        raw_val = r.get(agg_key) if agg_key in r else r.get(measure_col)
        actual_val = float(raw_val) if raw_val is not None else None

        if actual_val is not None and (is_source_ppm or source_of_truth_confirmed):
            variance = round(actual_val - target_ppm, 2)
            exceeded = actual_val > target_ppm
            if exceeded:
                exceeded_count += 1
            actual_by_period[period_val] = actual_val
        else:
            variance = None
            exceeded = False

        data_points.append(
            {
                "period": period_val,
                "actual_ppm": actual_val if (is_source_ppm or source_of_truth_confirmed) else None,
                "target_ppm": target_ppm,
                "variance": variance,
                "is_exceeded": exceeded,
            }
        )

    # Sort data points chronologically by period if possible
    recon = compute_ppm_reconciliation(
        actual_by_period,
        source_of_truth_confirmed=source_of_truth_confirmed or is_source_ppm,
        has_sot_conflict=not source_of_truth_confirmed and not is_source_ppm,
    )

    return {
        "widget_id": widget.widget_id,
        "widget_type": widget.widget_type,
        "title": widget.title,
        "data_points": data_points,
        "target_ppm": target_ppm,
        "exceeded_count": exceeded_count,
        "reconciliation": recon.model_dump(),
        "provenance": widget.provenance.model_dump(),
        "warnings": warnings,
    }


def _format_defect_pareto_widget(
    widget: ManufacturingWidgetSpec,
    rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Formats Defect Pareto with top-N ranking and cumulative percentages."""
    cat_col = widget.parameters.get("category_column", "Defect")
    meas_col = widget.parameters.get("measure_column", "Count")
    top_n = widget.parameters.get("top_n", 10)
    agg_key = f"{meas_col}_sum" if f"{meas_col}_sum" in (rows[0] if rows else {}) else meas_col

    # Group into defect items
    raw_items = []
    for r in rows:
        cat_val = str(r.get(cat_col) or "Unknown")
        qty_val = float(r.get(agg_key) or r.get(meas_col) or 0)
        raw_items.append({"category": cat_val, "quantity": qty_val})

    # Compute Pareto cumulative distribution
    pareto_items = compute_pareto_cumulative(raw_items, "quantity")

    if top_n and len(pareto_items) > top_n:
        displayed_items = pareto_items[:top_n]
    else:
        displayed_items = pareto_items

    return {
        "widget_id": widget.widget_id,
        "widget_type": widget.widget_type,
        "title": widget.title,
        "items": displayed_items,
        "total_categories": len(pareto_items),
        "displayed_categories": len(displayed_items),
        "threshold_line": widget.parameters.get("pareto_threshold", 80.0),
        "provenance": widget.provenance.model_dump(),
        "warnings": widget.warnings,
    }


def _format_paynter_heatmap_widget(
    widget: ManufacturingWidgetSpec,
    rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Formats 2D Heatmap matrix (Defect/Model on Y-axis, Months on X-axis).
    Safely handles future months as null without false zero values.
    """
    x_col = widget.parameters.get("x_column", "Month")
    y_col = widget.parameters.get("y_column", "Defect")
    meas_col = widget.parameters.get("measure_column", "Count")
    agg_key = f"{meas_col}_sum" if f"{meas_col}_sum" in (rows[0] if rows else {}) else meas_col

    x_values = sorted(list({str(r.get(x_col)) for r in rows if r.get(x_col) is not None}))
    y_values = sorted(list({str(r.get(y_col)) for r in rows if r.get(y_col) is not None}))

    # Map values into 2D dictionary
    val_map: Dict[Tuple[str, str], float] = {}
    for r in rows:
        x_val = str(r.get(x_col) or "")
        y_val = str(r.get(y_col) or "")
        qty = float(r.get(agg_key) or r.get(meas_col) or 0)
        val_map[(x_val, y_val)] = qty

    # Build ECharts heatmap matrix [ [x_idx, y_idx, value], ... ]
    matrix = []
    max_val = 0.0
    for y_idx, y_val in enumerate(y_values):
        for x_idx, x_val in enumerate(x_values):
            val = val_map.get((x_val, y_val), None)
            if val is not None and val > max_val:
                max_val = val
            matrix.append([x_idx, y_idx, val])

    return {
        "widget_id": widget.widget_id,
        "widget_type": widget.widget_type,
        "title": widget.title,
        "x_categories": x_values,
        "y_categories": y_values,
        "matrix_data": matrix,
        "max_value": max_val,
        "provenance": widget.provenance.model_dump(),
        "warnings": widget.warnings,
    }


def _format_action_tracker_widget(
    widget: ManufacturingWidgetSpec,
    rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Formats Countermeasure / Action Tracker board:
    - Counts by status (open, closed, overdue, unknown)
    - Owner/champion breakdown
    - Action item list with validated dates
    """
    status_col = widget.parameters.get("status_column", "Action_Status")
    owner_col = widget.parameters.get("owner_column", "Champion")
    due_col = widget.parameters.get("due_date_column", "Due_Date")
    close_col = widget.parameters.get("closure_date_column", "Closure_Date")

    status_counts = {"open": 0, "closed": 0, "overdue": 0, "unknown": 0}
    owner_counts: Dict[str, int] = {}
    action_items = []
    warnings = list(widget.warnings)

    today = dt.date.today()

    for idx, r in enumerate(rows):
        raw_status = str(r.get(status_col) or "").strip().lower()
        owner = str(r.get(owner_col) or "Unassigned").strip()
        due_raw = str(r.get(due_col) or "").strip()
        close_raw = str(r.get(close_col) or "").strip()

        # Parse due date safely
        is_overdue = False
        parsed_due = None
        if due_raw:
            try:
                # Handle ISO string or date
                parsed_due = dt.date.fromisoformat(due_raw[:10])
                if parsed_due < today and raw_status not in ["closed", "complete", "completed"]:
                    is_overdue = True
            except Exception:
                warnings.append(f"Row {idx+1}: Unparseable due date '{due_raw}'.")

        # Map semantic status
        if raw_status in ["closed", "complete", "completed"]:
            status_label = "closed"
        elif is_overdue or raw_status == "overdue":
            status_label = "overdue"
        elif raw_status in ["open", "in progress", "pending"]:
            status_label = "open"
        else:
            status_label = "unknown"

        status_counts[status_label] = status_counts.get(status_label, 0) + 1
        owner_counts[owner] = owner_counts.get(owner, 0) + 1

        action_items.append(
            {
                "id": f"action_{idx+1}",
                "status": status_label,
                "owner": owner,
                "due_date": due_raw or None,
                "closure_date": close_raw or None,
                "is_overdue": is_overdue,
                "raw_fields": r,
            }
        )

    # Deduplicate warnings
    unique_warnings = list(dict.fromkeys(warnings))

    return {
        "widget_id": widget.widget_id,
        "widget_type": widget.widget_type,
        "title": widget.title,
        "status_counts": status_counts,
        "owner_counts": owner_counts,
        "action_items": action_items[:50],  # Bounded to 50 items for dashboard display
        "total_actions": len(rows),
        "provenance": widget.provenance.model_dump(),
        "warnings": unique_warnings,
    }


def _format_model_comparison_widget(
    widget: ManufacturingWidgetSpec,
    rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Formats Model-Level Rejection Comparison:
    - Compares product models (e.g. 157 TY, 367 TY, 457 TY, Milwaukee).
    - Returns rejection quantities per model across periods.
    - Prohibits summing or averaging PPM across models.
    """
    model_col = widget.parameters.get("model_column", "Model")
    period_col = widget.parameters.get("period_column", "Month")
    meas_col = widget.parameters.get("measure_column", "Count")
    agg_key = f"{meas_col}_sum" if f"{meas_col}_sum" in (rows[0] if rows else {}) else meas_col

    model_totals: Dict[str, float] = {}
    model_by_period: Dict[str, Dict[str, float]] = {}
    periods = set()

    for r in rows:
        model = str(r.get(model_col) or "Other").strip()
        period = str(r.get(period_col) or "Total").strip()
        qty = float(r.get(agg_key) or r.get(meas_col) or 0)

        periods.add(period)
        model_totals[model] = model_totals.get(model, 0.0) + qty

        if model not in model_by_period:
            model_by_period[model] = {}
        model_by_period[model][period] = model_by_period[model].get(period, 0.0) + qty

    sorted_periods = sorted(list(periods))

    # Construct series per model
    series = []
    for model, p_dict in model_totals.items():
        series.append(
            {
                "name": model,
                "total": round(p_dict, 2),
                "period_data": [round(model_by_period[model].get(p, 0.0), 2) for p in sorted_periods],
            }
        )

    return {
        "widget_id": widget.widget_id,
        "widget_type": widget.widget_type,
        "title": widget.title,
        "periods": sorted_periods,
        "models": sorted(list(model_totals.keys())),
        "series": series,
        "provenance": widget.provenance.model_dump(),
        "warnings": widget.warnings,
    }
