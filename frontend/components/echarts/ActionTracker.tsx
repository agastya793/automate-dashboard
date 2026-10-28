"use client";

import React, { useMemo } from "react";
import * as echarts from "echarts";
import {
  CheckSquare,
  AlertCircle,
  Clock,
  CheckCircle2,
  HelpCircle,
  User,
  Calendar,
  AlertTriangle,
  Info,
} from "lucide-react";
import { EChartsWrapper } from "./EChartsWrapper";

export interface ActionItem {
  id: string;
  status: "open" | "closed" | "overdue" | "unknown";
  owner: string;
  due_date?: string | null;
  closure_date?: string | null;
  is_overdue?: boolean;
  raw_fields?: Record<string, any>;
}

export interface ActionTrackerProps {
  title?: string;
  statusCounts: {
    open: number;
    closed: number;
    overdue: number;
    unknown: number;
  };
  ownerCounts: Record<string, number>;
  actionItems: ActionItem[];
  totalActions?: number;
  warnings?: string[];
  provenance?: {
    sheet_name?: string;
    cell_range?: string;
    source_column?: string;
    confirmation_status?: string;
  };
  onOpenProvenance?: () => void;
}

export function ActionTracker({
  title = "Corrective-Action & Countermeasure Tracker",
  statusCounts,
  ownerCounts,
  actionItems,
  totalActions = 0,
  warnings = [],
  provenance,
  onOpenProvenance,
}: ActionTrackerProps) {
  // Chart option for Owner / Champion breakdown
  const ownerChartOption = useMemo<echarts.EChartsOption>(() => {
    const owners = Object.keys(ownerCounts);
    const counts = Object.values(ownerCounts);

    if (owners.length === 0) {
      return { series: [] };
    }

    return {
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        backgroundColor: "rgba(15, 23, 42, 0.95)",
        borderColor: "#334155",
        textStyle: { color: "#f8fafc", fontSize: 12 },
      },
      grid: {
        top: 10,
        left: 20,
        right: 30,
        bottom: 20,
        containLabel: true,
      },
      xAxis: {
        type: "value",
        axisLine: { lineStyle: { color: "#cbd5e1" } },
        splitLine: { lineStyle: { color: "#f1f5f9" } },
        axisLabel: { color: "#64748b", fontSize: 11 },
      },
      yAxis: {
        type: "category",
        data: owners,
        axisLine: { lineStyle: { color: "#cbd5e1" } },
        axisLabel: { color: "#334155", fontSize: 11 },
      },
      series: [
        {
          name: "Actions Assigned",
          type: "bar",
          data: counts,
          barMaxWidth: 20,
          itemStyle: {
            color: "#6366f1",
            borderRadius: [0, 4, 4, 0],
          },
        },
      ],
    };
  }, [ownerCounts]);

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-6 hover:border-slate-300 transition-all">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-indigo-50 border border-indigo-200 flex items-center justify-center text-indigo-600">
            <CheckSquare className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-900 tracking-tight flex items-center gap-2">
              <span>{title}</span>
              <span className="text-[11px] font-semibold text-slate-500">
                ({totalActions || actionItems.length} total actions)
              </span>
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Countermeasure status derived from confirmed cell-fill colours and worksheet records.
            </p>
          </div>
        </div>

        {provenance && (
          <button
            type="button"
            onClick={onOpenProvenance}
            className="inline-flex items-center gap-1 text-[11px] font-semibold text-indigo-600 hover:text-indigo-700 bg-indigo-50/70 hover:bg-indigo-50 px-2.5 py-1 rounded-lg border border-indigo-200/80 transition-colors"
          >
            <Info className="w-3 h-3" />
            <span>Lineage</span>
          </button>
        )}
      </div>

      {/* Warnings Banner */}
      {warnings.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-800 space-y-1">
          <div className="flex items-center gap-1.5 font-semibold text-amber-900">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
            <span>Action Data Warnings ({warnings.length}):</span>
          </div>
          <ul className="list-disc list-inside text-[11px] space-y-0.5 text-amber-700">
            {warnings.map((w, idx) => (
              <li key={idx}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Status KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {/* Closed */}
        <div className="bg-emerald-50/60 border border-emerald-200 rounded-xl p-3.5 flex items-center justify-between">
          <div>
            <p className="text-[11px] font-semibold text-emerald-800 uppercase tracking-wider">Completed</p>
            <p className="text-xl font-bold text-emerald-950 mt-0.5">{statusCounts.closed || 0}</p>
          </div>
          <div className="w-8 h-8 rounded-lg bg-emerald-100 flex items-center justify-center text-emerald-700">
            <CheckCircle2 className="w-4 h-4" />
          </div>
        </div>

        {/* Open */}
        <div className="bg-blue-50/60 border border-blue-200 rounded-xl p-3.5 flex items-center justify-between">
          <div>
            <p className="text-[11px] font-semibold text-blue-800 uppercase tracking-wider">In Progress / Open</p>
            <p className="text-xl font-bold text-blue-950 mt-0.5">{statusCounts.open || 0}</p>
          </div>
          <div className="w-8 h-8 rounded-lg bg-blue-100 flex items-center justify-center text-blue-700">
            <Clock className="w-4 h-4" />
          </div>
        </div>

        {/* Overdue */}
        <div className="bg-rose-50/60 border border-rose-200 rounded-xl p-3.5 flex items-center justify-between">
          <div>
            <p className="text-[11px] font-semibold text-rose-800 uppercase tracking-wider">Overdue</p>
            <p className="text-xl font-bold text-rose-950 mt-0.5">{statusCounts.overdue || 0}</p>
          </div>
          <div className="w-8 h-8 rounded-lg bg-rose-100 flex items-center justify-center text-rose-700">
            <AlertCircle className="w-4 h-4" />
          </div>
        </div>

        {/* Unknown */}
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-3.5 flex items-center justify-between">
          <div>
            <p className="text-[11px] font-semibold text-slate-700 uppercase tracking-wider">Unknown Status</p>
            <p className="text-xl font-bold text-slate-900 mt-0.5">{statusCounts.unknown || 0}</p>
          </div>
          <div className="w-8 h-8 rounded-lg bg-slate-200/70 flex items-center justify-center text-slate-600">
            <HelpCircle className="w-4 h-4" />
          </div>
        </div>
      </div>

      {/* Main Grid: Owner Breakdown Chart + Action Details Table */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 pt-2">
        {/* Owner Breakdown Chart */}
        <div className="lg:col-span-1 bg-slate-50/50 rounded-xl border border-slate-200/80 p-4">
          <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider mb-2 flex items-center gap-1.5">
            <User className="w-3.5 h-3.5 text-indigo-600" />
            <span>Champion Breakdown</span>
          </h4>
          <EChartsWrapper option={ownerChartOption} className="w-full h-52" />
        </div>

        {/* Action Items Table */}
        <div className="lg:col-span-2 overflow-hidden border border-slate-200 rounded-xl">
          <div className="max-h-60 overflow-y-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-100/90 text-slate-600 font-semibold sticky top-0 border-b border-slate-200">
                <tr>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-3">Description / Item</th>
                  <th className="py-2.5 px-3">Champion</th>
                  <th className="py-2.5 px-3">Due Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-800">
                {actionItems.map((act) => {
                  const desc =
                    act.raw_fields?.Action_Item ||
                    act.raw_fields?.Action ||
                    act.raw_fields?.Item ||
                    act.id;

                  return (
                    <tr key={act.id} className="hover:bg-slate-50/60 transition-colors">
                      <td className="py-2 px-3">
                        {act.status === "closed" && (
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-800">
                            Completed
                          </span>
                        )}
                        {act.status === "open" && (
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-blue-100 text-blue-800">
                            In Progress
                          </span>
                        )}
                        {act.status === "overdue" && (
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-rose-100 text-rose-800">
                            Overdue
                          </span>
                        )}
                        {act.status === "unknown" && (
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-200 text-slate-700">
                            Unmapped
                          </span>
                        )}
                      </td>
                      <td className="py-2 px-3 font-medium text-slate-900 max-w-xs truncate">{desc}</td>
                      <td className="py-2 px-3 text-slate-600">{act.owner}</td>
                      <td className="py-2 px-3 font-mono text-slate-600">
                        {act.due_date ? (
                          <span className={act.is_overdue ? "text-rose-600 font-bold" : ""}>
                            {act.due_date}
                          </span>
                        ) : (
                          <span className="text-slate-400 italic">None</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
