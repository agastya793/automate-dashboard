"use client";

import React, { createContext, useContext, useState, useCallback, ReactNode } from "react";
import { ConfiguredChart } from "@/components/RecommendedCharts";
import { useAuth } from "@/context/AuthContext";
import { apiFetch } from "@/lib/api";

import {
  ManufacturingDashboardData,
  ManufacturingGlobalFilters,
} from "@/lib/mappingTypes";

export interface GlobalFilterInput {
  date_column?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  category_column?: string | null;
  selected_categories?: string[] | null;
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
  column_count: number;
  missing_cells: number;
  duplicate_records: number;
  measure_summaries: MeasureSummary[];
}

export interface DateFilterOption {
  column_name: string;
  min_date?: string | null;
  max_date?: string | null;
}

export interface CategoryFilterOption {
  column_name: string;
  options: string[];
}

export interface AvailableFilters {
  date_filters: DateFilterOption[];
  category_filters: CategoryFilterOption[];
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
  data: Record<string, any>[];
  series_keys?: string[] | null;
  warnings: string[];
  total_points: number;
}

export interface DashboardResponse {
  filename: string;
  selected_sheet?: string | null;
  dataset_summary: DatasetSummary;
  available_filters: AvailableFilters;
  charts: ComputedChart[];
  warnings: string[];
}

export interface PersistStatus {
  type: "success" | "error" | "warning";
  message: string;
}

interface DashboardContextType {
  file: File | null;
  sheetName: string | null;
  configuredCharts: ConfiguredChart[];
  dashboardData: DashboardResponse | null;
  activeFilters: GlobalFilterInput | null;
  isGenerating: boolean;
  error: string | null;
  savedDatasetId: string | null;
  savedReportId: string | null;
  savedReportName: string | null;
  isPersisting: boolean;
  persistStatus: PersistStatus | null;
  manufacturingData: ManufacturingDashboardData | null;
  manufacturingFilters: ManufacturingGlobalFilters | null;
  activeUploadId: string | null;
  setSessionData: (file: File | null, sheetName: string | null) => void;
  setConfiguredCharts: (charts: ConfiguredChart[]) => void;
  generateDashboard: (customFilters?: GlobalFilterInput) => Promise<DashboardResponse | null>;
  resetFilters: () => Promise<DashboardResponse | null>;
  generateManufacturingDashboard: (
    uploadId: string,
    confirmedSot?: boolean,
    sotChoice?: string | null,
    targetPpm?: number
  ) => Promise<ManufacturingDashboardData | null>;

  queryManufacturingFilters: (filters: ManufacturingGlobalFilters) => Promise<void>;
  resetManufacturingFilters: () => Promise<void>;
  saveManufacturingDashboard: (title: string) => Promise<{ dashboardId: string | null; error: string | null }>;
  openManufacturingDashboardById: (dashboardId: string) => Promise<boolean>;
  saveDatasetMetadata: (
    fileToSave: File,
    sheetNames: string[],
    selectedSheet: string | null,
    rowCount: number,
    colCount: number
  ) => Promise<{ datasetId: string | null; error: string | null }>;
  saveCurrentReport: (reportName: string) => Promise<{ reportId: string | null; error: string | null }>;
  openReportById: (reportId: string) => Promise<{ success: boolean; error: string | null }>;
  clearSession: () => void;
  clearPersistStatus: () => void;
}


const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:18001";

const DashboardContext = createContext<DashboardContextType | undefined>(undefined);

