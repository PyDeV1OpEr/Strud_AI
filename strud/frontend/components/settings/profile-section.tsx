"use client";

import { useEffect, useState } from "react";
import { Check, Sparkles, BookOpen, Brain, Loader2 } from "lucide-react";
import { fetchProfileFull, updateProfileFull } from "@/lib/api";
import type { Profile } from "@/types";
import { Button } from "@/components/ui/primitives";

interface ProfileSectionProps {
  userId: string;
  onSaved?: (profile: Profile) => void;
  showToast: (msg: string) => void;
}

const AVATAR_COLORS = [
  { id: "emerald", label: "Emerald", bg: "bg-emerald-500", text: "text-emerald-950" },
  { id: "cyan", label: "Cyan", bg: "bg-cyan-500", text: "text-cyan-950" },
  { id: "violet", label: "Violet", bg: "bg-violet-500", text: "text-violet-950" },
  { id: "amber", label: "Amber", bg: "bg-amber-500", text: "text-amber-950" },
  { id: "rose", label: "Rose", bg: "bg-rose-500", text: "text-rose-950" },
];

export function ProfileSection({ userId, onSaved, showToast }: ProfileSectionProps) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [displayName, setDisplayName] = useState("Student");
  const [avatar, setAvatar] = useState("emerald");
  const [responseStyle, setResponseStyle] = useState<Profile["responseStyle"]>("balanced");
  const [explanationDetail, setExplanationDetail] = useState<Profile["explanationDetail"]>("standard");
  const [studyFocus, setStudyFocus] = useState<Profile["studyFocus"]>("exam");
  const [memoryEnabled, setMemoryEnabled] = useState(true);
  const [customInstructions, setCustomInstructions] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetchProfileFull(userId)
      .then((p) => {
        if (!cancelled) {
          setDisplayName(p.displayName || "Student");
          setAvatar(p.avatar || "emerald");
          setResponseStyle(p.responseStyle || "balanced");
          setExplanationDetail(p.explanationDetail || "standard");
          setStudyFocus(p.studyFocus || "exam");
          setMemoryEnabled(p.memoryEnabled ?? true);
          setCustomInstructions(p.customInstructions || "");
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [userId]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!displayName.trim() || saving) return;
    setSaving(true);
    try {
      const updated = await updateProfileFull(userId, {
        displayName: displayName.trim(),
        avatar,
        responseStyle,
        explanationDetail,
        studyFocus,
        memoryEnabled,
        customInstructions: customInstructions.trim(),
      });
      onSaved?.(updated);
      showToast("Profile and learning preferences updated");
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : "Failed to save profile");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="animate-spin text-emerald-400" size={24} />
      </div>
    );
  }

  const selectedAvatarObj = AVATAR_COLORS.find((c) => c.id === avatar) || AVATAR_COLORS[0];

  return (
    <form onSubmit={handleSave} className="flex flex-col gap-6">
      {/* Header Info */}
      <div className="flex flex-col gap-1">
        <h3 className="text-lg font-semibold text-[var(--color-ink)]">Profile & Personalization</h3>
        <p className="text-xs text-[var(--color-ink-muted)]">
          Customize how Strud AI addresses you and adapts its Biology teaching style to your study goals.
        </p>
      </div>

      {/* Identity Card */}
      <div className="rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-5">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-ink-muted)]">
          Local Student Identity
        </h4>
        <div className="mt-4 flex flex-col gap-4 sm:flex-row sm:items-center">
          <div
            className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl text-xl font-bold shadow-lg ${selectedAvatarObj.bg} ${selectedAvatarObj.text}`}
          >
            {displayName.trim().charAt(0).toUpperCase() || "S"}
          </div>

          <div className="flex-1 flex flex-col gap-1.5">
            <label htmlFor="display-name-input" className="text-xs font-medium text-[var(--color-ink-secondary)]">
              Display Name
            </label>
            <input
              id="display-name-input"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              maxLength={60}
              className="w-full rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.03] px-3.5 py-2 text-sm text-[var(--color-ink)] outline-none transition-colors focus:border-emerald-400/40 focus:bg-white/[0.06]"
              placeholder="e.g. Student or Your Name"
              required
            />
          </div>
        </div>

        {/* Avatar Color Picker */}
        <div className="mt-4 flex items-center gap-2">
          <span className="text-xs text-[var(--color-ink-muted)]">Avatar Color:</span>
          <div className="flex items-center gap-2">
            {AVATAR_COLORS.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => setAvatar(c.id)}
                aria-label={`Select ${c.label} color`}
                className={`relative flex h-6 w-6 items-center justify-center rounded-full transition-transform hover:scale-110 ${c.bg}`}
              >
                {avatar === c.id && <Check size={12} className={c.text} strokeWidth={3} />}
              </button>
            ))}
          </div>
        </div>

        <p className="mt-3 text-[11px] text-[var(--color-ink-muted)]">
          Anonymous browser identity: <span className="font-mono text-[10px] text-zinc-400">{userId}</span>
        </p>
      </div>

      {/* Teaching & Response Preferences Card */}
      <div className="rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-5 flex flex-col gap-5">
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-ink-muted)]">
            Tutor Teaching Preferences
          </h4>
          <p className="mt-0.5 text-xs text-[var(--color-ink-muted)]">
            These preferences are directly incorporated into the LangGraph prompt engine.
          </p>
        </div>

        {/* Response Style */}
        <div className="flex flex-col gap-2">
          <label className="text-xs font-medium text-[var(--color-ink)] flex items-center gap-1.5">
            <Sparkles size={14} className="text-emerald-400" />
            Response Style
          </label>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {[
              { id: "concise", label: "Concise", desc: "Direct & focused answers" },
              { id: "balanced", label: "Balanced", desc: "Default thorough clarity" },
              { id: "detailed", label: "Detailed", desc: "In-depth mechanism steps" },
              { id: "socratic", label: "Socratic", desc: "Guiding questions & clues" },
            ].map((opt) => (
              <button
                key={opt.id}
                type="button"
                onClick={() => setResponseStyle(opt.id as Profile["responseStyle"])}
                className={`flex flex-col rounded-xl border p-3 text-left transition-all ${
                  responseStyle === opt.id
                    ? "border-emerald-400/50 bg-emerald-400/10 text-[var(--color-ink)] shadow-[0_0_12px_rgba(52,211,153,0.15)]"
                    : "border-[var(--color-hairline-soft)] bg-white/[0.02] text-[var(--color-ink-secondary)] hover:bg-white/[0.04]"
                }`}
              >
                <span className="text-xs font-semibold">{opt.label}</span>
                <span className="mt-0.5 text-[11px] text-[var(--color-ink-muted)] leading-tight">{opt.desc}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Explanation Detail */}
        <div className="flex flex-col gap-2">
          <label className="text-xs font-medium text-[var(--color-ink)] flex items-center gap-1.5">
            <BookOpen size={14} className="text-cyan-400" />
            Explanation Depth
          </label>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            {[
              { id: "standard", label: "Standard A/L", desc: "Matches syllabus resource book depth" },
              { id: "deep", label: "Deep Mechanism", desc: "Biochemical & molecular focus" },
              { id: "quick", label: "Quick Summary", desc: "Key takeaway points only" },
            ].map((opt) => (
              <button
                key={opt.id}
                type="button"
                onClick={() => setExplanationDetail(opt.id as Profile["explanationDetail"])}
                className={`flex flex-col rounded-xl border p-3 text-left transition-all ${
                  explanationDetail === opt.id
                    ? "border-cyan-400/50 bg-cyan-400/10 text-[var(--color-ink)] shadow-[0_0_12px_rgba(56,189,248,0.15)]"
                    : "border-[var(--color-hairline-soft)] bg-white/[0.02] text-[var(--color-ink-secondary)] hover:bg-white/[0.04]"
                }`}
              >
                <span className="text-xs font-semibold">{opt.label}</span>
                <span className="mt-0.5 text-[11px] text-[var(--color-ink-muted)] leading-tight">{opt.desc}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Study Focus */}
        <div className="flex flex-col gap-2">
          <label className="text-xs font-medium text-[var(--color-ink)] flex items-center gap-1.5">
            <Brain size={14} className="text-violet-400" />
            Study Goal
          </label>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            {[
              { id: "exam", label: "Exam Preparation", desc: "Past-paper keywords & marking points" },
              { id: "conceptual", label: "Conceptual Mastery", desc: "Biological logic & understanding" },
              { id: "revision", label: "Rapid Revision", desc: "Flashcard summaries & checklists" },
            ].map((opt) => (
              <button
                key={opt.id}
                type="button"
                onClick={() => setStudyFocus(opt.id as Profile["studyFocus"])}
                className={`flex flex-col rounded-xl border p-3 text-left transition-all ${
                  studyFocus === opt.id
                    ? "border-violet-400/50 bg-violet-400/10 text-[var(--color-ink)] shadow-[0_0_12px_rgba(167,139,250,0.15)]"
                    : "border-[var(--color-hairline-soft)] bg-white/[0.02] text-[var(--color-ink-secondary)] hover:bg-white/[0.04]"
                }`}
              >
                <span className="text-xs font-semibold">{opt.label}</span>
                <span className="mt-0.5 text-[11px] text-[var(--color-ink-muted)] leading-tight">{opt.desc}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Custom Instructions */}
        <div className="flex flex-col gap-1.5">
          <label htmlFor="custom-instructions" className="text-xs font-medium text-[var(--color-ink-secondary)]">
            Custom Tutor Instructions (Optional)
          </label>
          <textarea
            id="custom-instructions"
            value={customInstructions}
            onChange={(e) => setCustomInstructions(e.target.value)}
            rows={3}
            maxLength={1000}
            placeholder="e.g. Always emphasize diagram labels and Sinhala/Tamil terminology where relevant, or remind me about unit conversions."
            className="w-full resize-none rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-3 text-xs text-[var(--color-ink)] outline-none transition-colors focus:border-emerald-400/40 focus:bg-white/[0.05]"
          />
          <div className="flex justify-end text-[10px] text-[var(--color-ink-muted)]">
            {customInstructions.length} / 1000 characters
          </div>
        </div>
      </div>

      {/* Save Button */}
      <div className="flex justify-end gap-3">
        <Button variant="primary" type="submit" disabled={saving}>
          {saving ? (
            <>
              <Loader2 className="animate-spin" size={15} />
              Saving…
            </>
          ) : (
            "Save Changes"
          )}
        </Button>
      </div>
    </form>
  );
}
