"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, Menu, X } from "lucide-react";
import { navigationItems } from "@/components/Sidebar";
import { cn } from "@/lib/utils";

export function MobileNav() {
  const [isOpen, setIsOpen] = useState(false);
  const pathname = usePathname();

  const handleClose = () => setIsOpen(false);

  return (
    <div className="md:hidden sticky top-0 z-40 bg-white border-b border-slate-200">
      <div className="h-16 px-4 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2.5" onClick={handleClose}>
          <div className="w-8 h-8 rounded-lg bg-brand-600 flex items-center justify-center text-white shadow-sm">
            <BarChart3 className="w-4 h-4" />
          </div>
          <span className="font-semibold text-slate-900 text-sm tracking-tight">
            Reporting Dashboard
          </span>
        </Link>

        <button
          type="button"
          aria-label={isOpen ? "Close menu" : "Open menu"}
          onClick={() => setIsOpen(!isOpen)}
          className="p-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-md focus:outline-none focus:ring-2 focus:ring-brand-500"
        >
          {isOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </div>

      {/* Drawer */}
      {isOpen && (
        <div className="fixed inset-0 top-16 z-50 bg-slate-900/40 backdrop-blur-sm">
          <div className="bg-white border-b border-slate-200 shadow-xl px-4 py-4 space-y-1">
            <div className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-600">
              Navigation
            </div>
            {navigationItems.map((item) => {
              const isActive =
                pathname === item.href ||
                (item.href !== "/" && pathname.startsWith(item.href));
              const Icon = item.icon;

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={handleClose}
                  className={cn(
                    "flex items-center gap-3 px-3 py-2.5 text-sm font-medium rounded-md transition-colors",
                    isActive
                      ? "bg-slate-100 text-brand-700 font-semibold"
                      : "text-slate-700 hover:bg-slate-50 hover:text-slate-900"
                  )}
                >
                  <Icon
                    className={cn(
                      "w-4 h-4 flex-shrink-0",
                      isActive ? "text-brand-600" : "text-slate-600"
                    )}
                  />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
