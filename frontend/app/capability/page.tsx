"use client";
import { useApi } from "@/lib/useApi";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import Link from "next/link";
import { Rocket } from "lucide-react";

const DOMAIN_ICONS: Record<string, string> = {
  reasoning: "🧠", knowledge: "📚", coding: "💻", math: "🔢",
  instruction_following: "📋", safety: "🛡", multimodal: "🖼",
};

export default function CapabilityPage() {
  const { data: taxonomy, isLoading } = useApi<Record<string, any>>("/capability/taxonomy");

  return (
    <div className="p-4 sm:p-8 max-w-5xl">
      <PageHeader
        title="Capability Intelligence"
        description="7-domain capability taxonomy · model profiles · coverage gaps · cross-benchmark normalization"
        action={
          <Link href="/evaluate?type=capability"
            className="flex items-center gap-2 bg-slate-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-slate-700">
            <Rocket size={14} /> New Capability Eval
          </Link>
        }
      />

      {isLoading ? (
        <div className="flex justify-center py-20"><Spinner size={24} /></div>
      ) : taxonomy && Object.keys(taxonomy).length > 0 ? (
        <div className="mt-6 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {Object.entries(taxonomy).map(([domain, data]: [string, any]) => {
            const capabilities: any[] = data?.capabilities ?? data?.sub_capabilities ?? [];
            return (
              <div key={domain} className="bg-white border border-slate-200 rounded-xl p-5 hover:border-slate-300 transition-colors">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xl">{DOMAIN_ICONS[domain] ?? "🔷"}</span>
                  <h3 className="font-semibold text-slate-900 capitalize">{data?.label ?? domain.replace(/_/g, " ")}</h3>
                  <span className="ml-auto text-xs text-slate-400">{capabilities.length} cap.</span>
                </div>
                {data?.description && <p className="text-xs text-slate-500 mb-3">{data.description}</p>}
                <div className="space-y-1">
                  {capabilities.slice(0, 4).map((cap: any, i: number) => (
                    <div key={i} className="flex items-center gap-1.5 text-xs text-slate-600">
                      <span className="w-1.5 h-1.5 rounded-full bg-slate-300 shrink-0" />
                      {typeof cap === "string" ? cap : (cap.label ?? cap.id ?? String(cap))}
                    </div>
                  ))}
                  {capabilities.length > 4 && (
                    <div className="text-[10px] text-slate-400">+{capabilities.length - 4} more</div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="mt-8 text-center text-sm text-slate-400 py-16 border border-dashed border-slate-200 rounded-2xl">
          <div className="text-3xl mb-3">🔷</div>
          <div className="font-medium text-slate-600">Capability taxonomy not yet available</div>
          <p className="text-xs mt-1">Run evaluations to populate model capability profiles.</p>
        </div>
      )}
    </div>
  );
}
