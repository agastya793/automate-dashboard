"use client";

import React from "react";
import Link from "next/link";
import { BarChart3, AlertCircle, ArrowLeft } from "lucide-react";

export default function ForgotPasswordPage() {
  return (
    <div className="min-h-[80vh] flex flex-col justify-center items-center px-4 sm:px-6 lg:px-8 py-12">
      <div className="w-full max-w-md space-y-6">
        {/* Brand Header */}
        <div className="text-center space-y-2">
          <div className="w-12 h-12 rounded-xl bg-brand-600 flex items-center justify-center text-white shadow-md mx-auto">
            <BarChart3 className="w-7 h-7" />
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            Password Recovery
          </h1>
          <p className="text-xs text-slate-500">
            Secure self-service credential recovery
          </p>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 p-8 shadow-sm space-y-5">
          <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-xs space-y-2">
            <div className="flex items-center gap-2 font-bold text-amber-800">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>Production Prerequisite: SMTP Not Configured</span>
            </div>
            <p className="text-[11px] leading-relaxed text-amber-800/90">
              In this on-premise private deployment, self-service email delivery is intentionally disabled until an internal SMTP relay or transactional mail server is connected.
            </p>
          </div>

          <div className="text-xs text-slate-600 space-y-3 leading-relaxed">
            <p>
              To regain access to your account or reset credentials:
            </p>
            <ul className="list-disc list-inside space-y-1.5 pl-1 text-[11px] text-slate-500">
              <li>Contact your organization&apos;s <strong>Workspace Administrator</strong> to update your account status.</li>
              <li>Or run the administrative CLI command in the backend: <code className="bg-slate-100 text-slate-800 px-1 py-0.5 rounded font-mono">python -m app.auth reset-password</code></li>
            </ul>
          </div>

          <div className="pt-3 border-t border-slate-100 text-center">
            <Link
              href="/login"
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-brand-600 hover:text-brand-700"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Return to Sign In</span>
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
