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
  Download,
  Copy,
  Edit2,
  Check,
  X,
} from "lucide-react";
import { Header } from "@/components/Header";
import { EmptyState } from "@/components/EmptyState";
import { ExportModal } from "@/components/ExportModal";
import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import { apiFetch } from "@/lib/api";

interface SavedDashboardItem {
  id: string;
  upload_id: string;
  title: string;
  template_id?: string | null;
  source_filename?: string;
  created_at: string;
  updated_at: string;
}

export default function ReportsPage() {
  const router = useRouter();
  const { user, workspace, role } = useAuth();
  const { openManufacturingDashboardById, isGenerating } = useDashboard();

  const [reports, setReports] = useState<SavedDashboardItem[]>([]);
  const [isLoadingReports, setIsLoadingReports] = useState(true);
  const [loadingReportId, setLoadingReportId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  // Modals state
  const [deleteTarget, setDeleteTarget] = useState<SavedDashboardItem | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const [renameTarget, setRenameTarget] = useState<SavedDashboardItem | null>(null);
  const [renameTitle, setRenameTitle] = useState("");
  const [isRenaming, setIsRenaming] = useState(false);

  const [duplicatingId, setDuplicatingId] = useState<string | null>(null);

  const [exportTarget, setExportTarget] = useState<SavedDashboardItem | null>(null);

  const isViewer = role === "viewer";

  const fetchReports = useCallback(async () => {
    try {
      setIsLoadingReports(true);
      setActionError(null);
      const res = await apiFetch("/api/dashboards");
      if (!res.ok) {
        throw new Error(`Failed to load saved reports (${res.status})`);
      }
      const data: SavedDashboardItem[] = await res.json();
      setReports(data || []);
    } catch (err: any) {
      setActionError(err.message || "Failed to load saved reports.");
    } finally {
      setIsLoadingReports(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const res = await apiFetch("/api/dashboards");
        if (!res.ok) throw new Error(`Failed to load saved reports (${res.status})`);
        const data: SavedDashboardItem[] = await res.json();
        if (active) {
          setReports(data || []);
          setIsLoadingReports(false);
        }
      } catch (err: any) {
        if (active) {
          setActionError(err.message || "Failed to load saved reports.");
          setIsLoadingReports(false);
        }
      }
    };
    load();
    return () => {
      active = false;
    };
  }, []);

  // Open report action
  const handleOpenReport = async (reportId: string) => {
    setLoadingReportId(reportId);
    setActionError(null);
    try {
      const ok = await openManufacturingDashboardById(reportId);
      if (ok) {
        router.push("/dashboard");
      } else {
        setActionError("Failed to recalculate and open saved dashboard.");
      }
    } catch (err: any) {
      setActionError(err.message || "Could not open saved dashboard.");
    } finally {
      setLoadingReportId(null);
    }
  };

  // Rename report action
  const handleRenameSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!renameTarget || !renameTitle.trim()) return;

    setIsRenaming(true);
    setActionError(null);
    try {
      const res = await apiFetch(`/api/dashboards/${renameTarget.id}`, {
        method: "PATCH",
        body: JSON.stringify({ title: renameTitle.trim() }),
      });
      if (!res.ok) {
        let msg = `Rename failed (${res.status})`;
        try {
          const d = await res.json();
          if (d.detail) msg = d.detail;
        } catch {}
        throw new Error(msg);
      }
      setActionSuccess(`Report renamed to "${renameTitle.trim()}".`);
      setRenameTarget(null);
      await fetchReports();
    } catch (err: any) {
      setActionError(err.message || "Failed to rename report.");
    } finally {
      setIsRenaming(false);
    }
  };

  // Duplicate report action
  const handleDuplicate = async (report: SavedDashboardItem) => {
    if (isViewer) return;
    setDuplicatingId(report.id);
    setActionError(null);
    try {
      const res = await apiFetch(`/api/dashboards/${report.id}/duplicate`, {
        method: "POST",
        body: JSON.stringify({ title: `Copy of ${report.title}` }),
      });
      if (!res.ok) {
        let msg = `Duplicate failed (${res.status})`;
        try {
          const d = await res.json();
          if (d.detail) msg = d.detail;
        } catch {}
        throw new Error(msg);
      }
      setActionSuccess(`Duplicated report configuration "${report.title}".`);
      await fetchReports();
    } catch (err: any) {
      setActionError(err.message || "Failed to duplicate report.");
    } finally {
      setDuplicatingId(null);
    }
  };

  // Delete report action
  const handleDeleteReport = async () => {
    if (!deleteTarget) return;

    setIsDeleting(true);
    setActionError(null);
    try {
      const res = await apiFetch(`/api/dashboards/${deleteTarget.id}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        let msg = `Delete failed (${res.status})`;
        try {
          const d = await res.json();
          if (d.detail) msg = d.detail;
        } catch {}
        throw new Error(msg);
      }
      setActionSuccess(`Report "${deleteTarget.title}" deleted.`);
      setDeleteTarget(null);
      await fetchReports();
    } catch (err: any) {
      setActionError(err.message || "Failed to delete report.");
    } finally {
      setIsDeleting(false);
    }
  };

  const filteredReports = reports.filter((r) => {
    const q = searchQuery.toLowerCase();
    const titleMatch = r.title.toLowerCase().includes(q);
    const fileMatch = r.source_filename?.toLowerCase().includes(q);
    return titleMatch || fileMatch;
  });

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 pb-20">
      <Header
        title="Saved Reports"
        description="Local-first business intelligence reports for manufacturing quality tracking."
      />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-8 space-y-6">
        {/* Top Header & Actions */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-6">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold tracking-tight text-slate-900">
                Manufacturing Quality Reports
              </h1>
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-sky-100 text-sky-800 border border-sky-200">
                Local-First BI
              </span>
            </div>
            <p className="text-sm text-slate-500 mt-1">
              Reopen confirmed dashboards, recalculate from normalized Parquet data, and export verified executive reports.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={fetchReports}
              disabled={isLoadingReports}
              className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 border border-slate-200 rounded-xl shadow-xs transition disabled:opacity-60"
            >
              <RotateCw className={`w-3.5 h-3.5 ${isLoadingReports ? "animate-spin" : ""}`} />
              Refresh
            </button>

            <Link
              href="/dashboard"
              className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-sky-600 hover:bg-sky-500 rounded-xl shadow-sm transition"
            >
              <Plus className="w-3.5 h-3.5" />
              New Report
            </Link>
          </div>
        </div>

        {/* Banners & Messages */}
        {actionError && (
          <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-rose-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1 text-xs text-rose-800 font-medium">
              {actionError}
            </div>
            <button
              onClick={() => setActionError(null)}
              className="text-rose-400 hover:text-rose-600"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {actionSuccess && (
          <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 flex items-start gap-3">
            <Check className="w-5 h-5 text-emerald-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1 text-xs text-emerald-800 font-medium">
              {actionSuccess}
            </div>
            <button
              onClick={() => setActionSuccess(null)}
              className="text-emerald-400 hover:text-emerald-600"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Search & Stats Bar */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="relative w-full sm:w-80">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              type="text"
              placeholder="Search reports or files..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-4 py-2 text-xs bg-white border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500 shadow-xs"
            />
          </div>

          <div className="text-xs text-slate-500 self-end sm:self-center font-medium">
            Showing {filteredReports.length} of {reports.length} saved reports
          </div>
        </div>

        {/* Reports Grid */}
        {isLoadingReports ? (
          <div className="py-20 flex flex-col items-center justify-center space-y-3">
            <RotateCw className="w-6 h-6 text-sky-600 animate-spin" />
            <p className="text-xs font-semibold text-slate-500">
              Loading saved reports from PostgreSQL...
            </p>
          </div>
        ) : filteredReports.length === 0 ? (
          <EmptyState
            icon={FileSpreadsheet}
            title={searchQuery ? "No matching reports found" : "No saved reports yet"}
            description={
              searchQuery
                ? `No reports matched your query "${searchQuery}". Clear search to see all.`
                : "You haven't saved any quality reports in this workspace yet. Upload an Excel workbook to build and save your first dashboard."
            }
            action={
              <button
                type="button"
                onClick={() => router.push("/upload")}
                className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-sky-600 hover:bg-sky-500 rounded-xl shadow-xs transition"
              >
                Go to Upload
              </button>
            }
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {filteredReports.map((report) => {
              const isOpening = loadingReportId === report.id;
              const isDuplicating = duplicatingId === report.id;

              return (
                <div
                  key={report.id}
                  className="bg-white border border-slate-200 rounded-2xl shadow-xs hover:shadow-md transition-all flex flex-col justify-between overflow-hidden group"
                >
                  {/* Card Header */}
                  <div className="p-5 space-y-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <h2 className="text-base font-bold text-slate-900 truncate group-hover:text-sky-600 transition-colors">
                          {report.title}
                        </h2>
                        <div className="flex items-center gap-1.5 text-xs text-slate-500 mt-1 truncate">
                          <FileSpreadsheet className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                          <span className="truncate">{report.source_filename || "Workbook.xlsx"}</span>
                        </div>
                      </div>

                      {/* Top Action Menu for Edit/Duplicate/Delete */}
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          title={isViewer ? "Editing requires Editor role" : "Rename Report"}
                          disabled={isViewer}
                          onClick={() => {
                            setRenameTarget(report);
                            setRenameTitle(report.title);
                          }}
                          className="p-1.5 text-slate-400 hover:text-slate-700 disabled:opacity-40 rounded-lg hover:bg-slate-100 transition"
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                        </button>

                        <button
                          type="button"
                          title={isViewer ? "Duplicating requires Editor role" : "Duplicate Report"}
                          disabled={isViewer || isDuplicating}
                          onClick={() => handleDuplicate(report)}
                          className="p-1.5 text-slate-400 hover:text-slate-700 disabled:opacity-40 rounded-lg hover:bg-slate-100 transition"
                        >
                          {isDuplicating ? (
                            <RotateCw className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <Copy className="w-3.5 h-3.5" />
                          )}
                        </button>

                        <button
                          type="button"
                          title={isViewer ? "Deleting requires Editor role" : "Delete Report"}
                          disabled={isViewer}
                          onClick={() => setDeleteTarget(report)}
                          className="p-1.5 text-slate-400 hover:text-rose-600 disabled:opacity-40 rounded-lg hover:bg-rose-50 transition"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>

                    {/* Metadata Timestamps */}
                    <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-400">
                      <span className="flex items-center gap-1">
                        <Calendar className="w-3 h-3" />
                        {new Date(report.created_at).toLocaleDateString(undefined, {
                          month: "short",
                          day: "numeric",
                          year: "numeric",
                        })}
                      </span>
                      <span>Parquet Normalized</span>
                    </div>
                  </div>

                  {/* Card Action Buttons Footer */}
                  <div className="p-3 bg-slate-50 border-t border-slate-100 flex items-center justify-between gap-2">
                    <button
                      type="button"
                      onClick={() => setExportTarget(report)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-100 border border-slate-200 rounded-lg shadow-xs transition"
                    >
                      <Download className="w-3.5 h-3.5 text-sky-600" />
                      <span>Export</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => handleOpenReport(report.id)}
                      disabled={isOpening || isGenerating}
                      className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold text-white bg-sky-600 hover:bg-sky-500 rounded-lg shadow-xs transition disabled:opacity-60"
                    >
                      {isOpening ? (
                        <>
                          <RotateCw className="w-3.5 h-3.5 animate-spin" />
                          <span>Recalculating...</span>
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

        {/* Rename Modal */}
        {renameTarget && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs animate-in fade-in">
            <div className="bg-white rounded-2xl border border-slate-200 shadow-xl max-w-md w-full p-6 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                  <Edit2 className="w-4 h-4 text-sky-600" />
                  Rename Saved Report
                </h3>
                <button
                  onClick={() => setRenameTarget(null)}
                  className="text-slate-400 hover:text-slate-600"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <form onSubmit={handleRenameSubmit} className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">
                    Report Title
                  </label>
                  <input
                    type="text"
                    required
                    value={renameTitle}
                    onChange={(e) => setRenameTitle(e.target.value)}
                    className="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-sky-500"
                  />
                </div>

                <div className="flex items-center justify-end gap-2.5 pt-2">
                  <button
                    type="button"
                    onClick={() => setRenameTarget(null)}
                    disabled={isRenaming}
                    className="px-4 py-2 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 rounded-lg border border-slate-300"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isRenaming || !renameTitle.trim()}
                    className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-sky-600 hover:bg-sky-500 rounded-lg shadow-xs disabled:opacity-50"
                  >
                    {isRenaming ? (
                      <RotateCw className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <span>Save Changes</span>
                    )}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Delete Confirmation Modal */}
        {deleteTarget && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs animate-in fade-in">
            <div className="bg-white rounded-2xl border border-slate-200 shadow-xl max-w-sm w-full p-6 space-y-4">
              <div className="w-10 h-10 rounded-xl bg-rose-50 border border-rose-200 flex items-center justify-center text-rose-600 mx-auto">
                <Trash2 className="w-5 h-5" />
              </div>
              <div className="text-center space-y-1">
                <h3 className="text-base font-bold text-slate-900">
                  Delete Saved Report?
                </h3>
                <p className="text-xs text-slate-500 leading-relaxed">
                  This will remove the saved report specification &quot;{deleteTarget.title}&quot;.
                  Shared source datasets and Parquet files referenced by other reports will remain intact.
                </p>
              </div>

              <div className="flex items-center justify-end gap-2.5 pt-2">
                <button
                  type="button"
                  onClick={() => setDeleteTarget(null)}
                  disabled={isDeleting}
                  className="w-full px-4 py-2 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 rounded-lg border border-slate-300"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleDeleteReport}
                  disabled={isDeleting}
                  className="w-full inline-flex items-center justify-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-rose-600 hover:bg-rose-700 rounded-lg shadow-sm disabled:opacity-50"
                >
                  {isDeleting ? (
                    <RotateCw className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <span>Confirm Delete</span>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Export Modal */}
        {exportTarget && (
          <ExportModal
            isOpen={true}
            onClose={() => setExportTarget(null)}
            dashboardId={exportTarget.id}
            dashboardTitle={exportTarget.title}
            userRole={role || "viewer"}
          />
        )}
      </div>
    </div>
  );
}
