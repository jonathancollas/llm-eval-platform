"use client";
import { useEffect, useState, useCallback } from "react";
import { modelsApi, benchmarksApi, campaignsApi } from "@/lib/api";
import Link from "next/link";
import { Cpu, Library, Rocket, BarChart3, Trophy, ArrowRight,
         Dna, Gavel, Lock, Radio, FlaskConical, ShieldAlert } from "lucide-react";
import { APP_NAME, APP_TAGLINE, APP_VERSION } from "@/lib/config";

interface Stats {
  models: number;
  benchmarks: number;
  inesia_benchmarks: number;
  campaigns: number;
  completed_runs: number;
}

const QUICK_LINKS = [
  { href: "/models",      icon: Cpu,         label: "Model Registry",    desc: "Catalogue, access types, local download via Ollama",  color: "text-blue-600" },
  { href: "/benchmarks",  icon: Library,     label: "Benchmarks",        desc: "INESIA + public · taxonomy · source classification",   color: "text-violet-600" },
  { href: "/campaigns",   icon: Rocket,      label: "Campaigns",         desc: "Launch static evaluation runs",                        color: "text-slate-700" },
  { href: "/dashboard",   icon: BarChart3,   label: "Dashboard",         desc: "Heatmaps, radar, capability/propensity scores",        color: "text-green-600" },
  { href: "/leaderboard", icon: Trophy,      label: "Leaderboard",       desc: "Rankings by domain",                                  color: "text-amber-600" },
  { href: "/genome",      icon: Dna,         label: "Genomia",           desc: "Structural behavioral diagnostic · beyond the score",  color: "text-cyan-600" },
  { href: "/judge",       icon: Gavel,       label: "LLM-as-Judge",      desc: "Multi-judge · calibration · bias detection",          color: "text-slate-600" },
  { href: "/redbox",      icon: Lock,        label: "The Red Room",      desc: "Adversarial evaluation lab — restricted access",       color: "text-red-600" },
  { href: "/telemetry",   icon: Radio,       label: "Monitoring",        desc: "Continuous post-deployment safety monitoring",         color: "text-purple-600" },
  { href: "/methodology", icon: FlaskConical,label: "Methodology Center", desc: "Scientific foundations · papers · heuristics",        color: "text-teal-600" },
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
  const [stats, setStats] = useState<Stats>({ models: 0, benchmarks: 0, inesia_benchmarks: 0, campaigns: 0, completed_runs: 0 });
  const [loading, setLoading] = useState(true);

  const fetchStats = useCallback(async () => {
    try {
      const [models, benchmarks, campaigns] = await Promise.all([
        modelsApi.list(),
        benchmarksApi.list(),
        campaignsApi.list(),
      ]);
      setStats({
        models: models.length,
        benchmarks: benchmarks.length,
        inesia_benchmarks: benchmarks.filter((b: any) => b.source === "inesia").length,
        campaigns: campaigns.length,
        completed_runs: campaigns.filter((c: any) => c.status === "completed").length,
      });
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, 10_000);
    return () => clearInterval(interval);
  }, [fetchStats]);

  return (
    <div>
      {/* Hero */}
      <div className="px-8 py-8 border-b border-slate-100 bg-gradient-to-br from-slate-50 to-white">
        <div className="max-w-2xl">
          <div className="text-[10px] font-bold tracking-widest text-purple-500 uppercase mb-2">
            {APP_VERSION} · {APP_TAGLINE}
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight mb-2">
            {APP_NAME}
          </h1>
          <p className="text-sm text-slate-500 leading-relaxed">
            The operating system for frontier AI safety evaluation —
            system-in-context evaluation, continuous monitoring, and scientific methodology.
          </p>
        </div>
      </div>

      <div className="p-8 space-y-8 max-w-5xl">

        {/* Stat counters */}
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
          {[
            { label: "Models",           value: stats.models,           color: "text-blue-600",   bg: "bg-blue-50",   border: "border-blue-100" },
            { label: "Benchmarks",       value: stats.benchmarks,       color: "text-violet-600", bg: "bg-violet-50", border: "border-violet-100" },
            { label: "INESIA Benchmarks",value: stats.inesia_benchmarks,color: "text-purple-600", bg: "bg-purple-50", border: "border-purple-100" },
            { label: "Campaigns",        value: stats.campaigns,        color: "text-slate-700",  bg: "bg-slate-50",  border: "border-slate-100" },
            { label: "Completed Evals",  value: stats.completed_runs,   color: "text-green-600",  bg: "bg-green-50",  border: "border-green-100" },
          ].map(({ label, value, color, bg, border }) => (
            <div key={label} className={`${bg} border ${border} rounded-xl p-4`}>
              <div className={`text-2xl font-bold ${color} mb-0.5`}>
                {loading ? "—" : <AnimatedCount value={value} />}
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
        <div className="bg-white border border-slate-200 rounded-xl p-5 text-xs text-slate-500 space-y-1.5">
          <div className="font-semibold text-slate-700 mb-2 text-sm">Evaluation Engine</div>
          <div className="flex gap-2"><span className="text-slate-300">↺</span><span>Public benchmarks → <span className="font-mono text-slate-600">lm-evaluation-harness</span> (EleutherAI)</span></div>
          <div className="flex gap-2"><span className="text-slate-300">🛡</span><span>INESIA frontier benchmarks → custom safety scoring runners</span></div>
          <div className="flex gap-2"><span className="text-slate-300">☿</span><span>Models → LiteLLM + OpenRouter + Ollama ({stats.models} registered)</span></div>
          <div className="flex gap-2"><span className="text-slate-300">📚</span><span>Scientific methodology → {APP_VERSION} · <Link href="/methodology" className="text-blue-500 hover:underline">Methodology Center</Link></span></div>
        </div>

        {/* INESIA doctrine banner */}
        <div className="bg-gradient-to-r from-purple-50 to-blue-50 border border-purple-100 rounded-xl p-5 text-sm">
          <p className="font-semibold text-purple-800 mb-1">INESIA Research Doctrine</p>
          <p className="text-purple-700 text-xs leading-relaxed">
            "The evaluation paradigm has broken. Model scores alone are no longer enough.
            Systems must be evaluated in context and in production."
          </p>
          <div className="mt-3 flex gap-3 flex-wrap">
            <Link href="/methodology" className="text-xs text-purple-600 hover:underline font-medium">→ Methodology Center</Link>
            <Link href="/genome" className="text-xs text-purple-600 hover:underline font-medium">→ Genomia behavioral diagnostic</Link>
            <Link href="/redbox" className="text-xs text-red-600 hover:underline font-medium">→ The Red Room</Link>
          </div>
        </div>

      </div>
    </div>
  );
}
