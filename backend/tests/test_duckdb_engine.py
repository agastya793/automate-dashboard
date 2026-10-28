"""
Tests for DuckDB Analytical Query Engine and Query Safety (Milestone 3).
"""

import tempfile
import uuid
from pathlib import Path

import pandas as pd
import pytest

from app.dashboard_engine.duckdb_engine import (
    QueryFilter,
    QueryPlan,
    execute_query_plan,
    quote_ident,
    validate_identifier,
)
from app.db.models import Dataset
from app.storage import LocalStorageBackend, save_dataframe_as_parquet


@pytest.fixture
def temp_storage():
    with tempfile.TemporaryDirectory() as tmp:
        yield LocalStorageBackend(root_dir=Path(tmp))


@pytest.fixture
def sample_dataset(temp_storage):
    df = pd.DataFrame(
        {
            "Month": ["Jan-26", "Jan-26", "Feb-26", "Feb-26", "Mar-26"],
            "Model": ["Sedan", "SUV", "Sedan", "SUV", "Sedan"],
            "Defect": ["Scratch", "Dent", "Scratch", "Burr", "Scratch"],
            "Count": [10, 5, 8, 3, 12],
            "PPM": [120.0, 60.0, 96.0, 36.0, 144.0],
        }
    )
    dataset_id = uuid.uuid4()
    parquet_key = f"datasets/{dataset_id}/normalized.parquet"
    save_dataframe_as_parquet(df, temp_storage, parquet_key)

    ds = Dataset(
        id=dataset_id,
        upload_id=uuid.uuid4(),
        sheet_name="Defects 2026",
        cell_range="A1:E6",
        kind="tidy",
        column_metadata=[
            {"name": "Month", "role": "date"},
            {"name": "Model", "role": "category"},
            {"name": "Defect", "role": "category"},
            {"name": "Count", "role": "measure"},
            {"name": "PPM", "role": "measure"},
        ],
        parquet_storage_key=parquet_key,
        row_count=5,
        column_count=5,
    )
    return ds


class TestQueryValidationAndSafety:

    def test_safe_identifiers_accepted(self):
        assert validate_identifier("Defect") == "Defect"
        assert validate_identifier("Count (Units)") == "Count (Units)"
        assert validate_identifier("Total %") == "Total %"

    def test_sql_injection_rejected(self):
        with pytest.raises(ValueError, match="SQL injection"):
            validate_identifier("Defect; DROP TABLE users; --")

        with pytest.raises(ValueError, match="SQL injection"):
            validate_identifier("col UNION SELECT * FROM users")

        with pytest.raises(ValueError, match="SQL injection"):
            validate_identifier("id OR 1=1")

    def test_quote_ident(self):
        assert quote_ident("Defect") == '"Defect"'
        assert quote_ident('Col"With"Quotes') == '"Col""With""Quotes"'

    def test_invalid_aggregation_rejected(self):
        with pytest.raises(ValueError, match="Unsupported aggregation"):
            QueryPlan(
                dataset_id="ds-1",
                measures=["Count"],
                aggregations={"Count": "malicious_eval"},
            )


class TestDuckDBExecution:

    def test_group_by_aggregation(self, temp_storage, sample_dataset):
        plan = QueryPlan(
            dataset_id=str(sample_dataset.id),
            dimensions=["Defect"],
            measures=["Count"],
            aggregations={"Count": "sum"},
        )

        result = execute_query_plan(plan, temp_storage, sample_dataset)
        assert result["row_count"] == 3
        rows = result["rows"]
        # Scratch: 10 + 8 + 12 = 30
        scratch_row = next(r for r in rows if r["Defect"] == "Scratch")
        assert scratch_row["Count_sum"] == 30

    def test_filter_execution(self, temp_storage, sample_dataset):
        plan = QueryPlan(
            dataset_id=str(sample_dataset.id),
            dimensions=["Model"],
            measures=["Count"],
            aggregations={"Count": "sum"},
            filters=[QueryFilter(column="Month", operator="==", value="Jan-26")],
        )

        result = execute_query_plan(plan, temp_storage, sample_dataset)
        assert result["row_count"] == 2
        rows = result["rows"]
        # Jan-26 Sedan Count: 10, SUV Count: 5
        sedan_row = next(r for r in rows if r["Model"] == "Sedan")
        assert sedan_row["Count_sum"] == 10

    def test_top_n_and_sorting(self, temp_storage, sample_dataset):
        plan = QueryPlan(
            dataset_id=str(sample_dataset.id),
            dimensions=["Defect"],
            measures=["Count"],
            aggregations={"Count": "sum"},
            top_n=2,
        )

        result = execute_query_plan(plan, temp_storage, sample_dataset)
        assert result["row_count"] == 2
        # First row should be highest Count (Scratch: 30)
        assert result["rows"][0]["Defect"] == "Scratch"

    def test_nonexistent_column_raises(self, temp_storage, sample_dataset):
        plan = QueryPlan(
            dataset_id=str(sample_dataset.id),
            dimensions=["NonexistentCol"],
        )

        with pytest.raises(ValueError, match="does not exist in dataset"):
            execute_query_plan(plan, temp_storage, sample_dataset)

    def test_json_safe_output(self, temp_storage, sample_dataset):
        plan = QueryPlan(
            dataset_id=str(sample_dataset.id),
            dimensions=["Month"],
            measures=["PPM"],
            aggregations={"PPM": "avg"},
        )

        result = execute_query_plan(plan, temp_storage, sample_dataset)
        assert "rows" in result
        # Check all values are JSON serializable
        import json
        json_str = json.dumps(result)
        assert len(json_str) > 0
