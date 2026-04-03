"use client";
import { useEffect, useState } from "react";
import { campaignsApi, modelsApi, benchmarksApi } from "@/lib/api";
import type { Campaign, LLMModel, Benchmark } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { formatScore, formatCost, timeAgo } from "@/lib/utils";
import Link from "next/link";
import { Cpu, Library, Rocket, ArrowRight, AlertTriangle } from "lucide-react";

export default function OverviewPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [models, setModels] = useState<LLMModel[]>([]);
  const [benchmarks, setBenchmarks] = useState<Benchmark[]>([]);

  useEffect(() => {
    Promise.all([campaignsApi.list(), modelsApi.list(), benchmarksApi.list()])
      .then(([c, m, b]) => { setCampaigns(c); setModels(m); setBenchmarks(b); });
  }, []);

  const recent = campaigns.slice(0, 5);
  const running = campaigns.filter(c => c.status === "running");

  return (
    <div className="p-8 max-w-6xl">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-slate-900">Overview</h1>
        <p className="text-slate-500 text-sm mt-1">LLM Evaluation Platform</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        {[
          { label: "Models", value: models.length, icon: Cpu, href: "/models", color: "text-blue-600" },
          { label: "Benchmarks", value: benchmarks.length, icon: Library, href: "/benchmarks", color: "text-violet-600" },
          { label: "Campaigns", value: campaigns.length, icon: Rocket, href: "/campaigns", color: "text-emerald-600" },
        ].map(({ label, value, icon: Icon, href, color }) => (
          <Link key={label} href={href}
            className="bg-white border border-slate-200 rounded-xl p-5 flex items-center gap-4 hover:border-slate-300 transition-colors group">
            <div className={`${color} bg-slate-50 rounded-lg p-2.5`}>
              <Icon size={20} />
            </div>
            <div>
              <div className="text-2xl font-bold text-slate-900">{value}</div>
              <div className="text-sm text-slate-500">{label}</div>
            </div>
            <ArrowRight size={14} className="ml-auto text-slate-300 group-hover:text-slate-500 transition-colors" />
          </Link>
        ))}
      </div>

      {/* Running campaigns alert */}
      {running.length > 0 && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-6 flex items-center gap-3">
          <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
          <span className="text-sm text-blue-700 font-medium">
            {running.length} campaign{running.length > 1 ? "s" : ""} running
          </span>
          <Link href="/campaigns" className="ml-auto text-xs text-blue-600 hover:underline">View →</Link>
        </div>
      )}

      {/* Recent campaigns */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <h2 className="font-medium text-slate-900 text-sm">Recent Campaigns</h2>
          <Link href="/campaigns" className="text-xs text-slate-500 hover:text-slate-700">View all →</Link>
        </div>
        {recent.length === 0 ? (
          <div className="py-12 text-center text-slate-400 text-sm">
            No campaigns yet. <Link href="/campaigns" className="text-blue-600 hover:underline">Create one →</Link>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100">
                {["Name", "Status", "Progress", "Models", "Cost", "Created"].map(h => (
                  <th key={h} className="text-left px-6 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {recent.map(c => (
                <tr key={c.id} className="border-b border-slate-50 hover:bg-slate-50 transition-colors">
                  <td className="px-6 py-3">
                    <Link href={`/dashboard?campaign=${c.id}`} className="font-medium text-slate-900 hover:text-blue-600">
                      {c.name}
                    </Link>
                  </td>
                  <td className="px-6 py-3"><StatusBadge status={c.status} /></td>
                  <td className="px-6 py-3">
                    <div className="flex items-center gap-2">
                      <div className="w-24 bg-slate-100 rounded-full h-1.5">
                        <div className="bg-blue-500 h-1.5 rounded-full transition-all" style={{ width: `${c.progress}%` }} />
                      </div>
                      <span className="text-slate-500 text-xs">{c.progress.toFixed(0)}%</span>
                    </div>
                  </td>
                  <td className="px-6 py-3 text-slate-600">{c.model_ids.length}</td>
                  <td className="px-6 py-3 text-slate-600">
                    {formatCost(c.runs.reduce((s, r) => s + r.total_cost_usd, 0))}
                  </td>
                  <td className="px-6 py-3 text-slate-400">{timeAgo(c.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
