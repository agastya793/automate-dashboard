import Link from "next/link";
import {
  FileText,
  Database,
  Activity,
  UploadCloud,
  FileSpreadsheet,
  CheckCircle2,
  Sparkles,
  ArrowRight,
  ShieldCheck,
} from "lucide-react";
import { Header } from "@/components/Header";
import { SummaryCard } from "@/components/SummaryCard";
import { EmptyState } from "@/components/EmptyState";

export default function OverviewPage() {
  return (
    <div className="flex flex-col min-h-full">
      <Header
        title="Business Reporting Dashboard"
        description="Semi-automated reporting system for business owners. Inspect Excel and CSV files, validate dataset structures, and generate verified interactive reports."
        actions={
          <Link
            href="/upload"
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-brand-600 hover:bg-brand-700 active:bg-brand-800 rounded-lg shadow-sm transition-colors focus:ring-2 focus:ring-brand-500 focus:ring-offset-2"
          >
            <UploadCloud className="w-4 h-4" />
            <span>Upload Dataset</span>
          </Link>
        }
      />

      <div className="p-6 sm:p-8 space-y-8 max-w-7xl">
        {/* Welcome Banner */}
        <section aria-labelledby="welcome-heading" className="bg-white rounded-xl border border-slate-200 p-6 sm:p-7 shadow-sm">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
            <div className="space-y-2 max-w-2xl">
              <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-slate-100 text-slate-700 text-xs font-medium">
                <ShieldCheck className="w-3.5 h-3.5 text-brand-600" />
                <span>Verified Business Logic — No AI Hallucinations</span>
              </div>
              <h2
                id="welcome-heading"
                className="text-lg sm:text-xl font-bold text-slate-900 tracking-tight"
              >
                Welcome to your Reporting Workspace
              </h2>
              <p className="text-sm text-slate-600 leading-relaxed">
                Transform messy spreadsheets into clean, verifiable executive
                summaries. Upload your raw workbook or CSV, review automated column
                structure detection, and publish interactive dashboards with total
                confidence in the underlying numbers.
              </p>
            </div>
            <div className="flex-shrink-0">
              <Link
                href="/upload"
                className="inline-flex items-center justify-center gap-2 w-full sm:w-auto px-5 py-2.5 text-sm font-semibold text-white bg-slate-900 hover:bg-slate-800 rounded-lg transition-colors shadow-sm"
              >
                <span>Get Started</span>
                <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
          </div>
        </section>

        {/* Honest System Metrics */}
        <section aria-label="Key Performance Indicators">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
            <SummaryCard
              label="Total Reports"
              value={0}
              subtext="No reports generated yet"
              icon={FileText}
              badge={{ text: "Phase 1 Ready", variant: "muted" }}
            />
            <SummaryCard
              label="Datasets Processed"
              value={0}
              subtext="No active dataset uploaded"
              icon={Database}
              badge={{ text: "Awaiting Input", variant: "muted" }}
            />
            <SummaryCard
              label="Recent Activity"
              value="None"
              subtext="Workspace initialized cleanly"
              icon={Activity}
              badge={{ text: "Idle", variant: "muted" }}
            />
          </div>
        </section>

        {/* Planned Reporting Workflow */}
        <section aria-labelledby="workflow-heading" className="bg-white rounded-xl border border-slate-200 p-6 sm:p-7 shadow-sm">
          <div className="mb-5">
            <h2
              id="workflow-heading"
              className="text-base font-semibold text-slate-900 tracking-tight"
            >
              Reporting Workflow
            </h2>
            <p className="text-xs text-slate-500 mt-1">
              Deterministic, step-by-step reporting ensures accuracy without black-box calculations.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="p-4 rounded-lg bg-slate-50 border border-slate-200/80">
              <div className="w-7 h-7 rounded-md bg-brand-50 text-brand-700 text-xs font-bold flex items-center justify-center mb-3">
                1
              </div>
              <h3 className="text-sm font-semibold text-slate-900 mb-1">
                Upload File
              </h3>
              <p className="text-xs text-slate-500 leading-relaxed">
                Accepts multi-sheet .xlsx workbooks and raw .csv data exports.
              </p>
            </div>

            <div className="p-4 rounded-lg bg-slate-50 border border-slate-200/80">
              <div className="w-7 h-7 rounded-md bg-slate-200 text-slate-700 text-xs font-bold flex items-center justify-center mb-3">
                2
              </div>
              <h3 className="text-sm font-semibold text-slate-900 mb-1">
                Inspect & Validate
              </h3>
              <p className="text-xs text-slate-500 leading-relaxed">
                Evaluates row counts, null values, headers, and column data types.
              </p>
            </div>

            <div className="p-4 rounded-lg bg-slate-50 border border-slate-200/80">
              <div className="w-7 h-7 rounded-md bg-slate-200 text-slate-700 text-xs font-bold flex items-center justify-center mb-3">
                3
              </div>
              <h3 className="text-sm font-semibold text-slate-900 mb-1">
                Review Suggestions
              </h3>
              <p className="text-xs text-slate-500 leading-relaxed">
                App proposes relevant visualizations based on data shape and categories.
              </p>
            </div>

            <div className="p-4 rounded-lg bg-slate-50 border border-slate-200/80">
              <div className="w-7 h-7 rounded-md bg-slate-200 text-slate-700 text-xs font-bold flex items-center justify-center mb-3">
                4
              </div>
              <h3 className="text-sm font-semibold text-slate-900 mb-1">
                Publish & Export
              </h3>
              <p className="text-xs text-slate-500 leading-relaxed">
                Generate interactive dashboard with downloadable PDF and Excel summaries.
              </p>
            </div>
          </div>
        </section>

        {/* Recent Reports Section with Honest Empty State */}
        <section aria-labelledby="reports-heading" className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2
                id="reports-heading"
                className="text-base font-semibold text-slate-900 tracking-tight"
              >
                Recent Reports
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Saved business summaries and scheduled reporting runs.
              </p>
            </div>
          </div>

          <EmptyState
            icon={FileSpreadsheet}
            title="No reports generated yet"
            description="You haven't generated any business reports yet. Upload an Excel or CSV file to start the reporting workflow."
            action={
              <Link
                href="/upload"
                className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-brand-600 hover:bg-brand-700 rounded-lg shadow-sm transition-colors"
              >
                <UploadCloud className="w-4 h-4" />
                <span>Upload your first dataset</span>
              </Link>
            }
          />
        </section>
      </div>
    </div>
  );
}
