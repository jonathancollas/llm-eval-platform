"use client";

import { useEffect, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { AppErrorBoundary } from "@/components/AppErrorBoundary";
import { campaignsApi } from "@/lib/api";
import { API_BASE } from "@/lib/config";
import type { Campaign } from "@/lib/api";

interface GenomeData {
  models: Record<string, Record<string, number>>;
  ontology: Record<
    string,
    { label: string; color: string; description: string; severity: number }
  >;
  computed: boolean;
}

function RadarViz({
  genome,
  ontology,
}: {
  genome: Record<string, number>;
  ontology: Record<
    string,
    { label: string; color: string; description: string; severity: number }
  >;
}) {
  const entries = Object.entries(genome).filter(
    ([k]) => ontology[k] && genome[k] > 0
  );

  if (!entries.length)
    return (
      <div className="text-xs text-slate-400 py-2 text-center">
        No signals
      </div>
    );

  const SIZE = 140;
  const CENTER = SIZE / 2;
  const RADIUS = 52;
  const n = Math.max(entries.length, 1);

  const points = entries.map(([key, val], i) => {
    const angle = (i / n) * 2 * Math.PI - Math.PI / 2;
    const r = RADIUS * Math.min(val, 1);

    return {
      key,
      val,
      color: ontology[key]?.color ?? "#64748b",
      x: CENTER + r * Math.cos(angle),
      y: CENTER + r * Math.sin(angle),
    };
  });

  const pathD =
    points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ") +
    " Z";

  return (
    <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="w-36 h-36">
      {[0.25, 0.5, 0.75, 1.0].map((r) => (
        <circle
          key={r}
          cx={CENTER}
          cy={CENTER}
          r={RADIUS * r}
          fill="none"
          stroke="#e2e8f0"
          strokeWidth="0.5"
        />
      ))}

      {entries.map((_, i) => {
        const angle = (i / n) * 2 * Math.PI - Math.PI / 2;
        return (
          <line
            key={i}
            x1={CENTER}
            y1={CENTER}
            x2={CENTER + RADIUS * Math.cos(angle)}
            y2={CENTER + RADIUS * Math.sin(angle)}
            stroke="#e2e8f0"
            strokeWidth="0.5"
          />
        );
      })}

      <path
        d={pathD}
        fill="#ef444425"
        stroke="#ef4444"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />

      {points.map((p) => (
        <circle key={p.key} cx={p.x} cy={p.y} r={2.5} fill={p.color} />
      ))}
    </svg>
  );
}

function RiskBadge({ level }: { level: string }) {
  const cfg =
    {
      red: { bg: "bg-red-100 text-red-700", label: "Haut risque" },
      yellow: { bg: "bg-yellow-100 text-yellow-700", label: "Modéré" },
      green: { bg: "bg-green-100 text-green-700", label: "Faible" },
    }[level] ?? { bg: "bg-slate-100 text-slate-600", label: level };

  return (
    <span
      className={`text-xs px-2 py-0.5 rounded-full font-medium ${cfg.bg}`}
    >
      {cfg.label}
    </span>
  );
}

function GenomePage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [genome, setGenome] = useState<GenomeData | null>(null);
  const [heatmap, setHeatmap] = useState<any | null>(null);
  const [fingerprints, setFingerprints] = useState<any[]>([]);
  const [references, setReferences] = useState<any | null>(null);

  const [loading, setLoading] = useState(false);
  const [computing, setComputing] = useState(false);
  const [tab, setTab] = useState<
    "genome" | "heatmap" | "fingerprints" | "science"
  >("genome");

  const reload = () => {
    fetch(`${API_BASE}/genome/models`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d && setFingerprints(d.fingerprints ?? []));

    fetch(`${API_BASE}/genome/safety-heatmap`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d && setHeatmap(d));

    fetch(`${API_BASE}/genome/references`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d && setReferences(d));
  };

  useEffect(() => {
    campaignsApi
      .list()
      .then((cs) => {
        const completed = cs.filter((c) => c.status === "completed");
        setCampaigns(completed);
        if (completed.length) setSelectedId(completed[0].id);
      })
      .finally(() => reload());
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    fetch(`${API_BASE}/genome/campaigns/${selectedId}`)
      .then((r) => r.json())
      .then((d) => setGenome(d));
  }, [selectedId]);

  return (
    <div>
      <PageHeader
        title="Genomia"
        description="Structural behavioral diagnostic of models."
      />

      <div className="px-8 pt-4 flex gap-1 border-b border-slate-100">
        {["genome", "heatmap", "fingerprints", "science"].map((t) => (
          <button
            key={t}
            onClick={() => setTab(t as any)}
            className="px-4 py-2 text-sm"
          >
            {t}
          </button>
        ))}
      </div>

      <div className="p-8">
        {tab === "genome" && <div>Genome tab...</div>}
        {tab === "heatmap" && <div>Heatmap tab...</div>}
        {tab === "fingerprints" && <div>Fingerprints tab...</div>}

        {/* FIXED: inside return */}
        {tab === "science" && (
          <div className="space-y-6 max-w-4xl">
            <div className="bg-blue-50 border border-blue-200 p-4 text-sm">
              Scientific grounding
              {references && (
                <span className="ml-2">
                  ({references.total_papers} papers)
                </span>
              )}
            </div>

            {!references ? (
              <Spinner size={20} />
            ) : (
              Object.entries(references.references).map(
                ([category, heuristics]: any) => (
                  <div key={category}>
                    <h2 className="text-xs font-bold uppercase">
                      {category}
                    </h2>
                    <div>
                      {Object.entries(heuristics).map(
                        ([key, data]: any) => (
                          <div key={key} className="border p-3">
                            <div className="font-mono text-xs">{key}</div>
                            <p className="text-sm">{data.description}</p>
                          </div>
                        )
                      )}
                    </div>
                  </div>
                )
              )
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function GenomePageWrapper() {
  return (
    <AppErrorBoundary>
      <GenomePage />
    </AppErrorBoundary>
  );
}
