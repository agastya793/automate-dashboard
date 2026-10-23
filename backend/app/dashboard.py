"""
Dashboard data computation and aggregation engine for Phase 4.

Calculates aggregated chart data and summary statistics from full datasets
based on confirmed Phase 3 chart configurations and active global filters.
"""

from __future__ import annotations

import math
from typing import Any, List, Optional
import numpy as np
import pandas as pd
from pandas import DataFrame
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ChartConfigInput(BaseModel):
    id: str
    title: str
    chart_type: str  # "line", "bar", "ranked_bar", "donut", "histogram", "stacked_bar"
    dimension_column: Optional[str] = None
    secondary_dimension_column: Optional[str] = None
    date_column: Optional[str] = None
    measure_column: Optional[str] = None
    aggregation: str = "sum"  # "sum", "mean", "min", "max", "count"
    date_granularity: Optional[str] = None  # "day", "week", "month", "year"
    top_n: Optional[int] = None
    sort_order: Optional[str] = None  # "desc", "asc", "chronological"


class GlobalFilterInput(BaseModel):
    date_column: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    category_column: Optional[str] = None
    selected_categories: Optional[List[str]] = None


class ComputedChart(BaseModel):
    id: str
    title: str
    chart_type: str
    config: ChartConfigInput
    data: List[dict[str, Any]]
    series_keys: Optional[List[str]] = None
    total_points: int
    warnings: List[str] = Field(default_factory=list)


class FilterOptionDate(BaseModel):
    column_name: str
    min_date: Optional[str] = None
    max_date: Optional[str] = None


class FilterOptionCategory(BaseModel):
    column_name: str
    options: List[str]


class AvailableFilters(BaseModel):
    date_filters: List[FilterOptionDate] = Field(default_factory=list)
    category_filters: List[FilterOptionCategory] = Field(default_factory=list)


class DatasetSummary(BaseModel):
    total_records: int
    filtered_records: int
    column_count: int
    missing_cells: int
    duplicate_records: int
    is_filtered: bool
    measure_summaries: List[dict[str, Any]] = Field(default_factory=list)


class DashboardResponse(BaseModel):
    filename: str
    selected_sheet: Optional[str] = None
    dataset_summary: DatasetSummary
    charts: List[ComputedChart]
    available_filters: AvailableFilters
    warnings: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Sanitization Helper
# ---------------------------------------------------------------------------

def _sanitize_val(v: Any) -> Any:
    """Ensure floats are finite and JSON-serializable."""
    if v is None:
        return None
    if isinstance(v, (float, np.floating)):
        if math.isnan(v) or math.isinf(v):
            return None
        return round(float(v), 2)
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (pd.Timestamp, np.datetime64)):
        try:
            return v.strftime("%Y-%m-%d")
        except Exception:
            return str(v)
    return v


# ---------------------------------------------------------------------------
# Filter Application
# ---------------------------------------------------------------------------

def apply_global_filters(
    df: DataFrame,
    filters: Optional[GlobalFilterInput],
) -> tuple[DataFrame, list[str]]:
    """Applies date range and category filters to the DataFrame."""
    if df.empty or not filters:
        return df, []

    filtered = df.copy()
    warnings: list[str] = []

    # 1. Date Filter
    if filters.date_column:
        d_col = filters.date_column
        if d_col in filtered.columns:
            dt_series = pd.to_datetime(filtered[d_col], errors="coerce")
            valid_dates = dt_series.notna()

            if filters.start_date:
                start_dt = pd.to_datetime(filters.start_date, errors="coerce")
                if pd.notna(start_dt):
                    filtered = filtered[valid_dates & (dt_series >= start_dt)]
                    valid_dates = pd.to_datetime(filtered[d_col], errors="coerce").notna()
                    dt_series = pd.to_datetime(filtered[d_col], errors="coerce")
                else:
                    warnings.append(f"Invalid start date: '{filters.start_date}'")

            if filters.end_date:
                end_dt = pd.to_datetime(filters.end_date, errors="coerce")
                if pd.notna(end_dt):
                    filtered = filtered[valid_dates & (dt_series <= end_dt)]
                else:
                    warnings.append(f"Invalid end date: '{filters.end_date}'")
        else:
            warnings.append(f"Date filter column '{d_col}' not found in dataset.")

    # 2. Category Filter
    if filters.category_column and filters.selected_categories:
        c_col = filters.category_column
        if c_col in filtered.columns:
            str_series = filtered[c_col].fillna("Unknown").astype(str)
            filtered = filtered[str_series.isin(filters.selected_categories)]
        else:
            warnings.append(f"Category filter column '{c_col}' not found in dataset.")

    return filtered, warnings