export function DashboardProvider({ children }: { children: ReactNode }) {
  const { user, workspace, isConfigured } = useAuth();

  const [file, setFile] = useState<File | null>(null);
  const [sheetName, setSheetName] = useState<string | null>(null);
  const [configuredCharts, setConfiguredChartsState] = useState<ConfiguredChart[]>([]);
  const [dashboardData, setDashboardData] = useState<DashboardResponse | null>(null);
  const [activeFilters, setActiveFilters] = useState<GlobalFilterInput | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Persistence tracking
  const [savedDatasetId, setSavedDatasetId] = useState<string | null>(null);
  const [savedReportId, setSavedReportId] = useState<string | null>(null);
  const [savedReportName, setSavedReportName] = useState<string | null>(null);
  const [isPersisting, setIsPersisting] = useState(false);
  const [persistStatus, setPersistStatus] = useState<PersistStatus | null>(null);

  // Manufacturing Quality Dashboard state (Milestone 4)
  const [manufacturingData, setManufacturingData] = useState<ManufacturingDashboardData | null>(null);
  const [manufacturingFilters, setManufacturingFilters] = useState<ManufacturingGlobalFilters | null>(null);
  const [activeUploadId, setActiveUploadId] = useState<string | null>(null);

  const setSessionData = useCallback((newFile: File | null, newSheet: string | null) => {
    setFile(newFile);
    setSheetName(newSheet);
    if (!newFile) {
      setConfiguredChartsState([]);
      setDashboardData(null);
      setActiveFilters(null);
      setError(null);
      setSavedDatasetId(null);
      setSavedReportId(null);
      setSavedReportName(null);
      setPersistStatus(null);
      setManufacturingData(null);
      setManufacturingFilters(null);
      setActiveUploadId(null);
    }
  }, []);

  const setConfiguredCharts = useCallback((charts: ConfiguredChart[]) => {
    setConfiguredChartsState(charts);
  }, []);

  const clearPersistStatus = useCallback(() => {
    setPersistStatus(null);
  }, []);

  const clearSession = useCallback(() => {
    setFile(null);
    setSheetName(null);
    setConfiguredChartsState([]);
    setDashboardData(null);
    setActiveFilters(null);
    setError(null);
    setSavedDatasetId(null);
    setSavedReportId(null);
    setSavedReportName(null);
    setPersistStatus(null);
    setManufacturingData(null);
    setManufacturingFilters(null);
    setActiveUploadId(null);
  }, []);


  // ---------------------------------------------------------------------------
  // Save dataset file to private local storage + PostgreSQL upload record
  // ---------------------------------------------------------------------------
  const saveDatasetMetadata = useCallback(
    async (
      fileToSave: File,
      sheetNames: string[],
      selectedSheet: string | null,
      rowCount: number,
      colCount: number
    ): Promise<{ datasetId: string | null; error: string | null }> => {
      setIsPersisting(true);
      setPersistStatus(null);

      try {
        const formData = new FormData();
        formData.append("file", fileToSave);

        const res = await apiFetch("/api/uploads", {
          method: "POST",
          body: formData,
        });

        if (!res.ok) {
          throw new Error(`Dataset upload failed with status ${res.status}`);
        }

        const data = await res.json();
        const datasetId = data.upload_id;

        setSavedDatasetId(datasetId);
        setActiveUploadId(datasetId);
        setPersistStatus({
          type: "success",
          message: "Dataset safely uploaded to private workspace storage.",
        });
        return { datasetId, error: null };
      } catch (err: any) {
        const msg = err?.message || "Failed to persist dataset";
        setPersistStatus({
          type: "error",
          message: msg,
        });
        return { datasetId: null, error: msg };
      } finally {
        setIsPersisting(false);
      }
    },
    []
  );

  // ---------------------------------------------------------------------------
  // Generate dashboard via FastAPI
  // ---------------------------------------------------------------------------
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

        const res = await apiFetch("/api/datasets/dashboard", {
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
      selected_categories: null,
    });
  }, [generateDashboard]);

  // ---------------------------------------------------------------------------
  // Save or Update Report configuration in reports table
  // ---------------------------------------------------------------------------
  // ---------------------------------------------------------------------------
  // Save or Update Report configuration in PostgreSQL via FastAPI
  // ---------------------------------------------------------------------------
  const saveCurrentReport = useCallback(
    async (reportName: string): Promise<{ reportId: string | null; error: string | null }> => {
      if (!reportName.trim()) {
        return { reportId: null, error: "Report name cannot be empty." };
      }

      setIsPersisting(true);
      try {
        const eligibleCharts = configuredCharts.filter((c) => c.selected && !c.dismissed);
        const res = await apiFetch("/api/dashboards", {
          method: "POST",
          body: JSON.stringify({
            upload_id: savedDatasetId || activeUploadId,
            title: reportName.trim(),
            spec: {
              configured_charts: eligibleCharts,
              filters: activeFilters || {},
            },
          }),
        });

        if (!res.ok) {
          throw new Error(`Save failed with status ${res.status}`);
        }

        const saved = await res.json();
        setSavedReportId(saved.id);
        setSavedReportName(reportName.trim());
        setPersistStatus({
          type: "success",
          message: `Report "${reportName.trim()}" saved successfully.`,
        });
        return { reportId: saved.id, error: null };
      } catch (err: any) {
        const msg = err?.message || "Failed to save report";
        setPersistStatus({ type: "error", message: msg });
        return { reportId: null, error: msg };
      } finally {
        setIsPersisting(false);
      }
    },
    [savedDatasetId, activeUploadId, configuredCharts, activeFilters]
  );

  // ---------------------------------------------------------------------------
  // Open saved report: fetch dashboard specification from PostgreSQL and restore
  // ---------------------------------------------------------------------------
  const openReportById = useCallback(
    async (reportId: string): Promise<{ success: boolean; error: string | null }> => {
      setIsGenerating(true);
      setError(null);
      setPersistStatus(null);

      try {
        const res = await apiFetch(`/api/dashboards/${reportId}`);
        if (!res.ok) {
          throw new Error(`Report could not be found (${res.status})`);
        }

        const data = await res.json();
        setSavedReportId(data.id);
        setSavedReportName(data.title);
        setActiveUploadId(data.upload_id);

        if (data.spec?.configured_charts) {
          setConfiguredChartsState(data.spec.configured_charts);
        }
        if (data.spec?.filters) {
          setActiveFilters(data.spec.filters);
        }

        if (data.rendered_widgets) {
          setManufacturingData({
            spec: data.spec,
            rendered_widgets: data.rendered_widgets,
            available_filters: data.available_filters,
            reconciliation: data.reconciliation,
            status: "ready",
          });
        }

        return { success: true, error: null };
      } catch (err: any) {
        const msg = err?.message || "Failed to open report";
        setError(msg);
        return { success: false, error: msg };
      } finally {
        setIsGenerating(false);
      }
    },
    []
  );

  // ---------------------------------------------------------------------------
  // Milestone 4: Manufacturing Quality Dashboard Actions
  // ---------------------------------------------------------------------------

  const generateManufacturingDashboard = useCallback(
    async (
      uploadId: string,
      confirmedSot: boolean = false,
      sotChoice?: string | null,
      targetPpm: number = 2000
    ): Promise<ManufacturingDashboardData | null> => {
      setIsGenerating(true);
      setError(null);
      try {
        const res = await apiFetch("/api/dashboards/manufacturing/generate", {
          method: "POST",
          body: JSON.stringify({
            upload_id: uploadId,
            source_of_truth_confirmed: confirmedSot,
            source_of_truth_choice: sotChoice,
            target_ppm: targetPpm,
          }),
        });

        if (!res.ok) {
          let errDetail = `Manufacturing dashboard failed (${res.status})`;
          try {
            const errJson = await res.json();
            if (errJson?.detail) errDetail = errJson.detail;
          } catch {}
          throw new Error(errDetail);
        }

        const data: ManufacturingDashboardData = await res.json();
        setManufacturingData(data);
        setActiveUploadId(uploadId);
        setManufacturingFilters(null);
        return data;
      } catch (err: any) {
        setError(err.message || "Failed to generate manufacturing dashboard");
        return null;
      } finally {
        setIsGenerating(false);
      }
    },
    []
  );

  const queryManufacturingFilters = useCallback(
    async (filters: ManufacturingGlobalFilters) => {
      if (!manufacturingData) return;
      setIsGenerating(true);
      setError(null);
      try {
        if (savedReportId) {
          const res = await apiFetch(`/api/dashboards/${savedReportId}/query`, {
            method: "POST",
            body: JSON.stringify({ filters }),
          });
          if (res.ok) {
            const result = await res.json();
            setManufacturingData((prev) =>
              prev
                ? {
                    ...prev,
                    rendered_widgets: result.rendered_widgets,
                  }
                : null
            );
            setManufacturingFilters(filters);
            return;
          }
        }

        if (activeUploadId) {
          const res = await apiFetch("/api/dashboards/manufacturing/generate", {
            method: "POST",
            body: JSON.stringify({
              upload_id: activeUploadId,
              source_of_truth_confirmed: manufacturingData.spec.source_of_truth_confirmed,
              source_of_truth_choice: manufacturingData.spec.source_of_truth_choice,
            }),
          });
          if (res.ok) {
            const data: ManufacturingDashboardData = await res.json();
            setManufacturingData(data);
            setManufacturingFilters(filters);
          }
        }
      } catch (err: any) {
        setError(err.message || "Failed to filter manufacturing dashboard");
      } finally {
        setIsGenerating(false);
      }
    },
    [manufacturingData, savedReportId, activeUploadId]
  );

  const resetManufacturingFilters = useCallback(async () => {
    setManufacturingFilters(null);
    if (activeUploadId && manufacturingData) {
      await generateManufacturingDashboard(
        activeUploadId,
        manufacturingData.spec.source_of_truth_confirmed,
        manufacturingData.spec.source_of_truth_choice
      );
    }
  }, [activeUploadId, manufacturingData, generateManufacturingDashboard]);

  const saveManufacturingDashboard = useCallback(
    async (title: string): Promise<{ dashboardId: string | null; error: string | null }> => {
      if (!manufacturingData || !activeUploadId) {
        return { dashboardId: null, error: "No active manufacturing dashboard to save." };
      }
      setIsPersisting(true);
      setPersistStatus(null);
      try {
        const res = await apiFetch("/api/dashboards", {
          method: "POST",
          body: JSON.stringify({
            upload_id: activeUploadId,
            title,
            spec: manufacturingData.spec,
          }),
        });

        if (!res.ok) {
          throw new Error(`Save failed with status ${res.status}`);
        }

        const saved = await res.json();
        setSavedReportId(saved.id);
        setSavedReportName(title);
        setPersistStatus({
          type: "success",
          message: `Manufacturing dashboard saved successfully as "${title}".`,
        });
        return { dashboardId: saved.id, error: null };
      } catch (err: any) {
        const msg = err.message || "Failed to persist manufacturing dashboard.";
        setPersistStatus({ type: "error", message: msg });
        return { dashboardId: null, error: msg };
      } finally {
        setIsPersisting(false);
      }
    },
    [manufacturingData, activeUploadId]
  );

  const openManufacturingDashboardById = useCallback(
    async (dashboardId: string): Promise<boolean> => {
      setIsGenerating(true);
      setError(null);
      try {
        const res = await apiFetch(`/api/dashboards/${dashboardId}`);

        if (!res.ok) {
          throw new Error(`Failed to load dashboard (${res.status})`);
        }

        const data = await res.json();
        setManufacturingData({
          spec: data.spec,
          rendered_widgets: data.rendered_widgets,
          available_filters: data.available_filters,
          reconciliation: data.reconciliation,
          status: "ready",
        });
        setActiveUploadId(data.upload_id);
        setSavedReportId(data.id);
        setSavedReportName(data.title);
        return true;
      } catch (err: any) {
        setError(err.message || "Failed to open dashboard");
        return false;
      } finally {
        setIsGenerating(false);
      }
    },
    []
  );

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
        savedDatasetId,
        savedReportId,
        savedReportName,
        isPersisting,
        persistStatus,
        manufacturingData,
        manufacturingFilters,
        activeUploadId,
        setSessionData,
        setConfiguredCharts,
        generateDashboard,
        resetFilters,
        generateManufacturingDashboard,
        queryManufacturingFilters,
        resetManufacturingFilters,
        saveManufacturingDashboard,
        openManufacturingDashboardById,
        saveDatasetMetadata,
        saveCurrentReport,
        openReportById,
        clearSession,
        clearPersistStatus,
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
