"use client";

import { useEffect, useState } from "react";
import {
  Brain,
  Trash2,
  Plus,
  RefreshCw,
  AlertTriangle,
  Sparkles,
  ToggleLeft,
  ToggleRight,
  Info,
  Calendar,
} from "lucide-react";
import {
  fetchMemories,
  addMemory,
  deleteMemory,
  clearAllMemories,
  updateMemorySettings,
  fetchProfileFull,
} from "@/lib/api";
import { getUserId } from "@/lib/user-id";
import type { MemoryFact } from "@/types";

interface MemorySectionProps {
  showToast: (msg: string) => void;
}

export function MemorySection({ showToast }: MemorySectionProps) {
  const [facts, setFacts] = useState<MemoryFact[]>([]);
  const [memoryEnabled, setMemoryEnabled] = useState(true);
  const [loading, setLoading] = useState(true);
  const [newFact, setNewFact] = useState("");
  const [adding, setAdding] = useState(false);
  const [confirmClearOpen, setConfirmClearOpen] = useState(false);
  const [clearing, setClearing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const userId = getUserId();
    void Promise.all([fetchMemories(userId), fetchProfileFull(userId)])
      .then(([f, profile]) => {
        if (!cancelled) {
          setFacts(f);
          setMemoryEnabled(profile.memoryEnabled ?? true);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          showToast("Could not load memory facts");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [showToast]);

  const handleToggleMemory = async () => {
    const nextState = !memoryEnabled;
    setMemoryEnabled(nextState);
    try {
      await updateMemorySettings(getUserId(), nextState);
      showToast(
        nextState
          ? "Persistent memory enabled"
          : "Persistent memory paused (memories suppressed)"
      );
    } catch {
      setMemoryEnabled(!nextState);
      showToast("Failed to update memory setting");
    }
  };

  const handleAddFact = async () => {
    if (!newFact.trim()) return;
    setAdding(true);
    try {
      await addMemory(getUserId(), newFact.trim(), "explicit");
      setNewFact("");
      showToast("Fact saved to memory");
      const updated = await fetchMemories(getUserId());
      setFacts(updated);
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : "Failed to add memory fact");
    } finally {
      setAdding(false);
    }
  };

  const handleDeleteFact = async (id: number) => {
    try {
      await deleteMemory(getUserId(), id);
      setFacts((prev) => prev.filter((item) => item.id !== id));
      showToast("Memory fact removed");
    } catch {
      showToast("Could not remove memory fact");
    }
  };

  const handleClearAll = async () => {
    setClearing(true);
    try {
      const res = await clearAllMemories(getUserId());
      setFacts([]);
      setConfirmClearOpen(false);
      showToast(`Cleared ${res.clearedCount} memory facts`);
    } catch {
      showToast("Failed to clear memories");
    } finally {
      setClearing(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-[var(--color-ink-muted)]">
        <RefreshCw size={24} className="animate-spin text-emerald-400" />
        <p className="mt-3 text-xs">Loading context & user memories...</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h3 className="text-lg font-semibold text-[var(--color-ink)] flex items-center gap-2">
          <Brain size={20} className="text-emerald-400" />
          Memory & Context Manager
        </h3>
        <p className="text-xs text-[var(--color-ink-muted)]">
          Manage facts STRUD remembers about your learning pace, target exam scores, and difficult biology topics.
        </p>
      </div>

      {/* Master Toggle Card */}
      <div className="rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-5">
        <div className="flex items-center justify-between">
          <div className="flex items-start gap-3.5">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-400/10 border border-emerald-400/20 text-emerald-400">
              <Sparkles size={18} />
            </div>
            <div>
              <p className="text-sm font-semibold text-[var(--color-ink)]">
                Persistent Memory Extraction & Context Injection
              </p>
              <p className="mt-1 text-xs text-[var(--color-ink-muted)] leading-relaxed max-w-xl">
                When enabled, STRUD automatically extracts your study goals and prior questions to personalize future explanations. When disabled, existing facts are hidden from the model and new facts are not stored.
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={handleToggleMemory}
            className="flex items-center gap-1.5 transition-colors focus:outline-none"
            aria-label="Toggle memory"
          >
            {memoryEnabled ? (
              <ToggleRight size={36} className="text-emerald-400" />
            ) : (
              <ToggleLeft size={36} className="text-white/30" />
            )}
          </button>
        </div>

        {!memoryEnabled && (
          <div className="mt-3.5 flex items-center gap-2 rounded-xl bg-amber-400/10 border border-amber-400/20 px-3.5 py-2 text-xs text-amber-200">
            <Info size={14} className="text-amber-400 shrink-0" />
            <span>Memory is currently disabled. Active facts are suppressed from AI prompts.</span>
          </div>
        )}
      </div>

      {/* Add New Fact Input */}
      <div className="rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-5">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-ink-muted)] flex items-center gap-1.5">
          <Plus size={14} className="text-emerald-400" />
          Add Custom Memory Fact
        </h4>
        <div className="mt-3 flex gap-2">
          <input
            type="text"
            value={newFact}
            onChange={(e) => setNewFact(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAddFact()}
            placeholder="e.g. Target exam is 2026 A/L; prefers point-form explanations for botany."
            className="flex-1 rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.03] px-3.5 py-2 text-xs text-[var(--color-ink)] placeholder:text-[var(--color-ink-muted)] focus:border-emerald-400/50 focus:outline-none"
          />
          <button
            type="button"
            onClick={handleAddFact}
            disabled={adding || !newFact.trim()}
            className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-400/90 hover:bg-emerald-300 px-4 py-2 text-xs font-semibold text-emerald-950 transition-colors disabled:opacity-50"
          >
            {adding ? <RefreshCw size={14} className="animate-spin" /> : <Plus size={14} />}
            Save Fact
          </button>
        </div>
      </div>

      {/* Facts List */}
      <div className="rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-5">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-ink-muted)] flex items-center gap-1.5">
              <Brain size={14} className="text-cyan-400" />
              Stored Memory Items ({facts.length})
            </h4>
            <p className="text-xs text-[var(--color-ink-muted)] mt-0.5">
              Individual facts recalled by the tutoring graph during conversation context assembly.
            </p>
          </div>

          {facts.length > 0 && (
            <button
              type="button"
              onClick={() => setConfirmClearOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-1.5 text-xs font-medium text-red-300 hover:bg-red-500/20 transition-colors"
            >
              <Trash2 size={13} />
              Clear All
            </button>
          )}
        </div>

        {facts.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 text-center">
            <Brain size={32} className="text-white/20 mb-2" />
            <p className="text-xs font-medium text-[var(--color-ink)]">No memories recorded yet</p>
            <p className="mt-1 text-[11px] text-[var(--color-ink-muted)] max-w-sm">
              As you chat with STRUD, key preferences and study insights will be preserved here automatically.
            </p>
          </div>
        ) : (
          <div className="flex flex-col divide-y divide-[var(--color-hairline-soft)]">
            {facts.map((fact) => (
              <div key={fact.id} className="flex items-start justify-between py-3 gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-xs text-[var(--color-ink)] leading-relaxed">{fact.content}</p>
                  <div className="mt-1 flex items-center gap-2 text-[10px] text-[var(--color-ink-muted)]">
                    <span className="rounded bg-white/[0.05] px-1.5 py-0.5 font-mono capitalize">
                      {fact.source}
                    </span>
                    <span>•</span>
                    <span className="flex items-center gap-1">
                      <Calendar size={10} />
                      {new Date(fact.created_at).toLocaleDateString("en-GB", {
                        day: "numeric",
                        month: "short",
                        year: "numeric",
                      })}
                    </span>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => handleDeleteFact(fact.id)}
                  className="rounded-lg p-1.5 text-[var(--color-ink-muted)] hover:bg-red-500/10 hover:text-red-300 transition-colors"
                  aria-label="Delete memory fact"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Confirmation Modal for Clear All */}
      {confirmClearOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="glass-strong w-full max-w-md rounded-2xl p-5 border border-red-500/30">
            <div className="flex items-center gap-3 text-red-400 mb-3">
              <AlertTriangle size={20} />
              <h4 className="text-base font-semibold text-[var(--color-ink)]">Clear All Stored Memories?</h4>
            </div>
            <p className="text-xs text-[var(--color-ink-secondary)] leading-relaxed">
              This will permanently delete all {facts.length} memory facts stored for your profile. STRUD will forget your previous study goals and tailored preferences.
            </p>
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
                onClick={handleClearAll}
                disabled={clearing}
                className="rounded-xl bg-red-500/90 hover:bg-red-400 px-4 py-2 text-xs font-semibold text-white transition-colors"
              >
                {clearing ? "Clearing..." : "Yes, Delete Everything"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
