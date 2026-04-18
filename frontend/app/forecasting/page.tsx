"use client";
import { useApi } from "@/lib/useApi";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import Link from "next/link";
import { LineChart, Rocket } from "lucide-react";

const CAP_COLORS: Record<string, string> = {
  cybersecurity: "bg-red-100 text-red-700",
  reasoning: "bg-blue-100 text-blue-700",
  instruction_following: "bg-violet-100 text-violet-700",
  knowledge: "bg-amber-100 text-amber-700",
  agentic: "bg-cyan-100 text-cyan-700",
  safety: "bg-orange-100 text-orange-700",
  multimodal: "bg-teal-100 text-teal-700",
};

export default function ForecastingPage() {
  const { data: capabilities, isLoading: capLoading } = useApi<string[]>("/forecasting/capabilities");
  const { data: tasks, isLoading: tasksLoading } = useApi<any[]>("/forecasting/long-horizon/tasks");

  const isLoading = capLoading || tasksLoading;

  return (
    <div className="p-4 sm:p-8 max-w-5xl">
      <PageHeader
        title="Capability Forecasting"
        description="Scaling law fitting · capability extrapolation · long-horizon task evaluation · frontier metrics"
        action={
          <Link href="/evaluate?type=capability"
            className="flex items-center gap-2 bg-slate-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-slate-700">
            <Rocket size={14} /> New Capability Eval
          </Link>
        }
      />

      {isLoading ? (
        <div className="flex justify-center py-20"><Spinner size={24} /></div>
      ) : (
        <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-6">

          {/* Tracked capabilities */}
          <div className="bg-white border border-slate-200 rounded-xl p-5">
            <h3 className="font-semibold text-slate-900 mb-1">Tracked capabilities</h3>
            <p className="text-xs text-slate-500 mb-4">Run evaluations to build scaling trend data for these domains.</p>
            <div className="space-y-2">
              {(capabilities ?? []).map(cap => (
                <div key={cap} className="flex items-center gap-2">
                  <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${CAP_COLORS[cap] ?? "bg-slate-100 text-slate-600"}`}>
                    {cap.replace(/_/g, " ")}
                  </span>
                  <LineChart size={12} className="text-slate-300 ml-auto" />
                </div>
              ))}
              {!capabilities?.length && (
                <div className="text-xs text-slate-400 italic">Capabilities list unavailable.</div>
              )}
            </div>
          </div>

          {/* Long-horizon tasks */}
          <div className="bg-white border border-slate-200 rounded-xl p-5">
            <h3 className="font-semibold text-slate-900 mb-1">Long-horizon tasks</h3>
            <p className="text-xs text-slate-500 mb-4">Multi-step agentic evaluation tasks with partial credit scoring.</p>
            <div className="space-y-2">
              {(tasks ?? []).map((t: any, i: number) => (
                <div key={i} className="flex items-center gap-2 p-2 rounded-lg border border-slate-100 hover:border-slate-200 hover:bg-slate-50 transition-colors">
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-slate-800 truncate">{t.name ?? t.id ?? `Task ${i + 1}`}</div>
                    {t.description && <div className="text-xs text-slate-400 truncate">{t.description}</div>}
                  </div>
                  {t.domain && (
                    <span className={`text-[10px] px-2 py-0.5 rounded-full shrink-0 ${CAP_COLORS[t.domain] ?? "bg-slate-100 text-slate-500"}`}>
                      {t.domain}
                    </span>
                  )}
                </div>
              ))}
              {!tasks?.length && (
                <div className="text-xs text-slate-400 italic">No tasks available.</div>
              )}
            </div>
          </div>

          {/* Info card */}
          <div className="md:col-span-2 bg-gradient-to-br from-violet-50 to-slate-50 border border-violet-200 rounded-xl p-5">
            <h3 className="font-semibold text-violet-900 mb-2 flex items-center gap-2">
              <LineChart size={16} className="text-violet-500" />
              How forecasting works
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs text-violet-800">
              <div>
                <div className="font-semibold mb-1">1. Collect data points</div>
                <div className="text-violet-600">Run capability evaluations across multiple model versions or sizes to build a dataset.</div>
              </div>
              <div>
                <div className="font-semibold mb-1">2. Fit scaling law</div>
                <div className="text-violet-600">Linear, power-law, or logistic regression against compute / parameters / date.</div>
              </div>
              <div>
                <div className="font-semibold mb-1">3. Extrapolate</div>
                <div className="text-violet-600">Bootstrap confidence intervals around forward forecasts with phase transition detection.</div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
