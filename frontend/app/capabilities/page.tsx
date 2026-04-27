"use client";
import { useEffect, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { API_BASE } from "@/lib/config";
import Link from "next/link";

interface SubCapability {
  id: number | null;
  slug: string;
  display_name: string;
  risk_level: string;
  difficulty: string;
}

interface Domain {
  id: number | null;
  slug: string;
  display_name: string;
  sub_capabilities: SubCapability[];
}

interface ModelMeta {
  id: number;
  name: string;
  provider: string;
}

interface HeatmapData {
  domains: Domain[];
  models: ModelMeta[];
  scores: Record<string, Record<string, number | null>>;
  coverage: Record<string, Record<string, boolean>>;
}

const RISK_COLORS: Record<string, string> = {
  critical: "bg-red-500",
  high: "bg-orange-400",
  medium: "bg-amber-400",
  low: "bg-emerald-400",
};

const RISK_LABELS: Record<string, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
};

function scoreColor(score: number | null | undefined): string {
  if (score == null) return "bg-slate-100 text-slate-300";
  if (score >= 0.8) return "bg-green-100 text-green-700";
  if (score >= 0.6) return "bg-amber-100 text-amber-700";
  if (score >= 0.4) return "bg-orange-100 text-orange-600";
  return "bg-red-100 text-red-600";
}

function CoverageCell({
  covered,
  score,
}: {
  covered: boolean;
  score: number | null | undefined;
}) {
  if (!covered) {
    return (
      <td className="px-1 py-1 text-center">
        <div className="w-full h-7 rounded bg-slate-100 flex items-center justify-center">
          <span className="text-slate-300 text-xs">—</span>
        </div>
      </td>
    );
  }
  const pct = score != null ? `${(score * 100).toFixed(0)}%` : "✓";
  return (
    <td className="px-1 py-1 text-center">
      <div
        className={`w-full h-7 rounded flex items-center justify-center text-xs font-mono font-medium ${scoreColor(score)}`}
      >
        {pct}
      </div>
    </td>
  );
}

