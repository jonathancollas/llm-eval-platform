"use client";
import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  Search, Rocket, BarChart3, Cpu, Library, Trophy,
  Dna, Gavel, Radio, Shield, List, Bot, AlertCircle,
  FlaskConical, Layers, LineChart, TestTubes,
} from "lucide-react";

interface Command {
  id: string;
  group: string;
  label: string;
  desc?: string;
  icon: React.ElementType;
  action: () => void;
  keywords?: string[];
}

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);

  const close = useCallback(() => { setOpen(false); setQuery(""); }, []);

  const go = useCallback((path: string) => { router.push(path); close(); }, [router, close]);

  const commands: Command[] = [
    // Évaluer
    { id: "eval-new",         group: "Évaluer", label: "New Evaluation",                desc: "Open Evaluation Studio",            icon: Rocket,      action: () => go("/evaluate"),                       keywords: ["create", "start", "run", "nouveau"] },
    { id: "eval-capability",  group: "Évaluer", label: "New Capability Evaluation",     desc: "Academic · reasoning · coding",     icon: Rocket,      action: () => go("/evaluate?type=capability"),        keywords: ["capability", "academic", "mmlu", "coding"] },
    { id: "eval-safety",      group: "Évaluer", label: "New Safety Evaluation",         desc: "INESIA doctrine · CBRN · alignment",icon: Rocket,      action: () => go("/evaluate?type=safety"),            keywords: ["safety", "inesia", "cbrn", "alignment"] },
    { id: "eval-behavioral",  group: "Évaluer", label: "New Behavioral Evaluation",     desc: "Genomia fingerprint · propensity",  icon: Rocket,      action: () => go("/evaluate?type=behavioral"),        keywords: ["behavioral", "genomia", "propensity"] },
    { id: "eval-comparative", group: "Évaluer", label: "New Comparative Evaluation",    desc: "Head-to-head multi-model",          icon: Rocket,      action: () => go("/evaluate?type=comparative"),       keywords: ["comparative", "compare", "head-to-head"] },
    { id: "eval-compliance",  group: "Évaluer", label: "New Compliance Evaluation",     desc: "EU AI Act · NIST · ISO 42001",      icon: Rocket,      action: () => go("/evaluate?type=compliance"),        keywords: ["compliance", "eu", "nist", "iso", "regulation"] },
    { id: "nav-campaigns",    group: "Évaluer", label: "Run History",                   icon: List,        action: () => go("/campaigns"),               keywords: ["campaigns", "history", "runs"] },
    // Analyser
    { id: "nav-dashboard",    group: "Analyser", label: "Dashboard",                   icon: BarChart3,   action: () => go("/dashboard"),               keywords: ["results", "analytics", "heatmap"] },
    { id: "nav-leaderboard",  group: "Analyser", label: "Leaderboard",                 icon: Trophy,      action: () => go("/leaderboard"),             keywords: ["ranking", "score", "top"] },
    { id: "nav-genome",       group: "Analyser", label: "Genomia",                     icon: Dna,         action: () => go("/genome"),                  keywords: ["genome", "behavioral", "profile", "fingerprint"] },
    { id: "nav-judge",        group: "Analyser", label: "LLM Judge",                   icon: Gavel,       action: () => go("/judge"),                   keywords: ["judge", "llm", "calibrate", "bias"] },
    { id: "nav-agents",       group: "Analyser", label: "Agents",                      icon: Bot,         action: () => go("/agents"),                  keywords: ["agent", "agentic", "bot"] },
    { id: "nav-capability",   group: "Analyser", label: "Capability Intel",            desc: "7-domain taxonomy · model profiles", icon: Search,     action: () => go("/capability"),              keywords: ["capability", "taxonomy", "profile", "intel"] },
    { id: "nav-forecasting",  group: "Analyser", label: "Forecasting",                 desc: "Scaling laws · long-horizon eval",  icon: LineChart,   action: () => go("/forecasting"),             keywords: ["forecast", "scaling", "trend", "future"] },
    // Opérer
    { id: "nav-telemetry",    group: "Opérer",  label: "Monitoring",                   icon: Radio,       action: () => go("/telemetry"),               keywords: ["telemetry", "monitoring", "prod", "deployment"] },
    { id: "nav-incidents",    group: "Opérer",  label: "Incidents",                    icon: AlertCircle, action: () => go("/incidents"),               keywords: ["incident", "alert", "six"] },
    { id: "nav-policy",       group: "Opérer",  label: "Compliance",                   icon: Shield,      action: () => go("/policy"),                  keywords: ["compliance", "policy", "regulation"] },
    { id: "nav-scenarios",    group: "Opérer",  label: "Scenarios",                    desc: "Scenario runtime · agentic tasks",  icon: Layers,      action: () => go("/scenarios"),               keywords: ["scenario", "task", "agentic", "runtime"] },
    // Bibliothèque
    { id: "nav-models",       group: "Bibliothèque", label: "Models",                  icon: Cpu,         action: () => go("/models"),                  keywords: ["model", "register", "provider"] },
    { id: "nav-benchmarks",   group: "Bibliothèque", label: "Benchmarks",              icon: Library,     action: () => go("/benchmarks"),              keywords: ["benchmark", "dataset", "metric"] },
    { id: "nav-evidence",     group: "Bibliothèque", label: "Evidence (RCT)",          icon: TestTubes,   action: () => go("/evidence"),                keywords: ["evidence", "rct", "experiment"] },
    { id: "nav-methodology",  group: "Bibliothèque", label: "Methodology",             icon: FlaskConical,action: () => go("/methodology"),             keywords: ["methodology", "science", "paper"] },
  ];

  const filtered = query.trim() === ""
    ? commands
    : commands.filter(c => {
        const q = query.toLowerCase();
        return c.label.toLowerCase().includes(q)
          || c.desc?.toLowerCase().includes(q)
          || c.keywords?.some(k => k.includes(q));
      });

  // Reset selection when query changes
  useEffect(() => setSelected(0), [query]);

  // Global keyboard shortcut Cmd+K / Ctrl+K
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen(o => !o);
        setQuery("");
      }
      if (e.key === "Escape") close();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [close]);

  // Focus input when opened
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50);
  }, [open]);

  const execute = useCallback((cmd: Command) => { cmd.action(); }, []);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown")  { e.preventDefault(); setSelected(s => Math.min(s + 1, filtered.length - 1)); }
    else if (e.key === "ArrowUp")   { e.preventDefault(); setSelected(s => Math.max(s - 1, 0)); }
    else if (e.key === "Enter" && filtered[selected]) execute(filtered[selected]);
  };

  // Group headers
  const visibleGroups = Array.from(new Set(filtered.map(c => c.group)));

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[14vh]"
      onClick={close}
    >
      <div className="absolute inset-0 bg-black/40" />
      <div
        className="relative w-full max-w-lg mx-4 bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        {/* Search input */}
        <div className="flex items-center gap-3 px-4 py-3.5 border-b border-slate-100">
          <Search size={16} className="text-slate-400 shrink-0" />
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search commands or navigate…"
            className="flex-1 text-sm outline-none text-slate-900 placeholder-slate-400"
          />
          <kbd className="text-[10px] text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200 hidden sm:inline">ESC</kbd>
        </div>

        {/* Results */}
        <div className="max-h-80 overflow-y-auto py-1">
          {filtered.length === 0 ? (
            <div className="px-4 py-6 text-center text-sm text-slate-400">No commands found</div>
          ) : (
            (() => {
              let idx = -1;
              return visibleGroups.map(group => (
                <div key={group}>
                  {query.trim() === "" && (
                    <div className="px-4 pt-2 pb-0.5 text-[9px] font-bold tracking-widest uppercase text-slate-400">
                      {group}
                    </div>
                  )}
                  {filtered.filter(c => c.group === group).map(cmd => {
                    idx++;
                    const i = idx;
                    const Icon = cmd.icon;
                    return (
                      <button
                        key={cmd.id}
                        onMouseEnter={() => setSelected(i)}
                        onClick={() => execute(cmd)}
                        className={`w-full flex items-center gap-3 px-4 py-2 text-left transition-colors ${
                          i === selected ? "bg-slate-900 text-white" : "text-slate-700 hover:bg-slate-50"
                        }`}
                      >
                        <Icon size={14} className={i === selected ? "text-white" : "text-slate-400"} />
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium truncate">{cmd.label}</div>
                          {cmd.desc && (
                            <div className={`text-xs truncate ${i === selected ? "text-slate-300" : "text-slate-400"}`}>{cmd.desc}</div>
                          )}
                        </div>
                      </button>
                    );
                  })}
                </div>
              ));
            })()
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-2 border-t border-slate-100 flex items-center gap-3 text-[10px] text-slate-400">
          <span><kbd className="bg-slate-100 px-1 py-0.5 rounded border border-slate-200">↑↓</kbd> navigate</span>
          <span><kbd className="bg-slate-100 px-1 py-0.5 rounded border border-slate-200">↵</kbd> run</span>
          <span className="ml-auto"><kbd className="bg-slate-100 px-1 py-0.5 rounded border border-slate-200">⌘K</kbd> toggle</span>
        </div>
      </div>
    </div>
  );
}
