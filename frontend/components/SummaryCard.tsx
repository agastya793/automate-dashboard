import { ReactNode } from "react";
import { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface SummaryCardProps {
  label: string;
  value: string | number;
  subtext: string;
  icon: LucideIcon;
  badge?: {
    text: string;
    variant?: "default" | "muted" | "info";
  };
  className?: string;
}

export function SummaryCard({
  label,
  value,
  subtext,
  icon: Icon,
  badge,
  className,
}: SummaryCardProps) {
  return (
    <div
      className={cn(
        "bg-white rounded-xl border border-slate-200 p-5 shadow-sm hover:border-slate-300 transition-all",
        className
      )}
    >
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
          {label}
        </span>
        <div className="w-8 h-8 rounded-lg bg-slate-100 flex items-center justify-center text-slate-600">
          <Icon className="w-4 h-4" />
        </div>
      </div>
      <div className="flex items-baseline gap-2 mb-1">
        <span className="text-2xl sm:text-3xl font-bold text-slate-900 tracking-tight">
          {value}
        </span>
        {badge && (
          <span
            className={cn(
              "text-[11px] font-medium px-2 py-0.5 rounded-full",
              badge.variant === "info" && "bg-brand-50 text-brand-700",
              badge.variant === "muted" && "bg-slate-100 text-slate-600",
              (!badge.variant || badge.variant === "default") && "bg-slate-100 text-slate-700"
            )}
          >
            {badge.text}
          </span>
        )}
      </div>
      <p className="text-xs text-slate-500 font-normal leading-relaxed">
        {subtext}
      </p>
    </div>
  );
}
