"use client";

import React, { useMemo } from "react";
import * as echarts from "echarts";
import { Grid, Info } from "lucide-react";
import { EChartsWrapper } from "./EChartsWrapper";

export interface PaynterHeatmapProps {
  title?: string;
  xCategories: string[];
  yCategories: string[];
  matrixData: [number, number, number | null][];
  maxValue?: number;
  provenance?: {
    sheet_name?: string;
    cell_range?: string;
    source_column?: string;
    confirmation_status?: string;
  };
  onOpenProvenance?: () => void;
}

export function PaynterHeatmap({
  title = "Paynter Defect Heatmap",
  xCategories,
  yCategories,
  matrixData,
  maxValue = 100,
  provenance,
  onOpenProvenance,
}: PaynterHeatmapProps) {
  const chartOption = useMemo<echarts.EChartsOption>(() => {
    if (!xCategories || !yCategories || matrixData.length === 0) {
      return { series: [] };
    }

    const maxVal = Math.max(
      maxValue,
      ...matrixData.map((d) => (d[2] !== null ? Number(d[2]) : 0))
    );

    return {
      tooltip: {
        position: "top",
        backgroundColor: "rgba(15, 23, 42, 0.95)",
        borderColor: "#334155",
        textStyle: { color: "#f8fafc", fontSize: 12 },
        formatter: (params: any) => {
          const val = params.value;
          if (!val) return "";
          const xLabel = xCategories[val[0]];
          const yLabel = yCategories[val[1]];
          const qty = val[2];

          if (qty === null || qty === undefined) {
            return `<div class="font-bold text-xs pb-1 mb-1 border-b border-slate-700">${yLabel}</div>
              <div class="text-xs text-slate-400">Period: <span class="text-white">${xLabel}</span></div>
              <div class="text-xs text-slate-400 italic mt-0.5">No reported production (future/missing period)</div>`;
          }

          return `<div class="font-bold text-xs pb-1 mb-1 border-b border-slate-700">${yLabel}</div>
            <div class="text-xs text-slate-300">Period: <span class="text-white font-semibold">${xLabel}</span></div>
            <div class="text-xs text-indigo-300 mt-1 font-bold">Rejections: ${qty.toLocaleString()} units</div>`;
        },
      },
      grid: {
        top: 20,
        bottom: 50,
        left: 110,
        right: 40,
        containLabel: true,
      },
      xAxis: {
        type: "category",
        data: xCategories,
        splitArea: { show: true },
        axisLabel: {
          color: "#475569",
          fontSize: 11,
          interval: 0,
        },
        axisLine: { lineStyle: { color: "#cbd5e1" } },
      },
      yAxis: {
        type: "category",
        data: yCategories,
        splitArea: { show: true },
        axisLabel: {
          color: "#334155",
          fontSize: 11,
          formatter: (value: string) => (value.length > 18 ? `${value.substring(0, 17)}…` : value),
        },
        axisLine: { lineStyle: { color: "#cbd5e1" } },
      },
      visualMap: {
        min: 0,
        max: maxVal > 0 ? maxVal : 100,
        calculable: true,
        orient: "horizontal",
        left: "center",
        bottom: 0,
        inRange: {
          color: ["#f1f5f9", "#c7d2fe", "#818cf8", "#4f46e5", "#312e81"],
        },
        textStyle: { color: "#64748b", fontSize: 10 },
      },
      series: [
        {
          name: "Paynter Heatmap",
          type: "heatmap",
          data: matrixData,
          label: {
            show: matrixData.length < 60,
            fontSize: 10,
            color: "#1e1b4b",
            formatter: (p: any) => (p.value[2] !== null && p.value[2] > 0 ? `${p.value[2]}` : ""),
          },
          emphasis: {
            itemStyle: {
              shadowBlur: 10,
              shadowColor: "rgba(0, 0, 0, 0.4)",
            },
          },
        },
      ],
    };
  }, [xCategories, yCategories, matrixData, maxValue]);

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-4 hover:border-slate-300 transition-all">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-indigo-50 border border-indigo-200 flex items-center justify-center text-indigo-600">
            <Grid className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-900 tracking-tight flex items-center gap-2">
              <span>{title}</span>
              <span className="text-[11px] font-semibold text-slate-500">
                ({xCategories.length} months × {yCategories.length} categories)
              </span>
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Recurring defect concentrations across reporting periods. Future months represented as null cells without false zeroes.
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

      {/* ECharts Canvas */}
      <EChartsWrapper option={chartOption} className="w-full h-80" />
    </div>
  );
}
