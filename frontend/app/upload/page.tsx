"use client";

import { useState, useRef, DragEvent, ChangeEvent, useCallback, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useDashboard } from "@/context/DashboardContext";
import {
  UploadCloud,
  FileSpreadsheet,
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Trash2,
  TableProperties,
  ArrowRight,
  Info,
  Calendar,
  Hash,
  DollarSign,
  Percent,
  Tag,
  FileText,
  Binary,
  Layers,
  RotateCw,
  Search,
} from "lucide-react";
import { Header } from "@/components/Header";
import { RecommendedCharts, ChartRecommendation } from "@/components/RecommendedCharts";
import { formatBytes } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Types matching backend Phase 2 contract
// ---------------------------------------------------------------------------

export interface ColumnProfile {
  name: string;
  inferred_type: string;
  missing_count: number;
  missing_pct: number;
  missing_percentage?: number;
  unique_count: number;
  sample_values?: (string | number | boolean | null)[];
}

export interface DatasetPreviewResponse {
  filename: string;
  file_name?: string;
  file_type: string;
  file_size_bytes?: number;
  sheet_names: string[];
  available_worksheets?: string[];
  selected_sheet: string | null;
  selected_worksheet?: string | null;
  row_count: number;
  total_rows?: number;
  column_count: number;
  total_columns?: number;
  column_names: string[];
  columns: ColumnProfile[];
  duplicate_row_count: number;
  total_missing_cells: number;
  preview_rows: (string | number | boolean | null)[][];
  warnings: string[];
  chart_recommendations?: ChartRecommendation[];
}

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

// Max upload limit configuration (aligned with backend default: 10 MB = 10,485,760 bytes)
const MAX_UPLOAD_BYTES =
  Number(process.env.NEXT_PUBLIC_MAX_UPLOAD_BYTES) || 10 * 1024 * 1024;
const MAX_UPLOAD_MB = Math.round(MAX_UPLOAD_BYTES / (1024 * 1024));

// ---------------------------------------------------------------------------
// Helper: Inferred type badge
// ---------------------------------------------------------------------------

