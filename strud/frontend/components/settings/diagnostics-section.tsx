"use client";

import { useEffect, useState } from "react";
import {
  Activity,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  HelpCircle,
  RefreshCw,
  Terminal,
  GitBranch,
  Wifi,
  Database,
  Server,
  Cpu,
  Eye,
  BookOpen,
} from "lucide-react";
import { fetchDiagnostics } from "@/lib/api";
import type { DiagnosticsData, DiagnosticCheck } from "@/types";

interface DiagnosticsSectionProps {
  showToast: (msg: string) => void;
}

const STATUS_CONFIG = {
  healthy: {
    icon: CheckCircle2,
    color: "text-emerald-400",
    bg: "bg-emerald-400/10 border-emerald-400/20",
    label: "Healthy",
  },
  degraded: {
    icon: AlertTriangle,
    color: "text-amber-400",
    bg: "bg-amber-400/10 border-amber-400/20",
    label: "Degraded",
  },
  unavailable: {
    icon: XCircle,
    color: "text-red-400",
    bg: "bg-red-400/10 border-red-400/20",
    label: "Unavailable",
  },
  unknown: {
    icon: HelpCircle,
    color: "text-white/30",
    bg: "bg-white/[0.05] border-white/10",
    label: "Unknown",
  },
} as const;

const CHECK_ICONS: Record<string, React.ElementType> = {
  "FastAPI Backend Server": Wifi,
  "SQLite Database": Database,
  "LM Studio Server": Server,
  "Biology Textbook Index (RAG)": BookOpen,
  "Visual Engine (Qwen3-VL)": Eye,
};

function DiagnosticCard({ check }: { check: DiagnosticCheck }) {
  const status = STATUS_CONFIG[check.status] ?? STATUS_CONFIG.unknown;
  const Icon = CHECK_ICONS[check.name] ?? Cpu;
  const StatusIcon = status.icon;

  return (
    <div
      className={`flex items-start gap-3.5 rounded-xl border p-4 transition-all ${status.bg}`}
    >
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/[0.05]">
        <Icon size={16} className={status.color} />
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs font-semibold text-[var(--color-ink)] truncate">
            {check.name}
          </p>
          <div className="flex items-center gap-1.5 shrink-0">
            {check.latencyMs !== null && (
              <span className="font-mono text-[10px] text-[var(--color-ink-muted)]">
                {check.latencyMs}ms
              </span>
            )}
            <div className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium border ${status.bg} ${status.color}`}>
              <StatusIcon size={11} />
              {status.label}
            </div>
          </div>
        </div>
        <p className="mt-1 text-[11px] text-[var(--color-ink-muted)] leading-relaxed">
          {check.details}
        </p>
      </div>
    </div>
  );
}

export function DiagnosticsSection({ showToast }: DiagnosticsSectionProps) {
  const [data, setData] = useState<DiagnosticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);

  const refreshDiagnostics = async () => {
    setRefreshing(true);
    try {
      const res = await fetchDiagnostics();
      setData(res);
      setLastChecked(new Date());
    } catch {
      showToast("Could not fetch system diagnostics — is the backend running?");
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    void fetchDiagnostics()
      .then((res) => {
        if (!cancelled) {
          setData(res);
          setLastChecked(new Date());
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          showToast("Could not fetch system diagnostics — is the backend running?");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [showToast]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-[var(--color-ink-muted)]">
        <RefreshCw size={24} className="animate-spin text-emerald-400" />
        <p className="mt-3 text-xs">Running system health checks...</p>
      </div>
    );
  }

  const overallConfig = STATUS_CONFIG[data?.status ?? "unknown"];
  const OverallIcon = overallConfig.icon;
  const healthyCount = data?.checks.filter((c) => c.status === "healthy").length ?? 0;
  const totalCount = data?.checks.length ?? 0;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h3 className="text-lg font-semibold text-[var(--color-ink)] flex items-center gap-2">
            <Activity size={20} className="text-emerald-400" />
            System Diagnostics
          </h3>
          <p className="text-xs text-[var(--color-ink-muted)]">
            Live system health checks for all STRUD AI services. No values are hardcoded or fabricated.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void refreshDiagnostics()}
          disabled={refreshing}
          className="flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/[0.05] px-3.5 py-2 text-xs font-medium text-[var(--color-ink)] hover:bg-white/[0.09] transition-colors shrink-0 disabled:opacity-50"
        >
          <RefreshCw size={14} className={`text-emerald-400 ${refreshing ? "animate-spin" : ""}`} />
          {refreshing ? "Refreshing..." : "Refresh Checks"}
        </button>
      </div>

      {/* Overall Health Banner */}
      <div
        className={`flex items-center justify-between rounded-2xl border p-5 ${overallConfig.bg}`}
      >
        <div className="flex items-center gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-white/[0.05]">
            <OverallIcon size={22} className={overallConfig.color} />
          </div>
          <div>
            <p className={`text-base font-bold ${overallConfig.color}`}>
              System {overallConfig.label}
            </p>
            <p className="text-xs text-[var(--color-ink-muted)] mt-0.5">
              {healthyCount} of {totalCount} checks passing
              {data?.recentFailures24h !== undefined && data.recentFailures24h > 0 && (
                <span className="ml-1.5 text-amber-400">
                  · {data.recentFailures24h} failure{data.recentFailures24h !== 1 ? "s" : ""} in last 24h
                </span>
              )}
            </p>
          </div>
        </div>

        <div className="text-right text-[10px] text-[var(--color-ink-muted)]">
          {lastChecked && (
            <p>Checked at {lastChecked.toLocaleTimeString("en-LK", { timeZone: "Asia/Colombo" })}</p>
          )}
        </div>
      </div>

      {/* Individual Check Cards */}
      <div className="flex flex-col gap-3">
        {(data?.checks ?? []).map((check) => (
          <DiagnosticCard key={check.name} check={check} />
        ))}
      </div>

      {/* Build Info Footer */}
      <div className="rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-5">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-ink-muted)] flex items-center gap-1.5">
          <Terminal size={14} className="text-cyan-400" />
          Build Information
        </h4>
        <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
          <div className="flex flex-col gap-0.5">
            <span className="text-[var(--color-ink-muted)]">App Version</span>
            <code className="font-mono font-semibold text-emerald-300">
              {data?.appVersion ?? "—"}
            </code>
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="text-[var(--color-ink-muted)] flex items-center gap-1">
              <GitBranch size={12} />
              Git Commit
            </span>
            <code className="font-mono font-semibold text-cyan-300">
              {data?.gitCommit ?? "—"}
            </code>
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="text-[var(--color-ink-muted)]">Backend Stack</span>
            <code className="font-mono font-semibold text-[var(--color-ink)]">
              FastAPI · LangGraph · SQLite
            </code>
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="text-[var(--color-ink-muted)]">Frontend Stack</span>
            <code className="font-mono font-semibold text-[var(--color-ink)]">
              Next.js 16 · React 19 · Tailwind v4
            </code>
          </div>
        </div>
      </div>
    </div>
  );
}
