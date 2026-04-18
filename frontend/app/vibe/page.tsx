"use client";
import { useState, useRef } from "react";
import { vibeApi } from "@/lib/api";
import type { VibeModelResult } from "@/lib/api";
import { ModelSelector } from "@/components/ModelSelector";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { Zap, ThumbsUp, ThumbsDown, Download, Clock, Coins, Hash, ChevronDown, ChevronUp, Trash2 } from "lucide-react";

const MAX_MODELS = 3;

interface HistoryEntry {
  id: number;
  prompt: string;
  timestamp: string;
  results: VibeModelResult[];
  votes: Record<number, "up" | "down" | null>;
}

let _historySeq = 0;

function ResultCard({
  result,
  vote,
  onVote,
}: {
  result: VibeModelResult;
  vote: "up" | "down" | null;
  onVote: (v: "up" | "down") => void;
}) {
  const [expanded, setExpanded] = useState(true);

  const handleExport = () => {
    const content = [
      `Model: ${result.model_name}`,
      `Latency: ${result.latency_ms} ms`,
      `Tokens: ${result.input_tokens} in / ${result.output_tokens} out`,
      `Cost: $${result.cost_usd.toFixed(6)}`,
      `Vote: ${vote ?? "—"}`,
      "",
      result.text,
    ].join("\n");
    const blob = new Blob([content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `vibe-${result.model_name.replace(/[^a-z0-9]/gi, "_")}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className={`flex flex-col rounded-xl border ${result.error ? "border-red-200 bg-red-50" : "border-slate-200 bg-white"} overflow-hidden`}>
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-slate-100 bg-slate-50">
        <Zap size={13} className="text-cyan-600 shrink-0" />
        <span className="font-semibold text-sm text-slate-800 truncate flex-1">{result.model_name}</span>
        <button
          onClick={() => setExpanded(e => !e)}
          className="text-slate-400 hover:text-slate-600 transition-colors ml-1"
          aria-label={expanded ? "Collapse" : "Expand"}
        >
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
      </div>

      {/* Stats row */}
      <div className="flex items-center gap-4 px-4 py-1.5 bg-slate-50 border-b border-slate-100 text-[11px] text-slate-500">
        <span className="flex items-center gap-1"><Clock size={11} />{result.latency_ms} ms</span>
        <span className="flex items-center gap-1"><Hash size={11} />{result.input_tokens}+{result.output_tokens} tok</span>
        <span className="flex items-center gap-1"><Coins size={11} />${result.cost_usd.toFixed(5)}</span>
      </div>

      {/* Body */}
      {expanded && (
        <div className="px-4 py-3 flex-1">
          {result.error ? (
            <p className="text-sm text-red-600 font-medium">{result.error}</p>
          ) : (
            <p className="text-sm text-slate-700 whitespace-pre-wrap leading-relaxed">{result.text}</p>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-2 px-4 py-2 border-t border-slate-100 bg-slate-50">
        <button
          onClick={() => onVote("up")}
          className={`flex items-center gap-1 text-[12px] px-2.5 py-1 rounded-md border transition-colors font-medium ${
            vote === "up" ? "bg-green-600 text-white border-green-600" : "border-slate-200 text-slate-500 hover:border-green-400 hover:text-green-600"
          }`}
        >
          <ThumbsUp size={12} /> Good
        </button>
        <button
          onClick={() => onVote("down")}
          className={`flex items-center gap-1 text-[12px] px-2.5 py-1 rounded-md border transition-colors font-medium ${
            vote === "down" ? "bg-red-600 text-white border-red-600" : "border-slate-200 text-slate-500 hover:border-red-400 hover:text-red-600"
          }`}
        >
          <ThumbsDown size={12} /> Bad
        </button>
        <button
          onClick={handleExport}
          className="ml-auto flex items-center gap-1 text-[12px] px-2.5 py-1 rounded-md border border-slate-200 text-slate-500 hover:bg-slate-100 transition-colors"
        >
          <Download size={12} /> Export
        </button>
      </div>
    </div>
  );
}

export default function VibePage() {
  const [selectedModels, setSelectedModels] = useState<number[]>([]);
  const [prompt, setPrompt] = useState("");
  const [temperature, setTemperature] = useState(0.7);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentResults, setCurrentResults] = useState<VibeModelResult[] | null>(null);
  const [currentVotes, setCurrentVotes] = useState<Record<number, "up" | "down" | null>>({});
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [historyExpanded, setHistoryExpanded] = useState(false);
  const resultsRef = useRef<HTMLDivElement>(null);

  const canRun = selectedModels.length >= 1 && prompt.trim().length > 0 && !loading;

  const handleRun = async () => {
    if (!canRun) return;
    setLoading(true);
    setError(null);
    setCurrentResults(null);
    setCurrentVotes({});
    try {
      const res = await vibeApi.prompt(selectedModels, prompt.trim(), temperature);
      setCurrentResults(res.results);
      setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleSaveToHistory = () => {
    if (!currentResults) return;
    const entry: HistoryEntry = {
      id: ++_historySeq,
      prompt: prompt.trim(),
      timestamp: new Date().toLocaleTimeString(),
      results: currentResults,
      votes: { ...currentVotes },
    };
    setHistory(prev => [entry, ...prev].slice(0, 10));
  };

  const handleVote = (modelId: number, v: "up" | "down") => {
    setCurrentVotes(prev => ({ ...prev, [modelId]: prev[modelId] === v ? null : v }));
  };

  return (
    <div className="flex flex-col min-h-screen bg-slate-50">
      <PageHeader
        title="Vibe Check"
        description="Send a free-form prompt to up to 3 models simultaneously and compare responses side by side."
      />

      <div className="flex-1 p-4 sm:p-8 max-w-7xl mx-auto w-full space-y-6">

        {/* Config panel */}
        <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-5">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Model selector */}
            <div className="lg:col-span-1">
              <ModelSelector
                mode="multi"
                selected={selectedModels}
                onChange={(ids) => setSelectedModels((ids as number[]).slice(0, MAX_MODELS))}
                label={`Models (${selectedModels.length}/${MAX_MODELS})`}
                maxHeight="max-h-56"
              />
              {selectedModels.length >= MAX_MODELS && (
                <p className="text-[11px] text-amber-600 mt-1">Maximum {MAX_MODELS} models per check.</p>
              )}
            </div>

            {/* Prompt + options */}
            <div className="lg:col-span-2 flex flex-col gap-3">
              <div>
                <label className="text-xs font-medium text-slate-600 mb-1.5 block">Prompt</label>
                <textarea
                  value={prompt}
                  onChange={e => setPrompt(e.target.value)}
                  placeholder="Ask anything — compare how models reason, write, or respond…"
                  rows={6}
                  maxLength={4000}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:border-transparent"
                />
                <div className="text-[10px] text-slate-400 text-right mt-0.5">{prompt.length}/4000</div>
              </div>

              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2">
                  <label className="text-xs font-medium text-slate-600 whitespace-nowrap">Temperature: {temperature.toFixed(1)}</label>
                  <input
                    type="range" min={0} max={2} step={0.1}
                    value={temperature}
                    onChange={e => setTemperature(parseFloat(e.target.value))}
                    className="w-28 accent-cyan-600"
                  />
                </div>

                <button
                  onClick={handleRun}
                  disabled={!canRun}
                  className="ml-auto flex items-center gap-2 px-5 py-2 rounded-lg bg-cyan-700 text-white font-medium text-sm hover:bg-cyan-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  {loading ? <><Spinner size={14} /> Running…</> : <><Zap size={14} /> Run Vibe Check</>}
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">{error}</div>
        )}

        {/* Loading skeleton */}
        {loading && (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {selectedModels.map(id => (
              <div key={id} className="rounded-xl border border-slate-200 bg-white p-4 flex flex-col gap-3 animate-pulse">
                <div className="h-4 bg-slate-100 rounded w-2/3" />
                <div className="h-3 bg-slate-100 rounded w-1/3" />
                <div className="space-y-2 mt-2">
                  <div className="h-3 bg-slate-100 rounded" />
                  <div className="h-3 bg-slate-100 rounded" />
                  <div className="h-3 bg-slate-100 rounded w-4/5" />
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Results */}
        {currentResults && !loading && (
          <div ref={resultsRef} className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-700">Results</h2>
              <button
                onClick={handleSaveToHistory}
                className="text-[12px] px-3 py-1.5 rounded-md border border-slate-200 text-slate-500 hover:bg-slate-100 transition-colors"
              >
                Save to history
              </button>
            </div>
            <div className={`grid gap-4 ${currentResults.length === 1 ? "grid-cols-1 max-w-xl" : currentResults.length === 2 ? "grid-cols-1 md:grid-cols-2" : "grid-cols-1 md:grid-cols-2 xl:grid-cols-3"}`}>
              {currentResults.map(r => (
                <ResultCard
                  key={r.model_id}
                  result={r}
                  vote={currentVotes[r.model_id] ?? null}
                  onVote={(v) => handleVote(r.model_id, v)}
                />
              ))}
            </div>
          </div>
        )}

        {/* Session history */}
        {history.length > 0 && (
          <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
            <button
              onClick={() => setHistoryExpanded(e => !e)}
              className="w-full flex items-center justify-between px-5 py-3 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
            >
              <span>Session history ({history.length})</span>
              {historyExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
            {historyExpanded && (
              <div className="border-t border-slate-100 divide-y divide-slate-100">
                {history.map(entry => (
                  <div key={entry.id} className="px-5 py-3">
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <p className="text-xs text-slate-600 line-clamp-2 flex-1">{entry.prompt}</p>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className="text-[10px] text-slate-400">{entry.timestamp}</span>
                        <button
                          onClick={() => setHistory(prev => prev.filter(h => h.id !== entry.id))}
                          className="text-slate-300 hover:text-red-400 transition-colors"
                          aria-label="Remove"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {entry.results.map(r => (
                        <div key={r.model_id} className="flex items-center gap-1.5 text-[11px] bg-slate-50 border border-slate-200 rounded-md px-2 py-1">
                          <span className="font-medium text-slate-700 max-w-[120px] truncate">{r.model_name}</span>
                          <span className="text-slate-400">{r.latency_ms}ms</span>
                          {entry.votes[r.model_id] === "up" && <ThumbsUp size={10} className="text-green-500" />}
                          {entry.votes[r.model_id] === "down" && <ThumbsDown size={10} className="text-red-500" />}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Empty state */}
        {!loading && !currentResults && !error && (
          <div className="flex flex-col items-center justify-center py-16 text-center text-slate-400">
            <Zap size={32} className="mb-3 text-cyan-300" />
            <p className="text-sm font-medium text-slate-500">Select models, write a prompt, and hit Run.</p>
            <p className="text-xs mt-1">Responses appear side by side with latency and vote controls.</p>
          </div>
        )}
      </div>
    </div>
  );
}
