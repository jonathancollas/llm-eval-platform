import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { JobStatus } from "./api";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatScore(score: number | null, asPercent = true): string {
  if (score === null) return "—";
  return asPercent ? `${(score * 100).toFixed(1)}%` : score.toFixed(3);
}

export function formatCost(usd: number): string {
  if (usd === 0) return "$0.00";
  if (usd < 0.001) return `$${(usd * 1000).toFixed(3)}m`;
  return `$${usd.toFixed(4)}`;
}

export function formatLatency(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function statusColor(status: JobStatus): string {
  const map: Record<JobStatus, string> = {
    pending: "bg-slate-100 text-slate-600",
    running: "bg-blue-100 text-blue-700",
    completed: "bg-green-100 text-green-700",
    failed: "bg-red-100 text-red-700",
    cancelled: "bg-orange-100 text-orange-700",
  };
  return map[status] ?? "bg-slate-100 text-slate-600";
}

export function scoreColor(score: number | null): string {
  if (score === null) return "#94a3b8";
  if (score >= 0.8) return "#22c55e";
  if (score >= 0.6) return "#eab308";
  if (score >= 0.4) return "#f97316";
  return "#ef4444";
}

export function benchmarkTypeColor(type: string): string {
  const map: Record<string, string> = {
    academic: "bg-blue-100 text-blue-700",
    safety: "bg-red-100 text-red-700",
    coding: "bg-violet-100 text-violet-700",
    custom: "bg-slate-100 text-slate-700",
  };
  return map[type] ?? "bg-slate-100 text-slate-700";
}

export function providerColor(provider: string): string {
  const map: Record<string, string> = {
    openai: "bg-emerald-100 text-emerald-700",
    anthropic: "bg-amber-100 text-amber-700",
    mistral: "bg-orange-100 text-orange-700",
    groq: "bg-cyan-100 text-cyan-700",
    custom: "bg-slate-100 text-slate-700",
  };
  return map[provider] ?? "bg-slate-100 text-slate-700";
}

export function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  if (diff < 60_000) return "just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return `${Math.floor(diff / 86_400_000)}d ago`;
}
