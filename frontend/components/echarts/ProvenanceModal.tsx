"use client";

import React from "react";
import { X, Database, Table, Layers, FileSpreadsheet, ShieldCheck, AlertTriangle } from "lucide-react";

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

export interface ProvenanceModalProps {
  isOpen: boolean;
  onClose: () => void;
  widgetTitle: string;
  provenance: ProvenanceDetails | null;
}

export function ProvenanceModal({
  isOpen,
  onClose,
  widgetTitle,
  provenance,
}: ProvenanceModalProps) {
  if (!isOpen || !provenance) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs animate-in fade-in duration-200">
      <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-lg w-full overflow-hidden">
        {/* Modal Header */}
        <div className="bg-slate-900 text-white p-5 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-indigo-500/20 border border-indigo-400/30 flex items-center justify-center text-indigo-300">
              <Database className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-white tracking-tight">Metric Provenance & Lineage</h3>
              <p className="text-[11px] text-slate-400 truncate max-w-xs">{widgetTitle}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 space-y-4 text-xs">
          {/* Status Badge */}
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <span className="font-semibold text-slate-600">Verification Status:</span>
            {provenance.confirmation_status === "confirmed" ? (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
                <span>User Confirmed</span>
              </span>
            ) : provenance.confirmation_status === "unconfirmed_conflict" ? (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-amber-50 text-amber-800 border border-amber-200">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
                <span>Unconfirmed Conflict</span>
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
                <span>Source Measure</span>
              </span>
            )}
          </div>

          {/* Lineage Table */}
          <div className="space-y-2.5 text-slate-700">
            <div className="flex items-center justify-between py-1 border-b border-slate-100">
              <span className="text-slate-500 flex items-center gap-1.5">
                <FileSpreadsheet className="w-3.5 h-3.5 text-slate-400" />
                <span>Worksheet:</span>
              </span>
              <span className="font-mono font-semibold text-slate-900">{provenance.sheet_name || "N/A"}</span>
            </div>

            <div className="flex items-center justify-between py-1 border-b border-slate-100">
              <span className="text-slate-500 flex items-center gap-1.5">
                <Table className="w-3.5 h-3.5 text-slate-400" />
                <span>Detected Range:</span>
              </span>
              <span className="font-mono font-semibold text-slate-900">{provenance.cell_range || "N/A"}</span>
            </div>

            <div className="flex items-center justify-between py-1 border-b border-slate-100">
              <span className="text-slate-500 flex items-center gap-1.5">
                <Layers className="w-3.5 h-3.5 text-slate-400" />
                <span>Source Column:</span>
              </span>
              <span className="font-mono font-semibold text-slate-900">{provenance.source_column || "N/A"}</span>
            </div>

            <div className="flex items-center justify-between py-1 border-b border-slate-100">
              <span className="text-slate-500">Aggregation Applied:</span>
              <span className="font-mono uppercase font-semibold text-slate-900">{provenance.aggregation || "SUM"}</span>
            </div>

            {provenance.calculation_applied && (
              <div className="py-2 bg-slate-50 rounded-lg p-3 border border-slate-200 space-y-1">
                <span className="font-semibold text-slate-700 block">Calculation Applied:</span>
                <code className="text-[11px] font-mono text-indigo-700 block bg-white px-2 py-1 rounded border border-slate-200">
                  {provenance.calculation_applied}
                </code>
              </div>
            )}
          </div>

          {/* Caveats */}
          {provenance.caveats && provenance.caveats.length > 0 && (
            <div className="bg-amber-50 rounded-lg p-3 border border-amber-200 space-y-1">
              <span className="font-semibold text-amber-900 flex items-center gap-1">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
                <span>Caveats & Reconciliations:</span>
              </span>
              <ul className="list-disc list-inside text-[11px] text-amber-800 space-y-0.5">
                {provenance.caveats.map((c, idx) => (
                  <li key={idx}>{c}</li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="bg-slate-50 px-6 py-3 border-t border-slate-200 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs font-semibold text-slate-700 hover:text-slate-900 bg-white hover:bg-slate-100 border border-slate-300 rounded-lg shadow-2xs transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
