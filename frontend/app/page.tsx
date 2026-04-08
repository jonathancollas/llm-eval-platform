"use client";
import { useEffect, useState, useCallback } from "react";
import { modelsApi, benchmarksApi, campaignsApi } from "@/lib/api";
import { PageHeader } from "@/components/PageHeader";
import Link from "next/link";
import { Cpu, Library, Rocket, BarChart3, Trophy, ArrowRight } from "lucide-react";

interface Stats {
  models: number;
  benchmarks: number;
  campaigns: number;
  completed_runs: number;
}

const QUICK_LINKS = [
  { href: "/models",     icon: Cpu,      label: "Models",     desc: "Manage models" },
  { href: "/benchmarks", icon: Library,  label: "Benchmarks", desc: "Catalogue & datasets" },
  { href: "/campaigns",  icon: Rocket,   label: "Campaigns",  desc: "Launch an evaluation" },
  { href: "/dashboard",  icon: BarChart3,label: "Dashboard",  desc: "Visualize results" },
  { href: "/leaderboard",icon: Trophy,   label: "Leaderboard",desc: "Rankings by domain" },
];

function AnimatedCount({ value, suffix = "" }: { value: number; suffix?: string }) {
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    if (value === 0) return;
    let start = 0;
    const step = Math.ceil(value / 24);
    const timer = setInterval(() => {
      start += step;
      if (start >= value) { setDisplay(value); clearInterval(timer); }
      else setDisplay(start);
    }, 30);
    return () => clearInterval(timer);
  }, [value]);

  return <span>{display}{suffix}</span>;
}

export default function OverviewPage() {
  const [stats, setStats] = useState<Stats>({ models: 0, benchmarks: 0, campaigns: 0, completed_runs: 0 });
  const [loading, setLoading] = useState(true);

  const fetchStats = useCallback(async () => {
    const [models, benchmarks, campaigns] = await Promise.all([
      modelsApi.list(),
      benchmarksApi.list(),
      campaignsApi.list(),
    ]);
    setStats({
      models: models.length,
      benchmarks: benchmarks.length,
      campaigns: campaigns.length,
      completed_runs: campaigns.filter((c: any) => c.status === "completed").length,
    });
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchStats();
    // Refresh every 10s
    const interval = setInterval(fetchStats, 10_000);
    return () => clearInterval(interval);
  }, [fetchStats]);

  const statCards = [
    { label: "Models enregistrés", value: stats.models,        color: "text-blue-600",   bg: "bg-blue-50",   border: "border-blue-100" },
    { label: "Benchmarks actifs",   value: stats.benchmarks,    color: "text-violet-600", bg: "bg-violet-50", border: "border-violet-100" },
    { label: "Campagnes créées",    value: stats.campaigns,     color: "text-slate-700",  bg: "bg-slate-50",  border: "border-slate-100" },
    { label: "Évaluations complètes", value: stats.completed_runs, color: "text-green-600", bg: "bg-green-50", border: "border-green-100" },
  ];

  return (
    <div>
      <PageHeader
        title="Overview"
        description="Mercury Retrograde — INESIA AI Evaluation Platform"
      />
      <div className="p-8 space-y-8 max-w-4xl">

        {/* Stat counters */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {statCards.map(({ label, value, color, bg, border }) => (
            <div key={label} className={`${bg} border ${border} rounded-xl p-5`}>
              <div className={`text-3xl font-bold ${color} mb-1`}>
                {loading ? "—" : <AnimatedCount value={value} />}
              </div>
              <div className="text-xs text-slate-500">{label}</div>
            </div>
          ))}
        </div>

        {/* Quick nav */}
        <div>
          <h2 className="text-sm font-medium text-slate-700 mb-3">Navigation rapide</h2>
          <div className="grid grid-cols-1 gap-2">
            {QUICK_LINKS.map(({ href, icon: Icon, label, desc }) => (
              <Link key={href} href={href}
                className="flex items-center gap-4 bg-white border border-slate-200 rounded-xl px-5 py-4 hover:border-slate-300 hover:bg-slate-50 transition-colors group">
                <Icon size={18} className="text-slate-400 group-hover:text-slate-700 transition-colors shrink-0" />
                <div className="flex-1">
                  <div className="font-medium text-slate-900 text-sm">{label}</div>
                  <div className="text-xs text-slate-400">{desc}</div>
                </div>
                <ArrowRight size={14} className="text-slate-300 group-hover:text-slate-500 transition-colors" />
              </Link>
            ))}
          </div>
        </div>

        {/* Status note */}
        <div className="bg-white border border-slate-200 rounded-xl p-5 text-xs text-slate-500 space-y-1">
          <div className="font-medium text-slate-700 mb-2">Moteur d'évaluation</div>
          <div>↺ Benchmarks standards → <span className="font-mono text-slate-600">lm-evaluation-harness</span> (EleutherAI)</div>
          <div>🛡️ Benchmarks frontier INESIA → runners custom (safety scoring)</div>
          <div>☿ Models → LiteLLM + OpenRouter ({stats.models} configurés)</div>
        </div>

      </div>
    </div>
  );
}
