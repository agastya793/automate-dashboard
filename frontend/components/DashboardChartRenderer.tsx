"use client";

import React from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import { TrendingUp, BarChart3, PieChart as PieIcon, Layers, SlidersHorizontal, AlertTriangle, AlertCircle } from "lucide-react";
import { ComputedChart } from "@/context/DashboardContext";

const PALETTE = [
  "#2563eb", // blue-600
  "#059669", // emerald-600
  "#d97706", // amber-600
  "#7c3aed", // violet-600
  "#0891b2", // cyan-600
  "#e11d48", // rose-600
  "#4f46e5", // indigo-600
  "#0d9488", // teal-600
  "#ea580c", // orange-600
  "#64748b", // slate-500
];

function formatMetricValue(val: any): string {
  if (typeof val !== "number" || isNaN(val)) return String(val ?? "");
  if (Math.abs(val) >= 1_000_000) {
    return (val / 1_000_000).toLocaleString(undefined, { maximumFractionDigits: 2 }) + "M";
  }
  if (Math.abs(val) >= 1_000) {
    return (val / 1_000).toLocaleString(undefined, { maximumFractionDigits: 1 }) + "k";
  }
  if (Number.isInteger(val)) {
    return val.toLocaleString();
  }
  return val.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function ChartIcon({ chartType }: { chartType: string }) {
  switch (chartType) {
    case "line":
      return <TrendingUp className="w-4 h-4 text-blue-600" />;
    case "bar":
    case "vertical_bar":
      return <BarChart3 className="w-4 h-4 text-emerald-600" />;
    case "ranked_bar":
    case "horizontal_bar":
      return <BarChart3 className="w-4 h-4 text-teal-600" />;
    case "donut":
      return <PieIcon className="w-4 h-4 text-purple-600" />;
    case "pie":
      return <PieIcon className="w-4 h-4 text-violet-600" />;
    case "histogram":
      return <SlidersHorizontal className="w-4 h-4 text-amber-600" />;
    case "stacked_bar":
      return <Layers className="w-4 h-4 text-indigo-600" />;
    default:
      return <BarChart3 className="w-4 h-4 text-slate-600" />;
  }
}

export function DashboardChartCard({ chart }: { chart: ComputedChart }) {
  const hasData = chart.data && chart.data.length > 0;

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 flex flex-col justify-between hover:border-slate-300 transition-colors">
      {/* Card Header */}
      <div>
        <div className="flex items-start justify-between gap-3 mb-2">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-slate-100 flex items-center justify-center flex-shrink-0">
              <ChartIcon chartType={chart.chart_type} />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900 tracking-tight leading-snug">
                {chart.title}
              </h3>
              <p className="text-[11px] text-slate-500 font-medium">
                {chart.chart_type.toUpperCase()} · {chart.total_points} point{chart.total_points === 1 ? "" : "s"}
                {chart.config.aggregation ? ` · ${chart.config.aggregation.toUpperCase()}` : ""}
                {chart.config.date_granularity ? ` (${chart.config.date_granularity})` : ""}
                {chart.config.top_n ? ` · Top ${chart.config.top_n}` : ""}
              </p>
            </div>
          </div>

          <span className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
            {chart.config.measure_column || chart.config.dimension_column || "Frequency"}
          </span>
        </div>

        {/* Axis or Configuration hint */}
        {chart.config.measure_column && (
          <p className="text-[11px] text-slate-600 mb-4 font-mono font-medium">
            Measure: {chart.config.measure_column}
          </p>
        )}
      </div>

      {/* Chart Canvas */}
      <div className="w-full my-auto py-2">
        {!hasData ? (
          <div className="h-64 flex flex-col items-center justify-center bg-slate-50 rounded-lg border border-dashed border-slate-200 text-slate-400 p-6 text-center">
            <AlertCircle className="w-6 h-6 mb-2 text-slate-400" />
            <p className="text-xs font-semibold text-slate-700">No Data Points</p>
            <p className="text-[11px] text-slate-500 max-w-xs mt-1">
              No matching records found for this chart after applying filters.
            </p>
          </div>
        ) : chart.chart_type === "line" ? (
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chart.data} margin={{ top: 10, right: 20, left: 0, bottom: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                <XAxis
                  dataKey="label"
                  stroke="#94a3b8"
                  fontSize={11}
                  tickLine={false}
                  dy={6}
                />
                <YAxis
                  stroke="#94a3b8"
                  fontSize={11}
                  tickLine={false}
                  tickFormatter={formatMetricValue}
                  dx={-4}
                />
                <Tooltip
                  formatter={(value: any) => [
                    typeof value === "number" ? value.toLocaleString() : value,
                    chart.config.measure_column || "Value",
                  ]}
                  contentStyle={{
                    backgroundColor: "#ffffff",
                    borderRadius: "8px",
                    border: "1px solid #e2e8f0",
                    fontSize: "12px",
                  }}
                />
                <Legend wrapperStyle={{ fontSize: "11px", paddingTop: "8px" }} />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke="#2563eb"
                  strokeWidth={2.5}
                  dot={{ r: 3, fill: "#2563eb" }}
                  activeDot={{ r: 6 }}
                  name={chart.config.measure_column || "Value"}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : chart.chart_type === "bar" || chart.chart_type === "vertical_bar" ? (
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chart.data} margin={{ top: 10, right: 20, left: 0, bottom: 25 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                <XAxis
                  dataKey="label"
                  stroke="#94a3b8"
                  fontSize={11}
                  tickLine={false}
                  interval={0}
                  angle={chart.data.length > 5 ? -25 : 0}
                  textAnchor={chart.data.length > 5 ? "end" : "middle"}
                  dy={chart.data.length > 5 ? 8 : 4}
                />
                <YAxis
                  stroke="#94a3b8"
                  fontSize={11}
                  tickLine={false}
                  tickFormatter={formatMetricValue}
                  dx={-4}
                />
                <Tooltip
                  formatter={(value: any) => [
                    typeof value === "number" ? value.toLocaleString() : value,
                    chart.config.measure_column || "Value",
                  ]}
                  contentStyle={{
                    backgroundColor: "#ffffff",
                    borderRadius: "8px",
                    border: "1px solid #e2e8f0",
                    fontSize: "12px",
                  }}
                />
                <Bar
                  dataKey="value"
                  fill="#059669"
                  radius={[4, 4, 0, 0]}
                  name={chart.config.measure_column || "Value"}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : chart.chart_type === "ranked_bar" || chart.chart_type === "horizontal_bar" ? (
          <div className="w-full" style={{ height: Math.max(288, chart.data.length * 32) }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                layout="vertical"
                data={chart.data}
                margin={{ top: 10, right: 20, left: 20, bottom: 10 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" horizontal={false} />
                <XAxis
                  type="number"
                  stroke="#94a3b8"
                  fontSize={11}
                  tickLine={false}
                  tickFormatter={formatMetricValue}
                />
                <YAxis
                  type="category"
                  dataKey="label"
                  stroke="#64748b"
                  fontSize={11}
                  tickLine={false}
                  width={100}
                />
                <Tooltip
                  formatter={(value: any) => [
                    typeof value === "number" ? value.toLocaleString() : value,
                    chart.config.measure_column || "Value",
                  ]}
                  contentStyle={{
                    backgroundColor: "#ffffff",
                    borderRadius: "8px",
                    border: "1px solid #e2e8f0",
                    fontSize: "12px",
                  }}
                />
                <Bar
                  dataKey="value"
                  fill="#0d9488"
                  radius={[0, 4, 4, 0]}
                  name={chart.config.measure_column || "Value"}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : chart.chart_type === "donut" || chart.chart_type === "pie" ? (
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart margin={{ top: 10, right: 10, left: 10, bottom: 10 }}>
                <Tooltip
                  formatter={(value: any, name: any, item: any) => {
                    const pct = item?.payload?.percentage;
                    const formatted = typeof value === "number" ? value.toLocaleString() : value;
                    return pct !== undefined ? [`${formatted} (${pct}%)`, name] : [formatted, name];
                  }}
                  contentStyle={{
                    backgroundColor: "#ffffff",
                    borderRadius: "8px",
                    border: "1px solid #e2e8f0",
                    fontSize: "12px",
                  }}
                />
                <Legend wrapperStyle={{ fontSize: "11px" }} />
                <Pie
                  data={chart.data}
                  dataKey="value"
                  nameKey="label"
                  cx="50%"
                  cy="50%"
                  innerRadius={chart.chart_type === "pie" ? 0 : 65}
                  outerRadius={95}
                  paddingAngle={chart.chart_type === "pie" ? 1 : 2}
                >
                  {chart.data.map((_, idx) => (
                    <Cell key={`donut-cell-${idx}`} fill={PALETTE[idx % PALETTE.length]} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
          </div>
        ) : chart.chart_type === "histogram" ? (
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chart.data} margin={{ top: 10, right: 20, left: 0, bottom: 35 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                <XAxis
                  dataKey="label"
                  stroke="#94a3b8"
                  fontSize={10}
                  tickLine={false}
                  interval={0}
                  angle={-25}
                  textAnchor="end"
                  dy={6}
                />
                <YAxis
                  stroke="#94a3b8"
                  fontSize={11}
                  tickLine={false}
                  tickFormatter={(v) => Math.round(v).toString()}
                  dx={-4}
                />
                <Tooltip
                  formatter={(value: any) => [value, "Frequency"]}
                  contentStyle={{
                    backgroundColor: "#ffffff",
                    borderRadius: "8px",
                    border: "1px solid #e2e8f0",
                    fontSize: "12px",
                  }}
                />
                <Bar
                  dataKey="value"
                  fill="#d97706"
                  radius={[3, 3, 0, 0]}
                  name="Record Frequency"
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : chart.chart_type === "stacked_bar" ? (
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chart.data} margin={{ top: 10, right: 20, left: 0, bottom: 25 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                <XAxis
                  dataKey="label"
                  stroke="#94a3b8"
                  fontSize={11}
                  tickLine={false}
                  dy={6}
                />
                <YAxis
                  stroke="#94a3b8"
                  fontSize={11}
                  tickLine={false}
                  tickFormatter={formatMetricValue}
                  dx={-4}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#ffffff",
                    borderRadius: "8px",
                    border: "1px solid #e2e8f0",
                    fontSize: "12px",
                  }}
                />
                <Legend wrapperStyle={{ fontSize: "11px", paddingTop: "8px" }} />
                {(chart.series_keys || []).map((seriesKey, idx) => (
                  <Bar
                    key={seriesKey}
                    dataKey={seriesKey}
                    stackId="stack_all"
                    fill={PALETTE[idx % PALETTE.length]}
                    name={seriesKey}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : null}
      </div>

      {/* Card Footer Warnings / Exclusions */}
      {chart.warnings.length > 0 && (
        <div className="mt-3 pt-2 border-t border-slate-100 flex items-center gap-1.5 text-[11px] text-amber-700 bg-amber-50/70 p-2 rounded">
          <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 text-amber-600" />
          <span>
            {chart.warnings.join(" ")}
          </span>
        </div>
      )}
    </div>
  );
}
