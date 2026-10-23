"""
Automatic Chart Recommendation Engine for Phase 3.

Deterministic, rules-based engine that analyzes validated dataset columns
and profiling metadata to generate ranked, explainable chart recommendations.

Design principles:
- Deterministic and explainable (never invents metrics or business definitions).
- Conservative (avoids noisy combinations and skips identifiers/empty columns).
- Additive (integrates cleanly into preview response without altering existing schema).
"""

from __future__ import annotations

import re
from typing import Any, List, Optional
from pydantic import BaseModel, Field
import pandas as pd
from pandas import DataFrame


# ---------------------------------------------------------------------------
# Pydantic Recommendation Schema
# ---------------------------------------------------------------------------

class ChartRecommendation(BaseModel):
    id: str
    title: str
    chart_type: str  # "line", "bar", "ranked_bar", "donut", "histogram", "stacked_bar"
    dimension_column: Optional[str] = None
    secondary_dimension_column: Optional[str] = None
    date_column: Optional[str] = None
    measure_column: Optional[str] = None
    suggested_aggregation: str
    supported_aggregations: List[str]
    sort_order: Optional[str] = None  # "desc", "asc", "chronological"
    top_n: Optional[int] = None
    supported_top_n: Optional[List[int]] = None
    date_granularity: Optional[str] = None  # "day", "week", "month", "year"
    supported_date_granularities: Optional[List[str]] = None
    explanation: str
    suitability: str  # "high", "medium", "exploratory"
    suitability_reason: str
    caveats: List[str] = Field(default_factory=list)
    requires_confirmation: bool = True


# ---------------------------------------------------------------------------
# Helpers for Column Classification & Ranking
# ---------------------------------------------------------------------------

_YEAR_LIKE_PATTERN = re.compile(r"^(?:19|20)\d{2}$")


def _is_measure_candidate(col_profile: dict[str, Any]) -> bool:
    """
    Check if a column is a suitable quantitative measure.
    Identifiers, IDs, postal codes, and year numbers are excluded.
    """
    inferred = col_profile.get("inferred_type", "").lower()
    if inferred not in ("numeric", "currency", "percentage"):
        return False

    name = col_profile.get("name", "").lower()
    # Exclude ID-like or code-like names even if numeric
    if any(hint in name for hint in ("id", "code", "zip", "postal", "pin", "sku", "year", "barcode")):
        return False

    if col_profile.get("unique_count", 0) <= 1:
        return False

    return True


def _is_categorical_candidate(col_profile: dict[str, Any], total_rows: int) -> bool:
    """
    Check if a column is a suitable categorical grouping dimension.
    Cardinality must be manageable (2 to 35 unique values) and not unique per row.
    """
    inferred = col_profile.get("inferred_type", "").lower()
    if inferred not in ("categorical", "category", "boolean", "text"):
        return False

    name = col_profile.get("name", "").lower()
    # Skip obvious identifiers or descriptions
    if any(hint in name for hint in ("id", "code", "guid", "uuid", "hash", "token", "password", "key", "url", "email")):
        return False

    unique = col_profile.get("unique_count", 0)
    if unique < 2 or unique > 35:
        return False

    # Skip if almost every row is unique (free-text or random ID)
    if total_rows > 10 and (unique / total_rows) > 0.85:
        return False

    return True


def _format_column_title(col_name: str) -> str:
    """Converts snake_case or camelCase to clean Title Case."""
    clean = re.sub(r"[_\-]+", " ", col_name).strip()
    return " ".join(word.capitalize() for word in clean.split())


# ---------------------------------------------------------------------------
# Recommendation Rules
# ---------------------------------------------------------------------------