# ---------------------------------------------------------------------------
# Filter Options Extraction
# ---------------------------------------------------------------------------

def extract_available_filters(
    df: DataFrame,
    column_profiles: list[dict[str, Any]],
) -> AvailableFilters:
    """Extracts date bounds and category choices for user filter controls."""
    date_filters: list[FilterOptionDate] = []
    category_filters: list[FilterOptionCategory] = []

    for p in column_profiles:
        c_name = p["name"]
        inferred = p.get("inferred_type", "").lower()
        if c_name not in df.columns or p.get("unique_count", 0) == 0:
            continue

        # Date columns
        if inferred == "date":
            dt_series = pd.to_datetime(df[c_name], errors="coerce").dropna()
            if not dt_series.empty:
                date_filters.append(
                    FilterOptionDate(
                        column_name=c_name,
                        min_date=dt_series.min().strftime("%Y-%m-%d"),
                        max_date=dt_series.max().strftime("%Y-%m-%d"),
                    )
                )

        # Categorical columns
        elif inferred in ("categorical", "boolean", "category") or (
            inferred == "text" and p.get("unique_count", 0) <= 30
        ):
            unique_vals = (
                df[c_name]
                .dropna()
                .astype(str)
                .str.strip()
                .replace("", "Unknown")
                .unique()
                .tolist()
            )
            unique_vals = sorted([v for v in unique_vals if v][:40])
            if 2 <= len(unique_vals) <= 40:
                category_filters.append(
                    FilterOptionCategory(
                        column_name=c_name,
                        options=unique_vals,
                    )
                )

    return AvailableFilters(
        date_filters=date_filters,
        category_filters=category_filters,
    )


# ---------------------------------------------------------------------------
# Measure Cleaning Helper
# ---------------------------------------------------------------------------

def _clean_numeric_series(series: pd.Series) -> pd.Series:
    """Safely converts string/object numbers with currency symbols to floats."""
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    str_s = series.astype(str).str.strip()
    # Strip currency symbols and percent signs
    clean_s = str_s.str.replace(r"[$€£¥₹,%]", "", regex=True)
    return pd.to_numeric(clean_s, errors="coerce")


# ---------------------------------------------------------------------------
# Individual Chart Computations
# ---------------------------------------------------------------------------

