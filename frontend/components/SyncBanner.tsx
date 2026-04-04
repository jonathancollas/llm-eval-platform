"use client";
import { useState } from "react";
import { useSync } from "@/lib/useSync";
import { Spinner } from "./Spinner";
import { Sparkles, X, Download } from "lucide-react";

export function SyncBanner() {
  const { newBenchmarks, importing, importAll, checking } = useSync() as any;
  const [dismissed, setDismissed] = useState(false);
  const [importing2, setImporting2] = useState(false);
  const [imported, setImported] = useState<number | null>(null);

  if (checking || dismissed || newBenchmarks === 0) return null;

  const handleImport = async () => {
    setImporting2(true);
    try {
      const n = await importAll();
      setImported(n);
      setTimeout(() => setDismissed(true), 3000);
    } finally {
      setImporting2(false);
    }
  };

  return (
    <div className="mx-4 mt-3 bg-blue-50 border border-blue-200 rounded-xl px-4 py-3 flex items-center gap-3">
      <Sparkles size={14} className="text-blue-500 shrink-0" />
      {imported !== null ? (
        <span className="text-sm text-blue-700 flex-1">
          ✅ {imported} nouveau{imported > 1 ? "x" : ""} benchmark{imported > 1 ? "s" : ""} importé{imported > 1 ? "s" : ""} !
        </span>
      ) : (
        <>
          <span className="text-sm text-blue-700 flex-1">
            <strong>{newBenchmarks}</strong> nouveau{newBenchmarks > 1 ? "x" : ""} benchmark{newBenchmarks > 1 ? "s" : ""} disponible{newBenchmarks > 1 ? "s" : ""} dans le catalogue.
          </span>
          <button onClick={handleImport} disabled={importing2}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 shrink-0">
            {importing2 ? <Spinner size={11} /> : <Download size={11} />}
            {importing2 ? "Import…" : "Importer"}
          </button>
        </>
      )}
      <button onClick={() => setDismissed(true)} className="text-blue-400 hover:text-blue-600 shrink-0">
        <X size={14} />
      </button>
    </div>
  );
}
