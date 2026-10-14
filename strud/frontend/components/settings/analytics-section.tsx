"use client";

import { useEffect, useMemo, useState } from "react";
import {
  BarChart3,
  Calendar,
  ChevronLeft,
  ChevronRight,
  Clock,
  Cpu,
  Download,
  Layers,
  Loader2,
  TrendingUp,
  Zap,
} from "lucide-react";
import {
  exportUsageRecords,
  fetchUsageCalendar,
  fetchUsageModels,
  fetchUsageRequests,
  fetchUsageSummary,
  fetchUsageTimeseries,
} from "@/lib/api";
import type {
  CalendarDay,
  ContributionCalendarData,
  ModelUsage,
  TimeseriesPoint,
  UsageRequestRecord,
  UsageSummary,
} from "@/types";
import { Button } from "@/components/ui/primitives";

interface AnalyticsSectionProps {
  userId: string;
  showToast: (msg: string) => void;
}

const RANGE_OPTIONS = [
  { id: "today", label: "Today" },
  { id: "last_7_days", label: "Last 7 Days" },
  { id: "last_30_days", label: "Last 30 Days" },
  { id: "this_month", label: "This Month" },
  { id: "last_month", label: "Last Month" },
  { id: "this_year", label: "This Year" },
];

const MONTH_NAMES = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

