"use client";

import { useEffect, useState } from "react";
import {
  BookOpen,
  FileText,
  Search,
  RefreshCw,
  Database,
  Layers,
  Sparkles,
  CheckCircle2,
} from "lucide-react";
import { fetchRagStatus, fetchRagDocuments, testRagQuery, reindexRag } from "@/lib/api";
import type { RagStatus, RagDocument, RagTestResponse } from "@/types";

interface KnowledgeBaseSectionProps {
  showToast: (msg: string) => void;
}

const EXAMPLE_QUERIES = [
  "Photosynthesis light reaction and ATP synthesis",
  "Action potential propagation along a myelinated axon",
  "Nephron ultrafiltration in the glomerulus",
  "Secondary growth and vascular cambium activity",
];

export function KnowledgeBaseSection({ showToast }: KnowledgeBaseSectionProps) {
  const [status, setStatus] = useState<RagStatus | null>(null);
  const [documents, setDocuments] = useState<RagDocument[]>([]);
  const [loading, setLoading] = useState(true);

  // Inspector state
  const [query, setQuery] = useState(EXAMPLE_QUERIES[0]);
  const [inspecting, setInspecting] = useState(false);
  const [testResult, setTestResult] = useState<RagTestResponse | null>(null);

  // Reindexing state
  const [reindexing, setReindexing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void Promise.all([fetchRagStatus(), fetchRagDocuments()])
      .then(([s, docs]) => {
        if (!cancelled) {
          setStatus(s);
          setDocuments(docs);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          showToast("Could not load knowledge base status");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [showToast]);

  const handleTestQuery = async () => {
    if (!query.trim()) return;
    setInspecting(true);
    try {
      const res = await testRagQuery(query);
      setTestResult(res);
      showToast(`Retrieved ${res.chunks.length} chunks in ${res.latencyMs}ms`);
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : "RAG inspection failed");
    } finally {
      setInspecting(false);
    }
  };

  const handleReindex = async () => {
    setReindexing(true);
    try {
      const res = await reindexRag();
      showToast(`Re-indexing complete: ${res.chunkCount} chunks across ${res.pageCount} pages`);
      const [s, docs] = await Promise.all([fetchRagStatus(), fetchRagDocuments()]);
      setStatus(s);
      setDocuments(docs);
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : "Failed to re-index knowledge base");
    } finally {
      setReindexing(false);
    }
  };

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-[var(--color-ink-muted)]">
        <RefreshCw size={24} className="animate-spin text-emerald-400" />
        <p className="mt-3 text-xs">Loading Knowledge Base & RAG status...</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h3 className="text-lg font-semibold text-[var(--color-ink)] flex items-center gap-2">
          <BookOpen size={20} className="text-emerald-400" />
          Knowledge Base & RAG Inspector
        </h3>
        <p className="text-xs text-[var(--color-ink-muted)]">
          Manage Sri Lanka A/L Biology textbook indices, explore hybrid retrieval ranks, and audit source grounding.
        </p>
      </div>

      {/* RAG Status Overview Cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-3.5">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-ink-muted)] flex items-center gap-1">
            <Layers size={12} className="text-emerald-400" />
            Chunks Indexed
          </span>
          <p className="mt-1.5 font-mono text-xl font-bold text-[var(--color-ink)]">
            {status?.chunk_count?.toLocaleString() ?? 0}
          </p>
          <p className="text-[10px] text-[var(--color-ink-muted)] mt-0.5">
            {status?.page_count ?? 0} curriculum pages
          </p>
        </div>

        <div className="rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-3.5">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-ink-muted)] flex items-center gap-1">
            <Database size={12} className="text-cyan-400" />
            Retrieval Mode
          </span>
          <p className="mt-1.5 font-mono text-base font-bold capitalize text-cyan-300">
            {status?.retrieval_mode ?? "Hybrid"}
          </p>
          <p className="text-[10px] text-[var(--color-ink-muted)] mt-0.5">
            TF-IDF + BM25 + Vector
          </p>
        </div>

        <div className="rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-3.5">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-ink-muted)] flex items-center gap-1">
            <Sparkles size={12} className="text-violet-400" />
            Embedding Engine
          </span>
          <p className="mt-1.5 text-xs font-semibold text-[var(--color-ink)] truncate" title={status?.embedding_model}>
            {status?.embedding_model?.split("/").pop() || "all-MiniLM-L6-v2"}
          </p>
          <p className="text-[10px] text-[var(--color-ink-muted)] mt-0.5">
            Dense semantic vectors
          </p>
        </div>

        <div className="rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-3.5">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-ink-muted)] flex items-center gap-1">
            <CheckCircle2 size={12} className="text-amber-400" />
            Grounding Gate
          </span>
          <p className="mt-1.5 font-mono text-base font-bold text-amber-300">
            {((status?.grounding_threshold ?? 0.35) * 100).toFixed(0)}%
          </p>
          <p className="text-[10px] text-[var(--color-ink-muted)] mt-0.5">
            Confidence threshold
          </p>
        </div>
      </div>

      {/* Indexed Curriculum Documents Table */}
      <div className="rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-5">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-ink-muted)] flex items-center gap-1.5">
              <FileText size={14} className="text-emerald-400" />
              Indexed Courseware & Textbooks
            </h4>
            <p className="text-xs text-[var(--color-ink-muted)] mt-0.5">
              Core reference materials loaded into STRUD&apos;s local retrieval pipeline.
            </p>
          </div>
          <button
            type="button"
            onClick={handleReindex}
            disabled={reindexing}
            className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/[0.05] px-3 py-1.5 text-xs font-medium text-[var(--color-ink)] hover:bg-white/[0.09] transition-colors disabled:opacity-50"
          >
            <RefreshCw size={13} className={reindexing ? "animate-spin text-emerald-400" : "text-emerald-400"} />
            {reindexing ? "Re-indexing..." : "Re-index"}
          </button>
        </div>

        <div className="flex flex-col divide-y divide-[var(--color-hairline-soft)]">
          {documents.length === 0 ? (
            <p className="py-6 text-center text-xs text-[var(--color-ink-muted)]">
              No PDF documents detected in Science/Biology/books.
            </p>
          ) : (
            documents.map((doc) => (
              <div key={doc.name} className="flex items-center justify-between py-3">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-emerald-400/10 text-emerald-400 border border-emerald-400/20">
                    <FileText size={16} />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-xs font-medium text-[var(--color-ink)] truncate max-w-sm">
                        {doc.name}
                      </p>
                      {doc.isPrimary && (
                        <span className="rounded-full bg-emerald-400/15 border border-emerald-400/30 px-2 py-0.2 text-[9px] font-semibold text-emerald-300">
                          Primary Textbook
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 text-[11px] text-[var(--color-ink-muted)] mt-0.5">
                      <span>{formatBytes(doc.sizeBytes)}</span>
                      {doc.pageCount && <span>• {doc.pageCount} pages</span>}
                      {doc.chunkCount && <span>• {doc.chunkCount} chunks</span>}
                    </div>
                  </div>
                </div>

                <span
                  className={`rounded-full px-2.5 py-0.5 text-[10px] font-medium border ${
                    doc.status === "indexed"
                      ? "border-emerald-400/30 bg-emerald-400/15 text-emerald-300"
                      : "border-white/10 bg-white/[0.05] text-[var(--color-ink-muted)]"
                  }`}
                >
                  {doc.status === "indexed" ? "Indexed & Active" : "Ready"}
                </span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Interactive Live Query Inspector */}
      <div className="rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-5">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-ink-muted)] flex items-center gap-1.5">
          <Search size={14} className="text-cyan-400" />
          Interactive Retrieval & Score Inspector
        </h4>
        <p className="mt-1 text-xs text-[var(--color-ink-muted)]">
          Submit any biology concept to preview exact text chunks, ranking scores, and grounding confidence.
        </p>

        {/* Query Input */}
        <div className="mt-4 flex gap-2">
          <div className="relative flex-1">
            <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[var(--color-ink-muted)]" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleTestQuery()}
              placeholder="Enter biological concept or syllabus question..."
              className="w-full rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.03] pl-10 pr-3.5 py-2.5 text-xs text-[var(--color-ink)] placeholder:text-[var(--color-ink-muted)] focus:border-cyan-400/50 focus:outline-none"
            />
          </div>
          <button
            type="button"
            onClick={handleTestQuery}
            disabled={inspecting || !query.trim()}
            className="inline-flex items-center gap-2 rounded-xl bg-cyan-400/90 hover:bg-cyan-300 px-4 py-2.5 text-xs font-semibold text-cyan-950 transition-colors disabled:opacity-50"
          >
            {inspecting ? <RefreshCw size={14} className="animate-spin" /> : <Search size={14} />}
            {inspecting ? "Searching..." : "Inspect"}
          </button>
        </div>

        {/* Quick Example Query Pills */}
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          <span className="text-[10px] text-[var(--color-ink-muted)] py-1">Examples:</span>
          {EXAMPLE_QUERIES.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => {
                setQuery(q);
              }}
              className="rounded-lg border border-white/5 bg-white/[0.03] px-2 py-0.5 text-[10px] text-[var(--color-ink-muted)] hover:border-cyan-400/30 hover:text-cyan-300 transition-colors"
            >
              {q}
            </button>
          ))}
        </div>

        {/* Test Result Display */}
        {testResult && (
          <div className="mt-5 flex flex-col gap-4 border-t border-[var(--color-hairline-soft)] pt-4">
            {/* Grounding Header */}
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-white/[0.02] border border-white/5 p-3">
              <div className="flex items-center gap-2.5">
                <span
                  className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                    testResult.grounded
                      ? "bg-emerald-400/15 text-emerald-300 border border-emerald-400/30"
                      : "bg-amber-400/15 text-amber-300 border border-amber-400/30"
                  }`}
                >
                  {testResult.grounded ? "✓ Confirmed Grounded" : "⚠ Low Confidence"}
                </span>
                <span className="text-xs text-[var(--color-ink-muted)]">
                  Confidence:{" "}
                  <strong className="text-[var(--color-ink)] font-mono">
                    {(testResult.confidence * 100).toFixed(1)}%
                  </strong>
                </span>
                {testResult.bestPage && (
                  <span className="text-xs text-[var(--color-ink-muted)]">
                    • Best Page: <strong className="text-emerald-400 font-mono">p. {testResult.bestPage}</strong>
                  </span>
                )}
              </div>
              <span className="text-[11px] text-[var(--color-ink-muted)] font-mono">
                {testResult.latencyMs}ms ({testResult.resultsCount} chunks)
              </span>
            </div>

            {/* Chunks List */}
            <div className="flex flex-col gap-3">
              {testResult.chunks.map((chunk, idx) => (
                <div
                  key={chunk.index}
                  className="rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.02] p-4 transition-all hover:bg-white/[0.04]"
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="flex h-5 w-5 items-center justify-center rounded-md bg-white/10 font-mono text-[10px] font-bold text-emerald-400">
                        #{idx + 1}
                      </span>
                      <span className="font-mono text-xs font-semibold text-[var(--color-ink)]">
                        Page {chunk.page}
                      </span>
                    </div>

                    {/* Breakdown Scores */}
                    <div className="flex items-center gap-2 font-mono text-[10px]">
                      <span className="rounded bg-white/[0.05] px-1.5 py-0.5 text-[var(--color-ink-muted)]" title="TF-IDF Lexical Score">
                        TF-IDF: <strong className="text-cyan-300">{chunk.tfidfScore}</strong>
                      </span>
                      <span className="rounded bg-white/[0.05] px-1.5 py-0.5 text-[var(--color-ink-muted)]" title="BM25 Probabilistic Score">
                        BM25: <strong className="text-emerald-300">{chunk.bm25Score}</strong>
                      </span>
                      <span className="rounded bg-white/[0.05] px-1.5 py-0.5 text-[var(--color-ink-muted)]" title="Vector Semantic Cosine Similarity">
                        Vector: <strong className="text-violet-300">{chunk.semanticScore}</strong>
                      </span>
                      <span className="rounded bg-amber-400/10 px-1.5 py-0.5 text-amber-300" title="Fused Reciprocal Rank Score">
                        RRF: <strong>{chunk.rrfScore}</strong>
                      </span>
                    </div>
                  </div>

                  <p className="text-xs leading-relaxed text-[var(--color-ink-secondary)] italic">
                    &ldquo;{chunk.text}&rdquo;
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
