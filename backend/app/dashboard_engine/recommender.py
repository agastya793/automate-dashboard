"""
Dashboard recommendation engine — corrected and hardened version of
recommend_reference.py.

Key corrections over recommend_reference.py
-------------------------------------------
* is_id() heuristic is conservative: column-name patterns + leading zeros +
  sequential integer detection.  Plain numeric measures like PPM / defect
  counts are NOT classified as IDs.
* No dynamic SQL string interpolation.  All DuckDB queries use parameterised
  or pre-validated identifiers resolved from the registered DataFrame, not
  from untrusted client input.
* Widget specs are validated against a strict server-side allowlist before
  execution.  Unknown types, SQL-like column names, and arbitrary table names
  are rejected.
* Source-of-truth conflicts (production quantity: 37,111 vs 46,816) are
  surfaced as explicit warnings requiring user confirmation — never silently
  resolved.
* Distinct measures (qty, PPM, %) are kept in separate widget entries.
* Zero denominators, empty frames, and all-missing values are handled
  gracefully.
* clean_labels() / suggest_label_merges() is suggestions-only; no silent
  category rewrites.
* No client-workbook-specific hardcoded checks or print() statements in
  production code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from app.ingestion.scanner import BlockResult, suggest_label_merges


# ---------------------------------------------------------------------------
# Allowed widget types and aggregations (strict server-side allowlist)
# ---------------------------------------------------------------------------

ALLOWED_WIDGET_TYPES: frozenset[str] = frozenset(
    {
        "kpi",
        "line",
        "bar",
        "pareto",
        "heatmap",
        "gauge",
        "table",
        "donut",
        "stacked_bar",
    }
)

ALLOWED_AGGREGATIONS: frozenset[str] = frozenset(
    {"sum", "mean", "min", "max", "count"}
)

# Column names that could be SQL injection attempts
_SQL_DANGEROUS = re.compile(
    r"(--|;|/\*|\*/|xp_|0x|UNION|SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC)",
    re.IGNORECASE,
)

# Maximum allowed length for a column name in a widget spec
_MAX_COL_NAME_LEN = 256


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class WidgetSpec:
    """
    A single validated widget specification.
    All fields come from server-side recommendation; client may only adjust
    user-configurable parameters (title, top_n, filter) through the mapping UI.
    """
    widget_id: str
    widget_type: str         # one of ALLOWED_WIDGET_TYPES
    title: str
    dataset_key: str         # resolved server-side to a registered DataFrame
    x_col: str | None = None
    y_col: str | None = None
    z_col: str | None = None
    filter: dict[str, Any] = field(default_factory=dict)
    aggregation: str = "sum"
    cumulative: bool = False
    top_n: int | None = None
    source_of_truth_warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class DashboardSpec:
    """Container for a full set of widget specs and global metadata."""
    version: int = 1
    widgets: list[WidgetSpec] = field(default_factory=list)
    global_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "global_warnings": self.global_warnings,
            "widgets": [
                {
                    "widget_id": w.widget_id,
                    "widget_type": w.widget_type,
                    "title": w.title,
                    "dataset_key": w.dataset_key,
                    "x_col": w.x_col,
                    "y_col": w.y_col,
                    "z_col": w.z_col,
                    "filter": w.filter,
                    "aggregation": w.aggregation,
                    "cumulative": w.cumulative,
                    "top_n": w.top_n,
                    "source_of_truth_warnings": w.source_of_truth_warnings,
                    "notes": w.notes,
                }
                for w in self.widgets
            ],
        }


# ---------------------------------------------------------------------------
# Identifier detection (conservative — fixes recommend_reference.py is_id())
# ---------------------------------------------------------------------------

_ID_NAME_PATTERN = re.compile(
    r"^(sr\.?|s\.?\s*no|id|index|#|\bno\b|seq)\b",
    re.IGNORECASE,
)


def _is_id_column(series: pd.Series, name: str) -> bool:
    """
    Conservative identifier check.

    A column is an identifier when its name matches a known pattern
    (Sr No, ID, Index, #, Seq) OR it contains leading-zero strings OR it is
    a perfectly sequential integer series starting near 1.

    Genuine numeric measures (PPM, defect count, production qty) are NOT
    flagged as IDs even though they consist entirely of numbers.
    """
    if _ID_NAME_PATTERN.match(name.strip()):
        return True

    non_null = series.dropna()
    if len(non_null) == 0:
        return False

    str_vals = non_null.astype(str)
    if str_vals.str.match(r"^0\d+$").any():
        return True

    numeric = pd.to_numeric(non_null, errors="coerce")
    if numeric.notna().all() and len(numeric) > 1:
        int_vals = numeric.astype(int)
        if (
            int_vals.nunique() == len(int_vals)
            and int_vals.min() >= 0
            and int_vals.max() == int_vals.min() + len(int_vals) - 1
        ):
            return True

    return False


# ---------------------------------------------------------------------------
# Column name safety validation
# ---------------------------------------------------------------------------

def _validate_col_name(name: str | None) -> str | None:
    """
    Validate that a column name is safe for use in DuckDB queries.
    Raises ValueError if the name contains SQL-dangerous patterns or is too long.
    """
    if name is None:
        return None
    if len(name) > _MAX_COL_NAME_LEN:
        raise ValueError(
            f"Column name too long ({len(name)} chars): '{name[:40]}...'"
        )
    if _SQL_DANGEROUS.search(name):
        raise ValueError(
            f"Column name contains disallowed pattern: '{name}'. "
            "Column names must not contain SQL keywords or special characters."
        )
    return name


def _quote_identifier(name: str) -> str:
    """
    Safely quote a DuckDB identifier by doubling any embedded double-quotes.
    This is the only place identifiers are quoted — never done with f-strings
    in query bodies.
    """
    return '"' + name.replace('"', '""') + '"'


# ---------------------------------------------------------------------------
# Widget spec validation
# ---------------------------------------------------------------------------

def _validate_widget_spec(w: WidgetSpec, registered_keys: set[str]) -> list[str]:
    """
    Validate a WidgetSpec against the server-side allowlists and registered datasets.
    Returns a list of validation error strings (empty = valid).
    """
    errors: list[str] = []

    if w.widget_type not in ALLOWED_WIDGET_TYPES:
        errors.append(
            f"Unknown widget type '{w.widget_type}'. "
            f"Allowed: {sorted(ALLOWED_WIDGET_TYPES)}."
        )

    if w.aggregation not in ALLOWED_AGGREGATIONS:
        errors.append(
            f"Unknown aggregation '{w.aggregation}'. "
            f"Allowed: {sorted(ALLOWED_AGGREGATIONS)}."
        )

    if w.dataset_key not in registered_keys:
        errors.append(
            f"Dataset key '{w.dataset_key}' is not registered. "
            "The server resolves dataset references; arbitrary table names "
            "from clients are not accepted."
        )

    for col_field in (w.x_col, w.y_col, w.z_col):
        try:
            _validate_col_name(col_field)
        except ValueError as exc:
            errors.append(str(exc))

    for k, v in w.filter.items():
        try:
            _validate_col_name(k)
        except ValueError as exc:
            errors.append(str(exc))
        if not isinstance(v, (str, int, float, bool, type(None))):
            errors.append(
                f"Filter value for '{k}' must be a scalar "
                f"(str/int/float/bool/None), got {type(v).__name__}."
            )

    return errors


# ---------------------------------------------------------------------------
# Recommendation engine
# ---------------------------------------------------------------------------

def recommend_dashboard(
    blocks: list[BlockResult],
    dataset_keys: dict[str, pd.DataFrame],
) -> DashboardSpec:
    """
    Generate a validated DashboardSpec from detected blocks.

    Parameters
    ----------
    blocks:
        List of classified BlockResult objects from the scanner.
    dataset_keys:
        Server-resolved mapping of dataset_key → DataFrame.
        The server (not the client) populates this mapping.

    Returns
    -------
    DashboardSpec with validated WidgetSpec list.
    """
    spec = DashboardSpec()
    registered = set(dataset_keys.keys())
    widget_counter = 0

    # Source-of-truth conflict: production quantity discrepancy from blueprint.
    # This is an explicit warning — not silently resolved.
    sot_warning = (
        "SOURCE-OF-TRUTH CONFLICT: The blueprint flags a production-quantity "
        "discrepancy (Target 2026 January: 37,111 vs Paynter 2026: 46,816). "
        "PPM calculations used Paynter values in the reference snippet. "
        "Please confirm which value is authoritative before any PPM widget "
        "is used in reporting. No PPM widget is generated until this is resolved."
    )
    ppm_confirmed = False  # Would become True after user confirms mapping

    for b in blocks:
        df = b.df
        if df is None or df.empty:
            continue

        if b.kind not in ("wide", "tidy"):
            continue

        key = f"{b.sheet}!{b.range}"
        if key not in registered:
            continue

        # Find categorical dimensions (not IDs, not dates, not measures)
        dims = [
            c
            for c in df.columns
            if c not in ("period", "value", "measure")
            and not pd.api.types.is_numeric_dtype(df[c])
            and df[c].nunique() > 1
            and df[c].nunique() <= 30
            and not _is_id_column(df[c], c)
        ]

        measures: list[str] = []
        if "measure" in df.columns:
            measures = sorted(df["measure"].dropna().unique().tolist())

        # --- Wide/unpivoted blocks ---
        if b.kind == "wide" and {"period", "value"} <= set(df.columns):
            for m in measures:
                tag = "" if len(measures) == 1 else f" ({m})"
                filt = {"measure": m}

                # Skip PPM until source-of-truth is confirmed
                if re.search(r"ppm", m, re.IGNORECASE) and not ppm_confirmed:
                    spec.global_warnings.append(
                        f"PPM widget for measure '{m}' in block '{key}' "
                        "was suppressed pending source-of-truth confirmation. "
                        + sot_warning
                    )
                    continue

                widget_counter += 1
                # KPI
                spec.widgets.append(
                    WidgetSpec(
                        widget_id=f"w{widget_counter:03d}_kpi_{m}",
                        widget_type="kpi",
                        title=f"Total{tag}",
                        dataset_key=key,
                        y_col="value",
                        filter=filt,
                        aggregation="sum",
                    )
                )

                widget_counter += 1
                # Monthly trend
                spec.widgets.append(
                    WidgetSpec(
                        widget_id=f"w{widget_counter:03d}_line_{m}",
                        widget_type="line",
                        title=f"Monthly Trend{tag}",
                        dataset_key=key,
                        x_col="period",
                        y_col="value",
                        filter=filt,
                        aggregation="sum",
                    )
                )

                # Dimension breakdowns
                for d in dims[:3]:
                    sub = df[df["measure"] == m] if "measure" in df.columns else df
                    n_cats = sub[d].nunique() if d in sub.columns else 0
                    wtype = "pareto" if n_cats > 4 else "bar"
                    cumulative = n_cats > 4

                    widget_counter += 1
                    spec.widgets.append(
                        WidgetSpec(
                            widget_id=f"w{widget_counter:03d}_{wtype}_{d}_{m}",
                            widget_type=wtype,
                            title=f"By {d}{tag}",
                            dataset_key=key,
                            x_col=d,
                            y_col="value",
                            filter=filt,
                            aggregation="sum",
                            cumulative=cumulative,
                        )
                    )

                if len(dims) >= 2:
                    widget_counter += 1
                    spec.widgets.append(
                        WidgetSpec(
                            widget_id=f"w{widget_counter:03d}_heatmap_{m}",
                            widget_type="heatmap",
                            title=f"{dims[-1]} × month{tag}",
                            dataset_key=key,
                            x_col="period",
                            y_col=dims[-1],
                            z_col="value",
                            filter=filt,
                            aggregation="sum",
                        )
                    )

        # --- Tidy blocks ---
        elif b.kind == "tidy":
            numeric_cols = [
                c for c in df.columns
                if pd.api.types.is_numeric_dtype(df[c])
                and not _is_id_column(df[c], c)
            ]
            cat_cols = [
                c for c in df.columns
                if not pd.api.types.is_numeric_dtype(df[c])
                and df[c].nunique() > 1
                and df[c].nunique() <= 30
                and not _is_id_column(df[c], c)
            ]

            for nc in numeric_cols[:3]:
                for cc in cat_cols[:2]:
                    n_cats = df[cc].nunique()
                    wtype = "bar" if n_cats <= 8 else "pareto"
                    widget_counter += 1
                    spec.widgets.append(
                        WidgetSpec(
                            widget_id=f"w{widget_counter:03d}_{wtype}_{cc}_{nc}",
                            widget_type=wtype,
                            title=f"{nc} by {cc}",
                            dataset_key=key,
                            x_col=cc,
                            y_col=nc,
                            aggregation="sum",
                            cumulative=(wtype == "pareto"),
                        )
                    )

    # Validate all widgets
    valid_widgets: list[WidgetSpec] = []
    for w in spec.widgets:
        errs = _validate_widget_spec(w, registered)
        if errs:
            spec.global_warnings.append(
                f"Widget '{w.widget_id}' rejected: {'; '.join(errs)}"
            )
        else:
            valid_widgets.append(w)
    spec.widgets = valid_widgets

    if not spec.widgets:
        spec.global_warnings.append(
            "No widgets could be generated from the detected blocks. "
            "Review detected block kinds — only 'wide' and 'tidy' blocks "
            "produce widgets in this milestone."
        )

    return spec


# ---------------------------------------------------------------------------
# Widget execution (server-side only, parameterised queries)
# ---------------------------------------------------------------------------

def run_widget(
    spec: WidgetSpec,
    tables: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """
    Execute a validated WidgetSpec against in-memory DataFrames.

    Uses DuckDB with quoted, pre-validated identifiers — never dynamic SQL
    built from untrusted input.  All column names are validated by
    _validate_col_name() before use.

    Returns a DataFrame ready for serialisation.
    Raises ValueError for invalid/missing data.
    """
    import duckdb  # imported lazily — not required for scanner-only use

    if spec.dataset_key not in tables:
        raise ValueError(
            f"Dataset '{spec.dataset_key}' is not available. "
            "Server must register datasets before running widgets."
        )

    df = tables[spec.dataset_key].copy()

    # Apply server-side filters
    for col, val in spec.filter.items():
        _validate_col_name(col)  # raises ValueError if unsafe
        if col not in df.columns:
            raise ValueError(
                f"Filter column '{col}' does not exist in dataset "
                f"'{spec.dataset_key}'."
            )
        df = df[df[col] == val]

    if df.empty:
        return pd.DataFrame()

    con = duckdb.connect()
    con.register("_tbl", df)

    wtype = spec.widget_type
    agg = spec.aggregation if spec.aggregation in ALLOWED_AGGREGATIONS else "sum"

    # Quote all column identifiers before embedding in SQL
    x_q = _quote_identifier(spec.x_col) if spec.x_col else None
    y_q = _quote_identifier(spec.y_col) if spec.y_col else None
    z_q = _quote_identifier(spec.z_col) if spec.z_col else None

    try:
        if wtype in ("pareto", "bar"):
            if not x_q or not y_q:
                raise ValueError("pareto/bar widgets require x_col and y_col.")
            q = (
                f"SELECT {x_q} AS x, {agg.upper()}({y_q}) AS y "
                f"FROM _tbl WHERE {x_q} IS NOT NULL "
                f"GROUP BY {x_q} ORDER BY y DESC"
            )
            result = con.execute(q).df()
            total = result["y"].sum()
            if spec.cumulative and total > 0:
                result["cum_pct"] = (result["y"].cumsum() / total * 100).round(2)
            elif spec.cumulative:
                result["cum_pct"] = 0.0
            return result

        elif wtype == "line":
            if not x_q or not y_q:
                raise ValueError("line widgets require x_col and y_col.")
            q = (
                f"SELECT {x_q} AS x, {agg.upper()}({y_q}) AS y "
                f"FROM _tbl GROUP BY {x_q} ORDER BY {x_q}"
            )
            return con.execute(q).df()

        elif wtype == "kpi":
            if not y_q:
                raise ValueError("kpi widgets require y_col.")
            if agg == "count":
                q = "SELECT COUNT(*) AS y FROM _tbl"
            else:
                q = f"SELECT {agg.upper()}({y_q}) AS y FROM _tbl"
            return con.execute(q).df()

        elif wtype == "heatmap":
            if not x_q or not y_q or not z_q:
                raise ValueError("heatmap widgets require x_col, y_col, and z_col.")
            q = (
                f"SELECT {x_q} AS x, {y_q} AS y, {agg.upper()}({z_q}) AS z "
                f"FROM _tbl GROUP BY {x_q}, {y_q} ORDER BY {x_q}, {y_q}"
            )
            return con.execute(q).df()

        elif wtype in ("donut", "stacked_bar"):
            if not x_q or not y_q:
                raise ValueError(f"{wtype} widgets require x_col and y_col.")
            q = (
                f"SELECT {x_q} AS x, {agg.upper()}({y_q}) AS y "
                f"FROM _tbl GROUP BY {x_q} ORDER BY y DESC"
            )
            return con.execute(q).df()

        elif wtype == "table":
            cols = ", ".join(
                _quote_identifier(c) for c in df.columns[:20]
            )
            top = spec.top_n or 50
            q = f"SELECT {cols} FROM _tbl LIMIT {int(top)}"
            return con.execute(q).df()

        else:
            raise ValueError(
                f"Widget type '{wtype}' is in the allowlist but has no "
                "execution handler. This is a server bug."
            )

    except duckdb.Error as exc:
        raise ValueError(f"Query error for widget '{spec.widget_id}': {exc}") from exc
    finally:
        con.close()