function CoverageSummaryBar({
  model,
  domains,
  coverage,
}: {
  model: ModelMeta;
  domains: Domain[];
  coverage: Record<string, Record<string, boolean>>;
}) {
  const mid = String(model.id);
  const allSubs = domains.flatMap((d) => d.sub_capabilities);
  const coveredCount = allSubs.filter(
    (sc) => coverage[mid]?.[sc.slug]
  ).length;
  const pct = allSubs.length > 0 ? (coveredCount / allSubs.length) * 100 : 0;
  const barColor =
    pct >= 75
      ? "bg-green-500"
      : pct >= 40
      ? "bg-amber-500"
      : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${barColor} transition-all`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-slate-500 w-10 text-right">
        {pct.toFixed(0)}%
      </span>
    </div>
  );
}

export default function CapabilitiesPage() {
  const [data, setData] = useState<HeatmapData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState<string>("all");
  const [showUncoveredOnly, setShowUncoveredOnly] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetch(`${API_BASE}/capability/heatmap`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((d) => setData(d))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <Spinner size={32} />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-8 text-red-500">
        Failed to load capability heatmap: {error}
      </div>
    );
  }

  const filteredDomains =
    activeFilter === "all"
      ? data.domains
      : data.domains.filter((d) => d.slug === activeFilter);

  // Compute total coverage stats
  const allSubs = data.domains.flatMap((d) => d.sub_capabilities);
  const totalSubCaps = allSubs.length;

  return (
    <div>
      <PageHeader
        title="🧠 Capability Coverage Heatmap"
        description="Model × capability matrix — which capabilities has each model been evaluated on?"
        action={
          <Link
            href="/leaderboard"
            className="text-xs text-slate-500 hover:text-slate-800"
          >
            ← Leaderboard
          </Link>
        }
      />

      <div className="p-4 sm:p-8 space-y-6">
        {/* Summary stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            { label: "Domains", value: data.domains.length },
            { label: "Sub-capabilities", value: totalSubCaps },
            { label: "Models evaluated", value: data.models.length },
            {
              label: "Avg coverage",
              value:
                data.models.length > 0
                  ? `${(
                      (data.models.reduce((sum, m) => {
                        const mid = String(m.id);
                        const cov = data.coverage[mid] ?? {};
                        return (
                          sum +
                          allSubs.filter((sc) => cov[sc.slug]).length /
                            Math.max(allSubs.length, 1)
                        );
                      }, 0) /
                        data.models.length) *
                        100
                    ).toFixed(0)}%`
                  : "—",
            },
          ].map(({ label, value }) => (
            <div
              key={label}
              className="bg-white border border-slate-200 rounded-xl p-4"
            >
              <div className="text-xs text-slate-500 mb-1">{label}</div>
              <div className="text-2xl font-semibold text-slate-900">
                {value}
              </div>
            </div>
          ))}
        </div>

        {/* Legend */}
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <div className="flex flex-wrap items-center gap-6">
            <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">
              Risk level
            </span>
            {Object.entries(RISK_LABELS).map(([key, label]) => (
              <div key={key} className="flex items-center gap-1.5">
                <span
                  className={`w-3 h-3 rounded-full ${RISK_COLORS[key]}`}
                />
                <span className="text-xs text-slate-600">{label}</span>
              </div>
            ))}
            <div className="ml-auto flex items-center gap-4">
              <label className="flex items-center gap-2 text-xs text-slate-600 cursor-pointer">
                <input
                  type="checkbox"
                  checked={showUncoveredOnly}
                  onChange={(e) => setShowUncoveredOnly(e.target.checked)}
                  className="rounded"
                />
                Show gaps only
              </label>
            </div>
          </div>
        </div>

        {/* Domain filter tabs */}
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setActiveFilter("all")}
            className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
              activeFilter === "all"
                ? "bg-slate-900 text-white"
                : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
            }`}
          >
            All domains
          </button>
          {data.domains.map((d) => (
            <button
              key={d.slug}
              onClick={() =>
                setActiveFilter(activeFilter === d.slug ? "all" : d.slug)
              }
              className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                activeFilter === d.slug
                  ? "bg-slate-900 text-white"
                  : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
              }`}
            >
              {d.display_name}
            </button>
          ))}
        </div>

        {data.models.length === 0 ? (
          <div className="bg-white border border-slate-200 rounded-xl py-16 text-center">
            <div className="text-3xl mb-3">🧬</div>
            <p className="font-medium text-slate-600 mb-1">No models yet</p>
            <p className="text-xs text-slate-400 mb-4">
              Add models and run evaluations to populate the heatmap.
            </p>
            <Link
              href="/models"
              className="text-xs text-blue-600 hover:underline"
            >
              Add a model →
            </Link>
          </div>
        ) : (
          <div className="space-y-6">
            {filteredDomains.map((domain) => {
              let displaySubs = domain.sub_capabilities;
              if (showUncoveredOnly) {
                displaySubs = displaySubs.filter((sc) =>
                  data.models.some(
                    (m) => !data.coverage[String(m.id)]?.[sc.slug]
                  )
                );
              }
              if (displaySubs.length === 0) return null;

              return (
                <div
                  key={domain.slug}
                  className="bg-white border border-slate-200 rounded-xl overflow-hidden"
                >
                  <div className="px-6 py-3 border-b border-slate-100 bg-slate-50 flex items-center justify-between">
                    <h2 className="font-semibold text-slate-800 text-sm">
                      {domain.display_name}
                    </h2>
                    <span className="text-xs text-slate-400">
                      {domain.sub_capabilities.length} sub-capabilities
                    </span>
                  </div>

                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-slate-100">
                          {/* Model column header */}
                          <th className="text-left px-4 py-2 text-xs font-medium text-slate-500 sticky left-0 bg-white z-10 min-w-40">
                            Model
                          </th>
                          <th className="text-left px-4 py-2 text-xs font-medium text-slate-500 min-w-28">
                            Coverage
                          </th>
                          {displaySubs.map((sc) => (
                            <th
                              key={sc.slug}
                              className="px-1 py-2 text-center min-w-20 max-w-24"
                            >
                              <div className="flex flex-col items-center gap-0.5">
                                <span
                                  className={`w-2 h-2 rounded-full ${RISK_COLORS[sc.risk_level] ?? "bg-slate-300"}`}
                                  title={`Risk: ${sc.risk_level}`}
                                />
                                <span
                                  className="text-[10px] text-slate-500 truncate max-w-16 text-center leading-tight"
                                  title={sc.display_name}
                                >
                                  {sc.display_name}
                                </span>
                              </div>
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {data.models.map((model) => {
                          const mid = String(model.id);
                          return (
                            <tr
                              key={model.id}
                              className="border-b border-slate-50 hover:bg-slate-50 transition-colors"
                            >
                              <td className="px-4 py-2 sticky left-0 bg-white z-10">
                                <div className="font-medium text-slate-800">
                                  {model.name}
                                </div>
                                <div className="text-slate-400 capitalize">
                                  {model.provider}
                                </div>
                              </td>
                              <td className="px-4 py-2 min-w-28">
                                <CoverageSummaryBar
                                  model={model}
                                  domains={[domain]}
                                  coverage={data.coverage}
                                />
                              </td>
                              {displaySubs.map((sc) => (
                                <CoverageCell
                                  key={sc.slug}
                                  covered={
                                    data.coverage[mid]?.[sc.slug] ?? false
                                  }
                                  score={data.scores[mid]?.[sc.slug]}
                                />
                              ))}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