def _recommend_time_series(
    date_col: dict[str, Any],
    measures: list[dict[str, Any]],
    total_rows: int,
) -> list[ChartRecommendation]:
    """Rule A: Time-series trends over date columns."""
    recs: list[ChartRecommendation] = []
    d_name = date_col["name"]
    d_title = _format_column_title(d_name)

    # 1. With numeric measures
    for m in measures[:3]:  # Top 3 measures max for time-series
        m_name = m["name"]
        m_title = _format_column_title(m_name)
        is_pct = m.get("inferred_type") == "percentage"

        suggested_agg = "mean" if is_pct else "sum"
        supported_aggs = ["mean", "min", "max", "count"] if is_pct else ["sum", "mean", "min", "max", "count"]

        caveats = [
            f"Provisional default aggregation is '{suggested_agg}'. Please confirm if this matches reporting definitions.",
        ]
        if is_pct:
            caveats.append("Percentages default to average (mean) because additive sums across periods are typically non-standard.")
        if date_col.get("missing_count", 0) > 0:
            caveats.append(f"Contains {date_col['missing_count']} missing date records which will be excluded from time-series alignment.")

        recs.append(
            ChartRecommendation(
                id=f"rec_timeseries_{d_name}_{m_name}",
                title=f"{m_title} Trend over {d_title}",
                chart_type="line",
                date_column=d_name,
                measure_column=m_name,
                suggested_aggregation=suggested_agg,
                supported_aggregations=supported_aggs,
                date_granularity="month" if total_rows > 30 else "day",
                supported_date_granularities=["day", "week", "month", "year"],
                sort_order="chronological",
                explanation=f"Visualizes how {m_title} progresses over {d_title} to track directional velocity and periodic patterns.",
                suitability="high",
                suitability_reason=f"High-quality combination of verified temporal column '{d_name}' and quantitative measure '{m_name}'.",
                caveats=caveats,
                requires_confirmation=True,
            )
        )

    # 2. Record count trend if no measure exists or as supplementary activity volume
    if not measures or len(recs) == 0:
        caveats = ["Aggregates total dataset row volume per date interval."]
        if date_col.get("missing_count", 0) > 0:
            caveats.append(f"Excludes {date_col['missing_count']} missing date rows.")

        recs.append(
            ChartRecommendation(
                id=f"rec_timeseries_{d_name}_record_count",
                title=f"Record Volume Trend over {d_title}",
                chart_type="line",
                date_column=d_name,
                measure_column=None,
                suggested_aggregation="count",
                supported_aggregations=["count"],
                date_granularity="month" if total_rows > 30 else "day",
                supported_date_granularities=["day", "week", "month", "year"],
                sort_order="chronological",
                explanation=f"Shows transaction and record arrival activity across {d_title}.",
                suitability="medium",
                suitability_reason=f"Tracks operational record frequency when no specific numeric measure is chosen.",
                caveats=caveats,
                requires_confirmation=True,
            )
        )

    return recs


def _recommend_category_comparisons(
    categories: list[dict[str, Any]],
    measures: list[dict[str, Any]],
) -> list[ChartRecommendation]:
    """Rule B & C: Category bar charts and ranked Top-N comparisons."""
    recs: list[ChartRecommendation] = []

    for cat in categories[:3]:  # Limit to top 3 cleanest categories
        c_name = cat["name"]
        c_title = _format_column_title(c_name)
        cardinality = cat.get("unique_count", 0)

        for m in measures[:2]:  # Pair with top 2 measures
            m_name = m["name"]
            m_title = _format_column_title(m_name)
            is_pct = m.get("inferred_type") == "percentage"

            suggested_agg = "mean" if is_pct else "sum"
            supported_aggs = ["mean", "min", "max", "count"] if is_pct else ["sum", "mean", "min", "max", "count"]

            caveats = [
                f"Default aggregation is '{suggested_agg}'. Please review before final reporting.",
            ]
            if is_pct:
                caveats.append("Percentage measures default to mean instead of sum.")

            # Rule C: Ranked Top-N if category has more than 6 unique values
            if cardinality >= 6:
                top_val = 10 if cardinality >= 10 else 5
                recs.append(
                    ChartRecommendation(
                        id=f"rec_ranked_{c_name}_{m_name}",
                        title=f"Top {top_val} {c_title} by {m_title}",
                        chart_type="ranked_bar",
                        dimension_column=c_name,
                        measure_column=m_name,
                        suggested_aggregation=suggested_agg,
                        supported_aggregations=supported_aggs,
                        sort_order="desc",
                        top_n=top_val,
                        supported_top_n=[5, 10, 20],
                        explanation=f"Ranks the highest contributing {c_title} groups by total {m_title}.",
                        suitability="high",
                        suitability_reason=f"Category '{c_name}' has {cardinality} values; a ranked Top-{top_val} presentation provides high executive clarity.",
                        caveats=caveats,
                        requires_confirmation=True,
                    )
                )
            else:
                # Rule B: Standard category bar comparison
                recs.append(
                    ChartRecommendation(
                        id=f"rec_bar_{c_name}_{m_name}",
                        title=f"{m_title} by {c_title}",
                        chart_type="bar",
                        dimension_column=c_name,
                        measure_column=m_name,
                        suggested_aggregation=suggested_agg,
                        supported_aggregations=supported_aggs,
                        sort_order="desc",
                        top_n=None,
                        explanation=f"Compares aggregate {m_title} across all {cardinality} {c_title} categories.",
                        suitability="high",
                        suitability_reason=f"Clean comparison of concise category '{c_name}' ({cardinality} values) against numeric measure '{m_name}'.",
                        caveats=caveats,
                        requires_confirmation=True,
                    )
                )

    return recs


