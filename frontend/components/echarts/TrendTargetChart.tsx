"use client";

import React, { useMemo } from "react";
import * as echarts from "echarts";
import { TrendingUp, AlertTriangle, CheckCircle2, Info, ShieldAlert } from "lucide-react";
import { EChartsWrapper } from "./EChartsWrapper";

export interface PPMDataPoint {
  period: string;
  actual_ppm: number | null;
  target_ppm: number;
  variance?: number | null;
  is_exceeded?: boolean;
}

export interface TrendTargetChartProps {
  title?: string;
  dataPoints: PPMDataPoint[];
  targetPpm?: number;
  exceededCount?: number;
  warnings?: string[];
  provenance?: {
    sheet_name?: string;
    cell_range?: string;
    source_column?: string;
    confirmation_status?: string;
    caveats?: string[];
  };
  onOpenProvenance?: () => void;
}

export function TrendTargetChart({
  title = "Monthly Rejection PPM versus Target",
  dataPoints,
  targetPpm = 2000,
  exceededCount = 0,
  warnings = [],
  provenance,
  onOpenProvenance,
}: TrendTargetChartProps) {
  const chartOption = useMemo<echarts.EChartsOption>(() => {
    if (!dataPoints || dataPoints.length === 0) {
      return { series: [] };
    }

    const periods = dataPoints.map((d) => d.period);
    const actualValues = dataPoints.map((d) => d.actual_ppm);
    const targetValues = dataPoints.map((d) => d.target_ppm || targetPpm);

    return {
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(15, 23, 42, 0.95)",
        borderColor: "#334155",
        textStyle: { color: "#f8fafc", fontSize: 12 },
        formatter: (params: any) => {
          if (!Array.isArray(params) || params.length === 0) return "";
          const p = params[0];
          const dp = dataPoints[p.dataIndex];
          if (!dp) return "";

          let html = `<div class="font-bold text-xs pb-1 mb-1 border-b border-slate-700">${dp.period}</div>`;
          if (dp.actual_ppm !== null && dp.actual_ppm !== undefined) {
            html += `<div class="flex items-center justify-between gap-4 py-0.5 text-xs">
              <span class="text-indigo-300">Actual PPM:</span>
              <span class="font-mono font-bold">${dp.actual_ppm.toLocaleString()}</span>
            </div>`;
          } else {
            html += `<div class="text-xs text-amber-400 italic py-0.5">Calculated PPM Blocked (Conflict Pending)</div>`;
          }

          html += `<div class="flex items-center justify-between gap-4 py-0.5 text-xs">
            <span class="text-slate-400">Target PPM:</span>
            <span class="font-mono">${dp.target_ppm.toLocaleString()}</span>
          </div>`;

          if (dp.variance !== null && dp.variance !== undefined) {
            const varColor = dp.variance > 0 ? "text-rose-400" : "text-emerald-400";
            const sign = dp.variance > 0 ? "+" : "";
            html += `<div class="flex items-center justify-between gap-4 py-0.5 text-xs">
              <span class="text-slate-400">Variance:</span>
              <span class="font-mono font-semibold ${varColor}">${sign}${dp.variance.toLocaleString()} PPM</span>
            </div>`;
          }

          return html;
        },
      },
      legend: {
        bottom: 0,
        textStyle: { color: "#64748b", fontSize: 11 },
        data: ["Actual PPM", "PPM Target"],
      },
      grid: {
        top: 25,
        left: 50,
        right: 25,
        bottom: 40,
        containLabel: true,
      },
      xAxis: {
        type: "category",
        data: periods,
        axisLine: { lineStyle: { color: "#cbd5e1" } },
        axisLabel: { color: "#64748b", fontSize: 11 },
      },
      yAxis: {
        type: "value",
        name: "PPM",
        nameTextStyle: { color: "#64748b", fontSize: 11, align: "right" },
        splitLine: { lineStyle: { color: "#f1f5f9" } },
        axisLabel: {
          color: "#64748b",
          fontSize: 11,
          formatter: (val: number) => (val >= 1000 ? `${(val / 1000).toFixed(1)}k` : `${val}`),
        },
      },
      series: [
        {
          name: "Actual PPM",
          type: "line",
          data: actualValues,
          smooth: true,
          showSymbol: true,
          symbolSize: 7,
          itemStyle: { color: "#4f46e5" },
          lineStyle: { width: 3, color: "#4f46e5" },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: "rgba(79, 70, 229, 0.25)" },
              { offset: 1, color: "rgba(79, 70, 229, 0.0)" },
            ]),
          },
          markPoint: {
            data: dataPoints
              .map((dp, idx) =>
                dp.is_exceeded
                  ? {
                      name: "Target Exceeded",
                      coord: [idx, dp.actual_ppm],
                      value: "!",
                      itemStyle: { color: "#e11d48" },
                    }
                  : null
              )
              .filter(Boolean) as any[],
          },
        },
        {
          name: "PPM Target",
          type: "line",
          data: targetValues,
          lineStyle: {
            width: 2,
            type: "dashed",
            color: "#e11d48",
          },
          itemStyle: { color: "#e11d48" },
          symbol: "none",
        },
      ],
    };
  }, [dataPoints, targetPpm]);

  const hasBlockedPPM = dataPoints.some((d) => d.actual_ppm === null);

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-4 hover:border-slate-300 transition-all">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-indigo-50 border border-indigo-200 flex items-center justify-center text-indigo-600">
            <TrendingUp className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-900 tracking-tight flex items-center gap-2">
              <span>{title}</span>
              {exceededCount > 0 ? (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-rose-50 text-rose-700 border border-rose-200">
                  <AlertTriangle className="w-3 h-3 text-rose-600" />
                  <span>Target exceeded in {exceededCount} period{exceededCount === 1 ? "" : "s"}</span>
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                  <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                  <span>Within Target</span>
                </span>
              )}
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Verified monthly rejection PPM plotted against the configured {targetPpm.toLocaleString()} PPM ceiling.
            </p>
          </div>
        </div>

        {/* Provenance Button */}
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

      {/* Warnings & Conflict Notification */}
      {hasBlockedPPM && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-800 flex items-start gap-2">
          <ShieldAlert className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
          <div className="space-y-0.5">
            <span className="font-semibold text-amber-900">Denominator Conflict Guard Active:</span>
            <p>
              Calculated PPM values are locked from publication because the January production total
              (37,111 in breakdown vs 46,816 in overview) requires confirmation in the Mapping Workspace.
            </p>
          </div>
        </div>
      )}

      {/* ECharts Canvas */}
      <EChartsWrapper option={chartOption} className="w-full h-72" />
    </div>
  );
}
