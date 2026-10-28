"use client";

import React, { useState } from "react";
import {
  ShieldCheck,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  FileSpreadsheet,
  CheckCircle2,
  Clock,
  HelpCircle,
  ShieldAlert,
} from "lucide-react";

export interface ReconciliationItem {
  period: string;
  reference_ppm: number;
  calculated_ppm?: number | null;
  variance?: number | null;
  status: "match" | "variance" | "missing_actual" | "conflict_blocked";
  notes?: string | null;
}

export interface ReconciliationReport {
  status: "verified" | "has_variances" | "conflict_blocked" | "synthetic_fixture" | "unverified";
  match_count: number;
  total_periods: number;
  max_variance: number;
  items: ReconciliationItem[];
  explanation: string;
  is_authoritative: boolean;
}

export interface ReconciliationBannerProps {
  report: ReconciliationReport | null;
  hasSotConflict?: boolean;
  sotConfirmed?: boolean;
  onResolveConflict?: () => void;
}

export function ReconciliationBanner({
  report,
  hasSotConflict = false,
  sotConfirmed = false,
  onResolveConflict,
}: ReconciliationBannerProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!report) return null;

  const isVerified = report.status === "verified";
  const isConflict = report.status === "conflict_blocked" || (hasSotConflict && !sotConfirmed);
  const isSynthetic = report.status === "synthetic_fixture";

  return (
    <div
      className={`rounded-2xl border transition-all overflow-hidden shadow-xs ${
        isConflict
          ? "bg-amber-50/70 border-amber-300"
          : isVerified
          ? "bg-emerald-50/70 border-emerald-300"
          : isSynthetic
          ? "bg-indigo-50/70 border-indigo-300"
          : "bg-slate-50 border-slate-300"
      }`}
    >
      {/* Banner Header Bar */}
      <div className="p-4 sm:p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-start gap-3.5">
          <div
            className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${
              isConflict
                ? "bg-amber-100 text-amber-700"
                : isVerified
                ? "bg-emerald-100 text-emerald-700"
                : "bg-indigo-100 text-indigo-700"
            }`}
          >
            {isConflict ? (
              <ShieldAlert className="w-5 h-5" />
            ) : isVerified ? (
              <ShieldCheck className="w-5 h-5" />
            ) : (
              <FileSpreadsheet className="w-5 h-5" />
            )}
          </div>

          <div className="space-y-1">
            <div className="flex items-center gap-2 flex-wrap">
              <h4 className="text-sm font-bold text-slate-900 tracking-tight">
                Manufacturing Quality Reconciliation Engine
              </h4>
              {isConflict ? (
                <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-200/80 text-amber-900 border border-amber-300">
                  Conflict Pending Confirmation
                </span>
              ) : isVerified ? (
                <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-200/80 text-emerald-900 border border-emerald-300">
                  Jan–Aug 2026 Reference Verified
                </span>
              ) : isSynthetic ? (
                <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-indigo-200/80 text-indigo-900 border border-indigo-300">
                  Synthetic Test Fixture Verified
                </span>
              ) : (
                <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-slate-200 text-slate-700">
                  Unverified
                </span>
              )}
            </div>

            <p className="text-xs text-slate-600 max-w-3xl leading-relaxed">
              {report.explanation ||
                "Reconciles calculated and source metrics against approved manufacturing reference figures (Blueprint 2026)."}
            </p>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-3 self-end md:self-center">
          {isConflict && onResolveConflict && (
            <button
              type="button"
              onClick={onResolveConflict}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-amber-600 hover:bg-amber-700 text-white shadow-xs transition-colors"
            >
              Resolve Conflict
            </button>
          )}

          {report.items && report.items.length > 0 && (
            <button
              type="button"
              onClick={() => setIsExpanded(!isExpanded)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-slate-700 hover:text-slate-900 bg-white hover:bg-slate-50 border border-slate-300 transition-colors"
            >
              <span>{isExpanded ? "Hide Details" : "Inspect Reconciliation Table"}</span>
              {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </button>
          )}
        </div>
      </div>

      {/* Expanded Monthly Reference Comparison Table */}
      {isExpanded && report.items && report.items.length > 0 && (
        <div className="border-t border-slate-200/80 bg-white/90 p-4 sm:p-5">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200">
                <tr>
                  <th className="py-2.5 px-3">Reporting Period</th>
                  <th className="py-2.5 px-3 font-mono">Approved Blueprint Reference</th>
                  <th className="py-2.5 px-3 font-mono">Recalculated Actual PPM</th>
                  <th className="py-2.5 px-3 font-mono">Variance (PPM)</th>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-3">Audit Notes</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-800">
                {report.items.map((item) => (
                  <tr key={item.period} className="hover:bg-slate-50/70 transition-colors">
                    <td className="py-2 px-3 font-semibold text-slate-900">{item.period}</td>
                    <td className="py-2 px-3 font-mono text-slate-700">{item.reference_ppm.toLocaleString()}</td>
                    <td className="py-2 px-3 font-mono font-bold">
                      {item.calculated_ppm !== null && item.calculated_ppm !== undefined ? (
                        item.calculated_ppm.toLocaleString()
                      ) : (
                        <span className="text-amber-600 font-normal italic">Locked (Unconfirmed)</span>
                      )}
                    </td>
                    <td className="py-2 px-3 font-mono">
                      {item.variance !== null && item.variance !== undefined ? (
                        <span
                          className={
                            item.variance === 0
                              ? "text-emerald-600"
                              : Math.abs(item.variance) <= 1.5
                              ? "text-emerald-700 font-medium"
                              : "text-rose-600 font-bold"
                          }
                        >
                          {item.variance > 0 ? `+${item.variance}` : item.variance}
                        </span>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>
                    <td className="py-2 px-3">
                      {item.status === "match" ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700">
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                          <span>Match</span>
                        </span>
                      ) : item.status === "conflict_blocked" ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-700">
                          <ShieldAlert className="w-3.5 h-3.5 text-amber-600" />
                          <span>Blocked</span>
                        </span>
                      ) : item.status === "variance" ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-rose-700">
                          <AlertTriangle className="w-3.5 h-3.5 text-rose-600" />
                          <span>Variance</span>
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-500">
                          <Clock className="w-3.5 h-3.5 text-slate-400" />
                          <span>Missing</span>
                        </span>
                      )}
                    </td>
                    <td className="py-2 px-3 text-slate-500 text-[11px]">{item.notes || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
