"use client";
import { useSync } from "@/lib/useSync";
import { Spinner } from "./Spinner";

export function SyncBanner() {
  const { syncing, synced, benchmarksAdded, modelsAdded } = useSync();

  // Show a brief confirmation only if something was actually imported
  const showConfirm = synced && (benchmarksAdded > 0 || modelsAdded > 0);

  if (!syncing && !showConfirm) return null;

  return (
    <div className="mx-4 mt-3 bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 flex items-center gap-3">
      {syncing ? (
        <>
          <Spinner size={13} />
          <span className="text-xs text-slate-500">Synchronisation du catalogue…</span>
        </>
      ) : (
        <span className="text-xs text-slate-500">
          ✓ Catalogue synchronisé
          {benchmarksAdded > 0 && ` · ${benchmarksAdded} benchmark${benchmarksAdded > 1 ? "s" : ""} ajouté${benchmarksAdded > 1 ? "s" : ""}`}
          {modelsAdded > 0 && ` · ${modelsAdded} model${modelsAdded > 1 ? "s" : ""} ajouté${modelsAdded > 1 ? "s" : ""}`}
        </span>
      )}
    </div>
  );
}
