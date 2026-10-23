"use client";

import { useState, useEffect } from "react";
import {
  TrendingUp,
  BarChart3,
  PieChart,
  Layers,
  SlidersHorizontal,
  Check,
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  RotateCcw,
  EyeOff,
  Eye,
  Settings2,
  ChevronDown,
  ChevronUp,
  Sparkles,
  Info,
} from "lucide-react";
import { ColumnProfile } from "@/app/upload/page";

// ---------------------------------------------------------------------------
// Types matching backend Phase 3 contract
// ---------------------------------------------------------------------------

export interface ChartRecommendation {
  id: string;
  title: string;
  chart_type: string; // "line", "bar", "ranked_bar", "donut", "histogram", "stacked_bar"
  dimension_column?: string | null;
  secondary_dimension_column?: string | null;
  date_column?: string | null;
  measure_column?: string | null;
  suggested_aggregation: string;
  supported_aggregations: string[];
  sort_order?: string | null;
  top_n?: number | null;
  supported_top_n?: number[] | null;
  date_granularity?: string | null;
  supported_date_granularities?: string[] | null;
  explanation: string;
  suitability: string; // "high", "medium", "exploratory"
  suitability_reason: string;
  caveats: string[];
  requires_confirmation: boolean;
}

export interface ConfiguredChart {
  id: string;
  selected: boolean;
  dismissed: boolean;
  isConfirmed: boolean;
  userModified: boolean;
  isCustomizing: boolean;
  chart_type: string;
  dimension_column: string | null;
  secondary_dimension_column: string | null;
  date_column: string | null;
  measure_column: string | null;
  aggregation: string;
  date_granularity: string | null;
  top_n: number | null;
  original: ChartRecommendation;
}

interface RecommendedChartsProps {
  recommendations: ChartRecommendation[];
  columns: ColumnProfile[];
  onChartsChange?: (charts: ConfiguredChart[]) => void;
  initialCharts?: ConfiguredChart[];
}

// ---------------------------------------------------------------------------
// Chart Type Badge
// ---------------------------------------------------------------------------

function ChartTypeBadge({ chartType }: { chartType: string }) {
  switch (chartType) {
    case "line":
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-blue-50 text-blue-700 border border-blue-200">
          <TrendingUp className="w-3 h-3 text-blue-500" />
          <span>Line Trend</span>
        </span>
      );
    case "bar":
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
          <BarChart3 className="w-3 h-3 text-emerald-500" />
          <span>Category Bar</span>
        </span>
      );
    case "ranked_bar":
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-teal-50 text-teal-700 border border-teal-200">
          <BarChart3 className="w-3 h-3 text-teal-500" />
          <span>Ranked Top-N</span>
        </span>
      );
    case "donut":
    case "pie":
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-purple-50 text-purple-700 border border-purple-200">
          <PieChart className="w-3 h-3 text-purple-500" />
          <span>Donut Share</span>
        </span>
      );
    case "histogram":
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
          <SlidersHorizontal className="w-3 h-3 text-amber-500" />
          <span>Histogram</span>
        </span>
      );
    case "stacked_bar":
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
          <Layers className="w-3 h-3 text-indigo-500" />
          <span>Stacked Bar</span>
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-100 text-slate-700 border border-slate-200">
          <BarChart3 className="w-3 h-3 text-slate-500" />
          <span>{chartType}</span>
        </span>
      );
  }
}

// ---------------------------------------------------------------------------
// Suitability Badge
// ---------------------------------------------------------------------------

function SuitabilityBadge({ suitability }: { suitability: string }) {
  switch (suitability.toLowerCase()) {
    case "high":
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide bg-emerald-100 text-emerald-800">
          High Confidence
        </span>
      );
    case "medium":
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide bg-blue-100 text-blue-800">
          Standard Fit
        </span>
      );
    case "exploratory":
    default:
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide bg-purple-100 text-purple-800">
          Exploratory
        </span>
      );
  }
}

