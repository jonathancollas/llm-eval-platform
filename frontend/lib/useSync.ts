/**
 * Auto-sync hook — runs once at startup, imports everything silently.
 * No user action required.
 */
import { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "https://llm-eval-backend-kqlh.onrender.com/api";
const SYNC_KEY = "mr_sync_ts";
const SYNC_TTL = 15 * 60 * 1000; // re-sync every 15 min max

export interface SyncState {
  synced: boolean;
  benchmarksAdded: number;
  modelsAdded: number;
  syncing: boolean;
}

export function useSync(): SyncState {
  const [synced, setSynced]               = useState(false);
  const [benchmarksAdded, setBenchmarks]  = useState(0);
  const [modelsAdded, setModels]          = useState(0);
  const [syncing, setSyncing]             = useState(false);

  useEffect(() => {
    // Skip if synced recently
    const last = localStorage.getItem(SYNC_KEY);
    if (last && Date.now() - Number(last) < SYNC_TTL) {
      setSynced(true);
      return;
    }

    setSyncing(true);
    fetch(`${API_BASE}/sync/startup`, { method: "POST" })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data) return;
        setBenchmarks(data.benchmarks_added ?? 0);
        setModels(data.models_added ?? 0);
        localStorage.setItem(SYNC_KEY, String(Date.now()));
        setSynced(true);
      })
      .catch(() => setSynced(true)) // silent fail
      .finally(() => setSyncing(false));
  }, []);

  return { synced, benchmarksAdded, modelsAdded, syncing };
}
