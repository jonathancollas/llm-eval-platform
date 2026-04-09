/**
 * SWR hooks for data fetching with caching, deduplication, and revalidation.
 * Replaces raw useEffect + fetch patterns across all pages.
 *
 * Benefits over raw fetch:
 * - Automatic deduplication (same URL = 1 request)
 * - Stale-while-revalidate (instant display, background refresh)
 * - Smart refetch on focus/reconnect
 * - Cache across page navigation
 */
import useSWR from "swr";
import type { Campaign, LLMModel, Benchmark, DashboardData, GenomeData, FailedItemsData } from "./api";

import { API_BASE } from "./config";

async function fetcher<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `API error ${res.status}`);
  }
  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return null as unknown as T;
  }
  return res.json() as Promise<T>;
}

/** All campaigns — auto-refresh every 3s when running */
export function useCampaigns() {
  const { data, error, isLoading, mutate } = useSWR<Campaign[]>(
    "/campaigns/",
    fetcher,
    { refreshInterval: 3000, revalidateOnFocus: true }
  );
  return {
    campaigns: data ?? [],
    isLoading,
    error,
    refresh: mutate,
    hasRunning: data?.some(c => c.status === "running" || c.status === "pending") ?? false,
  };
}

/** Dedup models by model_id — guards against double-fetch race conditions */
function dedupModels(models: LLMModel[]): LLMModel[] {
  const map = new Map<string, LLMModel>();
  for (const m of models) map.set(m.model_id, m);
  return [...map.values()];
}

/** All models — cached 30s, deduplicated */
export function useModels() {
  const { data, error, isLoading, mutate } = useSWR<LLMModel[]>(
    "/models/",
    fetcher,
    { dedupingInterval: 30000 }
  );
  return { models: data ? dedupModels(data) : [], isLoading, error, refresh: mutate };
}

/** All benchmarks — cached 30s */
export function useBenchmarks(type?: string) {
  const key = type ? `/benchmarks/?type=${type}` : "/benchmarks/";
  const { data, error, isLoading, mutate } = useSWR<Benchmark[]>(
    key, fetcher, { dedupingInterval: 30000 }
  );
  return { benchmarks: data ?? [], isLoading, error, refresh: mutate };
}

/** Dashboard for a campaign — cached 10s */
export function useDashboard(campaignId: number | null) {
  const { data, error, isLoading } = useSWR<DashboardData>(
    campaignId ? `/results/campaign/${campaignId}/dashboard` : null,
    fetcher, { dedupingInterval: 10000 }
  );
  return { dashboard: data ?? null, isLoading, error };
}

/** Genome for a campaign */
export function useGenome(campaignId: number | null) {
  const { data, error, isLoading } = useSWR<GenomeData>(
    campaignId ? `/genome/campaigns/${campaignId}` : null,
    fetcher, { dedupingInterval: 10000 }
  );
  return { genome: data ?? null, isLoading, error };
}

/** Failed items for a campaign */
export function useFailedItems(campaignId: number | null) {
  const { data, error, isLoading } = useSWR<FailedItemsData>(
    campaignId ? `/results/campaign/${campaignId}/failed-items` : null,
    fetcher, { dedupingInterval: 10000 }
  );
  return { failedData: data ?? null, isLoading, error };
}

/** Unified insights for a campaign */
export function useInsights(campaignId: number | null) {
  const { data, error, isLoading } = useSWR(
    campaignId ? `/results/campaign/${campaignId}/insights` : null,
    fetcher, { dedupingInterval: 10000 }
  );
  return { insights: data ?? null, isLoading, error };
}

/** Generic hook for any API path */
export function useApi<T>(path: string | null, options?: { refreshInterval?: number }) {
  const { data, error, isLoading, mutate } = useSWR<T>(
    path, fetcher, { dedupingInterval: 5000, ...options }
  );
  return { data: data ?? null, isLoading, error, refresh: mutate };
}
