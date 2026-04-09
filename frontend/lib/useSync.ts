/**
 * Auto-sync hook — runs once at startup, imports everything silently.
 * No user action required.
 */
import { useEffect, useState } from "react";
import { API_BASE, SYNC_TTL_MS } from "./config";

const SYNC_KEY = "eval_os_sync_ts";

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
    if (last && Date.now() - Number(last) < SYNC_TTL_MS) {
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
