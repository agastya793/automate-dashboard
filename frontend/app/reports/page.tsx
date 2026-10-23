import Link from "next/link";
import { FileText, UploadCloud, Filter, Plus, Calendar } from "lucide-react";
import { Header } from "@/components/Header";
import { EmptyState } from "@/components/EmptyState";

export default function ReportsPage() {
  return (
    <div className="flex flex-col min-h-full">
      <Header
        title="Saved Reports"
        description="View, export, and inspect previously generated business reporting dashboards."
        actions={
          <Link
            href="/upload"
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-brand-600 hover:bg-brand-700 rounded-lg shadow-sm transition-colors focus:ring-2 focus:ring-brand-500 focus:ring-offset-2"
          >
            <Plus className="w-4 h-4" />
            <span>New Report</span>
          </Link>
        }
      />

      <div className="p-6 sm:p-8 space-y-6 max-w-7xl">
        {/* Filter / Controls Bar (Disabled in empty state) */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 bg-white rounded-xl border border-slate-200">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-slate-200 bg-slate-50 text-xs text-slate-500">
              <Calendar className="w-3.5 h-3.5" />
              <span>All Dates</span>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-slate-200 bg-slate-50 text-xs text-slate-500">
              <Filter className="w-3.5 h-3.5" />
              <span>All Types</span>
            </div>
          </div>
          <span className="text-xs text-slate-500 font-medium">
            0 reports total
          </span>
        </div>

        {/* Empty State */}
        <EmptyState
          icon={FileText}
          title="No reports created yet"
          description="Reports will appear here once you upload an Excel or CSV dataset, confirm the detected column schema, and generate analytics."
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
      </div>
    </div>
  );
}