def _recommend_category_distributions(
    categories: list[dict[str, Any]],
) -> list[ChartRecommendation]:
    """Rule D: Category distribution / frequency breakdowns (Record counts)."""
    recs: list[ChartRecommendation] = []

    for cat in categories[:2]:
        c_name = cat["name"]
        c_title = _format_column_title(c_name)
        cardinality = cat.get("unique_count", 0)

        # Ideal for donut / proportion breakdown if cardinality is 2 to 7
        chart_type = "donut" if cardinality <= 7 else "bar"
        top_n = 10 if cardinality > 10 else None

        caveats = ["Aggregates record count frequencies. Does not weight records by monetary value or volume."]
        if cat.get("missing_count", 0) > 0:
            caveats.append(f"Dataset has {cat['missing_count']} records with missing {c_title}.")

        recs.append(
            ChartRecommendation(
                id=f"rec_dist_{c_name}",
                title=f"Record Breakdown by {c_title}",
                chart_type=chart_type,
                dimension_column=c_name,
                measure_column=None,
                suggested_aggregation="count",
                supported_aggregations=["count"],
                sort_order="desc",
                top_n=top_n,
                supported_top_n=[5, 10] if top_n else None,
                explanation=f"Displays the distribution and relative share of records across {c_title} segments.",
                suitability="high" if cardinality <= 8 else "medium",
                suitability_reason=f"Concise categorical distribution ({cardinality} distinct segments) suitable for proportion analysis.",
                caveats=caveats,
                requires_confirmation=True,
            )
        )

    return recs


def _recommend_numeric_distributions(
    measures: list[dict[str, Any]],
    total_rows: int,
) -> list[ChartRecommendation]:
    """Rule E: Histograms for numeric measures to inspect spread and skewness."""
    recs: list[ChartRecommendation] = []

    if total_rows < 5:
        return recs

    for m in measures[:2]:
        m_name = m["name"]
        m_title = _format_column_title(m_name)
        cardinality = m.get("unique_count", 0)

        if cardinality < 5:
            continue

        caveats = [
            "Continuous value distribution; bin boundaries will be calculated dynamically.",
            "Null/missing values are omitted from binning.",
        ]

        recs.append(
            ChartRecommendation(
                id=f"rec_hist_{m_name}",
                title=f"{m_title} Distribution Frequency",
                chart_type="histogram",
                dimension_column=None,
                measure_column=m_name,
                suggested_aggregation="count",
                supported_aggregations=["count"],
                explanation=f"Examines value frequency distribution, dispersion, and potential outliers for {m_title}.",
                suitability="medium",
                suitability_reason=f"Quantitative measure with {cardinality} unique data points across {total_rows} records.",
                caveats=caveats,
                requires_confirmation=True,
            )
        )

    return recs


