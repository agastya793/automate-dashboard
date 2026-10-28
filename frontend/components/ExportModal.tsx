"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  X,
  FileText,
  Image as ImageIcon,
  FileSpreadsheet,
  FileCode,
  Download,
  AlertCircle,
  CheckCircle2,
  Loader2,
  Lock,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { apiFetch } from "@/lib/api";

export type ExportFormat = "pdf" | "png" | "xlsx" | "csv";

interface ExportModalProps {
  isOpen: boolean;
  onClose: () => void;
  dashboardId: string;
  dashboardTitle: string;
  userRole?: string; // "viewer" | "editor" | "admin"
}

export function ExportModal({
  isOpen,
  onClose,
  dashboardId,
  dashboardTitle,
  userRole = "viewer",
}: ExportModalProps) {
  const [format, setFormat] = useState<ExportFormat>("pdf");
  const [orientation, setOrientation] = useState<"landscape" | "portrait">("landscape");
  const [exportMode, setExportMode] = useState<"normalized" | "summary">("normalized");

  const [status, setStatus] = useState<"idle" | "queueing" | "processing" | "ready" | "failed">("idle");
  const [exportId, setExportId] = useState<string | null>(null);
  const [fileSizeBytes, setFileSizeBytes] = useState<number | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);
  const pollCountRef = useRef<number>(0);

  const isViewer = userRole === "viewer";

  const [prevOpen, setPrevOpen] = useState(isOpen);
  if (isOpen !== prevOpen) {
    setPrevOpen(isOpen);
    setStatus("idle");
    setExportId(null);
    setFileSizeBytes(null);
    setErrorMessage(null);
    if (isViewer && (format === "xlsx" || format === "csv")) {
      setFormat("pdf");
    }
  }

  // Clean up timer on unmount
  useEffect(() => {
    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
      }
    };
  }, []);

  const pollExportStatus = useCallback((id: string) => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
    }
    pollCountRef.current = 0;

    pollTimerRef.current = setInterval(async () => {
      pollCountRef.current += 1;
      // Max 40 attempts (~60s)
      if (pollCountRef.current > 40) {
        if (pollTimerRef.current) clearInterval(pollTimerRef.current);
        setStatus("failed");
        setErrorMessage("Export timed out after 60 seconds. Please try again.");
        return;
      }

      try {
        const res = await apiFetch(`/api/exports/${id}`);
        if (!res.ok) {
          throw new Error(`Status check failed (${res.status})`);
        }
        const data = await res.json();
        if (data.status === "ready" || data.status === "completed") {
          if (pollTimerRef.current) clearInterval(pollTimerRef.current);
          setStatus("ready");
          setFileSizeBytes(data.file_size_bytes || null);
        } else if (data.status === "failed") {
          if (pollTimerRef.current) clearInterval(pollTimerRef.current);
          setStatus("failed");
          setErrorMessage(data.error_message || "Export processing failed.");
        } else {
          setStatus("processing");
        }
      } catch (err: any) {
        // Continue polling unless network completely fails
        if (pollCountRef.current > 10) {
          if (pollTimerRef.current) clearInterval(pollTimerRef.current);
          setStatus("failed");
          setErrorMessage(err.message || "Failed to poll export status.");
        }
      }
    }, 1500);
  }, []);

  const handleStartExport = async () => {
    if (isViewer && (format === "xlsx" || format === "csv")) {
      setErrorMessage("Viewers are restricted to visual exports (PDF, PNG).");
      return;
    }

    setStatus("queueing");
    setErrorMessage(null);
    setFileSizeBytes(null);

    const options: Record<string, any> = {};
    if (format === "pdf") {
      options.orientation = orientation;
    } else if (format === "csv") {
      options.export_mode = exportMode;
    }

    try {
      const res = await apiFetch(`/api/dashboards/${dashboardId}/exports`, {
        method: "POST",
        body: JSON.stringify({
          format,
          options,
        }),
      });

      if (!res.ok) {
        let msg = `Export request failed (${res.status})`;
        try {
          const errData = await res.json();
          if (errData?.detail) msg = errData.detail;
        } catch {}
        throw new Error(msg);
      }

      const data = await res.json();
      setExportId(data.id);

      if (data.status === "ready" || data.status === "completed") {
        setStatus("ready");
        setFileSizeBytes(data.file_size_bytes || null);
      } else {
        setStatus("processing");
        pollExportStatus(data.id);
      }
    } catch (err: any) {
      setStatus("failed");
      setErrorMessage(err.message || "Could not start export.");
    }
  };

  const handleDownload = () => {
    if (!exportId) return;
    const downloadUrl = `/api/exports/${exportId}/download`;
    // Trigger download via anchor element
    const link = document.createElement("a");
    link.href = downloadUrl;
    link.setAttribute("download", `report_${dashboardTitle.replace(/\s+/g, "_")}.${format}`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (!isOpen) return null;

  const formatOptions = [
    {
      id: "pdf" as ExportFormat,
      name: "PDF Report",
      icon: FileText,
      desc: "Printable executive document (A4, KPI cards, tables & metric provenance)",
      locked: false,
      color: "text-rose-500",
      bg: "bg-rose-500/10",
      border: "border-rose-500/20",
    },
    {
      id: "png" as ExportFormat,
      name: "PNG Snapshot",
      icon: ImageIcon,
      desc: "High-DPI 1600x1100 modern dashboard card for slides and presentations",
      locked: false,
      color: "text-sky-500",
      bg: "bg-sky-500/10",
      border: "border-sky-500/20",
    },
    {
      id: "xlsx" as ExportFormat,
      name: "Excel Workbook (.xlsx)",
      icon: FileSpreadsheet,
      desc: "Multi-sheet workbook (Summary, Specs & Normalized Data with injection protection)",
      locked: isViewer,
      color: "text-emerald-500",
      bg: "bg-emerald-500/10",
      border: "border-emerald-500/20",
    },
    {
      id: "csv" as ExportFormat,
      name: "CSV Data Table",
      icon: FileCode,
      desc: "UTF-8 with BOM normalized table export with formula-injection mitigation",
      locked: isViewer,
      color: "text-amber-500",
      bg: "bg-amber-500/10",
      border: "border-amber-500/20",
    },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-xl bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden">
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-900/80">
          <div>
            <h3 className="text-lg font-semibold text-slate-100 flex items-center gap-2">
              <Download className="w-5 h-5 text-sky-400" />
              Export Verified Report
            </h3>
            <p className="text-xs text-slate-400 truncate max-w-md mt-0.5">
              Dashboard: <span className="text-slate-200 font-medium">{dashboardTitle}</span>
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-200 rounded-lg hover:bg-slate-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Content */}
        <div className="p-6 space-y-5">
          {/* Format Selector Cards */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">
              Select Export Format
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {formatOptions.map((opt) => {
                const Icon = opt.icon;
                const isSelected = format === opt.id;
                return (
                  <button
                    key={opt.id}
                    type="button"
                    disabled={opt.locked || status === "queueing" || status === "processing"}
                    onClick={() => {
                      if (!opt.locked) {
                        setFormat(opt.id);
                        setStatus("idle");
                        setExportId(null);
                        setErrorMessage(null);
                      }
                    }}
                    className={`relative text-left p-3.5 rounded-xl border transition-all ${
                      opt.locked
                        ? "opacity-50 cursor-not-allowed bg-slate-950/40 border-slate-800"
                        : isSelected
                        ? "bg-sky-950/30 border-sky-500 shadow-md shadow-sky-500/10"
                        : "bg-slate-950/50 border-slate-800/80 hover:border-slate-700 hover:bg-slate-800/40"
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <div className={`p-2 rounded-lg ${opt.bg} ${opt.color}`}>
                        <Icon className="w-5 h-5" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-semibold text-slate-200">{opt.name}</span>
                          {opt.locked && (
                            <span className="flex items-center gap-1 text-[10px] text-amber-400 font-medium bg-amber-400/10 px-1.5 py-0.5 rounded">
                              <Lock className="w-2.5 h-2.5" /> Editor Only
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-slate-400 mt-1 leading-snug line-clamp-2">{opt.desc}</p>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Conditional Options */}
          {format === "pdf" && (
            <div className="p-3.5 rounded-xl bg-slate-950/40 border border-slate-800/80 space-y-2">
              <label className="block text-xs font-medium text-slate-300">Page Orientation</label>
              <div className="flex gap-4">
                <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                  <input
                    type="radio"
                    name="orientation"
                    value="landscape"
                    checked={orientation === "landscape"}
                    onChange={() => setOrientation("landscape")}
                    className="text-sky-500 focus:ring-sky-500 bg-slate-900 border-slate-700"
                  />
                  Landscape (Recommended for wide manufacturing tables)
                </label>
                <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                  <input
                    type="radio"
                    name="orientation"
                    value="portrait"
                    checked={orientation === "portrait"}
                    onChange={() => setOrientation("portrait")}
                    className="text-sky-500 focus:ring-sky-500 bg-slate-900 border-slate-700"
                  />
                  Portrait
                </label>
              </div>
            </div>
          )}

          {format === "csv" && (
            <div className="p-3.5 rounded-xl bg-slate-950/40 border border-slate-800/80 space-y-2">
              <label className="block text-xs font-medium text-slate-300">CSV Export Mode</label>
              <div className="flex gap-4">
                <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                  <input
                    type="radio"
                    name="csvMode"
                    value="normalized"
                    checked={exportMode === "normalized"}
                    onChange={() => setExportMode("normalized")}
                    className="text-sky-500 focus:ring-sky-500 bg-slate-900 border-slate-700"
                  />
                  Normalized Parquet Records
                </label>
                <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                  <input
                    type="radio"
                    name="csvMode"
                    value="summary"
                    checked={exportMode === "summary"}
                    onChange={() => setExportMode("summary")}
                    className="text-sky-500 focus:ring-sky-500 bg-slate-900 border-slate-700"
                  />
                  Aggregated Metrics Summary
                </label>
              </div>
            </div>
          )}

          {/* Status Display */}
          {(status === "queueing" || status === "processing") && (
            <div className="p-4 rounded-xl bg-sky-950/20 border border-sky-800/50 flex items-center gap-3">
              <Loader2 className="w-5 h-5 text-sky-400 animate-spin flex-shrink-0" />
              <div>
                <p className="text-sm font-medium text-sky-200">
                  {status === "queueing" ? "Queueing export task..." : "Generating export file..."}
                </p>
                <p className="text-xs text-slate-400 mt-0.5">
                  DuckDB queries and layout formatting running locally. Bounded status polling active.
                </p>
              </div>
            </div>
          )}

          {status === "ready" && (
            <div className="p-4 rounded-xl bg-emerald-950/20 border border-emerald-800/50 flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0" />
                <div>
                  <p className="text-sm font-semibold text-emerald-200">Export Ready</p>
                  <p className="text-xs text-slate-400 mt-0.5">
                    File generated successfully
                    {fileSizeBytes ? ` (${(fileSizeBytes / 1024).toFixed(1)} KB)` : ""}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={handleDownload}
                className="inline-flex items-center gap-2 px-3.5 py-1.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-500 rounded-lg shadow transition"
              >
                <Download className="w-3.5 h-3.5" />
                Download Now
              </button>
            </div>
          )}

          {status === "failed" && (
            <div className="p-4 rounded-xl bg-rose-950/20 border border-rose-800/50 flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-rose-400 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="text-sm font-semibold text-rose-200">Export Generation Failed</p>
                <p className="text-xs text-rose-300 mt-0.5">{errorMessage || "An unexpected error occurred."}</p>
                <button
                  type="button"
                  onClick={handleStartExport}
                  className="mt-2.5 inline-flex items-center gap-1.5 text-xs font-medium text-rose-400 hover:text-rose-300"
                >
                  <RefreshCw className="w-3 h-3" /> Retry Generation
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-800 bg-slate-900/60">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs font-medium text-slate-400 hover:text-slate-200 rounded-lg hover:bg-slate-800 transition"
          >
            Close
          </button>

          {status !== "ready" ? (
            <button
              type="button"
              disabled={status === "queueing" || status === "processing"}
              onClick={handleStartExport}
              className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold text-white bg-sky-600 hover:bg-sky-500 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg shadow transition"
            >
              {status === "queueing" || status === "processing" ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" /> Processing...
                </>
              ) : (
                <>
                  <Download className="w-3.5 h-3.5" /> Generate Export
                </>
              )}
            </button>
          ) : (
            <button
              type="button"
              onClick={handleDownload}
              className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-500 rounded-lg shadow transition"
            >
              <Download className="w-3.5 h-3.5" /> Download {format.toUpperCase()}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
