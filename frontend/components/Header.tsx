import { ReactNode } from "react";

interface HeaderProps {
  title: string;
  description?: string;
  actions?: ReactNode;
}

export function Header({ title, description, actions }: HeaderProps) {
  return (
    <header className="bg-white border-b border-slate-200 px-6 py-5 sm:px-8">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight">
            {title}
          </h1>
          {description && (
            <p className="mt-1 text-sm text-slate-500 leading-normal max-w-3xl">
              {description}
            </p>
          )}
        </div>
        {actions && (
          <div className="flex items-center gap-3 flex-shrink-0">
            {actions}
          </div>
        )}
      </div>
    </header>
  );
}
