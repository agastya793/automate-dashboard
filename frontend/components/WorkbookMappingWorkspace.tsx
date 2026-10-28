"use client";

import React, { useState, useEffect, useMemo, useCallback } from "react";
import {
  TableProperties,
  Layers,
  Settings2,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  FileSpreadsheet,
  Calendar,
  Hash,
  Tag,
  Binary,
  FileText,
  Sliders,
  Save,
  RotateCw,
  FolderDown,
  Trash2,
  ArrowRight,
  HelpCircle,
  Eye,
  Check,
  X,
  Plus,
  RefreshCw,
  Sparkles,
  ShieldCheck,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import {
  WorkbookScanResponse,
  DetectedBlock,
  BlockMapping,
  MappingTemplate,
  MappingTemplateSummary,
  ColumnRole,
  RowDecision,
  UnpivotConfig,
  NormalizationResponse,
  CellColourStatusMap,
} from "@/lib/mappingTypes";
import { apiFetch } from "@/lib/api";

interface WorkbookMappingWorkspaceProps {
  scanResult: WorkbookScanResponse;
  rawFile: File;
  apiBaseUrl: string;
  getAccessToken: () => Promise<string | null>;
  onMappingApplied?: (normalizationResult: NormalizationResponse) => void;
  onCancel?: () => void;
}

const ROLE_OPTIONS: { role: ColumnRole; label: string; icon: any; color: string; desc: string }[] = [
  { role: "date", label: "Date / Period", icon: Calendar, color: "text-blue-600 bg-blue-50 border-blue-200", desc: "Calendar date or monthly period" },
  { role: "category", label: "Category", icon: Tag, color: "text-amber-600 bg-amber-50 border-amber-200", desc: "Discrete groups, models, defects, lines" },
  { role: "measure", label: "Measure", icon: Hash, color: "text-emerald-600 bg-emerald-50 border-emerald-200", desc: "Quantitative values to aggregate (qty, count)" },
  { role: "id", label: "Identifier", icon: Binary, color: "text-indigo-600 bg-indigo-50 border-indigo-200", desc: "Unique row/record keys or serial numbers" },
  { role: "derived", label: "Derived", icon: Sliders, color: "text-purple-600 bg-purple-50 border-purple-200", desc: "Formulas, percentages, running totals" },
  { role: "text", label: "Text / Other", icon: FileText, color: "text-slate-600 bg-slate-50 border-slate-200", desc: "Descriptive notes or uncategorized text" },
];

export function WorkbookMappingWorkspace({
  scanResult,
  rawFile,
  apiBaseUrl,
  getAccessToken,
  onMappingApplied,
  onCancel,
}: WorkbookMappingWorkspaceProps) {
  // Active sheet tab
  const [activeSheet, setActiveSheet] = useState<string>(
    scanResult.sheet_names[0] || (scanResult.blocks[0]?.sheet ?? "")
  );

  // Active block index
  const [selectedBlockIdx, setSelectedBlockIdx] = useState<number>(0);

  // Active sub-tab in mapping inspector
  const [activeSubTab, setActiveSubTab] = useState<"roles" | "unpivot" | "ambiguous" | "colours" | "merges">("roles");

  // Template state
  const [templateName, setTemplateName] = useState<string>(`Mapping for ${scanResult.filename}`);
  const [templateVersion, setTemplateVersion] = useState<number>(1);
  const [templateId, setTemplateId] = useState<string>(() => `template-${Date.now()}`);
  const [savedTemplates, setSavedTemplates] = useState<MappingTemplateSummary[]>([]);
  const [selectedSavedTemplateId, setSelectedSavedTemplateId] = useState<string>("");

  // Block mappings dictionary keyed by block index
  const [blockMappings, setBlockMappings] = useState<Record<number, BlockMapping>>(() => {
    const init: Record<number, BlockMapping> = {};
    scanResult.blocks.forEach((b, idx) => {
      // Default unpivot config for wide blocks
      const isWide = b.kind === "wide";
      const idCols = Object.entries(b.column_roles)
        .filter(([_, r]) => r === "category" || r === "id" || r === "text")
        .map(([c]) => c);
      const valCols = Object.entries(b.column_roles)
        .filter(([_, r]) => r === "date" || r === "measure")
        .map(([c]) => c);

      init[idx] = {
        block_index: idx,
        sheet: b.sheet,
        range: b.range,
        trimmed_range: b.range,
        included: b.kind !== "form", // Form-like blocks excluded by default
        kind: b.kind,
        column_roles: { ...b.column_roles },
        unpivot: {
          enabled: isWide,
          id_columns: idCols,
          value_columns: valCols,
          variable_name: "Month",
          value_name: "Value",
          measure_name: b.sheet.toLowerCase().includes("ppm") ? "PPM" : "Quantity",
        },
        ambiguous_row_decisions: b.ambiguous_rows.map((ar) => ({
          source_row: ar.source_row,
          sheet_row: ar.sheet_row,
          decision: "record",
          reason: ar.reason,
        })),
        colour_mappings: [
          { rgb: "#00B050", status_label: "Completed", description: "Green: Task complete" },
          { rgb: "#FFC000", status_label: "In Progress", description: "Amber: Work underway" },
          { rgb: "#FF0000", status_label: "Overdue", description: "Red: Action delayed" },
        ],
        value_merges: [],
      };
    });
    return init;
  });

  // Source-of-truth conflict confirmation
  const hasSotConflict = useMemo(() => {
    return scanResult.global_warnings.some(
      (w) => w.includes("37,111") || w.toLowerCase().includes("conflict")
    );
  }, [scanResult.global_warnings]);

  const [sotConfirmed, setSotConfirmed] = useState<boolean>(!hasSotConflict);
  const [sotChoice, setSotChoice] = useState<string>("monthly_breakdown");
  const [sotConfirmedQty, setSotConfirmedQty] = useState<number>(37111);

  // Status and execution states
  const [isSaving, setIsSaving] = useState(false);
  const [isNormalizing, setIsNormalizing] = useState(false);
  const [actionMessage, setActionMessage] = useState<{ type: "success" | "error" | "info"; text: string } | null>(null);
  const [normalizationResult, setNormalizationResult] = useState<NormalizationResponse | null>(null);

  // Load saved templates list on mount
  useEffect(() => {
    const fetchTemplates = async () => {
      try {
        const res = await apiFetch("/api/workbooks/mappings");
        if (res.ok) {
          const list: MappingTemplateSummary[] = await res.json();
          setSavedTemplates(list);
        }
      } catch {
        // Silently fail if offline
      }
    };
    fetchTemplates();
  }, []);

  // Current sheet blocks
  const sheetBlocks = useMemo(() => {
    return scanResult.blocks
      .map((b, idx) => ({ ...b, originalIndex: idx }))
      .filter((b) => b.sheet === activeSheet);
  }, [scanResult.blocks, activeSheet]);

  const currentBlockMapping = blockMappings[selectedBlockIdx];
  const currentBlock = scanResult.blocks[selectedBlockIdx];

  // Helper to update current block mapping
  const updateBlockMapping = useCallback(
    (updater: (prev: BlockMapping) => BlockMapping) => {
      setBlockMappings((prev) => {
        const current = prev[selectedBlockIdx];
        if (!current) return prev;
        return {
          ...prev,
          [selectedBlockIdx]: updater(current),
        };
      });
    },
    [selectedBlockIdx]
  );

  // Handle column role change
  const handleRoleChange = (colName: string, role: ColumnRole) => {
    updateBlockMapping((bm) => ({
      ...bm,
      column_roles: {
        ...bm.column_roles,
        [colName]: role,
      },
    }));
  };

  // Handle Ambiguous Row decision
  const handleAmbiguousDecision = (sourceRow: number, decision: RowDecision) => {
    updateBlockMapping((bm) => ({
      ...bm,
      ambiguous_row_decisions: bm.ambiguous_row_decisions.map((ar) =>
        ar.source_row === sourceRow ? { ...ar, decision } : ar
      ),
    }));
  };

  // Handle Color Status map update
  const handleColourStatusChange = (rgb: string, label: string) => {
    updateBlockMapping((bm) => ({
      ...bm,
      colour_mappings: bm.colour_mappings.map((cm) =>
        cm.rgb.toUpperCase() === rgb.toUpperCase() ? { ...cm, status_label: label } : cm
      ),
    }));
  };

  // Save template to backend
  const handleSaveTemplate = async () => {
    setIsSaving(true);
    setActionMessage(null);

    const templatePayload: MappingTemplate = {
      id: templateId,
      name: templateName,
      version: templateVersion,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      blocks: Object.values(blockMappings),
      source_of_truth: {
        confirmed: sotConfirmed,
        chosen_source: sotChoice,
        confirmed_quantity: sotConfirmedQty,
      },
      global_warnings_acknowledged: true,
    };

    try {
      const res = await apiFetch("/api/workbooks/mapping", {
        method: "POST",
        body: JSON.stringify(templatePayload),
      });

      if (!res.ok) {
        throw new Error(`Failed to save template: ${res.statusText}`);
      }

      const saved: MappingTemplate = await res.json();
      setTemplateVersion(saved.version);
      setActionMessage({
        type: "success",
        text: `Mapping template '${saved.name}' saved successfully (Version ${saved.version}).`,
      });
    } catch (err: any) {
      setActionMessage({
        type: "error",
        text: err.message || "Could not save template to server.",
      });
    } finally {
      setIsSaving(false);
    }
  };

  // Execute normalization
  const handleNormalize = async () => {
    setIsNormalizing(true);
    setActionMessage(null);

    const templatePayload: MappingTemplate = {
      id: templateId,
      name: templateName,
      version: templateVersion,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      blocks: Object.values(blockMappings),
      source_of_truth: {
        confirmed: sotConfirmed,
        chosen_source: sotChoice,
        confirmed_quantity: sotConfirmedQty,
      },
      global_warnings_acknowledged: true,
    };

    try {
      const formData = new FormData();
      formData.append("file", rawFile);
      formData.append("template_json", JSON.stringify(templatePayload));

      const res = await apiFetch("/api/workbooks/normalize", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || `Normalization failed with status ${res.status}`);
      }

      const result: NormalizationResponse = {
        ...(await res.json()),
        // Carry the approved mapping forward so the persisted async pipeline
        // cannot silently replace it with a default mapping.
        template: templatePayload,
      };
      setNormalizationResult(result);
      setActionMessage({
        type: "success",
        text: `Normalization complete! ${result.tables.length} tables prepared for reporting.`,
      });

      if (onMappingApplied) {
        onMappingApplied(result);
      }
    } catch (err: any) {
      setActionMessage({
        type: "error",
        text: err.message || "Normalization failed.",
      });
    } finally {
      setIsNormalizing(false);
    }
  };

  return (
    <div className="bg-slate-900/5 backdrop-blur-md border border-slate-200/80 rounded-2xl shadow-xl overflow-hidden transition-all duration-300">
      {/* ----------------------------------------------------------------- */}
      {/* 1. Header Bar: Title, Template Loader, Save & Apply Actions       */}
      {/* ----------------------------------------------------------------- */}
      <div className="bg-gradient-to-r from-slate-900 via-slate-800 to-indigo-950 text-white p-5 sm:p-6 flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-700/60">
        <div className="space-y-1">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-indigo-500/20 border border-indigo-400/30 flex items-center justify-center text-indigo-300">
              <TableProperties className="w-4 h-4" />
            </div>
            <h2 className="text-lg font-bold tracking-tight text-white flex items-center gap-2">
              <span>Mapping & Normalisation Workspace</span>
              <span className="px-2 py-0.5 text-[11px] font-semibold bg-indigo-500/30 text-indigo-200 border border-indigo-400/30 rounded-full">
                Milestone 2
              </span>
            </h2>
          </div>
          <p className="text-xs text-slate-300 max-w-2xl">
            Inspect detected table blocks, confirm unpivot rules, map cell colors to statuses, and resolve production count conflicts.
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-3 flex-wrap">
          {/* Template Version Badge */}
          <div className="px-2.5 py-1 bg-slate-800/80 border border-slate-700 rounded-lg text-xs font-mono text-slate-300 flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span>v{templateVersion}</span>
          </div>

          {/* Save Template Button */}
          <button
            type="button"
            onClick={handleSaveTemplate}
            disabled={isSaving}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-100 border border-slate-600 rounded-lg transition-all shadow-sm disabled:opacity-50"
          >
            <Save className={`w-3.5 h-3.5 ${isSaving ? "animate-spin" : ""}`} />
            <span>{isSaving ? "Saving..." : "Save Template"}</span>
          </button>

          {/* Primary Action: Normalize & Generate */}
          <button
            type="button"
            onClick={handleNormalize}
            disabled={isNormalizing}
            className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg transition-all shadow-md shadow-indigo-500/20 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isNormalizing ? "animate-spin" : ""}`} />
            <span>{isNormalizing ? "Normalising..." : "Apply & Normalise"}</span>
          </button>
        </div>
      </div>

      {/* ----------------------------------------------------------------- */}
      {/* Action Notification Banner                                        */}
      {/* ----------------------------------------------------------------- */}
      {actionMessage && (
        <div
          className={`px-6 py-3 text-xs font-medium flex items-center gap-2 transition-all ${
            actionMessage.type === "success"
              ? "bg-emerald-50 text-emerald-800 border-b border-emerald-200"
              : actionMessage.type === "error"
              ? "bg-rose-50 text-rose-800 border-b border-rose-200"
              : "bg-blue-50 text-blue-800 border-b border-blue-200"
          }`}
        >
          {actionMessage.type === "success" && <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />}
          {actionMessage.type === "error" && <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />}
          <span>{actionMessage.text}</span>
        </div>
      )}

      {/* ----------------------------------------------------------------- */}
      {/* 2. Critical Warning Banners: Formula Cache & Source-of-Truth      */}
      {/* ----------------------------------------------------------------- */}
      <div className="p-6 space-y-4 bg-slate-50 border-b border-slate-200">
        {/* Source-of-Truth Production Count Conflict Prompt */}
        {hasSotConflict && (
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 shadow-sm space-y-3">
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
              <div className="space-y-1">
                <h4 className="text-sm font-semibold text-amber-900">
                  Production Quantity Source-of-Truth Confirmation Required
                </h4>
                <p className="text-xs text-amber-800 leading-relaxed">
                  The scanner detected a discrepancy between the monthly production breakdown (37,111 units) and the summary overview total (46,816 units).
                  To prevent distorted defect rates, PPM charts will remain locked until you confirm which number represents authoritative production output.
                </p>
              </div>
            </div>

            <div className="bg-white/80 p-3 rounded-lg border border-amber-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-center gap-4 text-xs">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="sot_choice"
                    value="monthly_breakdown"
                    checked={sotChoice === "monthly_breakdown"}
                    onChange={() => {
                      setSotChoice("monthly_breakdown");
                      setSotConfirmedQty(37111);
                    }}
                    className="text-indigo-600 focus:ring-indigo-500"
                  />
                  <span className="font-semibold text-slate-800">Monthly Sum (37,111)</span>
                  <span className="text-slate-500 text-[11px]">(Recommended for time-series alignment)</span>
                </label>

                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="sot_choice"
                    value="yearly_overview"
                    checked={sotChoice === "yearly_overview"}
                    onChange={() => {
                      setSotChoice("yearly_overview");
                      setSotConfirmedQty(46816);
                    }}
                    className="text-indigo-600 focus:ring-indigo-500"
                  />
                  <span className="font-semibold text-slate-800">Yearly Ledger Total (46,816)</span>
                </label>
              </div>

              <button
                type="button"
                onClick={() => setSotConfirmed(!sotConfirmed)}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all ${
                  sotConfirmed
                    ? "bg-emerald-100 text-emerald-800 border border-emerald-300"
                    : "bg-amber-600 hover:bg-amber-500 text-white shadow-sm"
                }`}
              >
                {sotConfirmed ? <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" /> : <Check className="w-3.5 h-3.5" />}
                <span>{sotConfirmed ? "Source of Truth Confirmed" : "Confirm Choice"}</span>
              </button>
            </div>
          </div>
        )}

        {/* Formula Cache Warning */}
        {scanResult.blocks.some((b) => b.formula_cache_warning) && (
          <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 flex items-start gap-3 text-xs text-blue-900">
            <HelpCircle className="w-4 h-4 text-blue-600 flex-shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold">Formula Cache Notice: </span>
              Certain calculated formula values in this spreadsheet were empty or uncomputed in the uploaded file.
              The parser safely evaluated data-only values. For absolute numerical precision, open the workbook in Excel, press Save, and re-upload.
            </div>
          </div>
        )}
      </div>

      {/* ----------------------------------------------------------------- */}
      {/* 3. Sheet Tabs                                                     */}
      {/* ----------------------------------------------------------------- */}
      <div className="px-6 pt-4 bg-white border-b border-slate-200">
        <div className="flex items-center gap-2 overflow-x-auto pb-2 scrollbar-none">
          {scanResult.sheet_names.map((sheet) => {
            const count = scanResult.blocks.filter((b) => b.sheet === sheet).length;
            const isActive = sheet === activeSheet;
            return (
              <button
                key={sheet}
                type="button"
                onClick={() => {
                  setActiveSheet(sheet);
                  const firstIdx = scanResult.blocks.findIndex((b) => b.sheet === sheet);
                  if (firstIdx !== -1) setSelectedBlockIdx(firstIdx);
                }}
                className={`px-4 py-2 rounded-t-xl text-xs font-semibold transition-all border-b-2 flex items-center gap-2 ${
                  isActive
                    ? "border-indigo-600 text-indigo-900 bg-indigo-50/50"
                    : "border-transparent text-slate-600 hover:text-slate-900 hover:bg-slate-50"
                }`}
              >
                <FileSpreadsheet className={`w-3.5 h-3.5 ${isActive ? "text-indigo-600" : "text-slate-400"}`} />
                <span>{sheet}</span>
                <span
                  className={`px-1.5 py-0.2 rounded-full text-[10px] font-bold ${
                    isActive ? "bg-indigo-200 text-indigo-900" : "bg-slate-200 text-slate-700"
                  }`}
                >
                  {count}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* ----------------------------------------------------------------- */}
      {/* 4. Main Body: Block Navigator + Block Details Inspector            */}
      {/* ----------------------------------------------------------------- */}
      <div className="grid grid-cols-1 lg:grid-cols-12 min-h-[560px] bg-white">
        {/* Left Column: Detected Blocks List */}
        <div className="lg:col-span-4 border-r border-slate-200 p-5 space-y-3 bg-slate-50/50">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Detected Tables in {activeSheet}
            </h3>
            <span className="text-[11px] text-slate-400 font-mono">
              {sheetBlocks.length} block(s)
            </span>
          </div>

          <div className="space-y-2.5">
            {sheetBlocks.map((b) => {
              const idx = b.originalIndex;
              const mapping = blockMappings[idx];
              const isSelected = idx === selectedBlockIdx;
              const isIncluded = mapping?.included ?? true;

              return (
                <div
                  key={idx}
                  onClick={() => setSelectedBlockIdx(idx)}
                  className={`p-4 rounded-xl border text-xs cursor-pointer transition-all ${
                    isSelected
                      ? "border-indigo-600 bg-white shadow-md ring-1 ring-indigo-500/30"
                      : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50/80"
                  } ${!isIncluded ? "opacity-60 bg-slate-100/50" : ""}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-bold text-slate-900 text-xs">
                        Block #{idx + 1}
                      </span>
                      <span className="px-2 py-0.5 rounded font-mono text-[10px] bg-slate-100 text-slate-700 border border-slate-200">
                        {mapping?.trimmed_range || b.range}
                      </span>
                    </div>

                    {/* Include/Exclude Toggle */}
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setBlockMappings((prev) => ({
                          ...prev,
                          [idx]: { ...prev[idx], included: !isIncluded },
                        }));
                      }}
                      className={`px-2 py-0.5 rounded text-[10px] font-semibold transition-colors ${
                        isIncluded
                          ? "bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100"
                          : "bg-slate-200 text-slate-600 hover:bg-slate-300"
                      }`}
                    >
                      {isIncluded ? "Included" : "Excluded"}
                    </button>
                  </div>

                  <div className="mt-2.5 flex items-center gap-2 flex-wrap">
                    <span className="px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider bg-indigo-50 text-indigo-700 border border-indigo-200">
                      {b.kind}
                    </span>
                    <span className="text-[11px] text-slate-500 font-mono">
                      {b.dimensions.rows} rows × {b.dimensions.cols} cols
                    </span>
                    <span className="text-[11px] text-slate-400">
                      {(b.confidence * 100).toFixed(0)}% confidence
                    </span>
                  </div>

                  {b.ambiguous_row_count > 0 && (
                    <div className="mt-2 text-[11px] text-amber-700 flex items-center gap-1">
                      <AlertTriangle className="w-3 h-3 text-amber-500" />
                      <span>{b.ambiguous_row_count} summary rows need review</span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Column: Block Inspector & Configuration Tabs */}
        <div className="lg:col-span-8 p-6 flex flex-col space-y-6">
          {currentBlock && currentBlockMapping ? (
            <>
              {/* Block Header & Range Trimmer */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-200">
                <div>
                  <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                    <span>Block #{selectedBlockIdx + 1} Configuration</span>
                    <span className="text-xs font-mono font-normal text-slate-500">
                      ({currentBlock.sheet})
                    </span>
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Adjust coordinate boundaries, assign semantic column roles, and map data transformations.
                  </p>
                </div>

                {/* Range Trim Input */}
                <div className="flex items-center gap-2">
                  <label htmlFor="trim_range" className="text-xs font-semibold text-slate-600">
                    Range Trim:
                  </label>
                  <input
                    id="trim_range"
                    type="text"
                    value={currentBlockMapping.trimmed_range || currentBlock.range}
                    onChange={(e) =>
                      updateBlockMapping((bm) => ({ ...bm, trimmed_range: e.target.value.trim() }))
                    }
                    className="w-24 px-2 py-1 text-xs font-mono border border-slate-300 rounded-lg focus:ring-1 focus:ring-indigo-500 text-slate-900"
                    placeholder="e.g. A1:M20"
                  />
                </div>
              </div>

              {/* Inspector Sub-Tabs */}
              <div className="flex items-center gap-1 border-b border-slate-200">
                <button
                  type="button"
                  onClick={() => setActiveSubTab("roles")}
                  className={`px-3 py-1.5 text-xs font-semibold rounded-t-lg transition-all border-b-2 flex items-center gap-1.5 ${
                    activeSubTab === "roles"
                      ? "border-indigo-600 text-indigo-700 bg-indigo-50/40"
                      : "border-transparent text-slate-600 hover:text-slate-900"
                  }`}
                >
                  <Tag className="w-3.5 h-3.5" />
                  <span>Column Roles ({currentBlock.column_names.length})</span>
                </button>

                {currentBlock.kind === "wide" && (
                  <button
                    type="button"
                    onClick={() => setActiveSubTab("unpivot")}
                    className={`px-3 py-1.5 text-xs font-semibold rounded-t-lg transition-all border-b-2 flex items-center gap-1.5 ${
                      activeSubTab === "unpivot"
                        ? "border-indigo-600 text-indigo-700 bg-indigo-50/40"
                        : "border-transparent text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    <Sliders className="w-3.5 h-3.5" />
                    <span>Unpivot (Monthly Columns)</span>
                  </button>
                )}

                {currentBlock.ambiguous_rows.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setActiveSubTab("ambiguous")}
                    className={`px-3 py-1.5 text-xs font-semibold rounded-t-lg transition-all border-b-2 flex items-center gap-1.5 ${
                      activeSubTab === "ambiguous"
                        ? "border-indigo-600 text-indigo-700 bg-indigo-50/40"
                        : "border-transparent text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
                    <span>Summary Rows ({currentBlock.ambiguous_rows.length})</span>
                  </button>
                )}

                {currentBlock.cell_colours.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setActiveSubTab("colours")}
                    className={`px-3 py-1.5 text-xs font-semibold rounded-t-lg transition-all border-b-2 flex items-center gap-1.5 ${
                      activeSubTab === "colours"
                        ? "border-indigo-600 text-indigo-700 bg-indigo-50/40"
                        : "border-transparent text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    <Sparkles className="w-3.5 h-3.5 text-purple-500" />
                    <span>Colour Statuses</span>
                  </button>
                )}
              </div>

              {/* Sub-Tab 1: Column Roles Editor */}
              {activeSubTab === "roles" && (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-[380px] overflow-y-auto pr-1">
                    {currentBlock.column_names.map((colName) => {
                      const currentRole = currentBlockMapping.column_roles[colName] || "text";
                      return (
                        <div
                          key={colName}
                          className="p-3 rounded-xl border border-slate-200 bg-slate-50/50 hover:bg-slate-50 flex items-center justify-between gap-3 transition-colors"
                        >
                          <div className="min-w-0">
                            <p className="text-xs font-semibold text-slate-900 truncate" title={colName}>
                              {colName}
                            </p>
                            <p className="text-[10px] text-slate-500 font-mono mt-0.5">
                              Inferred: {currentBlock.column_roles[colName] || "text"}
                            </p>
                          </div>

                          {/* Role Selector Dropdown */}
                          <select
                            value={currentRole}
                            onChange={(e) => handleRoleChange(colName, e.target.value as ColumnRole)}
                            aria-label={`Role for column ${colName}`}
                            className="text-xs font-medium bg-white border border-slate-300 rounded-lg px-2.5 py-1 text-slate-800 focus:ring-1 focus:ring-indigo-500"
                          >
                            {ROLE_OPTIONS.map((opt) => (
                              <option key={opt.role} value={opt.role}>
                                {opt.label}
                              </option>
                            ))}
                          </select>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Sub-Tab 2: Unpivot Configuration */}
              {activeSubTab === "unpivot" && currentBlockMapping.unpivot && (
                <div className="space-y-4 p-4 rounded-xl bg-slate-50 border border-slate-200 text-xs">
                  <div className="flex items-center justify-between">
                    <div>
                      <h4 className="font-semibold text-slate-900">Wide Monthly Column Unpivot</h4>
                      <p className="text-slate-500 text-[11px] mt-0.5">
                        Transforms horizontal month series (e.g. Jan-26, Feb-26) into clean normalized rows.
                      </p>
                    </div>

                    <label className="flex items-center gap-2 cursor-pointer font-semibold text-slate-800">
                      <input
                        type="checkbox"
                        checked={currentBlockMapping.unpivot.enabled}
                        onChange={(e) =>
                          updateBlockMapping((bm) => ({
                            ...bm,
                            unpivot: bm.unpivot ? { ...bm.unpivot, enabled: e.target.checked } : undefined,
                          }))
                        }
                        className="rounded text-indigo-600 focus:ring-indigo-500"
                      />
                      <span>Enable Unpivot</span>
                    </label>
                  </div>

                  {currentBlockMapping.unpivot.enabled && (
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-3 border-t border-slate-200">
                      <div>
                        <label className="font-semibold text-slate-700 block mb-1">Date Column Name</label>
                        <input
                          type="text"
                          value={currentBlockMapping.unpivot.variable_name}
                          onChange={(e) =>
                            updateBlockMapping((bm) => ({
                              ...bm,
                              unpivot: bm.unpivot ? { ...bm.unpivot, variable_name: e.target.value } : undefined,
                            }))
                          }
                          className="w-full px-2.5 py-1 text-xs border border-slate-300 rounded-lg bg-white"
                        />
                      </div>

                      <div>
                        <label className="font-semibold text-slate-700 block mb-1">Value Column Name</label>
                        <input
                          type="text"
                          value={currentBlockMapping.unpivot.value_name}
                          onChange={(e) =>
                            updateBlockMapping((bm) => ({
                              ...bm,
                              unpivot: bm.unpivot ? { ...bm.unpivot, value_name: e.target.value } : undefined,
                            }))
                          }
                          className="w-full px-2.5 py-1 text-xs border border-slate-300 rounded-lg bg-white"
                        />
                      </div>

                      <div>
                        <label className="font-semibold text-slate-700 block mb-1">Measure Tag</label>
                        <input
                          type="text"
                          value={currentBlockMapping.unpivot.measure_name || ""}
                          onChange={(e) =>
                            updateBlockMapping((bm) => ({
                              ...bm,
                              unpivot: bm.unpivot ? { ...bm.unpivot, measure_name: e.target.value } : undefined,
                            }))
                          }
                          className="w-full px-2.5 py-1 text-xs border border-slate-300 rounded-lg bg-white"
                        />
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Sub-Tab 3: Ambiguous Row Triage */}
              {activeSubTab === "ambiguous" && (
                <div className="space-y-3">
                  <p className="text-xs text-slate-500">
                    The scanner identified rows that may be summary totals rather than atomic records. Select how each should be handled:
                  </p>

                  <div className="space-y-2 max-h-[300px] overflow-y-auto">
                    {currentBlockMapping.ambiguous_row_decisions.map((ar) => (
                      <div
                        key={ar.source_row}
                        className="p-3 bg-slate-50 border border-slate-200 rounded-xl flex items-center justify-between gap-3 text-xs"
                      >
                        <div>
                          <p className="font-semibold text-slate-900">
                            Sheet Row #{ar.sheet_row} (Source index: {ar.source_row})
                          </p>
                          <p className="text-[11px] text-slate-500 mt-0.5">{ar.reason}</p>
                        </div>

                        {/* Decision Buttons */}
                        <div className="flex items-center gap-1.5 bg-white p-1 rounded-lg border border-slate-200">
                          <button
                            type="button"
                            onClick={() => handleAmbiguousDecision(ar.source_row, "record")}
                            className={`px-2 py-0.5 rounded text-[11px] font-semibold transition-colors ${
                              ar.decision === "record"
                                ? "bg-indigo-600 text-white"
                                : "text-slate-600 hover:bg-slate-100"
                            }`}
                          >
                            Record
                          </button>
                          <button
                            type="button"
                            onClick={() => handleAmbiguousDecision(ar.source_row, "summary")}
                            className={`px-2 py-0.5 rounded text-[11px] font-semibold transition-colors ${
                              ar.decision === "summary"
                                ? "bg-amber-600 text-white"
                                : "text-slate-600 hover:bg-slate-100"
                            }`}
                          >
                            Summary
                          </button>
                          <button
                            type="button"
                            onClick={() => handleAmbiguousDecision(ar.source_row, "discard")}
                            className={`px-2 py-0.5 rounded text-[11px] font-semibold transition-colors ${
                              ar.decision === "discard"
                                ? "bg-rose-600 text-white"
                                : "text-slate-600 hover:bg-slate-100"
                            }`}
                          >
                            Discard
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Sub-Tab 4: Cell Colour Status Mapping */}
              {activeSubTab === "colours" && (
                <div className="space-y-3">
                  <p className="text-xs text-slate-500">
                    Map Excel cell fill colors to semantic status labels (e.g. Green = Completed, Red = Overdue):
                  </p>

                  <div className="space-y-2">
                    {currentBlockMapping.colour_mappings.map((cm) => (
                      <div
                        key={cm.rgb}
                        className="p-3 bg-slate-50 border border-slate-200 rounded-xl flex items-center justify-between gap-3 text-xs"
                      >
                        <div className="flex items-center gap-3">
                          <span
                            className="w-6 h-6 rounded-md border border-slate-300 shadow-inner flex-shrink-0"
                            style={{ backgroundColor: cm.rgb }}
                          />
                          <span className="font-mono font-semibold text-slate-800">{cm.rgb}</span>
                        </div>

                        <div className="flex items-center gap-2">
                          <input
                            type="text"
                            value={cm.status_label}
                            onChange={(e) => handleColourStatusChange(cm.rgb, e.target.value)}
                            aria-label={`Status label for ${cm.rgb}`}
                            className="px-2.5 py-1 text-xs border border-slate-300 rounded-lg bg-white text-slate-900 w-36 font-semibold"
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Bounded Sample Preview Table */}
              <div className="pt-4 border-t border-slate-200">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-slate-600 flex items-center gap-1.5">
                    <Eye className="w-3.5 h-3.5 text-slate-400" />
                    <span>Sample Table Preview</span>
                  </span>
                  <span className="text-[11px] text-slate-400 font-mono">
                    Showing top {currentBlock.sample_preview.length} rows
                  </span>
                </div>

                <div className="border border-slate-200 rounded-xl overflow-x-auto max-h-[160px] bg-slate-50/30">
                  <table className="w-full text-left text-[11px] border-collapse">
                    <thead>
                      <tr className="bg-slate-100 border-b border-slate-200 text-slate-700 font-semibold">
                        {currentBlock.column_names.slice(0, 10).map((col) => (
                          <th key={col} className="px-3 py-1.5 truncate max-w-[120px]">
                            {col}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 bg-white">
                      {currentBlock.sample_preview.map((row, rIdx) => (
                        <tr key={rIdx} className="hover:bg-slate-50/80">
                          {row.slice(0, 10).map((cell, cIdx) => (
                            <td key={cIdx} className="px-3 py-1 text-slate-600 truncate max-w-[120px]">
                              {cell === null ? (
                                <span className="text-slate-300 italic">null</span>
                              ) : (
                                String(cell)
                              )}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-center p-8 text-slate-400">
              <TableProperties className="w-12 h-12 text-slate-300 mb-2" />
              <p className="text-sm font-semibold text-slate-600">No Block Selected</p>
              <p className="text-xs">Choose a detected block from the list on the left to configure.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
