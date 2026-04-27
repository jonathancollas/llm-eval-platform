"use client";
import { useApi } from "@/lib/useApi";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import Link from "next/link";
import { Layers, Rocket } from "lucide-react";

const DOMAIN_COLORS: Record<string, string> = {
  cybersecurity: "bg-red-50 text-red-700 border-red-200",
  agentic: "bg-violet-50 text-violet-700 border-violet-200",
  reasoning: "bg-blue-50 text-blue-700 border-blue-200",
  safety: "bg-amber-50 text-amber-700 border-amber-200",
  multiagent: "bg-cyan-50 text-cyan-700 border-cyan-200",
};

export default function ScenariosPage() {
  const { data: scenarios, isLoading } = useApi<any[]>("/scenarios/examples");
  const list = scenarios ?? [];

  return (
    <div className="p-4 sm:p-8 max-w-4xl">
      <PageHeader
        title="Scenarios"
        description="Structured evaluation scenarios · agentic task templates · multi-step trajectory evaluation"
        action={
          <Link href="/evaluate?type=safety"
            className="flex items-center gap-2 bg-slate-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-slate-700">
            <Rocket size={14} /> New Safety Eval
          </Link>
        }
      />

      {isLoading ? (
        <div className="flex justify-center py-20"><Spinner size={24} /></div>
      ) : list.length > 0 ? (
        <div className="mt-6 space-y-3">
          {list.map((s: any, i: number) => {
            const colorClass = DOMAIN_COLORS[s.domain] ?? "bg-slate-100 text-slate-600 border-slate-200";
            return (
              <div key={i} className="bg-white border border-slate-200 rounded-xl p-5 hover:border-slate-300 transition-colors">
                <div className="flex items-start gap-3">
                  <Layers size={18} className="text-slate-400 shrink-0 mt-0.5" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <h3 className="font-semibold text-slate-900 text-sm">{s.name ?? s.id ?? `Scenario ${i + 1}`}</h3>
                      {s.domain && (
                        <span className={`text-[10px] px-2 py-0.5 rounded-full border font-medium ${colorClass}`}>
                          {s.domain}
                        </span>
                      )}
                      {s.difficulty && (
                        <span className="text-[10px] text-slate-400 ml-auto">{s.difficulty}</span>
                      )}
                    </div>
                    {s.description && <p className="text-xs text-slate-500">{s.description}</p>}
                    {s.steps?.length > 0 && (
                      <div className="mt-2 flex items-center gap-1.5 text-[10px] text-slate-400">
                        <span>{s.steps.length} steps</span>
                        {s.max_turns && <span>· max {s.max_turns} turns</span>}
                        {s.success_criteria && <span>· {typeof s.success_criteria === "string" ? s.success_criteria : "structured criteria"}</span>}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="mt-8 text-center text-sm text-slate-400 py-16 border border-dashed border-slate-200 rounded-2xl">
          <div className="text-3xl mb-3">🧩</div>
          <div className="font-medium text-slate-600">No scenarios available</div>
          <p className="text-xs mt-1">Scenario templates will appear here once the runtime is configured.</p>
        </div>
      )}
    </div>
  );
}
