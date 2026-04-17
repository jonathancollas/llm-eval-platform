/**
 * Auto-sync hook — triggers startup sync once per session, never blocks the UI.
 *
 * BEFORE: POST /sync/startup waited 20s for OpenRouter → entire app froze.
 * AFTER:
 *   1. POST /sync/startup returns immediately (background task on server)
 *   2. We poll GET /sync/startup/status every 2s until done
 *   3. All other requests (campaigns, models) are unblocked immediately
 */
import { useEffect, useState, useRef } from "react";
import { API_BASE, SYNC_TTL_MS } from "./config";

const SYNC_KEY = "eval_os_sync_ts";
const POLL_INTERVAL_MS = 2000;

export interface SyncState {
  synced: boolean;
  benchmarksAdded: number;
  modelsAdded: number;
  hfBenchmarksDiscovered: number;
  syncing: boolean;
}

export function useSync(): SyncState {
  const [synced, setSynced] = useState(false);
  const [benchmarksAdded, setBenchmarks] = useState(0);
  const [modelsAdded, setModels] = useState(0);
  const [hfBenchmarksDiscovered, setHfDiscovered] = useState(0);
  const [syncing, setSyncing] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    // Skip if synced recently (localStorage TTL cache)
    const last = localStorage.getItem(SYNC_KEY);
    if (last && Date.now() - Number(last) < SYNC_TTL_MS) {
      setSynced(true);
      return;
    }

    setSyncing(true);

    // Step 1 — fire POST, don't await the result (returns in <5ms now)
    fetch(`${API_BASE}/sync/startup`, { method: "POST" }).catch(() => {});

    // Step 2 — poll status until done or error
    let attempts = 0;
    let consecutiveErrors = 0;
    const MAX_ATTEMPTS = 30;        // 30 × 2 s = 60 s hard timeout
    const MAX_CONSECUTIVE_ERRORS = 3; // stop after 3 non-OK/network failures in a row

    const stopPolling = () => {
      clearInterval(pollRef.current!);
      pollRef.current = null;
      localStorage.setItem(SYNC_KEY, String(Date.now()));
      setSynced(true);
      setSyncing(false);
    };

    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/sync/startup/status`);
        if (!res.ok) {
          consecutiveErrors += 1;
          if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) stopPolling();
          return;
        }
        consecutiveErrors = 0;
        const data = await res.json();

        if (data.status === "done" || data.status === "error") {
          setBenchmarks(data.benchmarks_added ?? 0);
          setModels(data.models_added ?? 0);
          setHfDiscovered(data.hf_benchmarks_discovered ?? 0);
          stopPolling();
        }
      } catch (err) {
        // Network hiccup — log for diagnostics, then count toward error threshold
        console.warn("[useSync] polling error:", err);
        consecutiveErrors += 1;
        if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) stopPolling();
      }

      // Hard timeout — give up after MAX_ATTEMPTS regardless of server state
      attempts += 1;
      if (attempts >= MAX_ATTEMPTS) stopPolling();
    }, POLL_INTERVAL_MS);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  return { synced, benchmarksAdded, modelsAdded, hfBenchmarksDiscovered, syncing };
}
