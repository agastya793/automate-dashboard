import type { Metadata } from "next";
import { Sidebar } from "@/components/Sidebar";
import { MobileNav } from "@/components/MobileNav";
import { AuthProvider } from "@/context/AuthContext";
import { DashboardProvider } from "@/context/DashboardContext";
import "@/app/globals.css";

export const metadata: Metadata = {
  title: {
    default: "Business Reporting Dashboard",
    template: "%s | Business Reporting Dashboard",
  },
  description:
    "Automated reporting platform to inspect Excel & CSV datasets, detect column structures, and generate verified business analytics.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full">
      <body className="h-full bg-slate-50 text-slate-900 font-sans flex flex-col">
        <AuthProvider>
          <DashboardProvider>
            {/* Mobile Navigation Header */}
            <MobileNav />

            <div className="flex-1 flex w-full">
              {/* Desktop Fixed Sidebar */}
              <Sidebar />

              {/* Main Content Area (offset by sidebar on md+ screens) */}
              <div className="flex-1 flex flex-col min-w-0 md:pl-64">
                <main className="flex-1 pb-16">{children}</main>
              </div>
            </div>
          </DashboardProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
