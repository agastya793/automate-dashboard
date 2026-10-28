"use client";

import React, { useState, useMemo } from "react";
import * as echarts from "echarts";
import { Layers, Info, ShieldCheck, Eye } from "lucide-react";
import { EChartsWrapper } from "./EChartsWrapper";

export interface ModelSeriesItem {
  name: string;
  total: number;
  period_data: number[];
}

export interface ModelComparisonChartProps {
  title?: string;
  periods: string[];
  models: string[];
  series: ModelSeriesItem[];
  provenance?: {
    sheet_name?: string;
    cell_range?: string;
    source_column?: string;
    confirmation_status?: string;
  };
  onOpenProvenance?: () => void;
}

const MODEL_PALETTE = [
  "#4f46e5", // Indigo (157 TY)
  "#0891b2", // Cyan (367 TY)
  "#d97706", // Amber (457 TY)
  "#e11d48", // Rose (Milwaukee)
  "#059669", // Emerald
  "#7c3aed", // Violet
];

export function ModelComparisonChart({
  title = "Model-Level Rejection Comparison",
  periods,
  models,
  series,
  provenance,
  onOpenProvenance,
}: ModelComparisonChartProps) {
  const [isStacked, setIsStacked] = useState(false);

  const chartOption = useMemo<echarts.EChartsOption>(() => {
    if (!periods || periods.length === 0 || !series || series.length === 0) {
      return { series: [] };
    }

    const echartsSeries = series.map((s, idx) => ({
      name: s.name,
      type: "bar" as const,
      stack: isStacked ? "total_models" : undefined,
      data: s.period_data,
      barMaxWidth: 30,
      itemStyle: {
        color: MODEL_PALETTE[idx % MODEL_PALETTE.length],
        borderRadius: isStacked ? undefined : [4, 4, 0, 0],
      },
    }));

    return {
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        backgroundColor: "rgba(15, 23, 42, 0.95)",
        borderColor: "#334155",
        textStyle: { color: "#f8fafc", fontSize: 12 },
        formatter: (params: any) => {
          if (!Array.isArray(params) || params.length === 0) return "";
          let html = `<div class="font-bold text-xs pb-1 mb-1 border-b border-slate-700">${params[0].axisValue}</div>`;
          let periodTotal = 0;

          params.forEach((p: any) => {
            const val = Number(p.value) || 0;
            periodTotal += val;
            html += `<div class="flex items-center justify-between gap-4 py-0.5 text-xs">
              <span class="flex items-center gap-1.5">
                <span class="w-2.5 h-2.5 rounded-full inline-block" style="background-color: ${p.color}"></span>
                <span class="text-slate-300">${p.seriesName}:</span>
              </span>
              <span class="font-mono font-semibold">${val.toLocaleString()} units</span>
            </div>`;
          });

          if (params.length > 1) {
            html += `<div class="flex items-center justify-between gap-4 pt-1 mt-1 border-t border-slate-700 text-xs font-bold">
              <span class="text-slate-400">Total Rejections:</span>
              <span class="font-mono text-indigo-300">${periodTotal.toLocaleString()} units</span>
            </div>`;
          }

          return html;
        },
      },
      legend: {
        bottom: 0,
        textStyle: { color: "#64748b", fontSize: 11 },
        data: series.map((s) => s.name),
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
        name: "Rejection Qty",
        nameTextStyle: { color: "#64748b", fontSize: 11, align: "right" },
        splitLine: { lineStyle: { color: "#f1f5f9" } },
        axisLabel: {
          color: "#64748b",
          fontSize: 11,
          formatter: (val: number) => (val >= 1000 ? `${(val / 1000).toFixed(1)}k` : `${val}`),
        },
      },
      series: echartsSeries,
    };
  }, [periods, series, isStacked]);

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-4 hover:border-slate-300 transition-all">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-indigo-50 border border-indigo-200 flex items-center justify-center text-indigo-600">
            <Layers className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-900 tracking-tight flex items-center gap-2">
              <span>{title}</span>
              <span className="text-[11px] font-semibold text-slate-500">
                ({models.length} product models)
              </span>
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Direct comparison of defect quantities across models.
            </p>
          </div>
        </div>

        {/* View Toggle and Lineage */}
        <div className="flex items-center gap-2">
          {/* Stacked / Grouped Toggle */}
          <div className="flex items-center bg-slate-100 rounded-lg p-0.5 text-[11px] font-semibold text-slate-600">
            <button
              type="button"
              onClick={() => setIsStacked(false)}
              className={`px-2 py-0.5 rounded-md transition-colors ${
                !isStacked ? "bg-white text-indigo-600 shadow-xs" : "hover:text-slate-900"
              }`}
            >
              Grouped
            </button>
            <button
              type="button"
              onClick={() => setIsStacked(true)}
              className={`px-2 py-0.5 rounded-md transition-colors ${
                isStacked ? "bg-white text-indigo-600 shadow-xs" : "hover:text-slate-900"
              }`}
            >
              Stacked
            </button>
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
      </div>

      {/* Strict Architecture Notice */}
      <div className="bg-slate-50 border border-slate-200 rounded-lg p-2.5 text-[11px] text-slate-600 flex items-center gap-2">
        <ShieldCheck className="w-4 h-4 text-indigo-600 flex-shrink-0" />
        <span>
          <strong>Architecture Rule Enforced:</strong> Rejection quantities are compared directly.
          Averaging or summing PPM across disparate product models without verified joint denominators is strictly prohibited.
        </span>
      </div>

      {/* ECharts Canvas */}
      <EChartsWrapper option={chartOption} className="w-full h-72" />
    </div>
  );
}
