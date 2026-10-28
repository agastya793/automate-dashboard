/**
 * Type definitions for Milestone 2: Workbook Mapping and Normalisation UI
 */

export type ColumnRole = "date" | "category" | "measure" | "id" | "text" | "derived";
export type RowDecision = "summary" | "record" | "discard";
export type BlockKind = "tidy" | "wide" | "records" | "form" | "unknown";

export interface AmbiguousRowInfo {
  source_row: number;
  sheet_row: number;
  reason: string;
}

export interface CellColourInfo {
  row: number;
  col: number;
  rgb: string | null;
  raw_type: string;
}

export interface DetectedBlock {
  sheet: string;
  range: string;
  kind: BlockKind;
  confidence: number;
  dimensions: {
    rows: number;
    cols: number;
  };
  column_names: string[];
  column_roles: Record<string, ColumnRole>;
  sample_preview: (string | number | boolean | null)[][];
  notes: string[];
  warnings: string[];
  formula_cache_warning: boolean;
  cap_reached: boolean;
  ambiguous_row_count: number;
  ambiguous_rows: AmbiguousRowInfo[];
  cell_colours: CellColourInfo[];
  has_summary: boolean;
}

export interface WorkbookScanResponse {
  filename: string;
  sheet_names: string[];
  block_count: number;
  cap_reached: boolean;
  global_warnings: string[];
  blocks: DetectedBlock[];
}

export interface ColumnRoleMapping {
  column_name: string;
  role: ColumnRole;
  original_role?: string;
  data_type?: string;
}

export interface UnpivotConfig {
  enabled: boolean;
  id_columns: string[];
  value_columns: string[];
  variable_name: string;
  value_name: string;
  measure_name?: string;
}

export interface AmbiguousRowDecision {
  source_row: number;
  sheet_row: number;
  decision: RowDecision;
  reason?: string;
}

export interface CellColourStatusMap {
  rgb: string;
  status_label: string;
  description?: string;
}

export interface ValueMergeDecision {
  original_value: string;
  target_value: string;
  accepted: boolean;
}

export interface BlockMapping {
  block_index: number;
  sheet: string;
  range: string;
  trimmed_range?: string;
  included: boolean;
  kind: BlockKind;
  column_roles: Record<string, ColumnRole>;
  unpivot?: UnpivotConfig;
  ambiguous_row_decisions: AmbiguousRowDecision[];
  colour_mappings: CellColourStatusMap[];
  value_merges: ValueMergeDecision[];
}

export interface SourceOfTruthConfirmation {
  confirmed: boolean;
  chosen_source?: string;
  confirmed_quantity?: number;
  notes?: string;
}

export interface MappingTemplate {
  id: string;
  name: string;
  description?: string;
  version: number;
  created_at: string;
  updated_at: string;
  filename_pattern?: string;
  blocks: BlockMapping[];
  source_of_truth?: SourceOfTruthConfirmation;
  global_warnings_acknowledged: boolean;
}

export interface MappingTemplateSummary {
  id: string;
  name: string;
  version: number;
  created_at: string;
  updated_at: string;
  block_count: number;
  description?: string;
  source_of_truth_confirmed: boolean;
}

export interface NormalizedColumnMeta {
  name: string;
  role: ColumnRole;
  dtype: string;
}

export interface NormalizedTable {
  table_key: string;
  sheet: string;
  range: string;
  row_count: number;
  column_count: number;
  columns: NormalizedColumnMeta[];
  column_roles: Record<string, ColumnRole>;
  rows: (string | number | boolean | null)[][];
  summary_rows: (string | number | boolean | null)[][];
  notes: string[];
}

export interface NormalizationResponse {
  filename: string;
  template_id?: string;
  template_version?: number;
  tables: NormalizedTable[];
  warnings: string[];
  source_of_truth_status: {
    has_conflict: boolean;
    confirmed: boolean;
    chosen_source?: string;
    confirmed_quantity?: number;
  };
  ppm_ready: boolean;
  /** The exact user-approved mapping used for this preview. */
  template?: MappingTemplate;
}

// ---------------------------------------------------------------------------
// Milestone 3: Asynchronous Ingestion & DuckDB Datasets
// ---------------------------------------------------------------------------

export type ProcessingStatus = "queued" | "scanning" | "needs_mapping" | "ready" | "failed";

export interface AsyncUploadAccepted {
  upload_id: string;
  status: ProcessingStatus;
  original_filename: string;
  file_size_bytes: number;
  created_at: string;
  status_url: string;
}

export interface AsyncUploadStatus {
  upload_id: string;
  original_filename: string;
  sanitized_filename: string;
  file_size_bytes: number;
  file_type: string;
  status: ProcessingStatus;
  stage: string | null;
  progress: number;
  error_code: string | null;
  error_message: string | null;
  dataset_count: number;
  created_at: string;
  updated_at: string;
}

export interface DetectedDatasetSummary {
  dataset_id: string;
  upload_id: string;
  sheet_name: string;
  cell_range: string;
  kind: BlockKind;
  column_metadata: { name: string; role: ColumnRole }[];
  normalization_status: string;
  parquet_storage_key: string | null;
  row_count: number;
  column_count: number;
  summary_metadata: {
    confidence?: number;
    notes?: string[];
    warnings?: string[];
    formula_cache_warning?: boolean;
    ambiguous_rows?: { sheet_row: number; reason: string }[];
    sample_preview?: (string | number | boolean | null)[][];
    block_index?: number;
  };
}

// ---------------------------------------------------------------------------
// Milestone 4: Manufacturing Quality Dashboard & Apache ECharts Specifications
// ---------------------------------------------------------------------------

export interface ProvenanceDetails {
  upload_id?: string;
  sheet_name?: string;
  cell_range?: string;
  source_column?: string;
  aggregation?: string;
  calculation_applied?: string | null;
  confirmation_status?: string;
  caveats?: string[];
  joined_tables?: string[];
}

export interface ManufacturingGlobalFilters {
  period?: string | null;
  model?: string | null;
  defect?: string | null;
  action_owner?: string | null;
  action_status?: string | null;
}

export interface ManufacturingWidgetOutput {
  widget_id: string;
  widget_type:
    | "ppm_trend_target"
    | "defect_pareto"
    | "paynter_heatmap"
    | "action_tracker"
    | "model_comparison"
    | "kpi_card";
  title: string;
  data_points?: any[];
  items?: any[];
  x_categories?: string[];
  y_categories?: string[];
  matrix_data?: any[];
  max_value?: number;
  status_counts?: {
    open: number;
    closed: number;
    overdue: number;
    unknown: number;
  };
  owner_counts?: Record<string, number>;
  action_items?: any[];
  total_actions?: number;
  periods?: string[];
  models?: string[];
  series?: any[];
  target_ppm?: number;
  exceeded_count?: number;
  threshold_line?: number;
  reconciliation?: any;
  provenance?: ProvenanceDetails;
  warnings?: string[];
  error?: string;
}

export interface ManufacturingDashboardData {
  spec: {
    template_type: string;
    version: number;
    title: string;
    upload_id: string;
    source_of_truth_confirmed: boolean;
    source_of_truth_choice?: string | null;
    reconciliation: any;
    widgets: any[];
    available_filters: {
      periods: string[];
      models: string[];
      defects: string[];
      action_owners: string[];
      action_statuses: string[];
    };
    global_warnings: string[];
  };
  rendered_widgets: ManufacturingWidgetOutput[];
  available_filters: {
    periods: string[];
    models: string[];
    defects: string[];
    action_owners: string[];
    action_statuses: string[];
  };
  reconciliation: any;
  status: string;
}

