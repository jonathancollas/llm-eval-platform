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
import type { Campaign, LLMModel, LLMModelSlim, Benchmark, DashboardData, GenomeData, FailedItemsData } from "./api";

import { API_BASE, API_KEY } from "./config";

async function fetcher<T>(path: string): Promise<T> {
  // 10s timeout — never hang forever on slow backend
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10_000);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      headers: {
        "Content-Type": "application/json",
        ...(API_KEY ? { "X-API-Key": API_KEY } : {}),
      },
      signal: controller.signal,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail ?? `API error ${res.status}`);
    }
    if (res.status === 204 || res.headers.get("content-length") === "0") {
      return null as unknown as T;
    }
    return res.json() as Promise<T>;
  } catch (e: any) {
    if (e.name === "AbortError") throw new Error("Request timeout");
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

/** All campaigns — auto-refresh only when a campaign is running */
export function useCampaigns() {
  const { data, error, isLoading, mutate } = useSWR<Campaign[]>(
    "/campaigns/",
    fetcher,
    {
      // Refresh every 3s only if there's a running/pending campaign
      refreshInterval: (data) => {
        const hasActive = data?.some(c => c.status === "running" || c.status === "pending");
        return hasActive ? 3000 : 0;
      },
      revalidateOnFocus: false,   // Don't hammer on tab focus
      dedupingInterval: 2000,
    }
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

/** All models — uses /models/slim (lightweight projection, ~10x smaller payload) */
export function useModels() {
  const { data, error, isLoading, mutate } = useSWR<LLMModelSlim[]>(
    "/models/slim",
    fetcher,
    { dedupingInterval: 30000, revalidateOnFocus: false }
  );
  return { models: data ?? [], isLoading, error, refresh: mutate };
}

/** Full model list with all metadata — for the Models page only */
export function useModelsFull() {
  const { data, error, isLoading, mutate } = useSWR<LLMModel[]>(
    "/models/",
    fetcher,
    { dedupingInterval: 30000, revalidateOnFocus: false }
  );
  return { models: data ? dedupModels(data) : [], isLoading, error, refresh: mutate };
}

/** All benchmarks — cached 30s. Pass enabled=false to defer until ready. */
export function useBenchmarks(type?: string, enabled = true) {
  const key = !enabled ? null : type ? `/benchmarks/?type=${type}` : "/benchmarks/";
  const { data, error, isLoading, mutate } = useSWR<Benchmark[]>(
    key, fetcher, { dedupingInterval: 30000, revalidateOnFocus: false }
  );
  return { benchmarks: data ?? [], isLoading, error, refresh: mutate };
}

/** Dashboard for a campaign — cached 10s */
export function useDashboard(campaignId: number | null) {
  const { data, error, isLoading } = useSWR<DashboardData>(
    campaignId ? `/results/campaign/${campaignId}/dashboard` : null,
    fetcher, { dedupingInterval: 10000, revalidateOnFocus: false }
  );
  return { dashboard: data ?? null, isLoading, error };
}

/** Genome for a campaign */
export function useGenome(campaignId: number | null) {
  const { data, error, isLoading } = useSWR<GenomeData>(
    campaignId ? `/genome/campaigns/${campaignId}` : null,
    fetcher, { dedupingInterval: 10000, revalidateOnFocus: false }
  );
  return { genome: data ?? null, isLoading, error };
}

/** Failed items for a campaign */
export function useFailedItems(campaignId: number | null) {
  const { data, error, isLoading } = useSWR<FailedItemsData>(
    campaignId ? `/results/campaign/${campaignId}/failed-items` : null,
    fetcher, { dedupingInterval: 10000, revalidateOnFocus: false }
  );
  return { failedData: data ?? null, isLoading, error };
}

/** Unified insights for a campaign */
export function useInsights(campaignId: number | null) {
  const { data, error, isLoading } = useSWR(
    campaignId ? `/results/campaign/${campaignId}/insights` : null,
    fetcher, { dedupingInterval: 10000, revalidateOnFocus: false }
  );
  return { insights: data ?? null, isLoading, error };
}

/** Generic hook for any API path */
export function useApi<T>(path: string | null, options?: { refreshInterval?: number }) {
  const { data, error, isLoading, mutate } = useSWR<T>(
    path, fetcher, { dedupingInterval: 5000, revalidateOnFocus: false, ...options }
  );
  return { data: data ?? null, isLoading, error, refresh: mutate };
}