function TypeBadge({ type }: { type: string }) {
  const normalized = type.toLowerCase();

  switch (normalized) {
    case "date":
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-blue-50 text-blue-700 border border-blue-200">
          <Calendar className="w-3 h-3 text-blue-500" />
          <span>Date</span>
        </span>
      );
    case "numeric":
    case "number":
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
          <Hash className="w-3 h-3 text-emerald-500" />
          <span>Numeric</span>
        </span>
      );
    case "currency":
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-teal-50 text-teal-700 border border-teal-200">
          <DollarSign className="w-3 h-3 text-teal-500" />
          <span>Currency</span>
        </span>
      );
    case "percentage":
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-purple-50 text-purple-700 border border-purple-200">
          <Percent className="w-3 h-3 text-purple-500" />
          <span>Percentage</span>
        </span>
      );
    case "categorical":
    case "category":
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
          <Tag className="w-3 h-3 text-amber-500" />
          <span>Category</span>
        </span>
      );
    case "identifier":
    case "id":
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
          <Binary className="w-3 h-3 text-indigo-500" />
          <span>Identifier</span>
        </span>
      );
    case "boolean":
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-cyan-50 text-cyan-700 border border-cyan-200">
          <CheckCircle2 className="w-3 h-3 text-cyan-500" />
          <span>Boolean</span>
        </span>
      );
    case "text":
    default:
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-100 text-slate-700 border border-slate-200">
          <FileText className="w-3 h-3 text-slate-500" />
          <span>Text</span>
        </span>
      );
  }
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export default function UploadPage() {
  const router = useRouter();
  const {
    file: contextFile,
    sheetName: contextSheet,
    setSessionData,
    configuredCharts,
    setConfiguredCharts,
    generateDashboard,
    isGenerating,
    error: dashboardError,
    clearSession,
  } = useDashboard();

  const [selectedFile, setSelectedFile] = useState<File | null>(() => contextFile);
  const [isDragging, setIsDragging] = useState(false);
  const [clientError, setClientError] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [localGenError, setLocalGenError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSwitchingSheet, setIsSwitchingSheet] = useState(false);
  const [previewData, setPreviewData] = useState<DatasetPreviewResponse | null>(null);
  const [activeSheet, setActiveSheet] = useState<string | null>(() => contextSheet);
  const [columnFilter, setColumnFilter] = useState("");

  const fileInputRef = useRef<HTMLInputElement>(null);

  // -------------------------------------------------------------------------
  // Upload and parse handler
  // -------------------------------------------------------------------------
  const executePreview = useCallback(
    async (file: File, sheetName?: string | null) => {
      setServerError(null);
      if (sheetName) {
        setIsSwitchingSheet(true);
      } else {
        setIsLoading(true);
      }

      try {
        const formData = new FormData();
        formData.append("file", file);
        if (sheetName) {
          formData.append("sheet_name", sheetName);
        }

        const res = await fetch(`${API_BASE_URL}/api/datasets/preview`, {
          method: "POST",
          body: formData,
        });

        if (!res.ok) {
          let errorMsg = `Server returned status ${res.status}`;
          try {
            const errJson = await res.json();
            if (errJson?.detail) {
              errorMsg = errJson.detail;
            }
          } catch {
            // Keep default status message if body is not JSON
          }
          setServerError(errorMsg);
          return;
        }

        const data: DatasetPreviewResponse = await res.json();
        setPreviewData(data);
        const resolvedSheet = data.selected_sheet || (data.sheet_names.length > 0 ? data.sheet_names[0] : null);
        setActiveSheet(resolvedSheet);
        setSessionData(file, resolvedSheet);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : String(err);
        if (message.includes("Failed to fetch") || message.includes("NetworkError")) {
          setServerError(
            `Backend service is offline. Could not reach FastAPI at ${API_BASE_URL}. Please ensure the backend server is running.`
          );
        } else {
          setServerError(`Error processing dataset: ${message}`);
        }
      } finally {
        setIsLoading(false);
        setIsSwitchingSheet(false);
      }
    },
    [setSessionData]
  );

  const validateAndSetFile = (file: File) => {
    setClientError(null);
    setServerError(null);
    setPreviewData(null);
    setActiveSheet(null);

    const validExtensions = [".xlsx", ".xls", ".csv"];
    const extension = "." + file.name.split(".").pop()?.toLowerCase();

    if (!validExtensions.includes(extension)) {
      setClientError(
        "Unsupported file format. Please upload an Excel (.xlsx) or CSV (.csv) file."
      );
      return;
    }

    if (file.size > MAX_UPLOAD_BYTES) {
      setClientError(
        `File is too large (${formatBytes(file.size)}). Maximum supported file size is ${MAX_UPLOAD_MB} MB.`
      );
      return;
    }

    setSelectedFile(file);
    executePreview(file, null);
  };

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      validateAndSetFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      validateAndSetFile(e.target.files[0]);
    }
  };

  const handleRemoveFile = () => {
    setSelectedFile(null);
    setClientError(null);
    setServerError(null);
    setLocalGenError(null);
    setPreviewData(null);
    setActiveSheet(null);
    clearSession();
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleSelectSheet = (sheet: string) => {
    if (!selectedFile || sheet === activeSheet || isSwitchingSheet || isLoading) return;
    setSessionData(selectedFile, sheet);
    executePreview(selectedFile, sheet);
  };

  // Restore preview when navigating back from dashboard
  useEffect(() => {
    let cancelled = false;
    if (contextFile && !previewData && !isLoading) {
      const restorePreview = async () => {
        try {
          const formData = new FormData();
          formData.append("file", contextFile);
          if (contextSheet) {
            formData.append("sheet_name", contextSheet);
          }
          const res = await fetch(`${API_BASE_URL}/api/datasets/preview`, {
            method: "POST",
            body: formData,
          });
          if (res.ok && !cancelled) {
            const data: DatasetPreviewResponse = await res.json();
            if (!cancelled) {
              setPreviewData(data);
            }
          }
        } catch {
          // Ignore cancellation or offline errors on restore
        }
      };
      restorePreview();
    }
    return () => {
      cancelled = true;
    };
  }, [contextFile, contextSheet, previewData, isLoading]);

  // Chart configuration selection count
  const activeConfigured = configuredCharts.filter((c) => !c.dismissed);
  const selectedCharts = activeConfigured.filter((c) => c.selected);
  const confirmedCount = selectedCharts.filter((c) => c.isConfirmed).length;

  const handleGenerateDashboardClick = async () => {
    if (!selectedFile) return;

    if (selectedCharts.length === 0) {
      setLocalGenError("Please select at least one chart recommendation before generating the dashboard.");
      return;
    }

    // Auto-confirm remaining selected charts if user didn't individually confirm each
    const hasUnconfirmed = selectedCharts.some((c) => !c.isConfirmed);
    if (hasUnconfirmed) {
      const updated = configuredCharts.map((c) =>
        c.selected && !c.dismissed ? { ...c, isConfirmed: true } : c
      );
      setConfiguredCharts(updated);
    }

    setLocalGenError(null);
    const result = await generateDashboard();
    if (result) {
      router.push("/dashboard");
    }
  };

  // Filter columns in schema view
  const filteredColumns = previewData?.columns.filter((col) =>
    col.name.toLowerCase().includes(columnFilter.toLowerCase())
  );

  return (
    <div className="flex flex-col min-h-full">
      <Header
        title="Upload Dataset"
        description="Select an Excel (.xlsx) or CSV file from your local machine. The server will parse structure, profile column types, and calculate data quality metrics in real-time."
      />

      <div className="p-6 sm:p-8 space-y-8 max-w-6xl">
        {/* ================================================================= */}
        {/* STEP 1: Select / Drop Dataset                                     */}
        {/* ================================================================= */}
        <section
          aria-labelledby="upload-section-heading"
          className="bg-white rounded-xl border border-slate-200 p-6 sm:p-8 shadow-sm"
        >
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2
                id="upload-section-heading"
                className="text-base font-semibold text-slate-900 tracking-tight"
              >
                Step 1: Select or Drop Dataset
              </h2>
              <p className="text-xs text-slate-500 mt-1">
                Upload your raw transaction list, sales ledger, or operational metrics table.
              </p>
            </div>
            {selectedFile && (
              <button
                type="button"
                onClick={handleRemoveFile}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-rose-600 bg-rose-50 hover:bg-rose-100 rounded-lg transition-colors border border-rose-200"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>Clear Dataset</span>
              </button>
            )}
          </div>

          {/* Hidden native input */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.xls,.csv"
            className="hidden"
            onChange={handleFileChange}
            id="dataset-file-input"
          />

          {!selectedFile ? (
            /* Drag & Drop Zone */
            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-xl p-8 sm:p-12 text-center cursor-pointer transition-all flex flex-col items-center justify-center ${
                isDragging
                  ? "border-brand-500 bg-brand-50/50"
                  : "border-slate-300 hover:border-slate-400 bg-slate-50/50 hover:bg-slate-50"
              }`}
            >
              <div className="w-12 h-12 rounded-xl bg-white border border-slate-200 shadow-sm flex items-center justify-center text-brand-600 mb-4">
                <UploadCloud className="w-6 h-6" />
              </div>

              <div className="space-y-1 mb-3">
                <p className="text-sm font-semibold text-slate-900">
                  <span className="text-brand-600 underline underline-offset-2">Click to browse</span> or drag and drop
                </p>
                <p className="text-xs text-slate-500">
                  Supported formats: Microsoft Excel (.xlsx) or Comma-Separated Values (.csv)
                </p>
              </div>

              <div className="flex items-center gap-2 mt-2">
                <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-200/70 text-slate-700">
                  .XLSX
                </span>
                <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-200/70 text-slate-700">
                  .CSV
                </span>
                <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-200/70 text-slate-700">
                  Up to {MAX_UPLOAD_MB}MB
                </span>
              </div>
            </div>
          ) : (
            /* Selected File Card */
            <div className="border border-slate-200 rounded-xl p-5 bg-slate-50/80 space-y-4">
              <div className="flex items-center justify-between gap-4">
                <div className="flex items-center gap-3.5 min-w-0">
                  <div className="w-11 h-11 rounded-lg bg-emerald-100 text-emerald-800 flex items-center justify-center flex-shrink-0">
                    <FileSpreadsheet className="w-6 h-6" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-slate-900 truncate">
                      {selectedFile.name}
                    </p>
                    <p className="text-xs text-slate-500 mt-0.5">
                      {formatBytes(selectedFile.size)} • {selectedFile.name.endsWith(".csv") ? "CSV Dataset" : "Excel Workbook"}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="px-3 py-1.5 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 rounded-lg border border-slate-300 transition-colors shadow-sm"
                  >
                    Change File
                  </button>
                  <button
                    type="button"
                    onClick={() => executePreview(selectedFile, activeSheet)}
                    disabled={isLoading || isSwitchingSheet}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-brand-700 bg-brand-50 hover:bg-brand-100 rounded-lg border border-brand-200 transition-colors"
                    title="Reprocess file"
                  >
                    <RotateCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
                    <span>Reprocess</span>
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Client-side Validation Error */}
          {clientError && (
            <div className="mt-4 flex items-start gap-2.5 p-3.5 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs">
              <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold">Invalid File Selection</p>
                <p className="mt-0.5">{clientError}</p>
              </div>
            </div>
          )}

          {/* Server-side / Network Error */}
          {serverError && (
            <div className="mt-4 flex items-start gap-2.5 p-3.5 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs">
              <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5 text-rose-600" />
              <div className="flex-1">
                <p className="font-semibold">Processing Failed</p>
                <p className="mt-0.5 leading-relaxed">{serverError}</p>
                <div className="mt-2.5 flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => selectedFile && executePreview(selectedFile, activeSheet)}
                    className="px-2.5 py-1 text-xs font-semibold bg-rose-100 hover:bg-rose-200 text-rose-900 rounded transition-colors"
                  >
                    Try Again
                  </button>
                  <button
                    type="button"
                    onClick={handleRemoveFile}
                    className="px-2.5 py-1 text-xs font-medium text-slate-600 hover:text-slate-800 underline underline-offset-2"
                  >
                    Choose another file
                  </button>
                </div>
              </div>
            </div>
          )}
        </section>

        {/* ================================================================= */}
        {/* Loading State Skeleton                                            */}
        {/* ================================================================= */}
        {isLoading && (
          <div className="bg-white rounded-xl border border-slate-200 p-8 shadow-sm flex flex-col items-center justify-center space-y-4 text-center">
            <div className="w-12 h-12 rounded-full border-4 border-brand-100 border-t-brand-600 animate-spin" />
            <div className="space-y-1">
              <h3 className="text-sm font-semibold text-slate-900">
                Profiling Dataset Structure...
              </h3>
              <p className="text-xs text-slate-500 max-w-sm">
                Inspecting columns, inferring data types (dates, currencies, numbers), and analyzing data quality statistics.
              </p>
            </div>
          </div>
        )}

        {/* ================================================================= */}
        {/* Loaded Dataset Section (Steps 2, 3, 4)                            */}
        {/* ================================================================= */}
        {previewData && !isLoading && (
          <div className="space-y-8 animate-in fade-in duration-300">
            {/* ------------------------------------------------------------- */}
            {/* STEP 2: Worksheet Selector (Excel multi-sheet only)            */}
            {/* ------------------------------------------------------------- */}
            {previewData.sheet_names && previewData.sheet_names.length > 1 && (
              <section
                aria-labelledby="sheets-heading"
                className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <Layers className="w-4 h-4 text-brand-600" />
                    <h2
                      id="sheets-heading"
                      className="text-sm font-semibold text-slate-900 tracking-tight"
                    >
                      Workbook Worksheets ({previewData.sheet_names.length})
                    </h2>
                  </div>
                  <span className="text-xs text-slate-500">
                    Click a tab to switch worksheets and re-profile data
                  </span>
                </div>

                <div className="flex items-center gap-2 mt-4 flex-wrap">
                  {previewData.sheet_names.map((sheet) => {
                    const isActive = sheet === (previewData.selected_sheet || activeSheet);
                    return (
                      <button
                        key={sheet}
                        type="button"
                        onClick={() => handleSelectSheet(sheet)}
                        disabled={isSwitchingSheet}
                        className={`px-3.5 py-1.5 text-xs font-semibold rounded-lg transition-all border flex items-center gap-1.5 ${
                          isActive
                            ? "bg-brand-600 text-white border-brand-600 shadow-sm"
                            : "bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100 hover:border-slate-300"
                        } ${isSwitchingSheet ? "opacity-60 cursor-not-allowed" : ""}`}
                      >
                        <FileSpreadsheet className={`w-3.5 h-3.5 ${isActive ? "text-white" : "text-slate-400"}`} />
                        <span>{sheet}</span>
                        {isActive && isSwitchingSheet && (
                          <RotateCw className="w-3 h-3 animate-spin text-white ml-1" />
                        )}
                      </button>
                    );
                  })}
                </div>
              </section>
            )}

            {/* ------------------------------------------------------------- */}
            {/* STEP 3: Quality Summary Metrics Cards                         */}
            {/* ------------------------------------------------------------- */}
            <section aria-labelledby="quality-heading" className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2
                    id="quality-heading"
                    className="text-base font-semibold text-slate-900 tracking-tight"
                  >
                    Step 2: Data Quality & Profiling Summary
                  </h2>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Structure and integrity breakdown for sheet:{" "}
                    <span className="font-semibold text-slate-800">
                      {previewData.selected_sheet || previewData.filename}
                    </span>
                  </p>
                </div>

                <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-800 border border-emerald-200">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                  <span>Validation Passed</span>
                </div>
              </div>

              {/* 4 Metrics Cards */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                {/* Total Rows */}
                <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-1">
                  <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
                    Total Rows
                  </p>
                  <p className="text-2xl font-bold text-slate-900 tracking-tight">
                    {previewData.row_count.toLocaleString()}
                  </p>
                  <p className="text-[11px] text-slate-500">
                    Data records parsed in-memory
                  </p>
                </div>

                {/* Total Columns */}
                <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-1">
                  <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
                    Total Columns
                  </p>
                  <p className="text-2xl font-bold text-slate-900 tracking-tight">
                    {previewData.column_count}
                  </p>
                  <p className="text-[11px] text-slate-500">
                    Attributes profiled and typed
                  </p>
                </div>

                {/* Duplicate Rows */}
                <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-1">
                  <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
                    Duplicate Rows
                  </p>
                  <div className="flex items-center gap-2">
                    <p className={`text-2xl font-bold tracking-tight ${
                      previewData.duplicate_row_count > 0 ? "text-amber-600" : "text-slate-900"
                    }`}>
                      {previewData.duplicate_row_count}
                    </p>
                    {previewData.duplicate_row_count > 0 ? (
                      <span className="px-1.5 py-0.5 text-[10px] font-bold rounded bg-amber-100 text-amber-800">
                        Warning
                      </span>
                    ) : (
                      <span className="px-1.5 py-0.5 text-[10px] font-bold rounded bg-emerald-100 text-emerald-800">
                        Clean
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-500">
                    {previewData.duplicate_row_count > 0
                      ? "May affect aggregations"
                      : "No duplicate records found"}
                  </p>
                </div>

                {/* Missing Cells */}
                <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-1">
                  <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
                    Missing Cells
                  </p>
                  <div className="flex items-center gap-2">
                    <p className={`text-2xl font-bold tracking-tight ${
                      previewData.total_missing_cells > 0 ? "text-slate-900" : "text-emerald-700"
                    }`}>
                      {previewData.total_missing_cells.toLocaleString()}
                    </p>
                    {previewData.row_count > 0 && previewData.column_count > 0 && (
                      <span className="text-xs font-semibold text-slate-500">
                        (
                        {(
                          (previewData.total_missing_cells /
                            (previewData.row_count * previewData.column_count)) *
                          100
                        ).toFixed(1)}
                        %)
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-500">
                    Null or blank cell count
                  </p>
                </div>
              </div>

              {/* Data Quality Warnings Banner */}
              {previewData.warnings && previewData.warnings.length > 0 ? (
                <div className="bg-amber-50/80 border border-amber-200 rounded-xl p-4 sm:p-5 text-amber-900 space-y-2.5">
                  <div className="flex items-center gap-2 text-amber-800">
                    <AlertTriangle className="w-4 h-4 flex-shrink-0 text-amber-600" />
                    <h3 className="text-xs font-bold uppercase tracking-wider">
                      Detected Data Integrity Warnings ({previewData.warnings.length})
                    </h3>
                  </div>
                  <ul className="space-y-1.5 pl-6 list-disc text-xs text-amber-900/90 leading-relaxed">
                    {previewData.warnings.map((warning, idx) => (
                      <li key={idx}>{warning}</li>
                    ))}
                  </ul>
                </div>
              ) : (
                <div className="bg-emerald-50/70 border border-emerald-200 rounded-xl p-4 text-emerald-900 flex items-center gap-3 text-xs">
                  <CheckCircle2 className="w-4 h-4 flex-shrink-0 text-emerald-600" />
                  <span>
                    <strong className="font-semibold">Excellent Data Quality:</strong> No high missing-value ratios, empty columns, or duplicate rows detected.
                  </span>
                </div>
              )}
            </section>

            {/* ------------------------------------------------------------- */}
            {/* STEP 4: Column Schema & Type Inspection                       */}
            {/* ------------------------------------------------------------- */}
            <section
              aria-labelledby="schema-heading"
              className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4"
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <h2
                    id="schema-heading"
                    className="text-base font-semibold text-slate-900 tracking-tight"
                  >
                    Step 3: Inferred Column Schema & Health
                  </h2>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Deterministic type classification with sample values and missingness ratios.
                  </p>
                </div>

                {/* Filter Input */}
                {previewData.columns.length > 6 && (
                  <div className="relative w-full sm:w-64">
                    <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
                    <input
                      type="text"
                      placeholder="Filter column names..."
                      value={columnFilter}
                      onChange={(e) => setColumnFilter(e.target.value)}
                      className="w-full pl-8 pr-3 py-1.5 text-xs rounded-lg border border-slate-200 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500"
                    />
                  </div>
                )}
              </div>

              {/* Columns Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 pt-1">
                {(filteredColumns || previewData.columns).map((col) => {
                  const hasMissing = col.missing_count > 0;
                  const isHighMissing = col.missing_pct >= 30;

                  return (
                    <div
                      key={col.name}
                      className="p-3.5 rounded-lg border border-slate-200 bg-slate-50/50 hover:bg-slate-50 hover:border-slate-300 transition-colors space-y-2.5"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p
                            className="text-xs font-bold text-slate-900 truncate"
                            title={col.name}
                          >
                            {col.name}
                          </p>
                          <p className="text-[11px] text-slate-500 mt-0.5">
                            {col.unique_count.toLocaleString()} unique values
                          </p>
                        </div>
                        <TypeBadge type={col.inferred_type} />
                      </div>

                      {/* Missing rate bar */}
                      <div className="space-y-1">
                        <div className="flex items-center justify-between text-[11px]">
                          <span className="text-slate-500">Missing Rate</span>
                          <span
                            className={`font-semibold ${
                              isHighMissing
                                ? "text-rose-600"
                                : hasMissing
                                ? "text-amber-600"
                                : "text-emerald-700"
                            }`}
                          >
                            {col.missing_pct}% ({col.missing_count})
                          </span>
                        </div>
                        <div className="w-full h-1.5 rounded-full bg-slate-200 overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              isHighMissing
                                ? "bg-rose-500"
                                : hasMissing
                                ? "bg-amber-400"
                                : "bg-emerald-500"
                            }`}
                            style={{ width: `${Math.min(col.missing_pct, 100)}%` }}
                          />
                        </div>
                      </div>

                      {/* Sample Values Chips */}
                      {col.sample_values && col.sample_values.length > 0 && (
                        <div className="pt-1 border-t border-slate-200/80">
                          <p className="text-[10px] uppercase font-semibold text-slate-600 mb-1">
                            Sample values:
                          </p>
                          <div className="flex flex-wrap gap-1">
                            {col.sample_values.map((val, idx) => (
                              <span
                                key={idx}
                                className="inline-block px-1.5 py-0.5 rounded bg-white border border-slate-200 text-slate-700 text-[10px] font-mono truncate max-w-[140px]"
                                title={String(val)}
                              >
                                {String(val)}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </section>

            {/* ------------------------------------------------------------- */}
            {/* STEP 5: Data Preview Table (First 20 rows)                    */}
            {/* ------------------------------------------------------------- */}
            <section
              aria-labelledby="preview-heading"
              className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden"
            >
              <div className="p-6 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <TableProperties className="w-4 h-4 text-brand-600" />
                    <h2
                      id="preview-heading"
                      className="text-base font-semibold text-slate-900 tracking-tight"
                    >
                      Step 4: Raw Data Preview
                    </h2>
                  </div>
                  <p className="text-xs text-slate-500 mt-1">
                    Displaying first {previewData.preview_rows.length} rows of{" "}
                    {previewData.row_count.toLocaleString()} total rows across {previewData.column_count} columns.
                  </p>
                </div>

                <div className="text-xs text-slate-500 bg-slate-100 px-3 py-1.5 rounded-lg border border-slate-200 self-start sm:self-auto font-medium">
                  Read-Only Inspection Mode
                </div>
              </div>

              {/* Table with horizontal scroll */}
              <div className="overflow-x-auto max-h-[500px]">
                <table className="w-full text-left border-collapse text-xs">
                  <thead className="bg-slate-50/90 sticky top-0 z-10 border-b border-slate-200 backdrop-blur-sm">
                    <tr>
                      <th className="py-3 px-3.5 font-bold text-slate-600 w-12 text-center border-r border-slate-200">
                        #
                      </th>
                      {previewData.columns.map((col) => (
                        <th
                          key={col.name}
                          className="py-3 px-4 font-semibold text-slate-800 whitespace-nowrap min-w-[140px]"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="truncate max-w-[180px]" title={col.name}>
                              {col.name}
                            </span>
                            <TypeBadge type={col.inferred_type} />
                          </div>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {previewData.preview_rows.map((row, rowIdx) => (
                      <tr
                        key={rowIdx}
                        className="hover:bg-slate-50/70 transition-colors"
                      >
                        <td className="py-2.5 px-3.5 text-center font-mono text-[11px] text-slate-600 border-r border-slate-100 bg-slate-50/30">
                          {rowIdx + 1}
                        </td>
                        {row.map((val, cellIdx) => {
                          const isNull = val === null || val === undefined || val === "";
                          return (
                            <td
                              key={cellIdx}
                              className="py-2.5 px-4 text-slate-700 whitespace-nowrap max-w-xs truncate"
                              title={isNull ? "null" : String(val)}
                            >
                              {isNull ? (
                                <span className="text-slate-400 italic text-[11px] font-mono">
                                  null
                                </span>
                              ) : (
                                <span className="text-slate-800 font-sans">
                                  {String(val)}
                                </span>
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="p-4 bg-slate-50 border-t border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs text-slate-500">
                <span>
                  Showing {previewData.preview_rows.length} rows preview. All data processed in-memory.
                </span>
                <span className="text-[11px] text-slate-600">
                  Data validation, profiling & schema discovery complete.
                </span>
              </div>
            </section>

            {/* ------------------------------------------------------------- */}
            {/* STEP 5: Automatic Chart Recommendations                       */}
            {/* ------------------------------------------------------------- */}
            <RecommendedCharts
              recommendations={previewData.chart_recommendations || []}
              columns={previewData.columns}
              initialCharts={configuredCharts.length > 0 ? configuredCharts : undefined}
              onChartsChange={setConfiguredCharts}
            />

            {/* ------------------------------------------------------------- */}
            {/* STEP 6: Interactive Dashboard Action Bar                      */}
            {/* ------------------------------------------------------------- */}
            <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-brand-800 bg-brand-100 px-2 py-0.5 rounded">
                    Step 6
                  </span>
                  <span className="text-xs font-semibold text-slate-800">
                    Ready to Generate Interactive Dashboard
                  </span>
                </div>
                <p className="text-xs text-slate-600 max-w-xl leading-relaxed">
                  {selectedCharts.length} chart{selectedCharts.length === 1 ? "" : "s"} selected ({confirmedCount} explicitly confirmed). The backend will compute real aggregations, distributions, and category series across your complete {previewData.row_count.toLocaleString()}-row dataset.
                </p>
                {(localGenError || dashboardError) && (
                  <p className="text-xs text-rose-600 font-semibold flex items-center gap-1.5 mt-1">
                    <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
                    <span>{localGenError || dashboardError}</span>
                  </p>
                )}
              </div>

              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={handleRemoveFile}
                  disabled={isGenerating}
                  className="px-4 py-2.5 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 rounded-lg border border-slate-300 transition-colors shadow-sm disabled:opacity-50"
                >
                  Upload Another File
                </button>
                <button
                  type="button"
                  onClick={handleGenerateDashboardClick}
                  disabled={isGenerating || selectedCharts.length === 0}
                  className="inline-flex items-center gap-2 px-5 py-2.5 text-xs font-bold text-white bg-brand-600 hover:bg-brand-700 disabled:bg-slate-300 rounded-lg transition-colors shadow-sm cursor-pointer disabled:cursor-not-allowed"
                >
                  {isGenerating ? (
                    <>
                      <RotateCw className="w-4 h-4 animate-spin" />
                      <span>Aggregating Dataset...</span>
                    </>
                  ) : (
                    <>
                      <span>Generate Dashboard</span>
                      <ArrowRight className="w-4 h-4" />
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Placeholder Step 3 & 4 when no file selected */}
        {!selectedFile && (
          <div className="space-y-4">
            <section
              aria-labelledby="step2-heading"
              className="bg-white rounded-xl border border-slate-200 p-6 sm:p-7 shadow-sm opacity-80"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold uppercase tracking-wider text-slate-600 bg-slate-100 px-2 py-0.5 rounded">
                      Upcoming Step
                    </span>
                    <span className="text-xs text-slate-500">Step 2 of 4</span>
                  </div>
                  <h2
                    id="step2-heading"
                    className="text-base font-semibold text-slate-900 tracking-tight pt-1"
                  >
                    Data Inspection & Structure Validation
                  </h2>
                  <p className="text-xs text-slate-500 max-w-2xl leading-relaxed">
                    Once a file is selected, the system will automatically parse sheet headers, identify column types (dates, currencies, categories, quantities), and flag missing values for user confirmation.
                  </p>
                </div>

                <div className="w-8 h-8 rounded-lg bg-slate-100 flex items-center justify-center text-slate-500 flex-shrink-0">
                  <TableProperties className="w-4 h-4" />
                </div>
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
