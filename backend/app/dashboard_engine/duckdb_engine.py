"""
DuckDB Analytical Query Engine for Normalized Parquet Datasets (Milestone 3)

Features:
- Parameterized execution over local Parquet files via read_parquet().
- Strict typed QueryPlan schema.
- Schema validation against authorized dataset metadata.
- Safe identifier quoting and rejection of SQL keywords / injection patterns.
- Bounded result sizes (max 5,000 rows).
- JSON-safe output conversion (NaN, Infinity, timestamps).
"""

from __future__ import annotations

import datetime as dt
import math
import re
from typing import Any, Dict, List, Literal, Optional

import duckdb
import pandas as pd
from pydantic import BaseModel, Field, field_validator

from app.db.models import Dataset
from app.storage.base import StorageBackend

# Allowed aggregations
ALLOWED_AGGREGATIONS = {"sum", "avg", "min", "max", "count"}
ALLOWED_OPERATORS = {"==", "!=", ">", "<", ">=", "<=", "in", "contains"}

# Rejects SQL injection patterns in column names
_SQL_INJECTION_PATTERN = re.compile(
    r"(--|;|/\*|\*/|xp_|0x|UNION|SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|\bOR\b|\bAND\b)",
    re.IGNORECASE,
)
_SAFE_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z0-9_\s\.\-\(\)%/\"']+$")


def validate_identifier(name: str) -> str:
    """Validate that a column identifier is safe and free of SQL injection."""
    clean = (name or "").strip()
    if not clean:
        raise ValueError("Column identifier cannot be empty.")
    if len(clean) > 256:
        raise ValueError(f"Column identifier '{clean[:30]}...' exceeds maximum length of 256.")
    if _SQL_INJECTION_PATTERN.search(clean):
        raise ValueError(f"Potential SQL injection detected in identifier: '{clean}'")
    if not _SAFE_IDENTIFIER_PATTERN.match(clean):
        raise ValueError(f"Invalid characters in identifier: '{clean}'")
    return clean


def quote_ident(name: str) -> str:
    """Safely quote a SQL identifier using standard double quotes."""
    validated = validate_identifier(name)
    escaped = validated.replace('"', '""')
    return f'"{escaped}"'


class QueryFilter(BaseModel):
    column: str
    operator: str = "=="
    value: Any

    @field_validator("column")
    @classmethod
    def check_column(cls, v: str) -> str:
        return validate_identifier(v)

    @field_validator("operator")
    @classmethod
    def check_operator(cls, v: str) -> str:
        clean = (v or "").strip().lower()
        if clean not in ALLOWED_OPERATORS:
            raise ValueError(f"Invalid operator '{v}'. Allowed: {sorted(ALLOWED_OPERATORS)}")
        return clean


class QueryPlan(BaseModel):
    dataset_id: str
    dimensions: List[str] = Field(default_factory=list)
    measures: List[str] = Field(default_factory=list)
    aggregations: Dict[str, str] = Field(default_factory=dict)  # measure -> agg (sum, avg, min, max, count)
    filters: List[QueryFilter] = Field(default_factory=list)
    sort_by: Optional[str] = None
    sort_desc: bool = False
    top_n: Optional[int] = None
    limit: int = Field(default=500, ge=1, le=5000)

    @field_validator("dimensions", "measures")
    @classmethod
    def validate_cols(cls, cols: List[str]) -> List[str]:
        return [validate_identifier(c) for c in cols]

    @field_validator("aggregations")
    @classmethod
    def validate_aggs(cls, aggs: Dict[str, str]) -> Dict[str, str]:
        for m, a in aggs.items():
            validate_identifier(m)
            clean_a = (a or "").strip().lower()
            if clean_a not in ALLOWED_AGGREGATIONS:
                raise ValueError(f"Unsupported aggregation '{a}' for measure '{m}'.")
        return aggs


