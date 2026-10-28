"use client";

import React, { useState, useMemo } from "react";
import * as echarts from "echarts";
import { BarChart3, Info, SlidersHorizontal, Check } from "lucide-react";
import { EChartsWrapper } from "./EChartsWrapper";

export interface ParetoItem {
  category: string;
  quantity: number;
  cumulative_quantity?: number;
  cumulative_percentage: number;
}

export interface ParetoChartProps {
  title?: string;
  items: ParetoItem[];
  thresholdLine?: number;
  totalCategories?: number;
  displayedCategories?: number;
  provenance?: {
    sheet_name?: string;
    cell_range?: string;
    source_column?: string;
    confirmation_status?: string;
  };
  onOpenProvenance?: () => void;
}

export function ParetoChart({
  title = "Defect Pareto Analysis",
  items,
  thresholdLine = 80.0,
  provenance,
  onOpenProvenance,
}: ParetoChartProps) {
  const [topNChoice, setTopNChoice] = useState<number | "all">(10);

  const filteredItems = useMemo(() => {
    if (topNChoice === "all") return items;
    return items.slice(0, topNChoice);
  }, [items, topNChoice]);

  const chartOption = useMemo<echarts.EChartsOption>(() => {
    if (!filteredItems || filteredItems.length === 0) {
      return { series: [] };
    }

    const categories = filteredItems.map((d) => d.category);
    const quantities = filteredItems.map((d) => d.quantity);
    const cumulativePcts = filteredItems.map((d) => d.cumulative_percentage);

    return {
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(15, 23, 42, 0.95)",
        borderColor: "#334155",
        textStyle: { color: "#f8fafc", fontSize: 12 },
        formatter: (params: any) => {
          if (!Array.isArray(params) || params.length === 0) return "";
          const p = params[0];
          const it = filteredItems[p.dataIndex];
          if (!it) return "";

          return `<div class="font-bold text-xs pb-1 mb-1 border-b border-slate-700">${it.category}</div>
            <div class="flex items-center justify-between gap-4 py-0.5 text-xs">
              <span class="text-indigo-300">Rejections:</span>
              <span class="font-mono font-bold">${it.quantity.toLocaleString()}</span>
            </div>
            <div class="flex items-center justify-between gap-4 py-0.5 text-xs">
              <span class="text-amber-300">Cumulative %:</span>
              <span class="font-mono font-bold text-amber-400">${it.cumulative_percentage.toFixed(1)}%</span>
            </div>`;
        },
      },
      legend: {
        bottom: 0,
        textStyle: { color: "#64748b", fontSize: 11 },
        data: ["Defect Count", "Cumulative %"],
      },
      grid: {
        top: 25,
        left: 50,
        right: 50,
        bottom: 40,
        containLabel: true,
      },
      xAxis: {
        type: "category",
        data: categories,
        axisLine: { lineStyle: { color: "#cbd5e1" } },
        axisLabel: {
          color: "#475569",
          fontSize: 11,
          interval: 0,
          rotate: categories.length > 6 ? 25 : 0,
          formatter: (value: string) => (value.length > 15 ? `${value.substring(0, 14)}…` : value),
        },
      },
      yAxis: [
        {
          type: "value",
          name: "Count",
          nameTextStyle: { color: "#64748b", fontSize: 11, align: "right" },
          splitLine: { lineStyle: { color: "#f1f5f9" } },
          axisLabel: {
            color: "#64748b",
            fontSize: 11,
            formatter: (val: number) => (val >= 1000 ? `${(val / 1000).toFixed(1)}k` : `${val}`),
          },
        },
        {
          type: "value",
          name: "Cumulative %",
          nameTextStyle: { color: "#64748b", fontSize: 11, align: "left" },
          min: 0,
          max: 100,
          splitLine: { show: false },
          axisLabel: {
            color: "#d97706",
            fontSize: 11,
            formatter: "{value}%",
          },
        },
      ],
      series: [
        {
          name: "Defect Count",
          type: "bar",
          yAxisIndex: 0,
          data: quantities,
          barMaxWidth: 36,
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: "#6366f1" },
              { offset: 1, color: "#4338ca" },
            ]),
            borderRadius: [4, 4, 0, 0],
          },
        },
        {
          name: "Cumulative %",
          type: "line",
          yAxisIndex: 1,
          data: cumulativePcts,
          itemStyle: { color: "#f59e0b" },
          lineStyle: { width: 2.5, color: "#f59e0b" },
          symbol: "circle",
          symbolSize: 6,
          markLine: {
            symbol: "none",
            data: [
              {
                yAxis: thresholdLine,
                name: "80% Cutoff",
                lineStyle: { color: "#ef4444", type: "dashed", width: 1.5 },
                label: {
                  formatter: "80% Threshold",
                  position: "end",
                  color: "#ef4444",
                  fontSize: 10,
                },
              },
            ],
          },
        },
      ],
    };
  }, [filteredItems, thresholdLine]);

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-4 hover:border-slate-300 transition-all">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-indigo-50 border border-indigo-200 flex items-center justify-center text-indigo-600">
            <BarChart3 className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-900 tracking-tight flex items-center gap-2">
              <span>{title}</span>
              <span className="text-[11px] font-semibold text-slate-500">
                ({filteredItems.length} categories)
              </span>
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Ranked defects with cumulative impact line and 80% vital-few threshold.
            </p>
          </div>
        </div>

        {/* Top-N Selector and Lineage */}
        <div className="flex items-center gap-2">
          {/* Top-N Toggle */}
          <div className="flex items-center bg-slate-100 rounded-lg p-0.5 text-[11px] font-semibold text-slate-600">
            <button
              type="button"
              onClick={() => setTopNChoice(5)}
              className={`px-2 py-0.5 rounded-md transition-colors ${
                topNChoice === 5 ? "bg-white text-indigo-600 shadow-xs" : "hover:text-slate-900"
              }`}
            >
              Top 5
            </button>
            <button
              type="button"
              onClick={() => setTopNChoice(10)}
              className={`px-2 py-0.5 rounded-md transition-colors ${
                topNChoice === 10 ? "bg-white text-indigo-600 shadow-xs" : "hover:text-slate-900"
              }`}
            >
              Top 10
            </button>
            <button
              type="button"
              onClick={() => setTopNChoice("all")}
              className={`px-2 py-0.5 rounded-md transition-colors ${
                topNChoice === "all" ? "bg-white text-indigo-600 shadow-xs" : "hover:text-slate-900"
              }`}
            >
              All
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

      {/* ECharts Canvas */}
      <EChartsWrapper option={chartOption} className="w-full h-72" />
    </div>
  );
}
