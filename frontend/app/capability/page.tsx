"use client";
import { useState, useEffect } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import Link from "next/link";
import { Rocket, AlertTriangle, BarChart3, Search } from "lucide-react";
import { API_BASE } from "@/lib/config";

const DOMAIN_ICONS: Record<string, string> = {
  cyber: "🔐", cbrn: "☢️", persuasion: "🎭", scheming: "🧩",
  agentic: "🤖", reasoning: "🧠", coding: "💻", safety: "🛡️",
  alignment: "🎯", multimodal: "🖼️", knowledge: "📚", math: "🔢",
  science: "🔬", language: "🗣️", general: "🔷",
};

const RISK_COLORS: Record<string, string> = {
  good:    "bg-green-100 text-green-700 border-green-200",
  partial: "bg-yellow-100 text-yellow-700 border-yellow-200",
  gap:     "bg-red-100 text-red-700 border-red-200",
};

export default function CapabilityPage() {
  const [gaps, setGaps] = useState<any[]>([]);
  const [domains, setDomains] = useState<any[]>([]);
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [activeTab, setActiveTab] = useState<"gaps" | "search">("gaps");

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE}/catalog/benchmarks/tasks/gaps`).then(r => r.json()),
      fetch(`${API_BASE}/catalog/benchmarks/tasks/domains`).then(r => r.json()),
    ]).then(([gapData, domainData]) => {
      setGaps(gapData.gaps ?? []);
      setDomains(domainData.domains ?? []);
    }).catch(err => console.error("[capability] load failed:", err))
      .finally(() => setLoading(false));
  }, []);

  const search = () => {
    if (!query.trim()) return;
    setSearching(true);
    fetch(`${API_BASE}/catalog/benchmarks/tasks/search?q=${encodeURIComponent(query)}&limit=30`)
      .then(r => r.json())
      .then(d => { setSearchResults(d.tasks ?? []); setActiveTab("search"); })
      .catch(err => console.error("[capability] search failed:", err))
      .finally(() => setSearching(false));
  };

  return (
    <div className="p-4 sm:p-8 max-w-6xl">
      <PageHeader
        title="Capability Intelligence"
        description="Coverage gap analysis · 109 benchmark tasks · capability domain mapping"
        action={
          <Link href="/evaluate?type=capability"
            className="flex items-center gap-2 bg-slate-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-slate-700">
            <Rocket size={14} /> New Capability Eval
          </Link>
        }
      />

      {/* Search bar */}
      <div className="mt-6 flex gap-2">
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === "Enter" && search()}
          placeholder="Search benchmark tasks… (e.g. cyber, reasoning, mmlu)"
          className="flex-1 border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-slate-300"
        />
        <button onClick={search} disabled={searching}
          className="flex items-center gap-2 bg-slate-900 text-white px-4 py-2.5 rounded-xl text-sm hover:bg-slate-700 disabled:opacity-50">
          {searching ? <Spinner size={14} /> : <Search size={14} />}
          Search
        </button>
      </div>

      {/* Tabs */}
      <div className="mt-6 flex gap-2 border-b border-slate-100 pb-1">
        {[
          { key: "gaps",   label: "Coverage Gaps",        icon: <AlertTriangle size={13} /> },
          { key: "search", label: `Results (${searchResults.length})`, icon: <BarChart3 size={13} /> },
        ].map(t => (
          <button key={t.key} onClick={() => setActiveTab(t.key as any)}
            className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-colors ${activeTab === t.key ? "bg-slate-900 text-white" : "text-slate-500 hover:bg-slate-50"}`}>
            {t.icon}{t.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex justify-center py-20"><Spinner size={24} /></div>
      ) : activeTab === "gaps" ? (
        <div className="mt-6">
          <p className="text-xs text-slate-500 mb-4">
            Domains with fewest benchmarks relative to their safety importance.
            <strong className="text-red-600 ml-1">Red = gap</strong>,
            <strong className="text-yellow-600 ml-1">Yellow = partial</strong>,
            <strong className="text-green-600 ml-1">Green = good coverage</strong>.
          </p>
          <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-3">
            {gaps.map((g: any) => (
              <div key={g.domain}
                className={`border rounded-xl p-4 ${RISK_COLORS[g.coverage_level] ?? "bg-slate-50 text-slate-600 border-slate-200"}`}>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-lg">{DOMAIN_ICONS[g.domain] ?? "🔷"}</span>
                  <span className="font-semibold capitalize text-sm">{g.domain}</span>
                </div>
                <div className="text-xs opacity-75">{g.benchmark_count} benchmark{g.benchmark_count !== 1 ? "s" : ""}</div>
                <div className="mt-1.5 h-1.5 rounded-full bg-black/10 overflow-hidden">
                  <div className="h-full rounded-full bg-current"
                    style={{ width: `${Math.min(100, (g.benchmark_count / 10) * 100)}%` }} />
                </div>
              </div>
            ))}
          </div>

          <div className="mt-8">
            <h3 className="text-sm font-semibold text-slate-700 mb-3">All domains by coverage</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-100 text-left text-slate-400">
                    <th className="pb-2 font-medium">Domain</th>
                    <th className="pb-2 font-medium text-right">Benchmarks</th>
                    <th className="pb-2 font-medium text-right">Coverage</th>
                  </tr>
                </thead>
                <tbody>
                  {domains.map((d: any) => (
                    <tr key={d.domain} className="border-b border-slate-50 hover:bg-slate-50">
                      <td className="py-2 flex items-center gap-1.5">
                        <span>{DOMAIN_ICONS[d.domain] ?? "🔷"}</span>
                        <span className="capitalize">{d.domain}</span>
                      </td>
                      <td className="py-2 text-right font-mono">{d.count}</td>
                      <td className="py-2 text-right">
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium border ${
                          d.count >= 5 ? "bg-green-50 text-green-700 border-green-200" :
                          d.count >= 2 ? "bg-yellow-50 text-yellow-700 border-yellow-200" :
                          "bg-red-50 text-red-700 border-red-200"
                        }`}>
                          {d.count >= 5 ? "Good" : d.count >= 2 ? "Partial" : "Gap"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : (
        <div className="mt-6">
          {searchResults.length === 0 ? (
            <div className="text-center py-12 text-sm text-slate-400">
              No results yet — enter a query and press Search.
            </div>
          ) : (
            <div className="space-y-2">
              <p className="text-xs text-slate-500 mb-3">{searchResults.length} tasks found</p>
              {searchResults.map((t: any) => (
                <div key={t.task_id}
                  className="bg-white border border-slate-200 rounded-xl p-4 hover:border-slate-300 transition-colors">
                  <div className="flex items-start gap-3">
                    <span className="text-lg mt-0.5">{DOMAIN_ICONS[t.domain] ?? "🔷"}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-semibold text-slate-900 text-sm">{t.name}</span>
                        {t.is_frontier && (
                          <span className="text-[10px] px-1.5 py-0.5 bg-orange-100 text-orange-700 border border-orange-200 rounded font-bold">FRONTIER</span>
                        )}
                        <span className="text-[10px] text-slate-400 font-mono ml-auto">{t.task_id}</span>
                      </div>
                      {t.description && <p className="text-xs text-slate-500 mt-1 line-clamp-2">{t.description}</p>}
                      <div className="flex flex-wrap gap-1 mt-2">
                        {t.capability_domains?.map((d: string) => (
                          <span key={d} className="text-[10px] px-1.5 py-0.5 bg-slate-100 text-slate-600 rounded">
                            {DOMAIN_ICONS[d] ?? ""} {d}
                          </span>
                        ))}
                        {t.num_samples && (
                          <span className="text-[10px] px-1.5 py-0.5 bg-blue-50 text-blue-600 rounded ml-auto">
                            {t.num_samples} samples
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
