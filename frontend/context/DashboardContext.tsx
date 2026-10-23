"use client";

import React, { createContext, useContext, useState, useCallback, ReactNode } from "react";
import { ConfiguredChart } from "@/components/RecommendedCharts";

export interface GlobalFilterInput {
  date_column?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  category_column?: string | null;
  category_values?: string[] | null;
}

export interface MeasureSummary {
  column: string;
  aggregation: string;
  label: string;
  value: number;
}

export interface DatasetSummary {
  total_records: number;
  filtered_records: number;
  is_filtered: boolean;
  total_columns: number;
  missing_cells: number;
  duplicate_rows: number;
  measure_summaries: MeasureSummary[];
}

export interface AvailableFilters {
  date_columns: string[];
  date_ranges: Record<string, { min: string | null; max: string | null }>;
  category_columns: string[];
  category_values: Record<string, string[]>;
}

export interface ChartConfigInput {
  id: string;
  chart_type: string;
  title: string;
  dimension_column?: string | null;
  secondary_dimension_column?: string | null;
  date_column?: string | null;
  measure_column?: string | null;
  aggregation?: string;
  date_granularity?: string | null;
  top_n?: number | null;
  is_confirmed?: boolean;
}

export interface ComputedChart {
  id: string;
  title: string;
  chart_type: string;
  config: ChartConfigInput;
  data_points: Record<string, any>[];
  series_keys: string[];
  x_axis_key: string;
  y_axis_key?: string | null;
  y_axis_label?: string | null;
  x_axis_label?: string | null;
  warnings: string[];
  total_points: number;
  excluded_missing_count: number;
}

export interface DashboardResponse {
  filename: string;
  sheet_name?: string | null;
  summary: DatasetSummary;
  available_filters: AvailableFilters;
  active_filters?: GlobalFilterInput | null;
  charts: ComputedChart[];
  warnings: string[];
}

interface DashboardContextType {
  file: File | null;
  sheetName: string | null;
  configuredCharts: ConfiguredChart[];
  dashboardData: DashboardResponse | null;
  activeFilters: GlobalFilterInput | null;
  isGenerating: boolean;
  error: string | null;
  setSessionData: (file: File | null, sheetName: string | null) => void;
  setConfiguredCharts: (charts: ConfiguredChart[]) => void;
  generateDashboard: (customFilters?: GlobalFilterInput) => Promise<DashboardResponse | null>;
  resetFilters: () => Promise<DashboardResponse | null>;
  clearSession: () => void;
}

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

const DashboardContext = createContext<DashboardContextType | undefined>(undefined);

export function DashboardProvider({ children }: { children: ReactNode }) {
  const [file, setFile] = useState<File | null>(null);
  const [sheetName, setSheetName] = useState<string | null>(null);
  const [configuredCharts, setConfiguredChartsState] = useState<ConfiguredChart[]>([]);
  const [dashboardData, setDashboardData] = useState<DashboardResponse | null>(null);
  const [activeFilters, setActiveFilters] = useState<GlobalFilterInput | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const setSessionData = useCallback((newFile: File | null, newSheet: string | null) => {
    setFile(newFile);
    setSheetName(newSheet);
    if (!newFile) {
      setConfiguredChartsState([]);
      setDashboardData(null);
      setActiveFilters(null);
      setError(null);
    }
  }, []);

  const setConfiguredCharts = useCallback((charts: ConfiguredChart[]) => {
    setConfiguredChartsState(charts);
  }, []);

  const clearSession = useCallback(() => {
    setFile(null);
    setSheetName(null);
    setConfiguredChartsState([]);
    setDashboardData(null);
    setActiveFilters(null);
    setError(null);
  }, []);

  const generateDashboard = useCallback(
    async (customFilters?: GlobalFilterInput): Promise<DashboardResponse | null> => {
      if (!file) {
        setError("No file available in active session. Please upload a dataset first.");
        return null;
      }

      // Filter only selected charts
      const eligibleCharts = configuredCharts.filter((c) => c.selected && !c.dismissed);

      if (eligibleCharts.length === 0) {
        setError("Please select and confirm at least one chart configuration to generate a dashboard.");
        return null;
      }

      const configsPayload: ChartConfigInput[] = eligibleCharts.map((c) => ({
        id: c.id,
        chart_type: c.chart_type,
        title: c.original.title,
        dimension_column: c.dimension_column,
        secondary_dimension_column: c.secondary_dimension_column,
        date_column: c.date_column,
        measure_column: c.measure_column,
        aggregation: c.aggregation,
        date_granularity: c.date_granularity,
        top_n: c.top_n,
        is_confirmed: c.isConfirmed,
      }));

      setIsGenerating(true);
      setError(null);

      try {
        const formData = new FormData();
        formData.append("file", file);
        if (sheetName) {
          formData.append("sheet_name", sheetName);
        }
        formData.append("chart_configs", JSON.stringify(configsPayload));

        const filtersToApply = customFilters !== undefined ? customFilters : activeFilters;
        if (filtersToApply) {
          formData.append("filters", JSON.stringify(filtersToApply));
        }

        const res = await fetch(`${API_BASE_URL}/api/datasets/dashboard`, {
          method: "POST",
          body: formData,
        });

        if (!res.ok) {
          let errorDetail = `Dashboard generation failed (${res.status})`;
          try {
            const errData = await res.json();
            if (errData && errData.detail) {
              errorDetail = typeof errData.detail === "string" ? errData.detail : JSON.stringify(errData.detail);
            }
          } catch {
            // non-JSON response
          }
          throw new Error(errorDetail);
        }

        const data: DashboardResponse = await res.json();
        setDashboardData(data);
        setActiveFilters(filtersToApply || null);
        return data;
      } catch (err: any) {
        const msg = err.message || "Failed to generate dashboard";
        setError(msg);
        return null;
      } finally {
        setIsGenerating(false);
      }
    },
    [file, sheetName, configuredCharts, activeFilters]
  );

  const resetFilters = useCallback(async (): Promise<DashboardResponse | null> => {
    setActiveFilters(null);
    return generateDashboard({
      date_column: null,
      start_date: null,
      end_date: null,
      category_column: null,
      category_values: null,
    });
  }, [generateDashboard]);

  return (
    <DashboardContext.Provider
      value={{
        file,
        sheetName,
        configuredCharts,
        dashboardData,
        activeFilters,
        isGenerating,
        error,
        setSessionData,
        setConfiguredCharts,
        generateDashboard,
        resetFilters,
        clearSession,
      }}
    >
      {children}
    </DashboardContext.Provider>
  );
}

export function useDashboard() {
  const context = useContext(DashboardContext);
  if (!context) {
    throw new Error("useDashboard must be used within a DashboardProvider");
  }
  return context;
}
