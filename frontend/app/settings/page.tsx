import {
  Building2,
  FileSpreadsheet,
  Database,
  Lock,
  Layers,
  CheckCircle,
  HelpCircle,
} from "lucide-react";
import { Header } from "@/components/Header";

export default function SettingsPage() {
  return (
    <div className="flex flex-col min-h-full">
      <Header
        title="Settings"
        description="Configure workspace preferences, reporting defaults, and review system integration status."
      />

      <div className="p-6 sm:p-8 space-y-8 max-w-4xl">
        {/* Workspace Profile Settings */}
        <section aria-labelledby="workspace-section-heading" className="bg-white rounded-xl border border-slate-200 p-6 sm:p-7 shadow-sm space-y-6">
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center text-slate-700 flex-shrink-0">
              <Building2 className="w-5 h-5" />
            </div>
            <div>
              <h2 id="workspace-section-heading" className="text-base font-semibold text-slate-900 tracking-tight">
                Workspace Preferences
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                General display and regional options for generated reports.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 pt-2">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-700">
                Workspace Name
              </label>
              <input
                type="text"
                readOnly
                defaultValue="My Business Operations"
                className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg bg-slate-50 text-slate-700 focus:outline-none"
              />
              <p className="text-[11px] text-slate-500">
                Local workspace identifier for report titles.
              </p>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-700">
                Default Currency Symbol
              </label>
              <select
                disabled
                defaultValue="USD"
                className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg bg-slate-50 text-slate-700 focus:outline-none cursor-not-allowed"
              >
                <option value="USD">USD ($)</option>
                <option value="EUR">EUR (€)</option>
                <option value="GBP">GBP (£)</option>
                <option value="INR">INR (₹)</option>
              </select>
              <p className="text-[11px] text-slate-500">
                Applied to currency-detected columns in Phase 2.
              </p>
            </div>
          </div>
        </section>

        {/* Export & Reporting Defaults */}
        <section aria-labelledby="export-section-heading" className="bg-white rounded-xl border border-slate-200 p-6 sm:p-7 shadow-sm space-y-6">
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center text-slate-700 flex-shrink-0">
              <FileSpreadsheet className="w-5 h-5" />
            </div>
            <div>
              <h2 id="export-section-heading" className="text-base font-semibold text-slate-900 tracking-tight">
                Reporting & Export Defaults
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Output configurations for PDF generation and spreadsheet downloads.
              </p>
            </div>
          </div>

          <div className="space-y-3 pt-2">
            <div className="flex items-center justify-between p-3 rounded-lg border border-slate-100 bg-slate-50/70">
              <div>
                <p className="text-xs font-semibold text-slate-800">
                  Include raw data table summary in PDF export
                </p>
                <p className="text-[11px] text-slate-500">
                  Appends verified aggregate tables alongside executive charts.
                </p>
              </div>
              <span className="text-[11px] font-medium text-slate-500 bg-slate-200 px-2 py-0.5 rounded">
                Default: Enabled (Phase 4)
              </span>
            </div>

            <div className="flex items-center justify-between p-3 rounded-lg border border-slate-100 bg-slate-50/70">
              <div>
                <p className="text-xs font-semibold text-slate-800">
                  Strict schema adherence
                </p>
                <p className="text-[11px] text-slate-500">
                  Refuses report generation if column header types contain ambiguous values without manual verification.
                </p>
              </div>
              <span className="text-[11px] font-medium text-slate-500 bg-slate-200 px-2 py-0.5 rounded">
                Strict by design
              </span>
            </div>
          </div>
        </section>

        {/* Database & Authentication Roadmap Notice */}
        <section aria-labelledby="integration-section-heading" className="bg-white rounded-xl border border-slate-200 p-6 sm:p-7 shadow-sm space-y-4">
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-lg bg-indigo-50 flex items-center justify-center text-brand-600 flex-shrink-0">
              <Database className="w-5 h-5" />
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <h2 id="integration-section-heading" className="text-base font-semibold text-slate-900 tracking-tight">
                  Database & Authentication Roadmap
                </h2>
                <span className="text-[10px] font-bold uppercase tracking-wider text-brand-700 bg-brand-50 px-2 py-0.5 rounded border border-brand-200">
                  Planned for Phase 3
                </span>
              </div>
              <p className="text-xs text-slate-500 leading-relaxed">
                Supabase PostgreSQL, Supabase Auth, and Supabase Storage will be introduced in a future development phase. No database or auth credentials are required for this Phase 1 foundation.
              </p>
            </div>
          </div>

          <div className="p-4 rounded-lg bg-slate-50 border border-slate-200/80 space-y-2 text-xs text-slate-600">
            <div className="flex items-center gap-2 text-slate-800 font-semibold">
              <Lock className="w-3.5 h-3.5 text-slate-500" />
              <span>Upcoming Security Features:</span>
            </div>
            <ul className="list-disc list-inside space-y-1 text-slate-500 pl-1">
              <li>Supabase Row-Level Security (RLS) ensuring strict multi-tenant isolation</li>
              <li>Secure token handling via server-side session cookies</li>
              <li>Protected file storage buckets for uploaded client workbooks</li>
            </ul>
          </div>
        </section>
      </div>
    </div>
  );
}