def _recommend_secondary_comparisons(
    categories: list[dict[str, Any]],
    measures: list[dict[str, Any]],
) -> list[ChartRecommendation]:
    """Rule F: Grouped or stacked bar for two clean categories with low combined cardinality."""
    recs: list[ChartRecommendation] = []

    if len(categories) < 2 or not measures:
        return recs

    # Find two distinct categories with small cardinality
    cat1 = categories[0]
    cat2 = categories[1]

    c1_card = cat1.get("unique_count", 0)
    c2_card = cat2.get("unique_count", 0)

    # Conservative limit: product of cardinalities <= 36 to avoid visual noise
    if 2 <= c1_card <= 8 and 2 <= c2_card <= 6 and (c1_card * c2_card <= 36):
        m = measures[0]
        c1_name, c2_name = cat1["name"], cat2["name"]
        m_name = m["name"]
        c1_title = _format_column_title(c1_name)
        c2_title = _format_column_title(c2_name)
        m_title = _format_column_title(m_name)

        is_pct = m.get("inferred_type") == "percentage"
        suggested_agg = "mean" if is_pct else "sum"

        recs.append(
            ChartRecommendation(
                id=f"rec_stacked_{c1_name}_{c2_name}_{m_name}",
                title=f"{m_title} by {c1_title} segmented by {c2_title}",
                chart_type="stacked_bar",
                dimension_column=c1_name,
                secondary_dimension_column=c2_name,
                measure_column=m_name,
                suggested_aggregation=suggested_agg,
                supported_aggregations=["sum", "mean", "count"],
                sort_order="desc",
                explanation=f"Multivariate comparison displaying {m_title} by {c1_title} with sub-segmentation by {c2_title}.",
                suitability="exploratory",
                suitability_reason=f"Both '{c1_name}' ({c1_card} values) and '{c2_name}' ({c2_card} values) have compact cardinality suitable for multi-dimensional stacking.",
                caveats=[
                    "Multi-variable chart: ensure relationship between dimensions is logically meaningful for stakeholders.",
                    f"Default aggregation is '{suggested_agg}'.",
                ],
                requires_confirmation=True,
            )
        )

    return recs


# ---------------------------------------------------------------------------
# Public Recommendation Engine Entry Point
# ---------------------------------------------------------------------------

def recommend_charts(
    df: DataFrame,
    column_profiles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Generate ranked, deduplicated, deterministic chart recommendations
    from a validated DataFrame and its column profile metadata.

    Returns a list of dicts conforming to ChartRecommendation schema.
    """
    total_rows = len(df)
    if total_rows == 0 or not column_profiles:
        return []

    # Filter columns by role
    date_cols: list[dict[str, Any]] = []
    measure_cols: list[dict[str, Any]] = []
    cat_cols: list[dict[str, Any]] = []

    for p in column_profiles:
        # Ignore completely empty columns
        if p.get("unique_count", 0) == 0 or p.get("missing_pct", 0) >= 100.0:
            continue

        inferred = p.get("inferred_type", "").lower()

        if inferred == "date":
            date_cols.append(p)
        elif _is_measure_candidate(p):
            measure_cols.append(p)
        elif _is_categorical_candidate(p, total_rows):
            cat_cols.append(p)

    all_recs: list[ChartRecommendation] = []

    # 1. Time-series recommendations (if dates exist)
    for d in date_cols[:2]:
        all_recs.extend(_recommend_time_series(d, measure_cols, total_rows))

    # 2. Category comparisons & Ranked Bar (if categories & measures exist)
    if cat_cols and measure_cols:
        all_recs.extend(_recommend_category_comparisons(cat_cols, measure_cols))

    # 3. Categorical distributions (Frequency / Donut)
    if cat_cols:
        all_recs.extend(_recommend_category_distributions(cat_cols))

    # 4. Numeric distributions (Histograms)
    if measure_cols:
        all_recs.extend(_recommend_numeric_distributions(measure_cols, total_rows))

    # 5. Secondary multi-variable comparison (max 1)
    if len(cat_cols) >= 2 and measure_cols:
        all_recs.extend(_recommend_secondary_comparisons(cat_cols, measure_cols))

    # Deduplicate by key attributes
    seen_keys: set[tuple[Any, ...]] = set()
    deduped: list[ChartRecommendation] = []

    for r in all_recs:
        key = (
            r.chart_type,
            r.dimension_column,
            r.secondary_dimension_column,
            r.date_column,
            r.measure_column,
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(r)

    # Rank recommendations: "high" > "medium" > "exploratory"
    suitability_rank = {"high": 0, "medium": 1, "exploratory": 2}
    deduped.sort(key=lambda r: suitability_rank.get(r.suitability, 3))

    # Cap to a curated top 6 to 8 recommendations
    final_recs = deduped[:8]

    # Return pure JSON-serializable dicts
    return [r.model_dump() for r in final_recs]
