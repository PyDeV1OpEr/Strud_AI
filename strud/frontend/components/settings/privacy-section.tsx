"use client";

import { useEffect, useState } from "react";
import {
  Shield,
  HardDrive,
  Download,
  Trash2,
  RefreshCw,
  AlertTriangle,
  FileCheck,
  Sparkles,
  Database,
  Image as ImageIcon,
} from "lucide-react";
import {
  fetchStorageStats,
  cleanOrphanedUploads,
  exportFullData,
  clearAllUserChats,
} from "@/lib/api";
import { getUserId } from "@/lib/user-id";
import type { StorageStats } from "@/types";

interface PrivacySectionProps {
  showToast: (msg: string) => void;
  onChatsCleared?: () => void;
}

export function PrivacySection({ showToast, onChatsCleared }: PrivacySectionProps) {
  const [stats, setStats] = useState<StorageStats | null>(null);
  const [loading, setLoading] = useState(true);

  // Export state
  const [exporting, setExporting] = useState(false);

  // Clean uploads state
  const [cleaning, setCleaning] = useState(false);

  // Clear history state
  const [confirmClearOpen, setConfirmClearOpen] = useState(false);
  const [permanentClear, setPermanentClear] = useState(false);
  const [clearingHistory, setClearingHistory] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void fetchStorageStats(getUserId())
      .then((res) => {
        if (!cancelled) {
          setStats(res);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          showToast("Could not load storage stats");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [showToast]);

  const formatBytes = (bytes: number) => {
    if (!bytes || bytes <= 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  };

  const handleExportData = async () => {
    setExporting(true);
    try {
      const data = await exportFullData(getUserId());
      const jsonStr = JSON.stringify(data, null, 2);
      const blob = new Blob([jsonStr], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `strud_backup_${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      showToast("Data archive exported successfully");
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : "Failed to export data");
    } finally {
      setExporting(false);
    }
  };

  const handleCleanUploads = async () => {
    setCleaning(true);
    try {
      const res = await cleanOrphanedUploads();
      showToast(`Cleaned ${res.removed_count} orphaned files (${formatBytes(res.freed_bytes)} reclaimed)`);
      const refreshed = await fetchStorageStats(getUserId());
      setStats(refreshed);
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : "Failed to clean orphaned uploads");
    } finally {
      setCleaning(false);
    }
  };

  const handleClearHistory = async () => {
    setClearingHistory(true);
    try {
      const res = await clearAllUserChats(getUserId(), permanentClear);
      setConfirmClearOpen(false);
      showToast(
        permanentClear
          ? `Permanently deleted ${res.clearedCount} chats`
          : `Moved ${res.clearedCount} chats to Recently Deleted`
      );
      if (onChatsCleared) onChatsCleared();
      const refreshed = await fetchStorageStats(getUserId());
      setStats(refreshed);
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : "Failed to clear chat history");
    } finally {
      setClearingHistory(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-[var(--color-ink-muted)]">
        <RefreshCw size={24} className="animate-spin text-emerald-400" />
        <p className="mt-3 text-xs">Auditing local storage & database...</p>
      </div>
    );
  }

  const totalBytes =
    (stats?.database_size_bytes ?? 0) +
    (stats?.uploads_size_bytes ?? 0) +
    (stats?.checkpoints_size_bytes ?? 0);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h3 className="text-lg font-semibold text-[var(--color-ink)] flex items-center gap-2">
          <Shield size={20} className="text-emerald-400" />
          Privacy & Data Management
        </h3>
        <p className="text-xs text-[var(--color-ink-muted)]">
          STRUD runs 100% locally on your machine. Inspect disk footprint, export archives, or wipe chat history.
        </p>
      </div>

      {/* Storage Breakdown */}
      <div className="rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-5">
        <div className="flex items-center justify-between mb-4">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-ink-muted)] flex items-center gap-1.5">
            <HardDrive size={14} className="text-emerald-400" />
            Local Disk Footprint
          </h4>
          <span className="font-mono text-xs font-bold text-emerald-400">
            {formatBytes(totalBytes)} Total
          </span>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {/* SQLite DB */}
          <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3.5">
            <div className="flex items-center gap-2 text-[var(--color-ink-muted)] mb-1.5">
              <Database size={14} className="text-emerald-400" />
              <span className="text-xs font-medium text-[var(--color-ink)]">SQLite Database</span>
            </div>
            <p className="font-mono text-base font-bold text-[var(--color-ink)]">
              {formatBytes(stats?.database_size_bytes ?? 0)}
            </p>
            <div className="mt-2 text-[10px] text-[var(--color-ink-muted)] space-y-0.5">
              <p>• {stats?.messages_count ?? 0} messages in {stats?.active_chats_count ?? 0} chats</p>
              <p>• {stats?.memories_count ?? 0} memory items</p>
              <p>• {stats?.usage_records_count ?? 0} token usage logs</p>
            </div>
          </div>

          {/* Uploaded Files */}
          <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3.5">
            <div className="flex items-center gap-2 text-[var(--color-ink-muted)] mb-1.5">
              <ImageIcon size={14} className="text-cyan-400" />
              <span className="text-xs font-medium text-[var(--color-ink)]">Media & Uploads</span>
            </div>
            <p className="font-mono text-base font-bold text-[var(--color-ink)]">
              {formatBytes(stats?.uploads_size_bytes ?? 0)}
            </p>
            <div className="mt-2 text-[10px] text-[var(--color-ink-muted)] space-y-0.5">
              <p>• {stats?.uploads_count ?? 0} diagrams & photos</p>
              <p>• Stored in <code className="text-cyan-300">strud/uploads</code></p>
            </div>
          </div>

          {/* LangGraph Checkpoints */}
          <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3.5">
            <div className="flex items-center gap-2 text-[var(--color-ink-muted)] mb-1.5">
              <Sparkles size={14} className="text-violet-400" />
              <span className="text-xs font-medium text-[var(--color-ink)]">Graph Checkpoints</span>
            </div>
            <p className="font-mono text-base font-bold text-[var(--color-ink)]">
              {formatBytes(stats?.checkpoints_size_bytes ?? 0)}
            </p>
            <div className="mt-2 text-[10px] text-[var(--color-ink-muted)] space-y-0.5">
              <p>• State preservation</p>
              <p>• Instant session resumption</p>
            </div>
          </div>
        </div>
      </div>

      {/* Export & Cleanup Actions */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {/* Full Archive Export */}
        <div className="rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-5 flex flex-col justify-between">
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-ink-muted)] flex items-center gap-1.5">
              <Download size={14} className="text-emerald-400" />
              Export Complete Archive
            </h4>
            <p className="mt-2 text-xs text-[var(--color-ink-muted)] leading-relaxed">
              Download your entire STRUD profile, conversation histories, quiz scores, memories, and token usage logs as an unencrypted JSON document.
            </p>
          </div>
          <button
            type="button"
            onClick={handleExportData}
            disabled={exporting}
            className="mt-4 inline-flex items-center justify-center gap-2 rounded-xl border border-emerald-400/30 bg-emerald-400/10 hover:bg-emerald-400/20 px-4 py-2.5 text-xs font-semibold text-emerald-300 transition-colors disabled:opacity-50"
          >
            {exporting ? <RefreshCw size={14} className="animate-spin" /> : <Download size={14} />}
            {exporting ? "Generating Archive..." : "Export Full JSON Archive"}
          </button>
        </div>

        {/* Clean Orphaned Uploads */}
        <div className="rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-5 flex flex-col justify-between">
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-ink-muted)] flex items-center gap-1.5">
              <FileCheck size={14} className="text-cyan-400" />
              Clean Orphaned Attachments
            </h4>
            <p className="mt-2 text-xs text-[var(--color-ink-muted)] leading-relaxed">
              Scan uploaded images and diagrams that are no longer associated with any active message or quiz, and safely delete them from disk.
            </p>
          </div>
          <button
            type="button"
            onClick={handleCleanUploads}
            disabled={cleaning}
            className="mt-4 inline-flex items-center justify-center gap-2 rounded-xl border border-cyan-400/30 bg-cyan-400/10 hover:bg-cyan-400/20 px-4 py-2.5 text-xs font-semibold text-cyan-300 transition-colors disabled:opacity-50"
          >
            {cleaning ? <RefreshCw size={14} className="animate-spin" /> : <Trash2 size={14} />}
            {cleaning ? "Scanning Files..." : "Clean Orphaned Uploads"}
          </button>
        </div>
      </div>

      {/* Danger Zone: Clear History */}
      <div className="rounded-2xl border border-red-500/20 bg-red-500/[0.02] p-5">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-red-400 flex items-center gap-1.5">
          <AlertTriangle size={14} />
          Danger Zone: Reset Conversations
        </h4>
        <p className="mt-1.5 text-xs text-[var(--color-ink-secondary)]">
          Clear all current conversations. You can either move them to Recently Deleted (allowing recovery) or permanently purge them immediately.
        </p>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 pt-2">
          <div className="text-xs text-[var(--color-ink-muted)]">
            Active chats: <strong className="text-[var(--color-ink)] font-mono">{stats?.active_chats_count ?? 0}</strong>
          </div>
          <button
            type="button"
            onClick={() => setConfirmClearOpen(true)}
            className="inline-flex items-center gap-2 rounded-xl bg-red-500/80 hover:bg-red-500 px-4 py-2 text-xs font-semibold text-white transition-colors"
          >
            <Trash2 size={14} />
            Clear Chat History...
          </button>
        </div>
      </div>

      {/* Confirmation Modal */}
      {confirmClearOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="glass-strong w-full max-w-md rounded-2xl p-5 border border-red-500/30">
            <div className="flex items-center gap-3 text-red-400 mb-3">
              <AlertTriangle size={20} />
              <h4 className="text-base font-semibold text-[var(--color-ink)]">Clear Chat History</h4>
            </div>
            <p className="text-xs text-[var(--color-ink-secondary)] leading-relaxed">
              Are you sure you want to clear your conversation history? Choose how you want to handle your existing chats:
            </p>

            <div className="mt-4 flex flex-col gap-2.5">
              <label className="flex items-center gap-3 rounded-xl border border-white/5 bg-white/[0.02] p-3 cursor-pointer">
                <input
                  type="radio"
                  name="clearType"
                  checked={!permanentClear}
                  onChange={() => setPermanentClear(false)}
                  className="accent-emerald-400"
                />
                <div>
                  <p className="text-xs font-semibold text-[var(--color-ink)]">Move to Recently Deleted</p>
                  <p className="text-[11px] text-[var(--color-ink-muted)]">Chats can be restored from the Recycle Bin later</p>
                </div>
              </label>

              <label className="flex items-center gap-3 rounded-xl border border-red-500/20 bg-red-500/[0.04] p-3 cursor-pointer">
                <input
                  type="radio"
                  name="clearType"
                  checked={permanentClear}
                  onChange={() => setPermanentClear(true)}
                  className="accent-red-400"
                />
                <div>
                  <p className="text-xs font-semibold text-red-300">Permanently Delete Immediately</p>
                  <p className="text-[11px] text-[var(--color-ink-muted)]">Unrecoverable — completely purges all chats from disk</p>
                </div>
              </label>
            </div>

            <div className="mt-5 flex justify-end gap-2.5">
              <button
                type="button"
                onClick={() => setConfirmClearOpen(false)}
                className="rounded-xl px-3.5 py-2 text-xs font-medium text-[var(--color-ink-muted)] hover:text-[var(--color-ink)]"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleClearHistory}
                disabled={clearingHistory}
                className="rounded-xl bg-red-500/90 hover:bg-red-400 px-4 py-2 text-xs font-semibold text-white transition-colors"
              >
                {clearingHistory ? "Processing..." : "Confirm & Clear"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
