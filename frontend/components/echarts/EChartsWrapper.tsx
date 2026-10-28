"use client";

import React, { useEffect, useRef } from "react";
import * as echarts from "echarts";
import { AlertCircle, RotateCw } from "lucide-react";

export interface EChartsWrapperProps {
  option: echarts.EChartsOption | null;
  loading?: boolean;
  className?: string;
  style?: React.CSSProperties;
  emptyMessage?: string;
  onChartReady?: (chart: echarts.ECharts) => void;
  onEvents?: Record<string, (params: any) => void>;
}

/**
 * Lifecycle-safe, SSR-proof Apache ECharts wrapper for Next.js App Router (React 19).
 *
 * Guarantees:
 * 1. Initializes strictly on client mount in useEffect().
 * 2. Automatic responsive resize via ResizeObserver.
 * 3. Guaranteed disposal on component unmount via chart.dispose().
 * 4. High-DPI canvas rendering.
 * 5. Accessible loading and empty data states.
 */
export function EChartsWrapper({
  option,
  loading = false,
  className = "w-full h-80",
  style,
  emptyMessage = "No data points available for the selected filters.",
  onChartReady,
  onEvents,
}: EChartsWrapperProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartInstanceRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // Initialize ECharts instance
    if (!chartInstanceRef.current) {
      const chart = echarts.init(containerRef.current, undefined, {
        renderer: "canvas",
      });
      chartInstanceRef.current = chart;
      if (onChartReady) {
        onChartReady(chart);
      }
    }

    const chart = chartInstanceRef.current;

    // Register event listeners
    if (onEvents && chart) {
      Object.entries(onEvents).forEach(([eventName, handler]) => {
        chart.off(eventName);
        chart.on(eventName, handler);
      });
    }

    // Set chart options
    if (option && chart) {
      chart.setOption(option, { notMerge: true, lazyUpdate: true });
    }

    // ResizeObserver for reliable responsive resizing
    const resizeObserver = new ResizeObserver(() => {
      if (chart && !chart.isDisposed()) {
        chart.resize();
      }
    });

    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      if (chart && !chart.isDisposed()) {
        chart.dispose();
      }
      chartInstanceRef.current = null;
    };
  }, [option, onEvents, onChartReady]);

  // Handle loading state
  useEffect(() => {
    const chart = chartInstanceRef.current;
    if (!chart || chart.isDisposed()) return;

    if (loading) {
      chart.showLoading({
        text: "Calculating...",
        color: "#4f46e5",
        textColor: "#64748b",
        maskColor: "rgba(255, 255, 255, 0.8)",
      });
    } else {
      chart.hideLoading();
    }
  }, [loading]);

  const isEmpty = !option || (Array.isArray(option.series) && option.series.length === 0);

  return (
    <div className="relative w-full">
      {isEmpty && !loading ? (
        <div className={`flex flex-col items-center justify-center bg-slate-50 border border-dashed border-slate-200 rounded-xl p-6 text-center ${className}`}>
          <AlertCircle className="w-6 h-6 text-slate-400 mb-2" />
          <p className="text-xs font-semibold text-slate-700">No Chart Data</p>
          <p className="text-[11px] text-slate-500 mt-1 max-w-sm">{emptyMessage}</p>
        </div>
      ) : (
        <div ref={containerRef} className={className} style={style} />
      )}
    </div>
  );
}
