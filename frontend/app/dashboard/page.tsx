"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  BarChart3,
  Filter,
  RotateCcw,
  UploadCloud,
  FileSpreadsheet,
  Layers,
  Calendar,
  Tag,
  AlertCircle,
  AlertTriangle,
  RotateCw,
  SlidersHorizontal,
  ChevronDown,
  ChevronUp,
  X,
  FileText,
  Table,
  CheckCircle2,
  TrendingUp,
  Bookmark,
  Save,
  Check,
  Lock,
} from "lucide-react";
import { useDashboard, GlobalFilterInput } from "@/context/DashboardContext";
import { useAuth } from "@/context/AuthContext";
import { Header } from "@/components/Header";
import { SummaryCard } from "@/components/SummaryCard";
import { EmptyState } from "@/components/EmptyState";
import { DashboardChartCard } from "@/components/DashboardChartRenderer";

export default function DashboardPage() {
  const router = useRouter();
  const { user, role, isConfigured } = useAuth();
  const {
    file,
    sheetName,
    dashboardData,
    activeFilters,
    isGenerating,
    error,
    savedDatasetId,
    savedReportId,
    savedReportName,
    isPersisting,
    persistStatus,
    saveCurrentReport,
    generateDashboard,
    resetFilters,
    clearSession,
  } = useDashboard();

  // Save report modal state
  const [isSaveModalOpen, setIsSaveModalOpen] = useState(false);
  const [reportNameInput, setReportNameInput] = useState("");
  const [saveLocalError, setSaveLocalError] = useState<string | null>(null);
  const [saveSuccessMsg, setSaveSuccessMsg] = useState<string | null>(null);

  // Local filter form state initialized from dashboardData and activeFilters
  const avail = dashboardData?.available_filters;
  const initialDateCol = activeFilters?.date_column || (avail?.date_columns?.[0] ?? "");
  const initialCatCol = activeFilters?.category_column || (avail?.category_columns?.[0] ?? "");

  const [dateColumn, setDateColumn] = useState<string>(initialDateCol);
  const [startDate, setStartDate] = useState<string>(activeFilters?.start_date || "");
  const [endDate, setEndDate] = useState<string>(activeFilters?.end_date || "");
  const [categoryColumn, setCategoryColumn] = useState<string>(initialCatCol);
  const [selectedCategories, setSelectedCategories] = useState<string[]>(
    activeFilters?.category_values || []
  );
  const [isFilterOpen, setIsFilterOpen] = useState(true);
  const [filterError, setFilterError] = useState<string | null>(null);

  // If in-memory state is empty (e.g. page refresh)
  if (!dashboardData && !file) {
    return (
      <div className="flex flex-col min-h-full">
        <Header
          title="Analytics Dashboard"
          description="Interactive business reports generated from uploaded datasets."
        />
        <div className="p-6 sm:p-8 max-w-4xl mx-auto w-full">
          <EmptyState
            icon={FileSpreadsheet}
            title="No Active Dataset in Session"
            description="In-memory calculations are transient. To inspect an interactive dashboard, upload a new Excel or CSV file or reopen a previously saved report from your private workspace."
            action={
              <div className="flex items-center gap-3 flex-wrap justify-center">
                <Link
                  href="/upload"
                  className="inline-flex items-center gap-2 px-5 py-2.5 text-xs font-semibold text-white bg-brand-600 hover:bg-brand-700 rounded-lg shadow-sm transition-colors"
                >
                  <UploadCloud className="w-4 h-4" />
                  <span>Upload Dataset</span>
                </Link>
                <Link
                  href="/reports"
                  className="inline-flex items-center gap-2 px-5 py-2.5 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 border border-slate-300 rounded-lg shadow-xs transition-colors"
                >
                  <Bookmark className="w-4 h-4 text-brand-600" />
                  <span>View Saved Reports</span>
                </Link>
              </div>
            }
          />
        </div>
      </div>
    );
  }

  // If file is present but dashboard hasn't generated yet
  if (!dashboardData && file) {
    return (
      <div className="flex flex-col min-h-full">
        <Header
          title="Generating Dashboard"
          description="Calculating verified aggregations from source data..."
        />
        <div className="p-8 max-w-xl mx-auto w-full text-center space-y-4">
          <div className="w-12 h-12 rounded-xl bg-brand-50 border border-brand-200 flex items-center justify-center mx-auto text-brand-600">
            <RotateCw className="w-6 h-6 animate-spin" />
          </div>
          <h2 className="text-base font-semibold text-slate-800">
            Calculating Dataset Aggregations
          </h2>
          <p className="text-xs text-slate-500 leading-relaxed">
            Generating verified chart distributions and measure summaries for{" "}
            <strong>{file.name}</strong>.
          </p>
          {error && (
            <p className="text-xs text-rose-600 font-medium bg-rose-50 p-3 rounded-lg border border-rose-200">
              {error}
            </p>
          )}
          <div className="pt-2">
            <button
              type="button"
              onClick={() => router.push("/upload")}
              className="text-xs text-brand-600 hover:text-brand-700 font-semibold underline underline-offset-4"
            >
              Return to Upload and Chart Configuration
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Safe reference to data
  const data = dashboardData!;
  const summary = data.summary;
  const availFilters = data.available_filters;

  // Category choices for active category column
  const activeCategoryValues = categoryColumn ? availFilters.category_values[categoryColumn] || [] : [];

  // Toggle category value selection
  const handleToggleCategory = (val: string) => {
    setSelectedCategories((prev) =>
      prev.includes(val) ? prev.filter((c) => c !== val) : [...prev, val]
    );
  };

  const handleSelectAllCategories = () => {
    setSelectedCategories([...activeCategoryValues]);
  };

  const handleClearSelectedCategories = () => {
    setSelectedCategories([]);
  };

  // Apply filters
  const handleApplyFilters = async () => {
    setFilterError(null);

    // Date range validation
    if (startDate && endDate && startDate > endDate) {
      setFilterError("Start date cannot be after End date.");
      return;
    }

    const payload: GlobalFilterInput = {
      date_column: dateColumn ? dateColumn : null,
      start_date: startDate ? startDate : null,
      end_date: endDate ? endDate : null,
      category_column: categoryColumn ? categoryColumn : null,
      category_values: selectedCategories.length > 0 ? selectedCategories : null,
    };

    const res = await generateDashboard(payload);
    if (!res && error) {
      setFilterError(error);
    }
  };

  // Reset filters
  const handleResetFilters = async () => {
    setFilterError(null);
    setStartDate("");
    setEndDate("");
    setSelectedCategories([]);
    await resetFilters();
  };

  const handleNewUpload = () => {
    clearSession();
    router.push("/upload");
  };

  const handleOpenSaveModal = () => {
    setReportNameInput(
      savedReportName || `${data.filename.replace(/\.[^/.]+$/, "")} Report`
    );
    setSaveLocalError(null);
    setSaveSuccessMsg(null);
    setIsSaveModalOpen(true);
  };

  const handleConfirmSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reportNameInput.trim()) {
      setSaveLocalError("Report name cannot be empty.");
      return;
    }
    setSaveLocalError(null);
    const res = await saveCurrentReport(reportNameInput.trim());
    if (res.error) {
      setSaveLocalError(res.error);
    } else {
      setSaveSuccessMsg(`Report "${reportNameInput.trim()}" saved to workspace!`);
      setTimeout(() => setIsSaveModalOpen(false), 1200);
    }
  };

  return (
    <div className="flex flex-col min-h-full">
      <Header
        title="Interactive Business Dashboard"
        description="Calculated from full verified dataset records. Interactive date and category filters recalculate aggregations server-side in real time."
      />

      <div className="p-6 sm:p-8 space-y-6 max-w-7xl mx-auto w-full">
        {/* Source File & Controls Bar */}
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-3 flex-wrap">
            <div className="w-10 h-10 rounded-lg bg-brand-50 border border-brand-200 flex items-center justify-center text-brand-600 flex-shrink-0">
              <FileSpreadsheet className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-bold text-slate-900 text-sm tracking-tight">
                  {data.filename}
                </span>
                {data.sheet_name && (
                  <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-100 text-slate-700 border border-slate-200">
                    Sheet: {data.sheet_name}
                  </span>
                )}
                {summary.is_filtered ? (
                  <span className="px-2 py-0.5 rounded text-[11px] font-bold uppercase tracking-wider bg-amber-100 text-amber-800 border border-amber-200">
                    Filtered ({summary.filtered_records.toLocaleString()} rows)
                  </span>
                ) : (
                  <span className="px-2 py-0.5 rounded text-[11px] font-bold uppercase tracking-wider bg-emerald-100 text-emerald-800 border border-emerald-200">
                    Full Dataset ({summary.total_records.toLocaleString()} rows)
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-500 mt-0.5">
                Processed in-memory. Aggregations recalculated directly on verified source rows.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            {savedReportName ? (
              <div className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-50 border border-emerald-200 text-xs font-semibold text-emerald-800">
                <Bookmark className="w-3.5 h-3.5 text-emerald-600 fill-emerald-600" />
                <span>Saved: {savedReportName}</span>
              </div>
            ) : null}

            {user ? (
              role === "viewer" ? (
                <button
                  type="button"
                  disabled
                  title="Viewers cannot create or modify reports."
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold text-slate-400 bg-slate-100 rounded-lg border border-slate-200 cursor-not-allowed"
                >
                  <Lock className="w-3.5 h-3.5" />
                  <span>Save Report (Viewer)</span>
                </button>
              ) : (
                <button
                  type="button"
                  onClick={handleOpenSaveModal}
                  disabled={isPersisting}
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold text-white bg-brand-600 hover:bg-brand-700 rounded-lg shadow-sm transition-colors"
                >
                  {isPersisting ? (
                    <RotateCw className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Bookmark className="w-3.5 h-3.5" />
                  )}
                  <span>{savedReportId ? "Update Report" : "Save Report"}</span>
                </button>
              )
            ) : (
              <Link
                href="/login"
                className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold text-brand-700 bg-brand-50 hover:bg-brand-100 rounded-lg border border-brand-200 transition-colors"
                title="Sign in to save reports to your workspace"
              >
                <Bookmark className="w-3.5 h-3.5" />
                <span>Sign in to Save</span>
              </Link>
            )}

            <button
              type="button"
              onClick={() => router.push("/upload")}
              className="px-3.5 py-2 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 rounded-lg border border-slate-300 transition-colors shadow-xs"
            >
              Configure Charts
            </button>
            <button
              type="button"
              onClick={handleNewUpload}
              className="px-3.5 py-2 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 rounded-lg border border-slate-300 transition-colors shadow-xs"
            >
              Upload Another Dataset
            </button>
          </div>
        </div>

        {/* Global Filter Panel */}
        <section
          aria-labelledby="filter-panel-heading"
          className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden"
        >
          <div className="p-4 sm:p-5 border-b border-slate-100 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Filter className="w-4 h-4 text-brand-600" />
              <h2
                id="filter-panel-heading"
                className="text-sm font-bold text-slate-900 tracking-tight"
              >
                Global Dataset Filters
              </h2>
              {summary.is_filtered && (
                <span className="text-[10px] font-bold uppercase tracking-wider bg-brand-50 text-brand-700 px-2 py-0.5 rounded border border-brand-200">
                  Active
                </span>
              )}
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setIsFilterOpen(!isFilterOpen)}
                className="text-xs text-slate-500 hover:text-slate-800 font-medium flex items-center gap-1 px-2 py-1 rounded hover:bg-slate-50"
              >
                <span>{isFilterOpen ? "Collapse" : "Expand"}</span>
                {isFilterOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              </button>
            </div>
          </div>

          {isFilterOpen && (
            <div className="p-5 sm:p-6 space-y-5 bg-slate-50/50">
              {filterError && (
                <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 flex items-center gap-2 text-xs text-rose-700">
                  <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
                  <span>{filterError}</span>
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {/* Date Column Selection */}
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                    Date Column
                  </label>
                  <select
                    value={dateColumn}
                    onChange={(e) => setDateColumn(e.target.value)}
                    disabled={availFilters.date_columns.length === 0}
                    className="w-full text-xs bg-white border border-slate-300 rounded-lg p-2.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:bg-slate-100 disabled:text-slate-400"
                  >
                    {availFilters.date_columns.length === 0 ? (
                      <option value="">No date columns detected</option>
                    ) : (
                      <>
                        <option value="">Select date column...</option>
                        {availFilters.date_columns.map((col) => (
                          <option key={col} value={col}>
                            {col}
                          </option>
                        ))}
                      </>
                    )}
                  </select>
                </div>

                {/* Date Range: Start */}
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                    Start Date
                  </label>
                  <input
                    type="date"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    disabled={!dateColumn}
                    className="w-full text-xs bg-white border border-slate-300 rounded-lg p-2.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:bg-slate-100 disabled:text-slate-400"
                  />
                  {dateColumn && availFilters.date_ranges[dateColumn]?.min && (
                    <span className="text-[10px] text-slate-600 mt-1 block">
                      Min in data: {availFilters.date_ranges[dateColumn].min}
                    </span>
                  )}
                </div>

                {/* Date Range: End */}
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                    End Date
                  </label>
                  <input
                    type="date"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    disabled={!dateColumn}
                    className="w-full text-xs bg-white border border-slate-300 rounded-lg p-2.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:bg-slate-100 disabled:text-slate-400"
                  />
                  {dateColumn && availFilters.date_ranges[dateColumn]?.max && (
                    <span className="text-[10px] text-slate-600 mt-1 block">
                      Max in data: {availFilters.date_ranges[dateColumn].max}
                    </span>
                  )}
                </div>

                {/* Category Column Selection */}
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                    Category Column
                  </label>
                  <select
                    value={categoryColumn}
                    onChange={(e) => {
                      setCategoryColumn(e.target.value);
                      setSelectedCategories([]);
                    }}
                    disabled={availFilters.category_columns.length === 0}
                    className="w-full text-xs bg-white border border-slate-300 rounded-lg p-2.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:bg-slate-100 disabled:text-slate-400"
                  >
                    {availFilters.category_columns.length === 0 ? (
                      <option value="">No categorical columns</option>
                    ) : (
                      <>
                        <option value="">Select category column...</option>
                        {availFilters.category_columns.map((col) => (
                          <option key={col} value={col}>
                            {col}
                          </option>
                        ))}
                      </>
                    )}
                  </select>
                </div>
              </div>

              {/* Category Values Multi-select */}
              {categoryColumn && activeCategoryValues.length > 0 && (
                <div className="space-y-2 pt-2 border-t border-slate-200">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-slate-700">
                      Filter by {categoryColumn} values ({selectedCategories.length} of {activeCategoryValues.length} active)
                    </span>
                    <div className="flex items-center gap-2 text-[11px]">
                      <button
                        type="button"
                        onClick={handleSelectAllCategories}
                        className="text-brand-600 hover:text-brand-700 font-medium"
                      >
                        Select All
                      </button>
                      <span className="text-slate-300">·</span>
                      <button
                        type="button"
                        onClick={handleClearSelectedCategories}
                        className="text-slate-500 hover:text-slate-700 font-medium"
                      >
                        Clear All
                      </button>
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto p-2 bg-white rounded-lg border border-slate-200">
                    {activeCategoryValues.map((val) => {
                      const isSelected = selectedCategories.includes(val);
                      return (
                        <button
                          key={val}
                          type="button"
                          onClick={() => handleToggleCategory(val)}
                          className={`px-2.5 py-1 text-xs font-medium rounded-md border transition-colors ${
                            isSelected
                              ? "bg-brand-50 text-brand-700 border-brand-300 font-semibold"
                              : "bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100"
                          }`}
                        >
                          {val}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Action Buttons */}
              <div className="flex items-center justify-between gap-3 pt-3 border-t border-slate-200">
                <button
                  type="button"
                  onClick={handleResetFilters}
                  disabled={isGenerating || !summary.is_filtered}
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-100 rounded-lg border border-slate-300 transition-colors shadow-xs disabled:opacity-50"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  <span>Reset All Filters</span>
                </button>

                <button
                  type="button"
                  onClick={handleApplyFilters}
                  disabled={isGenerating}
                  className="inline-flex items-center gap-2 px-5 py-2 text-xs font-bold text-white bg-brand-600 hover:bg-brand-700 disabled:bg-slate-300 rounded-lg transition-colors shadow-sm"
                >
                  {isGenerating ? (
                    <>
                      <RotateCw className="w-3.5 h-3.5 animate-spin" />
                      <span>Recalculating...</span>
                    </>
                  ) : (
                    <>
                      <Filter className="w-3.5 h-3.5" />
                      <span>Apply Filters</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          )}
        </section>

        {/* Filtered Subset Notification Banner */}
        {summary.is_filtered && (
          <div className="p-4 rounded-xl bg-blue-50/80 border border-blue-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-blue-900">
            <div className="flex items-center gap-2.5">
              <Filter className="w-4 h-4 text-blue-600 flex-shrink-0" />
              <span>
                <strong>Filtered Subset Active:</strong> Showing {summary.filtered_records.toLocaleString()} of {summary.total_records.toLocaleString()} total rows ({Math.round((summary.filtered_records / Math.max(1, summary.total_records)) * 100)}%). All chart metrics reflect this subset.
              </span>
            </div>
            <button
              type="button"
              onClick={handleResetFilters}
              className="text-xs font-semibold text-blue-700 hover:text-blue-900 underline underline-offset-2 flex-shrink-0"
            >
              Clear Filters
            </button>
          </div>
        )}

        {/* Summary Metric Cards */}
        <section aria-labelledby="summary-metrics-heading">
          <div className="flex items-center justify-between mb-3">
            <h2 id="summary-metrics-heading" className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Dataset Quality & Measure Summaries
            </h2>
            <span className="text-[11px] text-slate-500">
              Recalculated on active slice
            </span>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
            <SummaryCard
              label="Filtered Records"
              value={summary.filtered_records.toLocaleString()}
              subtext={`of ${summary.total_records.toLocaleString()} total rows`}
              icon={Table}
              badge={
                summary.is_filtered
                  ? { text: `${Math.round((summary.filtered_records / Math.max(1, summary.total_records)) * 100)}%`, variant: "info" }
                  : undefined
              }
            />
            <SummaryCard
              label="Columns"
              value={summary.total_columns}
              subtext="Schema attributes"
              icon={Layers}
            />
            <SummaryCard
              label="Missing Cells"
              value={summary.missing_cells.toLocaleString()}
              subtext="Blank or null values"
              icon={AlertTriangle}
            />
            <SummaryCard
              label="Duplicates"
              value={summary.duplicate_rows.toLocaleString()}
              subtext="Identical row signatures"
              icon={RotateCcw}
            />

            {/* Dynamic Numeric Measure Summaries */}
            {summary.measure_summaries.map((m, idx) => (
              <SummaryCard
                key={`${m.column}-${m.aggregation}-${idx}`}
                label={m.label}
                value={
                  typeof m.value === "number"
                    ? m.value.toLocaleString(undefined, { maximumFractionDigits: 2 })
                    : m.value
                }
                subtext={`Aggregation across ${summary.filtered_records.toLocaleString()} rows`}
                icon={TrendingUp}
              />
            ))}
          </div>
        </section>

        {/* Charts Grid */}
        <section aria-labelledby="charts-grid-heading" className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-brand-600" />
              <h2 id="charts-grid-heading" className="text-sm font-bold text-slate-900 tracking-tight">
                Confirmed Visualizations ({data.charts.length})
              </h2>
            </div>
            <span className="text-xs text-slate-500">
              Full dataset calculations
            </span>
          </div>

          {summary.filtered_records === 0 ? (
            <div className="p-12 text-center bg-white rounded-xl border border-dashed border-slate-300 space-y-3">
              <AlertCircle className="w-8 h-8 text-slate-400 mx-auto" />
              <h3 className="text-sm font-bold text-slate-800">
                No Records Match Active Filters
              </h3>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                No rows in this dataset satisfy the current date or category filter bounds. Reset filters to recalculate charts.
              </p>
              <button
                type="button"
                onClick={handleResetFilters}
                className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-brand-600 hover:bg-brand-700 rounded-lg shadow-sm"
              >
                Reset Filters
              </button>
            </div>
          ) : data.charts.length === 0 ? (
            <div className="p-12 text-center bg-white rounded-xl border border-dashed border-slate-300 space-y-3">
              <AlertCircle className="w-8 h-8 text-slate-400 mx-auto" />
              <h3 className="text-sm font-bold text-slate-800">
                No Charts Configured
              </h3>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                No confirmed charts were submitted for this dashboard. Return to chart selection to select and confirm visualizations.
              </p>
              <button
                type="button"
                onClick={() => router.push("/upload")}
                className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-brand-600 hover:bg-brand-700 rounded-lg shadow-sm"
              >
                Select Charts
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {data.charts.map((chart) => (
                <DashboardChartCard key={chart.id} chart={chart} />
              ))}
            </div>
          )}
        </section>
      </div>

      {/* Save Report Modal Dialog */}
      {isSaveModalOpen && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-xs animate-in fade-in"
        >
          <div className="bg-white rounded-2xl border border-slate-200 shadow-xl max-w-md w-full p-6 space-y-5 animate-in zoom-in-95">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-9 h-9 rounded-xl bg-brand-50 border border-brand-200 flex items-center justify-center text-brand-600">
                  <Bookmark className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900">
                    {savedReportId ? "Update Saved Report" : "Save Report"}
                  </h3>
                  <p className="text-xs text-slate-500">
                    Persist configuration to reopen anytime from your workspace.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setIsSaveModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {saveSuccessMsg ? (
              <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center gap-2">
                <Check className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                <span className="font-semibold">{saveSuccessMsg}</span>
              </div>
            ) : (
              <form onSubmit={handleConfirmSave} className="space-y-4">
                <div>
                  <label
                    htmlFor="report-name"
                    className="block text-xs font-semibold text-slate-700 mb-1"
                  >
                    Report Name
                  </label>
                  <input
                    id="report-name"
                    type="text"
                    value={reportNameInput}
                    onChange={(e) => setReportNameInput(e.target.value)}
                    placeholder="e.g. Q3 Sales & Operations Overview"
                    className="w-full px-3.5 py-2 text-sm rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-brand-500 text-slate-900"
                    autoFocus
                    required
                  />
                </div>

                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 space-y-1 text-xs text-slate-600">
                  <p className="font-semibold text-slate-800">What will be saved:</p>
                  <ul className="list-disc list-inside space-y-0.5 text-slate-500">
                    <li>
                      Source dataset:{" "}
                      <span className="font-medium text-slate-700">{data.filename}</span>
                    </li>
                    <li>{data.charts.length} confirmed chart configurations</li>
                    <li>
                      {summary.is_filtered
                        ? "Active date and category filters"
                        : "Full dataset configuration"}
                    </li>
                  </ul>
                </div>

                {saveLocalError && (
                  <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-start gap-2">
                    <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0 mt-0.5" />
                    <span>{saveLocalError}</span>
                  </div>
                )}

                <div className="flex items-center justify-end gap-2.5 pt-2">
                  <button
                    type="button"
                    onClick={() => setIsSaveModalOpen(false)}
                    disabled={isPersisting}
                    className="px-4 py-2 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 rounded-lg border border-slate-300"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isPersisting}
                    className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-brand-600 hover:bg-brand-700 rounded-lg shadow-sm"
                  >
                    {isPersisting ? (
                      <>
                        <RotateCw className="w-3.5 h-3.5 animate-spin" />
                        <span>Saving...</span>
                      </>
                    ) : (
                      <>
                        <Save className="w-3.5 h-3.5" />
                        <span>Save to Workspace</span>
                      </>
                    )}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