def execute_query_plan(
    plan: QueryPlan,
    storage: StorageBackend,
    dataset: Dataset,
) -> Dict[str, Any]:
    """
    Executes a validated QueryPlan against a dataset's Parquet file using DuckDB.
    Returns JSON-safe results.
    """
    if not dataset.parquet_storage_key:
        raise ValueError(f"Dataset '{dataset.id}' has not been normalized to Parquet.")

    # 1. Resolve local Parquet path securely via storage abstraction
    parquet_path = storage.get_local_path(dataset.parquet_storage_key)
    path_str = str(parquet_path.resolve())

    # 2. Extract allowed columns from dataset metadata
    allowed_columns = {c["name"] for c in dataset.column_metadata if isinstance(c, dict) and "name" in c}
    if not allowed_columns and dataset.column_count > 0:
        # Fallback to inspecting Parquet file directly
        try:
            inspect_con = duckdb.connect(":memory:")
            cols = inspect_con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [path_str]).fetchall()
            allowed_columns = {row[0] for row in cols}
            inspect_con.close()
        except Exception:
            pass

    # 3. Validate requested dimensions and measures exist in dataset
    for dim in plan.dimensions:
        if allowed_columns and dim not in allowed_columns:
            raise ValueError(f"Dimension '{dim}' does not exist in dataset '{dataset.id}'.")

    for m in plan.measures:
        if allowed_columns and m not in allowed_columns:
            raise ValueError(f"Measure '{m}' does not exist in dataset '{dataset.id}'.")

    for f in plan.filters:
        if allowed_columns and f.column not in allowed_columns:
            raise ValueError(f"Filter column '{f.column}' does not exist in dataset '{dataset.id}'.")

    if plan.sort_by and allowed_columns and plan.sort_by not in allowed_columns:
        raise ValueError(f"Sort column '{plan.sort_by}' does not exist in dataset '{dataset.id}'.")

    # 4. Construct SQL statement safely
    select_items = []
    for dim in plan.dimensions:
        select_items.append(f"{quote_ident(dim)} AS {quote_ident(dim)}")

    for m in plan.measures:
        agg = plan.aggregations.get(m, "sum").upper()
        if agg == "AVG":
            agg = "AVG"
        alias = f"{m}_{agg.lower()}" if plan.dimensions else m
        select_items.append(f"{agg}({quote_ident(m)}) AS {quote_ident(alias)}")

    if not select_items:
        # Default select all with limit
        select_items = ["*"]

    # WHERE clause with parameterized literals
    where_clauses = []
    params: List[Any] = [path_str]

    for f in plan.filters:
        col_q = quote_ident(f.column)
        if f.operator == "==":
            where_clauses.append(f"{col_q} = ?")
            params.append(f.value)
        elif f.operator == "!=":
            where_clauses.append(f"{col_q} != ?")
            params.append(f.value)
        elif f.operator in (">", "<", ">=", "<="):
            where_clauses.append(f"{col_q} {f.operator} ?")
            params.append(f.value)
        elif f.operator == "contains":
            where_clauses.append(f"CAST({col_q} AS VARCHAR) ILIKE ?")
            params.append(f"%{f.value}%")
        elif f.operator == "in" and isinstance(f.value, (list, tuple)):
            placeholders = ", ".join(["?"] * len(f.value))
            where_clauses.append(f"{col_q} IN ({placeholders})")
            params.extend(f.value)

    sql = f"SELECT {', '.join(select_items)} FROM read_parquet(?)"

    if where_clauses:
        sql += f" WHERE {' AND '.join(where_clauses)}"

    if plan.dimensions and plan.measures:
        group_cols = [quote_ident(d) for d in plan.dimensions]
        sql += f" GROUP BY {', '.join(group_cols)}"

    if plan.sort_by:
        sort_col = plan.sort_by
        if plan.dimensions and plan.measures and sort_col in plan.measures:
            agg = plan.aggregations.get(sort_col, "sum").lower()
            sort_col = f"{sort_col}_{agg}"
        direction = "DESC" if plan.sort_desc else "ASC"
        sql += f" ORDER BY {quote_ident(sort_col)} {direction}"
    elif plan.dimensions and plan.measures:
        # Default order by first measure descending
        first_m = plan.measures[0]
        agg = plan.aggregations.get(first_m, "sum").lower()
        alias = f"{first_m}_{agg}"
        sql += f" ORDER BY {quote_ident(alias)} DESC"

    # Enforce limit and top_n
    effective_limit = min(plan.limit, plan.top_n if plan.top_n else plan.limit)
    sql += f" LIMIT {effective_limit}"

    # 5. Execute query with DuckDB
    con = duckdb.connect(":memory:")
    try:
        cursor = con.execute(sql, params)
        raw_rows = cursor.fetchall()
        col_names = [desc[0] for desc in cursor.description]
    finally:
        con.close()

    # 6. Convert to JSON-safe data structures
    clean_rows: List[Dict[str, Any]] = []
    for r in raw_rows:
        row_dict = {}
        for col_name, val in zip(col_names, r):
            if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
                row_dict[col_name] = None
            elif isinstance(val, (dt.date, dt.datetime)):
                row_dict[col_name] = val.isoformat()
            elif isinstance(val, float) and val.is_integer():
                row_dict[col_name] = int(val)
            else:
                row_dict[col_name] = val
        clean_rows.append(row_dict)

    return {
        "dataset_id": str(dataset.id),
        "row_count": len(clean_rows),
        "columns": col_names,
        "rows": clean_rows,
        "sql_summary": f"Executed on Parquet dataset with {len(clean_rows)} returned rows",
    }
