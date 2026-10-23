# Test Fixtures / Sample Datasets

This directory contains verified sample datasets used as test fixtures for the Phase 2 dataset upload, parsing, and profiling pipeline:

1. `clean_sales.csv`:
   - Clean UTF-8 CSV dataset with 5 transactions across 8 columns.
   - Tests diverse column type inferences: identifier (`transaction_id`), date (`order_date`), categorical (`customer_name`, `category`), numeric (`units`), currency (`revenue`), percentage (`margin_pct`), and boolean (`is_fulfilled`).

2. `multi_sheet_enterprise.xlsx`:
   - Multi-sheet Excel workbook with 3 distinct worksheets: `Sales_Transactions`, `Regional_Targets`, and `Product_Catalog`.
   - Tests worksheet discovery, default sheet selection, and sheet switching.

3. `dirty_dataset.csv`:
   - Dirty CSV dataset with intentional data quality issues:
     - 1 duplicate row (`ORD-001`)
     - 1 entirely empty column (`empty_notes`, 100% missing values)
     - High null percentages in `customer`, `amount`, and `priority`
     - Identifier code column (`order_id`)
   - Tests data-quality warning generation and summary metrics.

These files are retained in the repository as reproducible test fixtures. General user uploads and runtime spreadsheet artifacts remain excluded via `.gitignore`.
