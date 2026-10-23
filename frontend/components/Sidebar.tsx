"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  UploadCloud,
  FileText,
  Settings,
  BarChart3,
  CheckCircle2,
  LogOut,
  LogIn,
  User as UserIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/context/AuthContext";

export interface NavItem {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: string;
}

export const navigationItems: NavItem[] = [
  { label: "Overview", href: "/", icon: LayoutDashboard },
  { label: "Upload Data", href: "/upload", icon: UploadCloud },
  { label: "Dashboard", href: "/dashboard", icon: BarChart3 },
  { label: "Reports", href: "/reports", icon: FileText },
  { label: "Settings", href: "/settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const { user, profile, workspace, role, signOut } = useAuth();

  return (
    <aside className="hidden md:flex md:w-64 md:flex-col md:fixed md:inset-y-0 bg-white border-r border-slate-200 z-30">
      {/* Brand Header */}
      <div className="h-16 flex items-center px-6 border-b border-slate-200 gap-3">
        <div className="w-9 h-9 rounded-lg bg-brand-600 flex items-center justify-center text-white shadow-sm flex-shrink-0">
          <BarChart3 className="w-5 h-5" />
        </div>
        <div className="flex flex-col min-w-0">
          <span className="font-semibold text-slate-900 text-sm tracking-tight truncate leading-tight">
            Reporting Dashboard
          </span>
          <span className="text-xs text-slate-500 font-medium truncate">
            Automated Analytics
          </span>
        </div>
      </div>

      {/* Navigation Links */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        <div className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-600">
          Main Navigation
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
              className={cn(
                "group flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-md transition-colors",
                isActive
                  ? "bg-slate-100 text-brand-700 font-semibold"
                  : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
              )}
            >
              <Icon
                className={cn(
                  "w-4 h-4 flex-shrink-0 transition-colors",
                  isActive
                    ? "text-brand-600"
                    : "text-slate-600 group-hover:text-slate-600"
                )}
              />
              <span className="truncate flex-1">{item.label}</span>
              {item.badge && (
                <span className="text-[10px] bg-slate-200 text-slate-700 px-1.5 py-0.5 rounded font-mono">
                  {item.badge}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Account / Authentication Footer */}
      <div className="p-3.5 border-t border-slate-200 bg-slate-50/70">
        {user ? (
          <div className="space-y-2">
            <div className="flex items-center gap-2.5 px-1">
              <div className="w-8 h-8 rounded-full bg-brand-100 border border-brand-200 text-brand-700 flex items-center justify-center font-bold text-xs flex-shrink-0">
                {profile?.display_name?.charAt(0).toUpperCase() ||
                  user.email?.charAt(0).toUpperCase() ||
                  "U"}
              </div>
              <div className="flex flex-col min-w-0 flex-1">
                <span className="text-xs font-bold text-slate-900 truncate">
                  {profile?.display_name || user.email?.split("@")[0]}
                </span>
                <span className="text-[10px] text-slate-500 truncate">
                  {workspace
                    ? `${workspace.name} (${role || "owner"})`
                    : user.email}
                </span>
              </div>
            </div>
            <button
              type="button"
              onClick={() => signOut()}
              className="w-full flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-semibold text-slate-600 hover:text-rose-700 hover:bg-rose-50 transition-colors cursor-pointer"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span>Sign Out</span>
            </button>
          </div>
        ) : (
          <div className="space-y-2 px-1">
            <div className="flex items-center justify-between text-[11px] text-slate-500 font-medium">
              <span>Guest Session</span>
              <span className="text-[10px] bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded font-bold uppercase">
                Unauthenticated
              </span>
            </div>
            <Link
              href="/login"
              className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold text-white bg-brand-600 hover:bg-brand-700 transition-colors shadow-xs"
            >
              <LogIn className="w-3.5 h-3.5" />
              <span>Sign In</span>
            </Link>
          </div>
        )}
      </div>
    </aside>
  );
}