export function AnalyticsSection({ userId, showToast }: AnalyticsSectionProps) {
  const [range, setRange] = useState("last_30_days");
  const [selectedYear, setSelectedYear] = useState(2026);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);

  const [summary, setSummary] = useState<UsageSummary | null>(null);
  const [calendarData, setCalendarData] = useState<ContributionCalendarData | null>(null);
  const [timeseries, setTimeseries] = useState<TimeseriesPoint[]>([]);
  const [models, setModels] = useState<ModelUsage[]>([]);
  const [requests, setRequests] = useState<UsageRequestRecord[]>([]);

  // Selected day from calendar for detailed inspection
  const [selectedDay, setSelectedDay] = useState<CalendarDay | null>(null);
  const [hoveredDay, setHoveredDay] = useState<CalendarDay | null>(null);

  useEffect(() => {
    let cancelled = false;
    void Promise.all([
      fetchUsageSummary(userId, range),
      fetchUsageCalendar(userId, selectedYear),
      fetchUsageTimeseries(userId, range),
      fetchUsageModels(userId, range),
      fetchUsageRequests(userId, 20),
    ])
      .then(([sum, cal, ts, mod, req]) => {
        if (!cancelled) {
          setSummary(sum);
          setCalendarData(cal);
          setTimeseries(ts);
          setModels(mod);
          setRequests(req);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          showToast(err instanceof Error ? err.message : "Failed to load usage data");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [userId, range, selectedYear, showToast]);

  // Group calendar days into 12 individual month grids
  const monthGrids = useMemo(() => {
    if (!calendarData || !calendarData.days.length) return [];
    // Group days by month number 1-12
    const byMonth = new Map<number, CalendarDay[]>();
    for (const day of calendarData.days) {
      if (!byMonth.has(day.month)) byMonth.set(day.month, []);
      byMonth.get(day.month)!.push(day);
    }
    // Build grid for each month
    const grids: { month: number; name: string; rows: (CalendarDay | null)[][] }[] = [];
    for (let m = 1; m <= 12; m++) {
      const days = byMonth.get(m) ?? [];
      if (days.length === 0) continue;
      // firstWeekday: 0=Mon, 6=Sun (from backend)
      const firstWeekday = days[0].weekday;
      const cells: (CalendarDay | null)[] = [];
      // Leading nulls for days before the 1st of the month
      for (let i = 0; i < firstWeekday; i++) cells.push(null);
      for (const d of days) cells.push(d);
      // Pad to a multiple of 7
      while (cells.length % 7 !== 0) cells.push(null);
      // Split into rows of 7
      const rows: (CalendarDay | null)[][] = [];
      for (let r = 0; r < cells.length; r += 7) rows.push(cells.slice(r, r + 7));
      grids.push({ month: m, name: MONTH_NAMES[m - 1], rows });
    }
    return grids;
  }, [calendarData]);

  const handleExport = async () => {
    setExporting(true);
    try {
      const records = await exportUsageRecords(userId);
      const blob = new Blob([JSON.stringify(records, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `strud_usage_export_${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      showToast(`Exported ${records.length} usage records`);
    } catch {
      showToast("Failed to export usage data");
    } finally {
      setExporting(false);
    }
  };

  const getIntensityClass = (day: CalendarDay | null) => {
    if (!day) return "invisible";
    if (day.status === "unavailable") {
      return "bg-white/[0.02] border border-dashed border-white/[0.08] cursor-not-allowed";
    }
    switch (day.intensity) {
      case 1:
        return "bg-emerald-950/80 border border-emerald-800/40 hover:border-emerald-400/50";
      case 2:
        return "bg-emerald-800/80 border border-emerald-600/50 hover:border-emerald-400/70";
      case 3:
        return "bg-emerald-600/90 border border-emerald-500/60 hover:border-emerald-300";
      case 4:
        return "bg-emerald-400 text-emerald-950 border border-emerald-300 shadow-[0_0_8px_rgba(52,211,153,0.5)]";
      default:
        return "bg-white/[0.035] border border-white/[0.06] hover:border-white/20";
    }
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Header & Date Range Filter */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 className="text-lg font-semibold text-[var(--color-ink)] flex items-center gap-2">
            <BarChart3 className="text-emerald-400" size={20} />
            AI Usage & Analytics
          </h3>
          <p className="text-xs text-[var(--color-ink-muted)]">
            Verified model tokens, request latencies, and daily activity in Asia/Colombo time.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Range Dropdown */}
          <select
            value={range}
            onChange={(e) => {
              setLoading(true);
              setRange(e.target.value);
            }}
            className="rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.03] px-3 py-1.5 text-xs text-[var(--color-ink)] outline-none focus:border-emerald-400/40"
          >
            {RANGE_OPTIONS.map((opt) => (
              <option key={opt.id} value={opt.id} className="bg-zinc-900 text-white">
                {opt.label}
              </option>
            ))}
          </select>

          <Button
            variant="ghost"
            onClick={handleExport}
            disabled={exporting}
            className="text-xs h-8 px-2.5"
            title="Download full token records as JSON"
          >
            <Download size={13} />
            Export
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="animate-spin text-emerald-400" size={26} />
        </div>
      ) : (
        <>
          {/* Summary Metric Cards */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-4 flex flex-col gap-1">
              <span className="text-[11px] font-medium text-[var(--color-ink-muted)] flex items-center gap-1">
                <Clock size={12} className="text-emerald-400" />
                Tokens Today
              </span>
              <span className="text-xl font-bold text-[var(--color-ink)]">
                {summary?.tokens_today.toLocaleString() ?? 0}
              </span>
              <span className="text-[10px] text-[var(--color-ink-muted)]">
                This week: {summary?.tokens_this_week.toLocaleString() ?? 0}
              </span>
            </div>

            <div className="rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-4 flex flex-col gap-1">
              <span className="text-[11px] font-medium text-[var(--color-ink-muted)] flex items-center gap-1">
                <Calendar size={12} className="text-cyan-400" />
                Tokens This Month
              </span>
              <span className="text-xl font-bold text-[var(--color-ink)]">
                {summary?.tokens_this_month.toLocaleString() ?? 0}
              </span>
              <span className="text-[10px] text-[var(--color-ink-muted)]">
                Last month: {summary?.tokens_last_month.toLocaleString() ?? 0}
              </span>
            </div>

            <div className="rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-4 flex flex-col gap-1">
              <span className="text-[11px] font-medium text-[var(--color-ink-muted)] flex items-center gap-1">
                <Layers size={12} className="text-violet-400" />
                Filter Period Total
              </span>
              <span className="text-xl font-bold text-[var(--color-ink)]">
                {summary?.total_tokens.toLocaleString() ?? 0}
              </span>
              <span className="text-[10px] text-[var(--color-ink-muted)]">
                In: {summary?.input_tokens.toLocaleString() ?? 0} · Out: {summary?.output_tokens.toLocaleString() ?? 0}
              </span>
            </div>

            <div className="rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-4 flex flex-col gap-1">
              <span className="text-[11px] font-medium text-[var(--color-ink-muted)] flex items-center gap-1">
                <Zap size={12} className="text-amber-400" />
                Requests & Latency
              </span>
              <span className="text-xl font-bold text-[var(--color-ink)]">
                {summary?.successful_requests ?? 0} reqs
              </span>
              <span className="text-[10px] text-[var(--color-ink-muted)]">
                {summary?.avg_latency_ms ? `${summary.avg_latency_ms}ms avg` : "No latency data"} · {summary?.avg_tokens_per_request ?? 0} tok/req
              </span>
            </div>
          </div>

          {/* Contribution Calendar Card */}
          <div className="rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-5 flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-ink-muted)] flex items-center gap-1.5">
                  <Calendar size={14} className="text-emerald-400" />
                  Annual Token Contribution Calendar
                </h4>
                <p className="text-[11px] text-[var(--color-ink-muted)]">
                  {calendarData?.total_tokens.toLocaleString()} tokens across {calendarData?.total_requests} requests in {selectedYear} ({calendarData?.timezone}).
                </p>
              </div>

              {/* Year Navigation */}
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => {
                    setLoading(true);
                    setSelectedYear((y) => y - 1);
                  }}
                  className="rounded-lg border border-[var(--color-hairline-soft)] bg-white/[0.03] p-1 text-[var(--color-ink-muted)] hover:text-[var(--color-ink)]"
                  aria-label="Previous year"
                >
                  <ChevronLeft size={14} />
                </button>
                <span className="font-mono text-xs font-semibold px-1 text-[var(--color-ink)]">
                  {selectedYear}
                </span>
                <button
                  type="button"
                  onClick={() => {
                    setLoading(true);
                    setSelectedYear((y) => y + 1);
                  }}
                  className="rounded-lg border border-[var(--color-hairline-soft)] bg-white/[0.03] p-1 text-[var(--color-ink-muted)] hover:text-[var(--color-ink)]"
                  aria-label="Next year"
                >
                  <ChevronRight size={14} />
                </button>
              </div>
            </div>

            {/* 12-Month Grid Calendar */}
            <div className="flex flex-col gap-4">
              {monthGrids.length > 0 ? (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                  {monthGrids.map(({ month, name, rows }) => {
                    const activeDays = rows
                      .flat()
                      .filter((d) => d !== null && d.status !== "unavailable" && d.intensity > 0)
                      .length;
                    return (
                      <div
                        key={month}
                        className="rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.025] p-3 flex flex-col gap-2"
                      >
                        {/* Month header */}
                        <div className="flex items-center justify-between">
                          <span className="text-[11px] font-semibold text-[var(--color-ink)]">{name}</span>
                          {activeDays > 0 && (
                            <span className="text-[9px] text-emerald-400">{activeDays}d active</span>
                          )}
                        </div>

                        {/* Weekday labels: M T W T F S S */}
                        <div className="grid grid-cols-7 gap-[2px]">
                          {["M", "T", "W", "T", "F", "S", "S"].map((label, i) => (
                            <div
                              key={i}
                              className="text-center text-[8px] font-mono text-[var(--color-ink-muted)] leading-none"
                            >
                              {label}
                            </div>
                          ))}
                        </div>

                        {/* Day cells */}
                        {rows.map((week, ri) => (
                          <div key={ri} className="grid grid-cols-7 gap-[2px]">
                            {week.map((day, ci) => {
                              const isSelected = selectedDay?.date === day?.date;
                              return (
                                <button
                                  key={`${ri}-${ci}`}
                                  type="button"
                                  tabIndex={day ? 0 : -1}
                                  disabled={!day}
                                  aria-label={
                                    day
                                      ? `${day.date}: ${day.total_tokens.toLocaleString()} tokens`
                                      : "empty"
                                  }
                                  onClick={() => day && setSelectedDay(day)}
                                  onMouseEnter={() => day && setHoveredDay(day)}
                                  onMouseLeave={() => setHoveredDay(null)}
                                  className={`aspect-square rounded-[2px] transition-all outline-none focus:ring-1 focus:ring-emerald-400 ${
                                    !day ? "invisible" : getIntensityClass(day)
                                  } ${
                                    isSelected
                                      ? "ring-2 ring-emerald-300 ring-offset-[1px] ring-offset-black scale-125 z-10"
                                      : ""
                                  }`}
                                />
                              );
                            })}
                          </div>
                        ))}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="flex h-32 items-center justify-center text-xs text-[var(--color-ink-muted)]">
                  No calendar data available for {selectedYear}.
                </div>
              )}

              {/* Day Inspector Panel */}
              <div className="flex flex-col gap-2 rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.02] p-3 text-xs">
                {hoveredDay || selectedDay ? (
                  (() => {
                    const target = hoveredDay || selectedDay!;
                    return (
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-emerald-400">{target.date}</span>
                          <span className="text-[11px] text-[var(--color-ink-muted)]">
                            {target.status === "unavailable"
                              ? "(Prior to tracking inception)"
                              : `${target.request_count} request${target.request_count === 1 ? "" : "s"}`}
                          </span>
                        </div>
                        <div className="flex items-center gap-4 text-[11px]">
                          <span>
                            Input:{" "}
                            <strong className="text-[var(--color-ink)]">
                              {target.input_tokens.toLocaleString()}
                            </strong>
                          </span>
                          <span>
                            Output:{" "}
                            <strong className="text-[var(--color-ink)]">
                              {target.output_tokens.toLocaleString()}
                            </strong>
                          </span>
                          <span>
                            Total:{" "}
                            <strong className="text-emerald-300">
                              {target.total_tokens.toLocaleString()} tokens
                            </strong>
                          </span>
                        </div>
                      </div>
                    );
                  })()
                ) : (
                  <div className="flex items-center justify-between text-[11px] text-[var(--color-ink-muted)]">
                    <span>Click any day to inspect detailed tokens and request counts.</span>
                    {calendarData?.first_tracked_date && (
                      <span className="text-[10px]">Tracking since {calendarData.first_tracked_date}</span>
                    )}
                  </div>
                )}
              </div>

              {/* Legend */}
              <div className="flex flex-wrap items-center justify-between gap-3 text-[11px] text-[var(--color-ink-muted)] pt-1">
                <div className="flex items-center gap-2">
                  <span className="h-2.5 w-2.5 rounded-[2px] border border-dashed border-white/20 bg-white/[0.02]" />
                  <span>Unavailable</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span>Less</span>
                  <span className="h-2.5 w-2.5 rounded-[2px] bg-white/[0.04] border border-white/[0.06]" />
                  <span className="h-2.5 w-2.5 rounded-[2px] bg-emerald-950/80 border border-emerald-800/40" />
                  <span className="h-2.5 w-2.5 rounded-[2px] bg-emerald-800/80 border border-emerald-600/50" />
                  <span className="h-2.5 w-2.5 rounded-[2px] bg-emerald-600/90 border border-emerald-500/60" />
                  <span className="h-2.5 w-2.5 rounded-[2px] bg-emerald-400" />
                  <span>More</span>
                </div>
              </div>
            </div>

          </div>

          {/* Usage Chart Over Time & Models */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            {/* SVG Activity Chart */}
            <div className="rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-5 lg:col-span-2 flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-ink-muted)] flex items-center gap-1.5">
                    <TrendingUp size={14} className="text-cyan-400" />
                    Daily Token Flow
                  </h4>
                  <p className="text-[11px] text-[var(--color-ink-muted)]">
                    Input tokens (prompt/context) vs output tokens (generated biology answer).
                  </p>
                </div>
                <div className="flex items-center gap-3 text-[10px]">
                  <span className="flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-cyan-400" />
                    Input Tokens
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-emerald-400" />
                    Output Tokens
                  </span>
                </div>
              </div>

              {timeseries.length === 0 ? (
                <div className="flex h-36 items-center justify-center text-xs text-[var(--color-ink-muted)]">
                  No request activity recorded in this period.
                </div>
              ) : (
                <div className="flex h-44 items-end gap-1.5 pt-4 pb-1">
                  {timeseries.map((pt, idx) => {
                    const maxVal = Math.max(...timeseries.map((t) => t.total_tokens), 100);
                    const inHeight = Math.max(3, (pt.input_tokens / maxVal) * 140);
                    const outHeight = Math.max(3, (pt.output_tokens / maxVal) * 140);
                    return (
                      <div
                        key={pt.date + idx}
                        className="group relative flex-1 flex flex-col justify-end items-center h-full"
                      >
                        {/* Tooltip on hover */}
                        <div className="absolute -top-12 z-20 hidden rounded-lg border border-[var(--color-hairline-soft)] bg-zinc-900/95 px-2 py-1 text-[10px] text-white shadow-xl group-hover:block whitespace-nowrap">
                          <p className="font-semibold text-emerald-400">{pt.date}</p>
                          <p>In: {pt.input_tokens.toLocaleString()} · Out: {pt.output_tokens.toLocaleString()}</p>
                        </div>
                        {/* Stacked/Parallel bars */}
                        <div className="flex w-full items-end justify-center gap-[2px]">
                          <div
                            style={{ height: `${inHeight}px` }}
                            className="w-full max-w-[8px] rounded-t-[2px] bg-cyan-400/80 transition-all group-hover:bg-cyan-300"
                          />
                          <div
                            style={{ height: `${outHeight}px` }}
                            className="w-full max-w-[8px] rounded-t-[2px] bg-emerald-400/90 transition-all group-hover:bg-emerald-300"
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Model Breakdown */}
            <div className="rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-5 flex flex-col gap-4">
              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-ink-muted)] flex items-center gap-1.5">
                  <Cpu size={14} className="text-violet-400" />
                  Model Distribution
                </h4>
                <p className="text-[11px] text-[var(--color-ink-muted)]">
                  Tokens by configured model architecture.
                </p>
              </div>

              {models.length === 0 ? (
                <div className="flex h-36 items-center justify-center text-xs text-[var(--color-ink-muted)]">
                  No model usage recorded.
                </div>
              ) : (
                <div className="flex flex-col gap-3">
                  {models.map((m) => (
                    <div
                      key={m.model_id}
                      className="rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.02] p-3 flex flex-col gap-1"
                    >
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-semibold text-[var(--color-ink)] truncate max-w-[150px]">
                          {m.model_id.split("/").pop()}
                        </span>
                        <span className="text-emerald-300 font-mono text-[11px]">
                          {m.total_tokens.toLocaleString()} tok
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-[10px] text-[var(--color-ink-muted)]">
                        <span>{m.request_count} requests</span>
                        <span>
                          {m.input_tokens.toLocaleString()} in / {m.output_tokens.toLocaleString()} out
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Recent Requests Table */}
          <div className="rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-5 flex flex-col gap-3">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-ink-muted)]">
              Recent Model Invocations
            </h4>
            {requests.length === 0 ? (
              <p className="text-xs text-[var(--color-ink-muted)] py-4 text-center">
                No recent model calls recorded yet. Send a message to start tracking.
              </p>
            ) : (
              <div className="overflow-x-auto scroll-slim">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-[var(--color-hairline-soft)] text-[11px] text-[var(--color-ink-muted)]">
                      <th className="py-2 font-medium">Time (Local)</th>
                      <th className="py-2 font-medium">Model</th>
                      <th className="py-2 font-medium">Input</th>
                      <th className="py-2 font-medium">Output</th>
                      <th className="py-2 font-medium">Total</th>
                      <th className="py-2 font-medium">Method</th>
                      <th className="py-2 font-medium">Status</th>
                      <th className="py-2 font-medium">Latency</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--color-hairline-soft)] text-[11px]">
                    {requests.map((r) => (
                      <tr key={r.id} className="hover:bg-white/[0.02]">
                        <td className="py-2 text-[var(--color-ink-secondary)] whitespace-nowrap">
                          {r.created_at_local || r.created_at.slice(0, 19).replace("T", " ")}
                        </td>
                        <td className="py-2 text-[var(--color-ink)] font-mono text-[10px] truncate max-w-[120px]">
                          {r.model_id.split("/").pop()}
                        </td>
                        <td className="py-2 text-[var(--color-ink-muted)]">{r.input_tokens.toLocaleString()}</td>
                        <td className="py-2 text-[var(--color-ink-muted)]">{r.output_tokens.toLocaleString()}</td>
                        <td className="py-2 font-medium text-emerald-300">{r.total_tokens.toLocaleString()}</td>
                        <td className="py-2 text-[var(--color-ink-muted)] capitalize">
                          {r.token_counting_method === "provider" ? (
                            <span className="text-emerald-400">provider</span>
                          ) : (
                            "tiktoken"
                          )}
                        </td>
                        <td className="py-2">
                          <span
                            className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                              r.request_status === "success"
                                ? "bg-emerald-400/10 text-emerald-300"
                                : "bg-red-500/15 text-red-400"
                            }`}
                          >
                            {r.request_status}
                          </span>
                        </td>
                        <td className="py-2 text-[var(--color-ink-muted)] font-mono">
                          {r.duration_ms ? `${r.duration_ms}ms` : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
