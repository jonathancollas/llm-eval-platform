"use client";
import { useEffect, useState } from "react";
import { useApi } from "@/lib/useApi";
import Link from "next/link";
import { Cpu, Library, Rocket, BarChart3, Trophy, ArrowRight,
         Dna, Gavel, Lock, Radio, FlaskConical } from "lucide-react";

interface Stats {
  models: number;
  benchmarks: number;
  inesia_benchmarks: number;
  campaigns: number;
  completed_runs: number;
}

const QUICK_LINKS = [
  { href: "/models",      icon: Cpu,         label: "Model Registry",     desc: "Catalogue, access types, Ollama download",           color: "text-blue-600" },
  { href: "/benchmarks",  icon: Library,     label: "Benchmarks",         desc: "INESIA + public · taxonomy · source classification",  color: "text-violet-600" },
  { href: "/campaigns",   icon: Rocket,      label: "Evaluations",        desc: "Run static or system-in-context evaluations",                color: "text-slate-700" },
  { href: "/dashboard",   icon: BarChart3,   label: "Dashboard",          desc: "Heatmaps, radar, capability / propensity scores",     color: "text-green-600" },
  { href: "/leaderboard", icon: Trophy,      label: "Leaderboard",        desc: "Rankings by domain",                                 color: "text-amber-600" },
  { href: "/genome",      icon: Dna,         label: "Genomia",            desc: "Structural behavioral diagnostic · beyond the score", color: "text-cyan-600" },
  { href: "/judge",       icon: Gavel,       label: "LLM-as-Judge",       desc: "Multi-judge · calibration · bias detection",         color: "text-slate-600" },
  { href: "/redbox",      icon: Lock,        label: "The Red Room",       desc: "Adversarial evaluation lab — restricted access",      color: "text-red-600" },
  { href: "/telemetry",   icon: Radio,       label: "Monitoring",         desc: "Continuous post-deployment safety monitoring",        color: "text-purple-600" },
  { href: "/methodology", icon: FlaskConical, label: "Methodology Center", desc: "Scientific foundations · papers · heuristics",       color: "text-teal-600" },
];

function AnimatedCount({ value }: { value: number }) {
  const [display, setDisplay] = useState(0);
  useEffect(() => {
    if (value === 0) return;
    let start = 0;
    const step = Math.max(1, Math.ceil(value / 24));
    const timer = setInterval(() => {
      start += step;
      if (start >= value) { setDisplay(value); clearInterval(timer); }
      else setDisplay(start);
    }, 30);
    return () => clearInterval(timer);
  }, [value]);
  return <span>{display}</span>;
}

export default function OverviewPage() {
  // Single aggregated endpoint — replaces three separate list() calls
  const { data: stats, isLoading } = useApi<Stats>("/results/stats/summary", { refreshInterval: 30_000 });

  const s: Stats = stats ?? { models: 0, benchmarks: 0, inesia_benchmarks: 0, campaigns: 0, completed_runs: 0 };

  return (
    <div className="p-4 sm:p-8 space-y-6 max-w-5xl">

      {/* Stat counters */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        {[
          { label: "Models",            value: s.models,            color: "text-blue-600",   bg: "bg-blue-50",   border: "border-blue-100" },
          { label: "Benchmarks",        value: s.benchmarks,        color: "text-violet-600", bg: "bg-violet-50", border: "border-violet-100" },
          { label: "INESIA Benchmarks", value: s.inesia_benchmarks, color: "text-purple-600", bg: "bg-purple-50", border: "border-purple-100" },
          { label: "Evaluations",        value: s.campaigns,         color: "text-slate-700",  bg: "bg-slate-50",  border: "border-slate-100" },
          { label: "Completed Evals",   value: s.completed_runs,    color: "text-green-600",  bg: "bg-green-50",  border: "border-green-100" },
        ].map(({ label, value, color, bg, border }) => (
          <div key={label} className={`${bg} border ${border} rounded-xl p-4`}>
            <div className={`text-2xl font-bold ${color} mb-0.5`}>
              {isLoading ? "—" : <AnimatedCount value={value} />}
            </div>
            <div className="text-[11px] text-slate-500 leading-tight">{label}</div>
          </div>
        ))}
      </div>

      {/* Quick nav */}
      <div>
        <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-3">Platform modules</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {QUICK_LINKS.map(({ href, icon: Icon, label, desc, color }) => (
            <Link key={href} href={href}
              className="flex items-center gap-4 bg-white border border-slate-200 rounded-xl px-4 py-3.5 hover:border-slate-300 hover:bg-slate-50 transition-colors group">
              <Icon size={16} className={`${color} shrink-0`} />
              <div className="flex-1 min-w-0">
                <div className="font-medium text-slate-900 text-sm">{label}</div>
                <div className="text-xs text-slate-400 truncate">{desc}</div>
              </div>
              <ArrowRight size={13} className="text-slate-300 group-hover:text-slate-500 transition-colors shrink-0" />
            </Link>
          ))}
        </div>
      </div>

      {/* Engine info */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 text-xs text-slate-500 space-y-1.5">
        <div className="font-semibold text-slate-700 mb-1.5 text-sm">Evaluation Engine</div>
        <div className="flex gap-2"><span className="text-slate-300">↺</span><span>Public benchmarks → <span className="font-mono text-slate-600">lm-evaluation-harness</span> (EleutherAI)</span></div>
        <div className="flex gap-2"><span className="text-slate-300">🛡</span><span>INESIA frontier benchmarks → custom safety scoring runners</span></div>
        <div className="flex gap-2"><span className="text-slate-300">☿</span><span>Models → LiteLLM + OpenRouter + Ollama ({s.models} registered)</span></div>
        <div className="flex gap-2"><span className="text-slate-300">📚</span><span><Link href="/methodology" className="text-blue-500 hover:underline">Methodology Center</Link> · <Link href="/about" className="text-blue-500 hover:underline">About</Link></span></div>
      </div>
    </div>
  );
}