def _compute_line_chart(
    df: DataFrame,
    config: ChartConfigInput,
) -> ComputedChart:
    d_col = config.date_column
    m_col = config.measure_column
    agg = config.aggregation.lower()
    granularity = (config.date_granularity or "day").lower()
    warnings: list[str] = []

    if not d_col or d_col not in df.columns:
        return ComputedChart(
            id=config.id,
            title=config.title,
            chart_type="line",
            config=config,
            data=[],
            total_points=0,
            warnings=[f"Date column '{d_col}' not found."],
        )

    dt_series = pd.to_datetime(df[d_col], errors="coerce")
    valid_mask = dt_series.notna()
    null_dates = int((~valid_mask).sum())
    if null_dates > 0:
        warnings.append(f"{null_dates} records have missing/invalid dates and were omitted.")

    sub_df = df[valid_mask].copy()
    if sub_df.empty:
        return ComputedChart(
            id=config.id,
            title=config.title,
            chart_type="line",
            config=config,
            data=[],
            total_points=0,
            warnings=["No valid date records available."],
        )

    # Format date bucket
    sub_dt = pd.to_datetime(sub_df[d_col], errors="coerce")
    if granularity == "year":
        sub_df["_bucket"] = sub_dt.dt.strftime("%Y")
    elif granularity == "month":
        sub_df["_bucket"] = sub_dt.dt.strftime("%Y-%m")
    elif granularity == "week":
        sub_df["_bucket"] = sub_dt.dt.strftime("%Y-W%W")
    else:
        sub_df["_bucket"] = sub_dt.dt.strftime("%Y-%m-%d")

    data_points: list[dict[str, Any]] = []

    if m_col and m_col in sub_df.columns:
        sub_df["_measure"] = _clean_numeric_series(sub_df[m_col])
        grouped = sub_df.groupby("_bucket")["_measure"]

        if agg == "mean":
            agg_series = grouped.mean()
        elif agg == "min":
            agg_series = grouped.min()
        elif agg == "max":
            agg_series = grouped.max()
        elif agg == "count":
            agg_series = grouped.count()
        else:
            agg_series = grouped.sum()

        agg_df = agg_series.reset_index().sort_values("_bucket")
        for _, row in agg_df.iterrows():
            val = _sanitize_val(row["_measure"])
            if val is not None:
                data_points.append({"label": str(row["_bucket"]), "value": val})
    else:
        # Record count trend
        agg_series = sub_df.groupby("_bucket").size().reset_index(name="count").sort_values("_bucket")
        for _, row in agg_series.iterrows():
            data_points.append({"label": str(row["_bucket"]), "value": int(row["count"])})

    return ComputedChart(
        id=config.id,
        title=config.title,
        chart_type="line",
        config=config,
        data=data_points,
        total_points=len(data_points),
        warnings=warnings,
    )


def _compute_bar_chart(
    df: DataFrame,
    config: ChartConfigInput,
    is_ranked: bool = False,
) -> ComputedChart:
    dim_col = config.dimension_column
    m_col = config.measure_column
    agg = config.aggregation.lower()
    top_n = config.top_n
    warnings: list[str] = []

    if not dim_col or dim_col not in df.columns:
        return ComputedChart(
            id=config.id,
            title=config.title,
            chart_type="ranked_bar" if is_ranked else "bar",
            config=config,
            data=[],
            total_points=0,
            warnings=[f"Dimension column '{dim_col}' not found."],
        )

    sub_df = df.copy()
    sub_df["_dim"] = sub_df[dim_col].fillna("Unknown").astype(str).str.strip()

    data_points: list[dict[str, Any]] = []

    if m_col and m_col in sub_df.columns:
        sub_df["_measure"] = _clean_numeric_series(sub_df[m_col])
        grouped = sub_df.groupby("_dim")["_measure"]

        if agg == "mean":
            agg_series = grouped.mean()
        elif agg == "min":
            agg_series = grouped.min()
        elif agg == "max":
            agg_series = grouped.max()
        elif agg == "count":
            agg_series = grouped.count()
        else:
            agg_series = grouped.sum()

        agg_df = agg_series.reset_index()
        # Sort descending by value
        agg_df = agg_df.sort_values("_measure", ascending=False)

        if is_ranked and top_n:
            agg_df = agg_df.head(top_n)

        for _, row in agg_df.iterrows():
            val = _sanitize_val(row["_measure"])
            if val is not None:
                data_points.append({"label": str(row["_dim"]), "value": val})
    else:
        # Count frequency
        agg_series = sub_df["_dim"].value_counts().reset_index()
        agg_series.columns = ["_dim", "count"]
        if is_ranked and top_n:
            agg_series = agg_series.head(top_n)
        for _, row in agg_series.iterrows():
            data_points.append({"label": str(row["_dim"]), "value": int(row["count"])})

    return ComputedChart(
        id=config.id,
        title=config.title,
        chart_type="ranked_bar" if is_ranked else "bar",
        config=config,
        data=data_points,
        total_points=len(data_points),
        warnings=warnings,
    )


