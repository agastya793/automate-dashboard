"use client";

import React, { useState, useEffect, useCallback, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
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
  Grid,
  Info,
  CheckSquare,
  ShieldCheck,
  ShieldAlert,
  Download,
} from "lucide-react";
import { useDashboard, GlobalFilterInput } from "@/context/DashboardContext";
import { useAuth } from "@/context/AuthContext";
import { Header } from "@/components/Header";
import { SummaryCard } from "@/components/SummaryCard";
import { EmptyState } from "@/components/EmptyState";
import { DashboardChartCard } from "@/components/DashboardChartRenderer";
import { ExportModal } from "@/components/ExportModal";
import {
  TrendTargetChart,
  ParetoChart,
  PaynterHeatmap,
  ActionTracker,
  ModelComparisonChart,
  ProvenanceModal,
  ReconciliationBanner,
} from "@/components/echarts";
import { ProvenanceDetails, ManufacturingGlobalFilters } from "@/lib/mappingTypes";

function DashboardContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
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
    manufacturingData,
    manufacturingFilters,
    activeUploadId,
    saveCurrentReport,
    generateDashboard,
    resetFilters,
    generateManufacturingDashboard,
    queryManufacturingFilters,
    resetManufacturingFilters,
    saveManufacturingDashboard,
    openManufacturingDashboardById,
    clearSession,
  } = useDashboard();

  // Save report modal state
  const [isSaveModalOpen, setIsSaveModalOpen] = useState(false);
  const [reportNameInput, setReportNameInput] = useState("");
  const [saveLocalError, setSaveLocalError] = useState<string | null>(null);
  const [saveSuccessMsg, setSaveSuccessMsg] = useState<string | null>(null);
  const [isExportModalOpen, setIsExportModalOpen] = useState(false);

  // Provenance modal state
  const [activeProvenance, setActiveProvenance] = useState<{
    title: string;
    provenance: ProvenanceDetails | null;
  } | null>(null);

  // Manufacturing Filter Form state
  const [mPeriod, setMPeriod] = useState<string>("");
  const [mModel, setMModel] = useState<string>("");
  const [mDefect, setMDefect] = useState<string>("");
  const [mOwner, setMOwner] = useState<string>("");
  const [mStatus, setMStatus] = useState<string>("");
  const [isFilterPanelOpen, setIsFilterPanelOpen] = useState(true);

  // Check URL query parameters for auto-load
  useEffect(() => {
    const urlDashboardId = searchParams.get("dashboard_id");
    const urlUploadId = searchParams.get("upload_id");

    if (urlDashboardId && !manufacturingData && !isGenerating) {
      openManufacturingDashboardById(urlDashboardId);
    } else if (urlUploadId && !manufacturingData && !isGenerating) {
      generateManufacturingDashboard(urlUploadId);
    }
  }, [searchParams, manufacturingData, isGenerating, openManufacturingDashboardById, generateManufacturingDashboard]);

  // Handle manufacturing filter changes
  const handleApplyManufacturingFilters = useCallback(async () => {
    const filters: ManufacturingGlobalFilters = {
      period: mPeriod || null,
      model: mModel || null,
      defect: mDefect || null,
      action_owner: mOwner || null,
      action_status: mStatus || null,
    };
    await queryManufacturingFilters(filters);
  }, [mPeriod, mModel, mDefect, mOwner, mStatus, queryManufacturingFilters]);

  const handleResetManufacturingFilters = useCallback(async () => {
    setMPeriod("");
    setMModel("");
    setMDefect("");
    setMOwner("");
    setMStatus("");
    await resetManufacturingFilters();
  }, [resetManufacturingFilters]);

  // Handle saving manufacturing dashboard
  const handleSaveDashboardSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reportNameInput.trim()) {
      setSaveLocalError("Please enter a title for the dashboard.");
      return;
    }
    setSaveLocalError(null);

    if (manufacturingData) {
      const res = await saveManufacturingDashboard(reportNameInput.trim());
      if (res.error) {
        setSaveLocalError(res.error);
      } else {
        setSaveSuccessMsg(`Dashboard saved successfully as "${reportNameInput.trim()}".`);
        setTimeout(() => {
          setIsSaveModalOpen(false);
          setSaveSuccessMsg(null);
        }, 1500);
      }
    } else {
      const res = await saveCurrentReport(reportNameInput.trim());
      if (res.error) {
        setSaveLocalError(res.error);
      } else {
        setSaveSuccessMsg(`Report saved successfully as "${reportNameInput.trim()}".`);
        setTimeout(() => {
          setIsSaveModalOpen(false);
          setSaveSuccessMsg(null);
        }, 1500);
      }
    }
  };

  // If in-memory state is empty (e.g. page refresh) and no manufacturing data
  if (!dashboardData && !file && !manufacturingData) {
    return (
      <div className="flex flex-col min-h-full">
        <Header
          title="Manufacturing Quality Dashboard"
          description="Interactive quality reporting and verified PPM metrics."
        />
        <div className="p-6 sm:p-8 max-w-4xl mx-auto w-full">
          <EmptyState
            icon={FileSpreadsheet}
            title="No Active Dataset or Dashboard in Session"
            description="To inspect verified quality dashboards, upload an Excel or CSV file in the Upload & Mapping workspace, or reopen a saved manufacturing dashboard."
            action={
              <div className="flex items-center gap-3 flex-wrap justify-center">
                <Link
                  href="/upload"
                  className="inline-flex items-center gap-2 px-5 py-2.5 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg shadow-sm transition-colors"
                >
                  <UploadCloud className="w-4 h-4" />
                  <span>Upload & Map Dataset</span>
                </Link>
                <Link
                  href="/reports"
                  className="inline-flex items-center gap-2 px-5 py-2.5 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 border border-slate-300 rounded-lg shadow-2xs transition-colors"
                >
                  <Bookmark className="w-4 h-4 text-indigo-600" />
                  <span>View Saved Reports</span>
                </Link>
              </div>
            }
          />
        </div>
      </div>
    );
  }

  // Loading state
  if (isGenerating && !manufacturingData && !dashboardData) {
    return (
      <div className="flex flex-col min-h-full">
        <Header
          title="Generating Quality Dashboard"
          description="Calculating verified aggregations and DuckDB queries..."
        />
        <div className="p-8 max-w-xl mx-auto w-full text-center space-y-4">
          <div className="w-12 h-12 rounded-xl bg-indigo-50 border border-indigo-200 flex items-center justify-center mx-auto text-indigo-600">
            <RotateCw className="w-6 h-6 animate-spin" />
          </div>
          <h2 className="text-base font-semibold text-slate-800">
            Executing Manufacturing Analytical Queries
          </h2>
          <p className="text-xs text-slate-500 leading-relaxed">
            Running parameterized DuckDB queries over Parquet datasets and calculating reconciliation metrics.
          </p>
        </div>
      </div>
    );
  }

  // =========================================================================
  // VIEW 1: Manufacturing Quality Dashboard (Milestone 4 - Apache ECharts)
  // =========================================================================
  if (manufacturingData) {
    const widgets = manufacturingData.rendered_widgets || [];
    const ppmWidget = widgets.find((w) => w.widget_type === "ppm_trend_target");
    const paretoWidget = widgets.find((w) => w.widget_type === "defect_pareto");
    const heatmapWidget = widgets.find((w) => w.widget_type === "paynter_heatmap");
    const modelWidget = widgets.find((w) => w.widget_type === "model_comparison");
    const actionWidget = widgets.find((w) => w.widget_type === "action_tracker");

    const availFilters = manufacturingData.available_filters || {
      periods: [],
      models: [],
      defects: [],
      action_owners: [],
      action_statuses: [],
    };

    const hasActiveFilters = Boolean(mPeriod || mModel || mDefect || mOwner || mStatus);

    return (
      <div className="flex flex-col min-h-full">
        <Header
          title={manufacturingData.spec.title || "Manufacturing Quality Dashboard"}
          description="Verified rejection PPM, Defect Pareto, Paynter Heatmap, and Countermeasure tracking."
        />

        <div className="p-6 sm:p-8 space-y-6 max-w-7xl">
          {/* Top Control Bar */}
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="flex items-center gap-3 flex-wrap">
              <div className="w-10 h-10 rounded-lg bg-indigo-50 border border-indigo-200 flex items-center justify-center text-indigo-600 flex-shrink-0">
                <FileSpreadsheet className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-bold text-slate-900 text-sm tracking-tight">
                    {manufacturingData.spec.title}
                  </span>
                  <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
                    Template v{manufacturingData.spec.version}
                  </span>
                  {hasActiveFilters ? (
                    <span className="px-2 py-0.5 rounded text-[11px] font-bold uppercase tracking-wider bg-amber-100 text-amber-800 border border-amber-200">
                      Filtered View
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 rounded text-[11px] font-bold uppercase tracking-wider bg-emerald-100 text-emerald-800 border border-emerald-200">
                      Complete Normalized Dataset
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-500 mt-0.5">
                  Analytical queries executed via DuckDB over private Parquet datasets.
                </p>
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-2 flex-wrap">
              {savedReportName && (
                <div className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-50 border border-emerald-200 text-xs font-semibold text-emerald-800">
                  <Bookmark className="w-3.5 h-3.5 text-emerald-600 fill-emerald-600" />
                  <span>Saved: {savedReportName}</span>
                </div>
              )}

              <button
                type="button"
                onClick={() => {
                  setReportNameInput(manufacturingData.spec.title);
                  setIsSaveModalOpen(true);
                }}
                disabled={isPersisting}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg shadow-sm transition-colors"
              >
                {isPersisting ? (
                  <RotateCw className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Bookmark className="w-3.5 h-3.5" />
                )}
                <span>{savedReportId ? "Update Dashboard" : "Save Dashboard"}</span>
              </button>

              <button
                type="button"
                onClick={() => {
                  if (!savedReportId) {
                    setReportNameInput(manufacturingData.spec.title);
                    setIsSaveModalOpen(true);
                  } else {
                    setIsExportModalOpen(true);
                  }
                }}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 rounded-lg border border-slate-300 transition-colors shadow-2xs"
              >
                <Download className="w-3.5 h-3.5 text-sky-600" />
                <span>Export Report</span>
              </button>

              <button
                type="button"
                onClick={() => router.push("/upload")}
                className="px-3.5 py-2 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 rounded-lg border border-slate-300 transition-colors shadow-2xs"
              >
                Workbook Mapping
              </button>
            </div>
          </div>

          {/* Reconciliation & Accuracy Verification Banner */}
          <ReconciliationBanner
            report={manufacturingData.reconciliation}
            hasSotConflict={!manufacturingData.spec.source_of_truth_confirmed}
            sotConfirmed={manufacturingData.spec.source_of_truth_confirmed}
            onResolveConflict={() => router.push("/upload")}
          />

          {/* Global Manufacturing Filters Toolbar */}
          <section
            aria-labelledby="manufacturing-filters-heading"
            className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden"
          >
            <div className="p-4 sm:p-5 border-b border-slate-100 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <Filter className="w-4 h-4 text-indigo-600" />
                <h3 id="manufacturing-filters-heading" className="text-sm font-bold text-slate-900 tracking-tight">
                  Global Manufacturing Filters
                </h3>
                {hasActiveFilters && (
                  <span className="w-2 h-2 rounded-full bg-indigo-600 animate-pulse" />
                )}
              </div>

              <div className="flex items-center gap-2">
                {hasActiveFilters && (
                  <button
                    type="button"
                    onClick={handleResetManufacturingFilters}
                    className="inline-flex items-center gap-1 text-xs text-rose-600 hover:text-rose-700 font-medium px-2 py-1 rounded hover:bg-rose-50"
                  >
                    <RotateCcw className="w-3 h-3" />
                    <span>Reset Filters</span>
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setIsFilterPanelOpen(!isFilterPanelOpen)}
                  className="text-xs text-slate-500 hover:text-slate-700 p-1 rounded hover:bg-slate-100"
                >
                  {isFilterPanelOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {isFilterPanelOpen && (
              <div className="p-4 sm:p-5 bg-slate-50/50">
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-3.5">
                  {/* Reporting Period */}
                  <div>
                    <label className="block text-[11px] font-semibold text-slate-700 mb-1">
                      Reporting Period
                    </label>
                    <select
                      value={mPeriod}
                      onChange={(e) => setMPeriod(e.target.value)}
                      className="w-full text-xs py-1.5 px-2.5 bg-white border border-slate-300 rounded-lg text-slate-900 focus:ring-1 focus:ring-indigo-500 focus:outline-none"
                    >
                      <option value="">All Periods ({availFilters.periods.length})</option>
                      {availFilters.periods.map((p) => (
                        <option key={p} value={p}>
                          {p}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Model */}
                  <div>
                    <label className="block text-[11px] font-semibold text-slate-700 mb-1">
                      Product Model
                    </label>
                    <select
                      value={mModel}
                      onChange={(e) => setMModel(e.target.value)}
                      className="w-full text-xs py-1.5 px-2.5 bg-white border border-slate-300 rounded-lg text-slate-900 focus:ring-1 focus:ring-indigo-500 focus:outline-none"
                    >
                      <option value="">All Models ({availFilters.models.length || 4})</option>
                      {(availFilters.models.length > 0
                        ? availFilters.models
                        : ["157 TY", "367 TY", "457 TY", "Milwaukee"]
                      ).map((m) => (
                        <option key={m} value={m}>
                          {m}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Defect */}
                  <div>
                    <label className="block text-[11px] font-semibold text-slate-700 mb-1">
                      Defect Category
                    </label>
                    <select
                      value={mDefect}
                      onChange={(e) => setMDefect(e.target.value)}
                      className="w-full text-xs py-1.5 px-2.5 bg-white border border-slate-300 rounded-lg text-slate-900 focus:ring-1 focus:ring-indigo-500 focus:outline-none"
                    >
                      <option value="">All Defects ({availFilters.defects.length})</option>
                      {availFilters.defects.map((d) => (
                        <option key={d} value={d}>
                          {d}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Champion / Owner */}
                  <div>
                    <label className="block text-[11px] font-semibold text-slate-700 mb-1">
                      Action Champion
                    </label>
                    <select
                      value={mOwner}
                      onChange={(e) => setMOwner(e.target.value)}
                      className="w-full text-xs py-1.5 px-2.5 bg-white border border-slate-300 rounded-lg text-slate-900 focus:ring-1 focus:ring-indigo-500 focus:outline-none"
                    >
                      <option value="">All Champions ({availFilters.action_owners.length})</option>
                      {availFilters.action_owners.map((o) => (
                        <option key={o} value={o}>
                          {o}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Action Status */}
                  <div>
                    <label className="block text-[11px] font-semibold text-slate-700 mb-1">
                      Action Status
                    </label>
                    <select
                      value={mStatus}
                      onChange={(e) => setMStatus(e.target.value)}
                      className="w-full text-xs py-1.5 px-2.5 bg-white border border-slate-300 rounded-lg text-slate-900 focus:ring-1 focus:ring-indigo-500 focus:outline-none"
                    >
                      <option value="">All Statuses</option>
                      <option value="open">Open / In Progress</option>
                      <option value="closed">Closed / Completed</option>
                      <option value="overdue">Overdue</option>
                      <option value="unknown">Unmapped / Unknown</option>
                    </select>
                  </div>
                </div>

                <div className="mt-3.5 flex items-center justify-between pt-2 border-t border-slate-200/60">
                  <span className="text-[11px] text-slate-500">
                    Applying filters recalculates all widgets simultaneously using DuckDB.
                  </span>
                  <button
                    type="button"
                    onClick={handleApplyManufacturingFilters}
                    disabled={isGenerating}
                    className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors shadow-2xs"
                  >
                    {isGenerating && <RotateCw className="w-3.5 h-3.5 animate-spin" />}
                    <span>Apply Global Filters</span>
                  </button>
                </div>
              </div>
            )}
          </section>

          {/* ================================================================= */}
          {/* 5 Specialized Manufacturing ECharts Widgets                      */}
          {/* ================================================================= */}
          <div className="space-y-6">
            {/* Row 1: PPM Trend vs Target + Defect Pareto Analysis */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {ppmWidget && (
                <TrendTargetChart
                  title={ppmWidget.title}
                  dataPoints={ppmWidget.data_points || []}
                  targetPpm={ppmWidget.target_ppm}
                  exceededCount={ppmWidget.exceeded_count}
                  warnings={ppmWidget.warnings}
                  provenance={ppmWidget.provenance}
                  onOpenProvenance={() =>
                    setActiveProvenance({
                      title: ppmWidget.title,
                      provenance: ppmWidget.provenance || null,
                    })
                  }
                />
              )}

              {paretoWidget && (
                <ParetoChart
                  title={paretoWidget.title}
                  items={paretoWidget.items || []}
                  thresholdLine={paretoWidget.threshold_line}
                  provenance={paretoWidget.provenance}
                  onOpenProvenance={() =>
                    setActiveProvenance({
                      title: paretoWidget.title,
                      provenance: paretoWidget.provenance || null,
                    })
                  }
                />
              )}
            </div>

            {/* Row 2: Paynter Defect Heatmap + Model-Level Comparison */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {heatmapWidget && (
                <PaynterHeatmap
                  title={heatmapWidget.title}
                  xCategories={heatmapWidget.x_categories || []}
                  yCategories={heatmapWidget.y_categories || []}
                  matrixData={heatmapWidget.matrix_data || []}
                  maxValue={heatmapWidget.max_value}
                  provenance={heatmapWidget.provenance}
                  onOpenProvenance={() =>
                    setActiveProvenance({
                      title: heatmapWidget.title,
                      provenance: heatmapWidget.provenance || null,
                    })
                  }
                />
              )}

              {modelWidget && (
                <ModelComparisonChart
                  title={modelWidget.title}
                  periods={modelWidget.periods || []}
                  models={modelWidget.models || []}
                  series={modelWidget.series || []}
                  provenance={modelWidget.provenance}
                  onOpenProvenance={() =>
                    setActiveProvenance({
                      title: modelWidget.title,
                      provenance: modelWidget.provenance || null,
                    })
                  }
                />
              )}
            </div>

            {/* Row 3: Corrective-Action & Countermeasure Tracker */}
            {actionWidget && (
              <ActionTracker
                title={actionWidget.title}
                statusCounts={
                  actionWidget.status_counts || { open: 0, closed: 0, overdue: 0, unknown: 0 }
                }
                ownerCounts={actionWidget.owner_counts || {}}
                actionItems={actionWidget.action_items || []}
                totalActions={actionWidget.total_actions}
                warnings={actionWidget.warnings}
                provenance={actionWidget.provenance}
                onOpenProvenance={() =>
                  setActiveProvenance({
                    title: actionWidget.title,
                    provenance: actionWidget.provenance || null,
                  })
                }
              />
            )}
          </div>
        </div>

        {/* Provenance Modal */}
        <ProvenanceModal
          isOpen={Boolean(activeProvenance)}
          onClose={() => setActiveProvenance(null)}
          widgetTitle={activeProvenance?.title || ""}
          provenance={activeProvenance?.provenance || null}
        />

        {/* Save Dashboard Modal */}
        {isSaveModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
            <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-md w-full p-6 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-bold text-slate-900">
                  Save Manufacturing Dashboard
                </h3>
                <button
                  type="button"
                  onClick={() => setIsSaveModalOpen(false)}
                  className="text-slate-400 hover:text-slate-600"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {saveSuccessMsg ? (
                <div className="p-4 bg-emerald-50 rounded-xl border border-emerald-200 text-emerald-800 text-xs flex items-center gap-2 font-medium">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                  <span>{saveSuccessMsg}</span>
                </div>
              ) : (
                <form onSubmit={handleSaveDashboardSubmit} className="space-y-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">
                      Dashboard Title
                    </label>
                    <input
                      type="text"
                      value={reportNameInput}
                      onChange={(e) => setReportNameInput(e.target.value)}
                      placeholder="e.g. Q1 Manufacturing Quality Report"
                      className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-slate-900"
                      autoFocus
                      required
                    />
                  </div>

                  {saveLocalError && (
                    <div className="p-3 bg-rose-50 rounded-lg border border-rose-200 text-rose-800 text-xs">
                      {saveLocalError}
                    </div>
                  )}

                  <div className="flex justify-end gap-2 pt-2">
                    <button
                      type="button"
                      onClick={() => setIsSaveModalOpen(false)}
                      className="px-4 py-2 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 rounded-lg border border-slate-300"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={isPersisting}
                      className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg shadow-sm"
                    >
                      {isPersisting ? (
                        <>
                          <RotateCw className="w-3.5 h-3.5 animate-spin" />
                          <span>Saving...</span>
                        </>
                      ) : (
                        <>
                          <Save className="w-3.5 h-3.5" />
                          <span>Save Dashboard</span>
                        </>
                      )}
                    </button>
                  </div>
                </form>
              )}
            </div>
          </div>
        )}

        {/* Export Report Modal */}
        {isExportModalOpen && savedReportId && (
          <ExportModal
            isOpen={true}
            onClose={() => setIsExportModalOpen(false)}
            dashboardId={savedReportId}
            dashboardTitle={savedReportName || manufacturingData.spec.title}
            userRole={role || "viewer"}
          />
        )}
      </div>
    );
  }

  // =========================================================================
  // VIEW 2: Generic Dataset Dashboard (Milestone 1-3 Fallback)
  // =========================================================================
  const data = dashboardData!;
  const summary = data.dataset_summary;

  return (
    <div className="flex flex-col min-h-full">
      <Header
        title="Analytics Dashboard"
        description="Interactive business reports generated from uploaded datasets."
      />

      <div className="p-6 sm:p-8 space-y-6 max-w-7xl">
        {/* Top Control Bar */}
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-3 flex-wrap">
            <div className="w-10 h-10 rounded-lg bg-indigo-50 border border-indigo-200 flex items-center justify-center text-indigo-600 flex-shrink-0">
              <FileSpreadsheet className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-bold text-slate-900 text-sm tracking-tight">
                  {data.filename}
                </span>
                {data.selected_sheet && (
                  <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-100 text-slate-700 border border-slate-200">
                    Sheet: {data.selected_sheet}
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
            <button
              type="button"
              onClick={() => router.push("/upload")}
              className="px-3.5 py-2 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 rounded-lg border border-slate-300 transition-colors shadow-2xs"
            >
              Configure Charts
            </button>
            <button
              type="button"
              onClick={() => {
                clearSession();
                router.push("/upload");
              }}
              className="px-3.5 py-2 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 rounded-lg border border-slate-300 transition-colors shadow-2xs"
            >
              Upload Another Dataset
            </button>
          </div>
        </div>

        {/* Existing Generic Charts Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {data.charts.map((chart) => (
            <DashboardChartCard key={chart.id} chart={chart} />
          ))}
        </div>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <Suspense
      fallback={
        <div className="p-8 text-center text-xs text-slate-500">
          Loading dashboard...
        </div>
      }
    >
      <DashboardContent />
    </Suspense>
  );
}
