"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  FileText,
  UploadCloud,
  Plus,
  Calendar,
  FileSpreadsheet,
  BarChart3,
  Filter,
  Trash2,
  RotateCw,
  AlertCircle,
  AlertTriangle,
  ExternalLink,
  Lock,
  Search,
  Sparkles,
} from "lucide-react";
import { Header } from "@/components/Header";
import { EmptyState } from "@/components/EmptyState";
import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import { createClient } from "@/lib/supabase/client";

interface ReportItem {
  id: string;
  name: string;
  workspace_id: string;
  dataset_id: string;
  chart_configs: any[];
  filter_config: Record<string, any>;
  created_at: string;
  updated_at: string;
  datasets?: {
    id: string;
    original_filename: string;
    file_size_bytes: number;
    selected_sheet?: string | null;
    storage_path: string;
  } | null;
}

export default function ReportsPage() {
  const router = useRouter();
  const { user, workspace, role, isConfigured, isLoading: authLoading } = useAuth();
  const { openReportById, isGenerating } = useDashboard();

  const [reports, setReports] = useState<ReportItem[]>([]);
  const [isLoadingReports, setIsLoadingReports] = useState(false);
  const [loadingReportId, setLoadingReportId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const fetchReports = useCallback(async () => {
    if (!isConfigured || !user || !workspace) {
      setIsLoadingReports(false);
      return;
    }

    const supabase = createClient();
    if (!supabase) {
      setIsLoadingReports(false);
      return;
    }

    try {
      setIsLoadingReports(true);
      setActionError(null);

      const { data, error } = await supabase
        .from("reports")
        .select(`
          id,
          name,
          workspace_id,
          dataset_id,
          chart_configs,
          filter_config,
          created_at,
          updated_at,
          datasets (
            id,
            original_filename,
            file_size_bytes,
            selected_sheet,
            storage_path
          )
        `)
        .eq("workspace_id", workspace.id)
        .order("created_at", { ascending: false });

      if (error) {
        throw error;
      }

      setReports((data as unknown as ReportItem[]) || []);
    } catch (err: any) {
      setActionError(err?.message || "Failed to load saved reports.");
    } finally {
      setIsLoadingReports(false);
    }
  }, [isConfigured, user, workspace]);

  useEffect(() => {
    let cancelled = false;
    if (authLoading || !isConfigured || !user || !workspace) {
      return;
    }

    const load = async () => {
      await Promise.resolve();
      if (cancelled) return;

      const supabase = createClient();
      if (!supabase) return;

      setIsLoadingReports(true);
      try {
        const { data, error } = await supabase
          .from("reports")
          .select(`
            id,
            name,
            workspace_id,
            dataset_id,
            chart_configs,
            filter_config,
            created_at,
            updated_at,
            datasets (
              id,
              original_filename,
              file_size_bytes,
              selected_sheet,
              storage_path
            )
          `)
          .eq("workspace_id", workspace.id)
          .order("created_at", { ascending: false });

        if (error) throw error;
        if (!cancelled) {
          setReports((data as unknown as ReportItem[]) || []);
        }
      } catch (err: any) {
        if (!cancelled) {
          setActionError(err?.message || "Failed to load saved reports.");
        }
      } finally {
        if (!cancelled) {
          setIsLoadingReports(false);
        }
      }
    };

    load();

    return () => {
      cancelled = true;
    };
  }, [authLoading, isConfigured, user, workspace]);

  // Open saved report: download file from storage, recompute dashboard via FastAPI
  const handleOpenReport = async (reportId: string) => {
    setActionError(null);
    setLoadingReportId(reportId);
    try {
      const res = await openReportById(reportId);
      if (res.success) {
        router.push("/dashboard");
      } else {
        setActionError(res.error || "Failed to open report.");
      }
    } catch (err: any) {
      setActionError(err?.message || "Failed to reconstruct report dashboard.");
    } finally {
      setLoadingReportId(null);
    }
  };

  // Confirm delete report
  const handleDeleteReport = async () => {
    if (!deleteTargetId || !workspace) return;

    const supabase = createClient();
    if (!supabase) return;

    try {
      setIsDeleting(true);
      setActionError(null);

      const { error } = await supabase
        .from("reports")
        .delete()
        .eq("id", deleteTargetId)
        .eq("workspace_id", workspace.id);

      if (error) {
        throw error;
      }

      setReports((prev) => prev.filter((r) => r.id !== deleteTargetId));
      setDeleteTargetId(null);
    } catch (err: any) {
      setActionError(err?.message || "Failed to delete report.");
    } finally {
      setIsDeleting(false);
    }
  };

  const filteredReports = reports.filter((r) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    const nameMatch = r.name.toLowerCase().includes(q);
    const datasetMatch = r.datasets?.original_filename.toLowerCase().includes(q);
    return nameMatch || Boolean(datasetMatch);
  });

  return (
    <div className="flex flex-col min-h-full">
      <Header
        title="Saved Reports"
        description="Inspect, manage, and recalculate saved business reporting dashboards directly from private workspace storage."
        actions={
          <Link
            href="/upload"
            className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold text-white bg-brand-600 hover:bg-brand-700 rounded-lg shadow-sm transition-colors focus:ring-2 focus:ring-brand-500 focus:ring-offset-2"
          >
            <Plus className="w-4 h-4" />
            <span>New Report</span>
          </Link>
        }
      />

      <div className="p-6 sm:p-8 space-y-6 max-w-7xl mx-auto w-full">
        {/* Unconfigured / Guest Notice */}
        {!isConfigured ? (
          <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-xs flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-bold text-sm">Supabase Persistence Not Configured</p>
              <p className="mt-1 leading-relaxed text-amber-800">
                To enable persistent saved reports and private storage across browser refreshes, configure your Supabase project URL and keys in <code className="px-1.5 py-0.5 rounded bg-amber-100 font-mono">.env.local</code> and run the migrations in <code className="px-1.5 py-0.5 rounded bg-amber-100 font-mono">supabase/migrations/</code>.
              </p>
            </div>
          </div>
        ) : !user ? (
          <div className="p-4 rounded-xl bg-brand-50 border border-brand-200 text-brand-900 text-xs flex items-center justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-2.5">
              <Lock className="w-5 h-5 text-brand-600 flex-shrink-0" />
              <div>
                <p className="font-bold text-sm">Sign in to Access Saved Reports</p>
                <p className="text-slate-600 text-xs">
                  Reports and private dataset files are securely isolated per authenticated workspace.
                </p>
              </div>
            </div>
            <Link
              href="/login"
              className="px-4 py-2 rounded-lg bg-brand-600 hover:bg-brand-700 text-white text-xs font-semibold transition-colors shadow-xs"
            >
              Sign In to Workspace
            </Link>
          </div>
        ) : null}

        {/* Global Action Error Banner */}
        {actionError && (
          <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-900 text-xs flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-rose-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="font-bold">Error Accessing Report</p>
              <p className="mt-0.5 leading-relaxed">{actionError}</p>
            </div>
            <button
              type="button"
              onClick={() => setActionError(null)}
              className="text-rose-500 hover:text-rose-700 text-xs font-semibold"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Search & Statistics Filter Bar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 bg-white rounded-xl border border-slate-200 shadow-xs">
          <div className="flex items-center gap-3 flex-1 max-w-md">
            <div className="relative w-full">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search by report name or dataset file..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-3.5 py-1.5 text-xs rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-brand-500 text-slate-900 bg-slate-50/50"
              />
            </div>
          </div>
          <div className="flex items-center gap-3 text-xs text-slate-500">
            <span>
              <strong>{filteredReports.length}</strong> {filteredReports.length === 1 ? "report" : "reports"} in{" "}
              <strong className="text-slate-800">{workspace?.name || "Workspace"}</strong>
            </span>
            <button
              type="button"
              onClick={fetchReports}
              disabled={isLoadingReports}
              className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-600 transition-colors"
              title="Refresh reports"
            >
              <RotateCw className={`w-3.5 h-3.5 ${isLoadingReports ? "animate-spin" : ""}`} />
            </button>
          </div>
        </div>

        {/* Loading Skeletons */}
        {isLoadingReports ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="p-5 bg-white rounded-xl border border-slate-200 shadow-xs space-y-4 animate-pulse"
              >
                <div className="h-5 bg-slate-200 rounded w-2/3" />
                <div className="h-4 bg-slate-100 rounded w-1/2" />
                <div className="h-8 bg-slate-100 rounded" />
              </div>
            ))}
          </div>
        ) : filteredReports.length === 0 ? (
          <EmptyState
            icon={FileText}
            title={reports.length === 0 ? "No saved reports in this workspace" : "No matching reports found"}
            description={
              reports.length === 0
                ? "Saved reports will appear here once you upload an Excel or CSV file, generate a dashboard, and click Save Report."
                : `No reports matched your search term "${searchQuery}".`
            }
            action={
              <Link
                href="/upload"
                className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold text-white bg-brand-600 hover:bg-brand-700 rounded-lg shadow-sm transition-colors"
              >
                <UploadCloud className="w-4 h-4" />
                <span>Upload a Dataset to Build a Report</span>
              </Link>
            }
          />
        ) : (
          /* Reports Grid */
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {filteredReports.map((report) => {
              const isOpening = loadingReportId === report.id;
              const chartCount = Array.isArray(report.chart_configs) ? report.chart_configs.length : 0;
              const hasFilters = Boolean(
                report.filter_config &&
                  (report.filter_config.start_date ||
                    report.filter_config.category_values?.length > 0)
              );
              const isSourceMissing = !report.datasets;

              return (
                <div
                  key={report.id}
                  className="bg-white rounded-xl border border-slate-200 shadow-sm hover:border-slate-300 transition-all flex flex-col justify-between overflow-hidden"
                >
                  <div className="p-5 space-y-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-lg bg-brand-50 border border-brand-200 flex items-center justify-center text-brand-600 flex-shrink-0">
                          <FileText className="w-4 h-4" />
                        </div>
                        <h3 className="font-bold text-slate-900 text-sm tracking-tight line-clamp-1" title={report.name}>
                          {report.name}
                        </h3>
                      </div>
                      {role !== "viewer" && (
                        <button
                          type="button"
                          onClick={() => setDeleteTargetId(report.id)}
                          className="text-slate-400 hover:text-rose-600 p-1 rounded-lg transition-colors"
                          title="Delete report"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      )}
                    </div>

                    {/* Dataset details */}
                    <div className="space-y-1.5 pt-1">
                      <div className="flex items-center gap-1.5 text-xs text-slate-600">
                        <FileSpreadsheet className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                        <span className="truncate font-medium">
                          {report.datasets?.original_filename || (
                            <span className="text-amber-600 italic">Source file missing</span>
                          )}
                        </span>
                      </div>
                      {report.datasets?.selected_sheet && (
                        <p className="text-[11px] text-slate-500 pl-5">
                          Sheet: {report.datasets.selected_sheet}
                        </p>
                      )}
                    </div>

                    {/* Metadata Badges */}
                    <div className="flex items-center gap-2 flex-wrap pt-2 border-t border-slate-100">
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-100 text-slate-700">
                        <BarChart3 className="w-3 h-3 text-slate-500" />
                        <span>{chartCount} {chartCount === 1 ? "chart" : "charts"}</span>
                      </span>

                      {hasFilters && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                          <Filter className="w-3 h-3 text-amber-500" />
                          <span>Filtered</span>
                        </span>
                      )}

                      <span className="text-[11px] text-slate-400 ml-auto">
                        {new Date(report.created_at).toLocaleDateString(undefined, {
                          month: "short",
                          day: "numeric",
                          year: "numeric",
                        })}
                      </span>
                    </div>
                  </div>

                  {/* Card Action Footer */}
                  <div className="p-3 bg-slate-50/70 border-t border-slate-100 flex items-center justify-between">
                    <span className="text-[11px] text-slate-500">
                      Private storage source
                    </span>
                    <button
                      type="button"
                      onClick={() => handleOpenReport(report.id)}
                      disabled={isOpening || isGenerating}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-brand-600 hover:bg-brand-700 rounded-lg shadow-xs transition-colors disabled:opacity-60"
                    >
                      {isOpening ? (
                        <>
                          <RotateCw className="w-3.5 h-3.5 animate-spin" />
                          <span>Recomputing...</span>
                        </>
                      ) : (
                        <>
                          <span>Open Dashboard</span>
                          <ExternalLink className="w-3 h-3" />
                        </>
                      )}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Delete Confirmation Modal */}
        {deleteTargetId && (
          <div
            role="dialog"
            aria-modal="true"
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-xs animate-in fade-in"
          >
            <div className="bg-white rounded-2xl border border-slate-200 shadow-xl max-w-sm w-full p-6 space-y-4 animate-in zoom-in-95">
              <div className="w-10 h-10 rounded-xl bg-rose-50 border border-rose-200 flex items-center justify-center text-rose-600 mx-auto">
                <Trash2 className="w-5 h-5" />
              </div>
              <div className="text-center space-y-1">
                <h3 className="text-base font-bold text-slate-900">
                  Delete Saved Report?
                </h3>
                <p className="text-xs text-slate-500 leading-relaxed">
                  This will permanently remove the saved report configuration from your workspace. The underlying dataset file will remain in private storage if referenced by other reports.
                </p>
              </div>

              <div className="flex items-center justify-end gap-2.5 pt-2">
                <button
                  type="button"
                  onClick={() => setDeleteTargetId(null)}
                  disabled={isDeleting}
                  className="w-full px-4 py-2 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 rounded-lg border border-slate-300"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleDeleteReport}
                  disabled={isDeleting}
                  className="w-full inline-flex items-center justify-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-rose-600 hover:bg-rose-700 rounded-lg shadow-sm"
                >
                  {isDeleting ? (
                    <RotateCw className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <span>Delete Report</span>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