def _compute_donut_chart(
    df: DataFrame,
    config: ChartConfigInput,
) -> ComputedChart:
    dim_col = config.dimension_column
    warnings: list[str] = []

    if not dim_col or dim_col not in df.columns:
        return ComputedChart(
            id=config.id,
            title=config.title,
            chart_type="donut",
            config=config,
            data=[],
            total_points=0,
            warnings=[f"Dimension column '{dim_col}' not found."],
        )

    s = df[dim_col].fillna("Unknown").astype(str).str.strip()
    counts = s.value_counts()

    # If more than 10 categories, keep top 8 and group into "Other"
    data_points: list[dict[str, Any]] = []
    if len(counts) > 10:
        top_counts = counts.head(8)
        other_sum = int(counts.iloc[8:].sum())
        for cat, cnt in top_counts.items():
            data_points.append({"label": str(cat), "value": int(cnt)})
        if other_sum > 0:
            data_points.append({"label": "Other", "value": other_sum})
        warnings.append("Consolidated long-tail categories into 'Other' for readability.")
    else:
        for cat, cnt in counts.items():
            data_points.append({"label": str(cat), "value": int(cnt)})

    return ComputedChart(
        id=config.id,
        title=config.title,
        chart_type="donut",
        config=config,
        data=data_points,
        total_points=len(data_points),
        warnings=warnings,
    )


def _compute_histogram(
    df: DataFrame,
    config: ChartConfigInput,
) -> ComputedChart:
    m_col = config.measure_column
    warnings: list[str] = []

    if not m_col or m_col not in df.columns:
        return ComputedChart(
            id=config.id,
            title=config.title,
            chart_type="histogram",
            config=config,
            data=[],
            total_points=0,
            warnings=[f"Measure column '{m_col}' not found."],
        )

    nums = _clean_numeric_series(df[m_col]).dropna()
    if len(nums) < 2:
        return ComputedChart(
            id=config.id,
            title=config.title,
            chart_type="histogram",
            config=config,
            data=[],
            total_points=0,
            warnings=["Insufficient numeric data points for histogram binning."],
        )

    n_bins = min(8, max(4, int(np.sqrt(len(nums)))))
    counts, bin_edges = np.histogram(nums, bins=n_bins)

    data_points: list[dict[str, Any]] = []
    for i in range(len(counts)):
        low = round(float(bin_edges[i]), 1)
        high = round(float(bin_edges[i + 1]), 1)
        data_points.append({
            "label": f"{low:g} – {high:g}",
            "value": int(counts[i]),
            "bin_start": low,
            "bin_end": high,
        })

    return ComputedChart(
        id=config.id,
        title=config.title,
        chart_type="histogram",
        config=config,
        data=data_points,
        total_points=len(data_points),
        warnings=warnings,
    )