// ---------------------------------------------------------------------------
// Main Recommended Charts Component
// ---------------------------------------------------------------------------

export function RecommendedCharts({
  recommendations,
  columns,
  onChartsChange,
  initialCharts,
}: RecommendedChartsProps) {
  // Initialize state from recommendations or initialCharts
  const [charts, setCharts] = useState<ConfiguredChart[]>(() => {
    if (initialCharts && initialCharts.length > 0) {
      return initialCharts;
    }
    return recommendations.map((rec) => ({
      id: rec.id,
      selected: true, // Default to selected
      dismissed: false,
      isConfirmed: false,
      userModified: false,
      isCustomizing: false,
      chart_type: rec.chart_type,
      dimension_column: rec.dimension_column ?? null,
      secondary_dimension_column: rec.secondary_dimension_column ?? null,
      date_column: rec.date_column ?? null,
      measure_column: rec.measure_column ?? null,
      aggregation: rec.suggested_aggregation,
      date_granularity: rec.date_granularity ?? null,
      top_n: rec.top_n ?? null,
      original: rec,
    }));
  });

  useEffect(() => {
    onChartsChange?.(charts);
  }, [charts, onChartsChange]);

  const [showDismissed, setShowDismissed] = useState(false);

  // Column categorization for dropdowns
  const dateOptions = columns.filter((c) => c.inferred_type === "date").map((c) => c.name);
  const measureOptions = columns
    .filter((c) => ["numeric", "currency", "percentage"].includes(c.inferred_type))
    .map((c) => c.name);
  const dimensionOptions = columns
    .filter((c) => ["categorical", "boolean", "identifier", "text"].includes(c.inferred_type))
    .map((c) => c.name);

  // Toggle selection
  const handleToggleSelect = (id: string) => {
    setCharts((prev) =>
      prev.map((c) => (c.id === id ? { ...c, selected: !c.selected } : c))
    );
  };

  // Dismiss recommendation
  const handleDismiss = (id: string) => {
    setCharts((prev) =>
      prev.map((c) => (c.id === id ? { ...c, dismissed: true, selected: false } : c))
    );
  };

  // Restore dismissed recommendation
  const handleRestore = (id: string) => {
    setCharts((prev) =>
      prev.map((c) => (c.id === id ? { ...c, dismissed: false, selected: true } : c))
    );
  };

  // Toggle customization panel
  const handleToggleCustomize = (id: string) => {
    setCharts((prev) =>
      prev.map((c) => (c.id === id ? { ...c, isCustomizing: !c.isCustomizing } : c))
    );
  };

  // Confirm configuration
  const handleConfirm = (id: string) => {
    setCharts((prev) =>
      prev.map((c) => (c.id === id ? { ...c, isConfirmed: true, isCustomizing: false } : c))
    );
  };

  // Confirm all selected configurations
  const handleConfirmAll = () => {
    setCharts((prev) =>
      prev.map((c) =>
        c.selected && !c.dismissed ? { ...c, isConfirmed: true, isCustomizing: false } : c
      )
    );
  };

  // Reset to original defaults
  const handleReset = (id: string) => {
    setCharts((prev) =>
      prev.map((c) => {
        if (c.id !== id) return c;
        const o = c.original;
        return {
          ...c,
          userModified: false,
          isConfirmed: false,
          chart_type: o.chart_type,
          dimension_column: o.dimension_column ?? null,
          secondary_dimension_column: o.secondary_dimension_column ?? null,
          date_column: o.date_column ?? null,
          measure_column: o.measure_column ?? null,
          aggregation: o.suggested_aggregation,
          date_granularity: o.date_granularity ?? null,
          top_n: o.top_n ?? null,
        };
      })
    );
  };

  // Update field value
  const handleUpdateField = (
    id: string,
    field: keyof ConfiguredChart,
    value: string | number | null
  ) => {
    setCharts((prev) =>
      prev.map((c) => {
        if (c.id !== id) return c;
        return {
          ...c,
          [field]: value,
          userModified: true,
          isConfirmed: false, // Reset confirmation if user edits field
        };
      })
    );
  };

  const activeCharts = charts.filter((c) => !c.dismissed);
  const dismissedCharts = charts.filter((c) => c.dismissed);
  const selectedCount = activeCharts.filter((c) => c.selected).length;
  const confirmedCount = activeCharts.filter((c) => c.selected && c.isConfirmed).length;

  if (recommendations.length === 0) {
    return (
      <section
        aria-labelledby="recommendations-heading"
        className="bg-white rounded-xl border border-slate-200 p-8 shadow-sm space-y-4"
      >
        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-amber-500" />
          <h2
            id="recommendations-heading"
            className="text-base font-semibold text-slate-900 tracking-tight"
          >
            Recommended Charts
          </h2>
        </div>

        <div className="p-6 rounded-xl bg-slate-50 border border-slate-200 text-center space-y-3">
          <div className="w-10 h-10 rounded-full bg-slate-200/70 text-slate-500 flex items-center justify-center mx-auto">
            <Info className="w-5 h-5" />
          </div>
          <div className="space-y-1">
            <h3 className="text-sm font-semibold text-slate-800">
              No Automatic Chart Recommendations Available
            </h3>
            <p className="text-xs text-slate-500 max-w-lg mx-auto leading-relaxed">
              The recommendation engine could not identify suitable pairs of categorical dimensions, temporal dates, or quantitative measures in this sheet. Ensure your table contains column headers with dates, category names, or numeric values rather than purely arbitrary identifiers.
            </p>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section
      aria-labelledby="recommendations-heading"
      className="bg-white rounded-xl border border-slate-200 p-6 sm:p-7 shadow-sm space-y-6"
    >
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-brand-600" />
            <h2
              id="recommendations-heading"
              className="text-base font-semibold text-slate-900 tracking-tight"
            >
              Step 5: Recommended Charts ({activeCharts.length})
            </h2>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Deterministic visualizations generated from column schema analysis. Review mappings, adjust aggregations, or dismiss suggestions.
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-slate-100 text-slate-700 border border-slate-200">
            {selectedCount} of {activeCharts.length} selected
          </span>
          {confirmedCount < selectedCount && (
            <button
              type="button"
              onClick={handleConfirmAll}
              className="inline-flex items-center gap-1.5 px-3 py-1 text-xs font-semibold text-emerald-800 bg-emerald-100 hover:bg-emerald-200 rounded-md border border-emerald-300 transition-colors shadow-xs"
            >
              <Check className="w-3.5 h-3.5" />
              <span>Confirm All ({selectedCount})</span>
            </button>
          )}
          {dismissedCharts.length > 0 && (
            <button
              type="button"
              onClick={() => setShowDismissed(!showDismissed)}
              className="text-xs text-slate-600 hover:text-slate-900 underline underline-offset-2 flex items-center gap-1"
            >
              <Eye className="w-3.5 h-3.5" />
              <span>{showDismissed ? "Hide" : "Show"} dismissed ({dismissedCharts.length})</span>
            </button>
          )}
        </div>
      </div>

      {/* Recommendations Cards Grid */}
      <div className="space-y-4">
        {activeCharts.map((chart) => {
          const rec = chart.original;
          const isSelected = chart.selected;

          return (
            <div
              key={chart.id}
              className={`rounded-xl border transition-all ${
                isSelected
                  ? "border-brand-200 bg-brand-50/20 shadow-xs"
                  : "border-slate-200 bg-white opacity-70 hover:opacity-100"
              }`}
            >
              {/* Card Header & Controls */}
              <div className="p-5 flex flex-col md:flex-row md:items-start justify-between gap-4">
                <div className="flex items-start gap-3.5 min-w-0">
                  {/* Select Checkbox Button */}
                  <button
                    type="button"
                    onClick={() => handleToggleSelect(chart.id)}
                    className={`mt-0.5 w-5 h-5 rounded flex items-center justify-center transition-colors border flex-shrink-0 ${
                      isSelected
                        ? "bg-brand-600 text-white border-brand-600 shadow-xs"
                        : "bg-white text-transparent border-slate-300 hover:border-slate-400"
                    }`}
                    title={isSelected ? "Deselect chart" : "Select chart for reporting"}
                    aria-label={`Toggle selection for ${rec.title}`}
                  >
                    <Check className="w-3.5 h-3.5 stroke-[3]" />
                  </button>

                  <div className="space-y-1.5 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="text-sm font-bold text-slate-900 tracking-tight">
                        {rec.title}
                      </h3>
                      <ChartTypeBadge chartType={chart.chart_type} />
                      <SuitabilityBadge suitability={rec.suitability} />

                      {/* Confirmation Status */}
                      {chart.isConfirmed ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
                          <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                          <span>Reviewed</span>
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-50 text-amber-800 border border-amber-200">
                          <AlertCircle className="w-3 h-3 text-amber-600" />
                          <span>Requires Confirmation</span>
                        </span>
                      )}

                      {chart.userModified && (
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-200 text-slate-700">
                          Customized
                        </span>
                      )}
                    </div>

                    <p className="text-xs text-slate-600 leading-relaxed max-w-3xl">
                      {rec.explanation}
                    </p>

                    {/* Column Mappings Chips */}
                    <div className="flex items-center gap-2 pt-1 flex-wrap text-[11px] text-slate-600">
                      {chart.date_column && (
                        <span className="px-2 py-0.5 rounded bg-blue-50 text-blue-800 border border-blue-200 font-mono">
                          Date: {chart.date_column} ({chart.date_granularity || "auto"})
                        </span>
                      )}
                      {chart.dimension_column && (
                        <span className="px-2 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200 font-mono">
                          Dimension: {chart.dimension_column}
                        </span>
                      )}
                      {chart.secondary_dimension_column && (
                        <span className="px-2 py-0.5 rounded bg-purple-50 text-purple-800 border border-purple-200 font-mono">
                          Secondary: {chart.secondary_dimension_column}
                        </span>
                      )}
                      {chart.measure_column ? (
                        <span className="px-2 py-0.5 rounded bg-emerald-50 text-emerald-800 border border-emerald-200 font-mono">
                          Measure: {chart.measure_column} ({chart.aggregation})
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200 font-mono">
                          Metric: Record Count
                        </span>
                      )}
                      {chart.top_n && (
                        <span className="px-2 py-0.5 rounded bg-teal-50 text-teal-800 border border-teal-200 font-mono">
                          Top {chart.top_n}
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Action Buttons */}
                <div className="flex items-center gap-2 self-end md:self-start flex-shrink-0">
                  <button
                    type="button"
                    onClick={() => handleToggleCustomize(chart.id)}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 rounded-lg border border-slate-200 shadow-xs transition-colors"
                  >
                    <Settings2 className="w-3.5 h-3.5 text-slate-500" />
                    <span>Customize</span>
                    {chart.isCustomizing ? (
                      <ChevronUp className="w-3.5 h-3.5 text-slate-400" />
                    ) : (
                      <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
                    )}
                  </button>

                  <button
                    type="button"
                    onClick={() => handleDismiss(chart.id)}
                    className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
                    title="Dismiss recommendation"
                    aria-label="Dismiss recommendation"
                  >
                    <EyeOff className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {/* Caveats Banner */}
              {rec.caveats && rec.caveats.length > 0 && (
                <div className="px-5 pb-3">
                  <div className="p-2.5 rounded-lg bg-amber-50/70 border border-amber-200/70 text-[11px] text-amber-900 space-y-1">
                    <div className="flex items-center gap-1.5 font-semibold text-amber-800">
                      <AlertTriangle className="w-3 h-3 text-amber-600 flex-shrink-0" />
                      <span>Review Considerations:</span>
                    </div>
                    <ul className="pl-5 list-disc space-y-0.5 text-amber-900/90">
                      {rec.caveats.map((cav, idx) => (
                        <li key={idx}>{cav}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}

              {/* Customization Drawer / Inline Panel */}
              {chart.isCustomizing && (
                <div className="p-5 border-t border-slate-200/90 bg-slate-50/80 rounded-b-xl space-y-4">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                      Adjust Column Mapping & Aggregations
                    </p>
                    {chart.userModified && (
                      <button
                        type="button"
                        onClick={() => handleReset(chart.id)}
                        className="inline-flex items-center gap-1 text-[11px] text-slate-500 hover:text-slate-800"
                      >
                        <RotateCcw className="w-3 h-3" />
                        <span>Reset to Defaults</span>
                      </button>
                    )}
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {/* Dimension Selector */}
                    {chart.dimension_column !== undefined && (
                      <div className="space-y-1">
                        <label className="text-[11px] font-semibold text-slate-700">
                          Primary Dimension (Category)
                        </label>
                        <select
                          value={chart.dimension_column || ""}
                          onChange={(e) =>
                            handleUpdateField(chart.id, "dimension_column", e.target.value || null)
                          }
                          className="w-full text-xs py-1.5 px-2.5 rounded-lg border border-slate-300 bg-white text-slate-800 focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500"
                        >
                          <option value="">(None)</option>
                          {dimensionOptions.map((opt) => (
                            <option key={opt} value={opt}>
                              {opt}
                            </option>
                          ))}
                        </select>
                      </div>
                    )}

                    {/* Secondary Dimension Selector */}
                    {chart.secondary_dimension_column !== undefined && (
                      <div className="space-y-1">
                        <label className="text-[11px] font-semibold text-slate-700">
                          Secondary Dimension (Segment)
                        </label>
                        <select
                          value={chart.secondary_dimension_column || ""}
                          onChange={(e) =>
                            handleUpdateField(
                              chart.id,
                              "secondary_dimension_column",
                              e.target.value || null
                            )
                          }
                          className="w-full text-xs py-1.5 px-2.5 rounded-lg border border-slate-300 bg-white text-slate-800 focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500"
                        >
                          <option value="">(None)</option>
                          {dimensionOptions.map((opt) => (
                            <option key={opt} value={opt}>
                              {opt}
                            </option>
                          ))}
                        </select>
                      </div>
                    )}

                    {/* Date Column Selector */}
                    {chart.date_column !== undefined && (
                      <div className="space-y-1">
                        <label className="text-[11px] font-semibold text-slate-700">
                          Date Column (Time Axis)
                        </label>
                        <select
                          value={chart.date_column || ""}
                          onChange={(e) =>
                            handleUpdateField(chart.id, "date_column", e.target.value || null)
                          }
                          className="w-full text-xs py-1.5 px-2.5 rounded-lg border border-slate-300 bg-white text-slate-800 focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500"
                        >
                          <option value="">(None)</option>
                          {dateOptions.map((opt) => (
                            <option key={opt} value={opt}>
                              {opt}
                            </option>
                          ))}
                        </select>
                      </div>
                    )}

                    {/* Measure Column Selector */}
                    <div className="space-y-1">
                      <label className="text-[11px] font-semibold text-slate-700">
                        Numeric Measure
                      </label>
                      <select
                        value={chart.measure_column || ""}
                        onChange={(e) =>
                          handleUpdateField(chart.id, "measure_column", e.target.value || null)
                        }
                        className="w-full text-xs py-1.5 px-2.5 rounded-lg border border-slate-300 bg-white text-slate-800 focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500"
                      >
                        <option value="">(None - Record Count)</option>
                        {measureOptions.map((opt) => (
                          <option key={opt} value={opt}>
                            {opt}
                          </option>
                        ))}
                      </select>
                    </div>

                    {/* Aggregation Selector */}
                    <div className="space-y-1">
                      <label className="text-[11px] font-semibold text-slate-700">
                        Aggregation Method
                      </label>
                      <select
                        value={chart.aggregation}
                        onChange={(e) =>
                          handleUpdateField(chart.id, "aggregation", e.target.value)
                        }
                        className="w-full text-xs py-1.5 px-2.5 rounded-lg border border-slate-300 bg-white text-slate-800 focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500"
                      >
                        {rec.supported_aggregations.map((agg) => (
                          <option key={agg} value={agg}>
                            {agg.toUpperCase()}
                          </option>
                        ))}
                      </select>
                    </div>

                    {/* Date Granularity (if line trend) */}
                    {rec.supported_date_granularities && (
                      <div className="space-y-1">
                        <label className="text-[11px] font-semibold text-slate-700">
                          Date Granularity
                        </label>
                        <select
                          value={chart.date_granularity || "day"}
                          onChange={(e) =>
                            handleUpdateField(chart.id, "date_granularity", e.target.value)
                          }
                          className="w-full text-xs py-1.5 px-2.5 rounded-lg border border-slate-300 bg-white text-slate-800 focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500"
                        >
                          {rec.supported_date_granularities.map((g: string) => (
                            <option key={g} value={g}>
                              {g.charAt(0).toUpperCase() + g.slice(1)}
                            </option>
                          ))}
                        </select>
                      </div>
                    )}

                    {/* Top-N Filter */}
                    {rec.supported_top_n && (
                      <div className="space-y-1">
                        <label className="text-[11px] font-semibold text-slate-700">
                          Top-N Limit
                        </label>
                        <select
                          value={chart.top_n || ""}
                          onChange={(e) =>
                            handleUpdateField(
                              chart.id,
                              "top_n",
                              e.target.value ? Number(e.target.value) : null
                            )
                          }
                          className="w-full text-xs py-1.5 px-2.5 rounded-lg border border-slate-300 bg-white text-slate-800 focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500"
                        >
                          <option value="">All (No Limit)</option>
                          {rec.supported_top_n.map((n: number) => (
                            <option key={n} value={n}>
                              Top {n}
                            </option>
                          ))}
                        </select>
                      </div>
                    )}
                  </div>

                  {/* Confirmation Button */}
                  <div className="pt-2 flex items-center justify-between border-t border-slate-200">
                    <span className="text-[11px] text-slate-500">
                      Changes apply to local session state.
                    </span>
                    <button
                      type="button"
                      onClick={() => handleConfirm(chart.id)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg transition-colors shadow-xs"
                    >
                      <Check className="w-3.5 h-3.5" />
                      <span>Confirm Configuration</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Dismissed Recommendations Drawer */}
      {showDismissed && dismissedCharts.length > 0 && (
        <div className="p-4 rounded-xl border border-slate-200 bg-slate-50 space-y-3">
          <p className="text-xs font-bold text-slate-700 uppercase tracking-wider">
            Dismissed Recommendations ({dismissedCharts.length})
          </p>
          <div className="space-y-2">
            {dismissedCharts.map((chart) => (
              <div
                key={chart.id}
                className="flex items-center justify-between p-2.5 rounded-lg bg-white border border-slate-200 text-xs"
              >
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-slate-800">{chart.original.title}</span>
                  <ChartTypeBadge chartType={chart.chart_type} />
                </div>
                <button
                  type="button"
                  onClick={() => handleRestore(chart.id)}
                  className="px-2.5 py-1 text-xs font-semibold text-brand-700 bg-brand-50 hover:bg-brand-100 rounded border border-brand-200 transition-colors"
                >
                  Restore
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Summary Footer */}
      <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-slate-600">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
          <span>
            <strong>{confirmedCount}</strong> of <strong>{selectedCount}</strong> selected charts confirmed by user.
          </span>
        </div>

        <div className="text-[11px] text-slate-500">
          Ready for Phase 4 visual report assembly.
        </div>
      </div>
    </section>
  );
}
