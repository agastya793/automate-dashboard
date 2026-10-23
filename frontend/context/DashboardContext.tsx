"use client";

import React, { createContext, useContext, useState, useCallback, ReactNode } from "react";
import { ConfiguredChart } from "@/components/RecommendedCharts";
import { useAuth } from "@/context/AuthContext";
import { createClient } from "@/lib/supabase/client";

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
  setSessionData: (file: File | null, sheetName: string | null) => void;
  setConfiguredCharts: (charts: ConfiguredChart[]) => void;
  generateDashboard: (customFilters?: GlobalFilterInput) => Promise<DashboardResponse | null>;
  resetFilters: () => Promise<DashboardResponse | null>;
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
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

const DashboardContext = createContext<DashboardContextType | undefined>(undefined);

export function DashboardProvider({ children }: { children: ReactNode }) {
  const { user, workspace, isConfigured, getAccessToken } = useAuth();

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
  }, []);

  // ---------------------------------------------------------------------------
  // Save dataset file to private Supabase Storage + insert row in datasets table
  // ---------------------------------------------------------------------------
  const saveDatasetMetadata = useCallback(
    async (
      fileToSave: File,
      sheetNames: string[],
      selectedSheet: string | null,
      rowCount: number,
      colCount: number
    ): Promise<{ datasetId: string | null; error: string | null }> => {
      if (!isConfigured || !user || !workspace) {
        return {
          datasetId: null,
          error: "Supabase authentication or workspace not initialized.",
        };
      }

      const supabase = createClient();
      if (!supabase) {
        return { datasetId: null, error: "Supabase client unavailable." };
      }

      setIsPersisting(true);
      setPersistStatus(null);

      const datasetId = typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;

      const sanitizedFilename = fileToSave.name.replace(/[^a-zA-Z0-9._-]/g, "_");
      const storagePath = `${workspace.id}/${user.id}/${datasetId}/${sanitizedFilename}`;

      try {
        // 1. Upload file to private storage bucket 'business-datasets'
        const { error: uploadError } = await supabase.storage
          .from("business-datasets")
          .upload(storagePath, fileToSave, {
            contentType: fileToSave.type || "application/octet-stream",
            upsert: true,
          });

        if (uploadError) {
          throw new Error(`Storage upload failed: ${uploadError.message}`);
        }

        // 2. Insert metadata record in datasets table
        const { error: dbError } = await supabase.from("datasets").insert({
          id: datasetId,
          workspace_id: workspace.id,
          created_by: user.id,
          original_filename: fileToSave.name,
          storage_path: storagePath,
          file_size_bytes: fileToSave.size,
          file_mime_type: fileToSave.type || "application/octet-stream",
          sheet_names: sheetNames,
          selected_sheet: selectedSheet,
          row_count: rowCount,
          column_count: colCount,
        });

        if (dbError) {
          // Cleanup orphaned file on database error
          await supabase.storage.from("business-datasets").remove([storagePath]);
          throw new Error(`Database persistence failed: ${dbError.message}`);
        }

        setSavedDatasetId(datasetId);
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
    [isConfigured, user, workspace]
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

        const token = await getAccessToken();
        const headers: Record<string, string> = {};
        if (token) {
          headers["Authorization"] = `Bearer ${token}`;
        }

        const res = await fetch(`${API_BASE_URL}/api/datasets/dashboard`, {
          method: "POST",
          headers,
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
    [file, sheetName, configuredCharts, activeFilters, getAccessToken]
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

  // ---------------------------------------------------------------------------
  // Save or Update Report configuration in reports table
  // ---------------------------------------------------------------------------
  const saveCurrentReport = useCallback(
    async (reportName: string): Promise<{ reportId: string | null; error: string | null }> => {
      if (!isConfigured || !user || !workspace) {
        return { reportId: null, error: "Please sign in to save reports." };
      }
      if (!reportName.trim()) {
        return { reportId: null, error: "Report name cannot be empty." };
      }

      const supabase = createClient();
      if (!supabase) {
        return { reportId: null, error: "Supabase client not initialized." };
      }

      let targetDatasetId = savedDatasetId;

      // Auto-persist dataset if not yet persisted
      if (!targetDatasetId && file) {
        const sheetList = sheetName ? [sheetName] : [];
        const res = await saveDatasetMetadata(file, sheetList, sheetName, 0, 0);
        if (res.error || !res.datasetId) {
          return { reportId: null, error: `Could not persist dataset: ${res.error}` };
        }
        targetDatasetId = res.datasetId;
      }

      if (!targetDatasetId) {
        return { reportId: null, error: "No dataset available to associate with report." };
      }

      const eligibleCharts = configuredCharts.filter((c) => c.selected && !c.dismissed);
      if (eligibleCharts.length === 0) {
        return { reportId: null, error: "No chart configurations selected to save." };
      }

      setIsPersisting(true);

      try {
        const reportPayload = {
          workspace_id: workspace.id,
          dataset_id: targetDatasetId,
          created_by: user.id,
          name: reportName.trim(),
          chart_configs: eligibleCharts,
          filter_config: activeFilters || {},
          updated_at: new Date().toISOString(),
        };

        let resultingReportId = savedReportId;

        if (savedReportId) {
          const { error: updateError } = await supabase
            .from("reports")
            .update(reportPayload)
            .eq("id", savedReportId);

          if (updateError) throw updateError;
        } else {
          const { data: inserted, error: insertError } = await supabase
            .from("reports")
            .insert(reportPayload)
            .select("id")
            .single();

          if (insertError) throw insertError;
          resultingReportId = inserted.id;
          setSavedReportId(resultingReportId);
        }

        setSavedReportName(reportName.trim());
        setPersistStatus({
          type: "success",
          message: `Report "${reportName.trim()}" saved successfully.`,
        });
        return { reportId: resultingReportId, error: null };
      } catch (err: any) {
        const msg = err?.message || "Failed to save report";
        setPersistStatus({
          type: "error",
          message: msg,
        });
        return { reportId: null, error: msg };
      } finally {
        setIsPersisting(false);
      }
    },
    [
      isConfigured,
      user,
      workspace,
      savedDatasetId,
      file,
      sheetName,
      configuredCharts,
      activeFilters,
      savedReportId,
      saveDatasetMetadata,
    ]
  );

  // ---------------------------------------------------------------------------
  // Open saved report: download source file from storage and recalculate dashboard
  // ---------------------------------------------------------------------------
  const openReportById = useCallback(
    async (reportId: string): Promise<{ success: boolean; error: string | null }> => {
      const supabase = createClient();
      if (!supabase) {
        return { success: false, error: "Supabase client not initialized." };
      }

      setIsGenerating(true);
      setError(null);
      setPersistStatus(null);

      try {
        // 1. Fetch report and linked dataset record
        const { data: report, error: reportErr } = await supabase
          .from("reports")
          .select(`
            id,
            name,
            workspace_id,
            dataset_id,
            chart_configs,
            filter_config,
            datasets (
              id,
              original_filename,
              storage_path,
              file_mime_type,
              selected_sheet,
              sheet_names
            )
          `)
          .eq("id", reportId)
          .single();

        if (reportErr || !report) {
          throw new Error(
            reportErr?.message || "Report could not be found or you lack permission to view it."
          );
        }

        const dataset = report.datasets as any;
        if (!dataset || !dataset.storage_path) {
          throw new Error("Linked dataset metadata record was not found for this report.");
        }

        // 2. Download source file from private storage
        const { data: fileBlob, error: downloadErr } = await supabase.storage
          .from("business-datasets")
          .download(dataset.storage_path);

        if (downloadErr || !fileBlob) {
          throw new Error(
            `The original dataset file is no longer available in storage (${downloadErr?.message || "File not found"}).`
          );
        }

        // 3. Reconstruct browser File object
        const reconstructedFile = new File([fileBlob], dataset.original_filename, {
          type: dataset.file_mime_type || "application/octet-stream",
        });

        const restoredCharts: ConfiguredChart[] = Array.isArray(report.chart_configs)
          ? (report.chart_configs as ConfiguredChart[])
          : [];

        const restoredSheet = dataset.selected_sheet || null;
        const restoredFilters: GlobalFilterInput = report.filter_config || {};

        // 4. Update session state
        setFile(reconstructedFile);
        setSheetName(restoredSheet);
        setConfiguredChartsState(restoredCharts);
        setSavedDatasetId(dataset.id);
        setSavedReportId(report.id);
        setSavedReportName(report.name);
        setActiveFilters(restoredFilters);

        // 5. Recalculate dashboard with FastAPI
        const token = await getAccessToken();
        const headers: Record<string, string> = {};
        if (token) {
          headers["Authorization"] = `Bearer ${token}`;
        }

        const configsPayload: ChartConfigInput[] = restoredCharts
          .filter((c) => c.selected && !c.dismissed)
          .map((c) => ({
            id: c.id,
            chart_type: c.chart_type,
            title: c.original?.title || (c as any).title || "Chart",
            dimension_column: c.dimension_column,
            secondary_dimension_column: c.secondary_dimension_column,
            date_column: c.date_column,
            measure_column: c.measure_column,
            aggregation: c.aggregation,
            date_granularity: c.date_granularity,
            top_n: c.top_n,
            is_confirmed: c.isConfirmed ?? true,
          }));

        const formData = new FormData();
        formData.append("file", reconstructedFile);
        if (restoredSheet) {
          formData.append("sheet_name", restoredSheet);
        }
        formData.append("chart_configs", JSON.stringify(configsPayload));
        if (restoredFilters && Object.keys(restoredFilters).length > 0) {
          formData.append("filters", JSON.stringify(restoredFilters));
        }

        const res = await fetch(`${API_BASE_URL}/api/datasets/dashboard`, {
          method: "POST",
          headers,
          body: formData,
        });

        if (!res.ok) {
          let errorDetail = `Dashboard generation failed (${res.status})`;
          try {
            const errData = await res.json();
            if (errData && errData.detail) {
              errorDetail = typeof errData.detail === "string" ? errData.detail : JSON.stringify(errData.detail);
            }
          } catch {}
          throw new Error(errorDetail);
        }

        const data: DashboardResponse = await res.json();
        setDashboardData(data);
        return { success: true, error: null };
      } catch (err: any) {
        const msg = err?.message || "Failed to open report";
        setError(msg);
        return { success: false, error: msg };
      } finally {
        setIsGenerating(false);
      }
    },
    [getAccessToken]
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
        setSessionData,
        setConfiguredCharts,
        generateDashboard,
        resetFilters,
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
