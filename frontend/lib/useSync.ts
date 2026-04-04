/**
 * Silent sync hook — runs once at app startup.
 * Checks for new benchmarks in catalog vs local DB.
 * Returns count of new items available.
 */
import { useState, useEffect, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "https://llm-eval-backend-kqlh.onrender.com/api";
const SYNC_CACHE_KEY = "inesia_sync_last";
const SYNC_INTERVAL_MS = 10 * 60 * 1000; // 10 min

export interface SyncState {
  newBenchmarks: number;
  newBenchmarkItems: unknown[];
  lastChecked: Date | null;
  checking: boolean;
  importAll: () => Promise<number>;
  recheck: () => void;
}

export function useSync(): SyncState {
  const [newBenchmarks, setNewBenchmarks] = useState(0);
  const [newBenchmarkItems, setNewBenchmarkItems] = useState<unknown[]>([]);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);
  const [checking, setChecking] = useState(false);

  const check = useCallback(async () => {
    setChecking(true);
    try {
      const res = await fetch(`${API_BASE}/sync/benchmarks`);
      if (!res.ok) return;
      const data = await res.json();
      setNewBenchmarks(data.new_count ?? 0);
      setNewBenchmarkItems(data.new_benchmarks ?? []);
      setLastChecked(new Date());
      localStorage.setItem(SYNC_CACHE_KEY, new Date().toISOString());
    } catch {
      // silent fail — sync is best-effort
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    // Check if we synced recently
    const last = localStorage.getItem(SYNC_CACHE_KEY);
    if (last) {
      const elapsed = Date.now() - new Date(last).getTime();
      if (elapsed < SYNC_INTERVAL_MS) return; // skip if synced recently
    }
    check();
  }, [check]);

  const importAll = async (): Promise<number> => {
    const res = await fetch(`${API_BASE}/sync/benchmarks/import-all`, { method: "POST" });
    const data = await res.json();
    setNewBenchmarks(0);
    setNewBenchmarkItems([]);
    return data.added ?? 0;
  };

  return { newBenchmarks, newBenchmarkItems, lastChecked, checking, importAll, recheck: check };
}
