import { ReactNode } from "react";
import { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: ReactNode;
  secondaryAction?: ReactNode;
  className?: string;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  secondaryAction,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "rounded-xl border border-dashed border-slate-300 bg-white p-8 sm:p-12 text-center flex flex-col items-center justify-center",
        className
      )}
    >
      <div className="w-12 h-12 rounded-xl bg-slate-100 border border-slate-200/80 flex items-center justify-center text-slate-500 mb-4 shadow-sm">
        <Icon className="w-6 h-6" />
      </div>
      <h3 className="text-base font-semibold text-slate-900 tracking-tight mb-1.5">
        {title}
      </h3>
      <p className="text-sm text-slate-500 max-w-md mx-auto mb-6 leading-relaxed">
        {description}
      </p>
      {(action || secondaryAction) && (
        <div className="flex flex-col sm:flex-row items-center gap-3">
          {action}
          {secondaryAction}
        </div>
      )}
    </div>
  );
}