def _compute_stacked_bar(
    df: DataFrame,
    config: ChartConfigInput,
) -> ComputedChart:
    dim1 = config.dimension_column
    dim2 = config.secondary_dimension_column
    m_col = config.measure_column
    agg = config.aggregation.lower()
    warnings: list[str] = []

    if not dim1 or dim1 not in df.columns or not dim2 or dim2 not in df.columns:
        return ComputedChart(
            id=config.id,
            title=config.title,
            chart_type="stacked_bar",
            config=config,
            data=[],
            total_points=0,
            warnings=["Primary or secondary dimension column missing."],
        )

    sub_df = df.copy()
    sub_df["_dim1"] = sub_df[dim1].fillna("Unknown").astype(str).str.strip()
    sub_df["_dim2"] = sub_df[dim2].fillna("Unknown").astype(str).str.strip()

    if m_col and m_col in sub_df.columns:
        sub_df["_m"] = _clean_numeric_series(sub_df[m_col])
        pt = pd.pivot_table(
            sub_df,
            index="_dim1",
            columns="_dim2",
            values="_m",
            aggfunc=agg if agg in ("sum", "mean", "min", "max") else "sum",
            fill_value=0.0,
        )
    else:
        pt = pd.crosstab(sub_df["_dim1"], sub_df["_dim2"])

    series_keys = [str(c) for c in pt.columns]
    data_points: list[dict[str, Any]] = []

    for idx, row in pt.iterrows():
        item: dict[str, Any] = {"label": str(idx)}
        for col_name in series_keys:
            val = _sanitize_val(row[col_name])
            item[col_name] = val if val is not None else 0.0
        data_points.append(item)

    return ComputedChart(
        id=config.id,
        title=config.title,
        chart_type="stacked_bar",
        config=config,
        data=data_points,
        series_keys=series_keys,
        total_points=len(data_points),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Measure Summaries (KPIs)
# ---------------------------------------------------------------------------

def _compute_measure_summaries(
    df: DataFrame,
    chart_configs: list[ChartConfigInput],
) -> list[dict[str, Any]]:
    """Calculates summary metric values for confirmed quantitative measures."""
    summaries: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for cfg in chart_configs:
        m_col = cfg.measure_column
        if not m_col or m_col not in df.columns:
            continue

        agg = cfg.aggregation.lower()
        key = (m_col, agg)
        if key in seen:
            continue
        seen.add(key)

        clean_nums = _clean_numeric_series(df[m_col]).dropna()
        if clean_nums.empty:
            continue

        if agg == "mean":
            val = clean_nums.mean()
            label = f"Average {m_col.replace('_', ' ').title()}"
        elif agg == "min":
            val = clean_nums.min()
            label = f"Minimum {m_col.replace('_', ' ').title()}"
        elif agg == "max":
            val = clean_nums.max()
            label = f"Maximum {m_col.replace('_', ' ').title()}"
        else:
            val = clean_nums.sum()
            label = f"Total {m_col.replace('_', ' ').title()}"

        summaries.append({
            "column": m_col,
            "aggregation": agg,
            "label": label,
            "value": _sanitize_val(val),
        })

        if len(summaries) >= 4:
            break

    return summaries


# ---------------------------------------------------------------------------
# Public Engine Entry Point
# ---------------------------------------------------------------------------

def generate_dashboard_data(
    df: DataFrame,
    filename: str,
    selected_sheet: Optional[str],
    column_profiles: list[dict[str, Any]],
    chart_configs: list[ChartConfigInput],
    filters: Optional[GlobalFilterInput] = None,
) -> DashboardResponse:
    """
    Validates chart configs, applies filters, and executes data aggregation
    for all requested visualization types.
    """
    total_records = len(df)
    filtered_df, filter_warnings = apply_global_filters(df, filters)
    is_filtered = len(filtered_df) < total_records

    # Data Quality & Dimension counts on filtered data
    dup_count = int(filtered_df.duplicated().sum()) if not filtered_df.empty else 0
    missing_cells = sum(int(filtered_df[c].isna().sum()) for c in filtered_df.columns) if not filtered_df.empty else 0

    measure_summaries = _compute_measure_summaries(filtered_df, chart_configs)

    dataset_summary = DatasetSummary(
        total_records=total_records,
        filtered_records=len(filtered_df),
        column_count=len(df.columns),
        missing_cells=missing_cells,
        duplicate_records=dup_count,
        is_filtered=is_filtered,
        measure_summaries=measure_summaries,
    )

    available_filters = extract_available_filters(df, column_profiles)

    computed_charts: list[ComputedChart] = []
    dashboard_warnings: list[str] = list(filter_warnings)

    for cfg in chart_configs:
        c_type = cfg.chart_type.lower()
        if c_type == "line":
            computed_charts.append(_compute_line_chart(filtered_df, cfg))
        elif c_type == "ranked_bar":
            computed_charts.append(_compute_bar_chart(filtered_df, cfg, is_ranked=True))
        elif c_type == "bar":
            computed_charts.append(_compute_bar_chart(filtered_df, cfg, is_ranked=False))
        elif c_type in ("donut", "pie"):
            computed_charts.append(_compute_donut_chart(filtered_df, cfg))
        elif c_type == "histogram":
            computed_charts.append(_compute_histogram(filtered_df, cfg))
        elif c_type == "stacked_bar":
            computed_charts.append(_compute_stacked_bar(filtered_df, cfg))
        else:
            dashboard_warnings.append(f"Skipping unsupported chart type '{c_type}' for '{cfg.title}'.")

    return DashboardResponse(
        filename=filename,
        selected_sheet=selected_sheet,
        dataset_summary=dataset_summary,
        charts=computed_charts,
        available_filters=available_filters,
        warnings=dashboard_warnings,
    )
