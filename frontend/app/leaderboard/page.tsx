"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { formatScore, formatCost, formatLatency } from "@/lib/utils";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "https://llm-eval-backend-kqlh.onrender.com/api";

interface Domain { key: string; label: string; description: string; icon: string; }
interface LeaderboardRow {
  rank: number; model_name: string; model_provider: string;
  scores: Record<string, number | null>; avg_score: number | null;
  num_benchmarks_run: number; total_cost_usd: number; avg_latency_ms: number;
}
interface GlobalLeaderboard { rows: LeaderboardRow[]; benchmarks: string[]; total_runs: number; last_updated: string; }

const DOMAIN_COLORS: Record<string, string> = {
  frontier: "border-red-200 bg-red-50 hover:border-red-300",
  cyber: "border-orange-200 bg-orange-50 hover:border-orange-300",
  cbrne: "border-red-200 bg-red-50 hover:border-red-300",
  agentique: "border-purple-200 bg-purple-50 hover:border-purple-300",
  academique: "border-blue-200 bg-blue-50 hover:border-blue-300",
  francais: "border-blue-200 bg-blue-50 hover:border-blue-300",
  code: "border-violet-200 bg-violet-50 hover:border-violet-300",
  global: "border-slate-200 bg-slate-50 hover:border-slate-300",
};

export default function LeaderboardPage() {
  const [domains, setDomains] = useState<Domain[]>([]);
  const [global, setGlobal] = useState<GlobalLeaderboard | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE}/leaderboard/domains`).then(r => r.json()),
      fetch(`${API_BASE}/leaderboard/global`).then(r => r.json()),
    ]).then(([d, g]) => { setDomains(d); setGlobal(g); }).finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <PageHeader
        title="Leaderboard INESIA"
        description="Classement des modèles d'IA par domaine d'évaluation — données issues de campagnes réelles."
      />
      <div className="p-8 space-y-8">

        {/* Domain cards */}
        <div>
          <h2 className="text-sm font-medium text-slate-700 mb-4">Leaderboards par domaine</h2>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {domains.filter(d => d.key !== "global").map(d => (
              <Link key={d.key} href={`/leaderboard/${d.key}`}
                className={`border rounded-xl p-4 transition-colors group ${DOMAIN_COLORS[d.key] ?? "border-slate-200 bg-slate-50 hover:border-slate-300"}`}>
                <div className="text-2xl mb-2">{d.icon}</div>
                <div className="font-medium text-slate-900 text-sm group-hover:text-blue-600 transition-colors">{d.label}</div>
                <p className="text-xs text-slate-500 mt-1 line-clamp-2">{d.description}</p>
              </Link>
            ))}
          </div>
        </div>

        {/* Global ranking table */}
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
            <h2 className="font-medium text-slate-900 text-sm">Classement global</h2>
            {global && <span className="text-xs text-slate-400">{global.total_runs} runs · mis à jour {new Date(global.last_updated).toLocaleDateString("fr-FR")}</span>}
          </div>

          {loading ? (
            <div className="flex justify-center py-16"><Spinner size={24} /></div>
          ) : !global || global.rows.length === 0 ? (
            <div className="py-16 text-center text-slate-400 text-sm">
              <div className="text-3xl mb-3">📊</div>
              <p className="font-medium text-slate-600 mb-1">Aucun résultat disponible</p>
              <p className="text-xs">Lancez des campagnes d'évaluation pour alimenter le leaderboard.</p>
              <Link href="/campaigns" className="mt-4 inline-block text-xs text-blue-600 hover:underline">Créer une campagne →</Link>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className="text-left px-6 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide w-10">#</th>
                    <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Modèle</th>
                    <th className="text-center px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Score moyen</th>
                    <th className="text-center px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Benchmarks</th>
                    <th className="text-center px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Coût total</th>
                    <th className="text-center px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Latence moy.</th>
                  </tr>
                </thead>
                <tbody>
                  {global.rows.map(row => (
                    <tr key={row.model_name} className="border-b border-slate-50 hover:bg-slate-50 transition-colors">
                      <td className="px-6 py-3 text-slate-400 font-mono text-xs">
                        {row.rank === 1 ? "🥇" : row.rank === 2 ? "🥈" : row.rank === 3 ? "🥉" : `#${row.rank}`}
                      </td>
                      <td className="px-4 py-3">
                        <div className="font-medium text-slate-900">{row.model_name}</div>
                        <div className="text-xs text-slate-400 capitalize">{row.model_provider}</div>
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span className={`font-mono font-semibold text-sm ${
                          row.avg_score === null ? "text-slate-300"
                          : row.avg_score >= 0.8 ? "text-green-600"
                          : row.avg_score >= 0.6 ? "text-amber-600"
                          : "text-red-500"}`}>
                          {row.avg_score !== null ? `${(row.avg_score * 100).toFixed(1)}%` : "—"}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center text-slate-600 text-xs">{row.num_benchmarks_run}</td>
                      <td className="px-4 py-3 text-center text-slate-500 text-xs font-mono">{formatCost(row.total_cost_usd)}</td>
                      <td className="px-4 py-3 text-center text-slate-500 text-xs font-mono">{formatLatency(row.avg_latency_ms)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
