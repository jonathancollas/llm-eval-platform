"use client";
import { useState, useEffect, useCallback } from "react";
import {
  X, ChevronRight, ChevronLeft, Plus, Trash2, CheckCircle,
  Upload, Search, Database, BookOpen, ExternalLink,
} from "lucide-react";
import { benchmarksApi } from "@/lib/api";
import type { BenchmarkType } from "@/lib/api";
import { Spinner } from "./Spinner";
import { Badge } from "./Badge";
import { API_BASE } from "@/lib/config";

// ─────────────────────────────────────────────────────────────────────────────
// Shared types
// ─────────────────────────────────────────────────────────────────────────────

type Mode = "choose" | "import" | "create";
type ImportSource = "catalog" | "huggingface" | "file";

interface CatalogBenchmark {
  key: string; name: string; type: string; domain: string;
  description: string; metric: string; num_samples: number; tags: string[];
  is_frontier: boolean; year?: number | null; paper_url?: string | null;
}

interface HFDataset {
  id: string; downloads: number; likes: number;
  description: string; tags: string[]; gated: boolean; card_data: Record<string, unknown>;
}

interface ManualItem {
  prompt: string;
  expected: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-step: Catalog browser (for import → catalog source)
// ─────────────────────────────────────────────────────────────────────────────

function CatalogBrowser({
  selected,
  onSelect,
}: {
  selected: string | null;
  onSelect: (key: string) => void;
}) {
  const [catalog, setCatalog] = useState<CatalogBenchmark[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/catalog/benchmarks`)
      .then(r => r.json())
      .then(d => { if (Array.isArray(d)) setCatalog(d); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const filtered = search
    ? catalog.filter(b => b.name.toLowerCase().includes(search.toLowerCase()) || b.domain.toLowerCase().includes(search.toLowerCase()))
    : catalog;

  return (
    <div className="flex flex-col gap-3">
      <div className="relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search INESIA catalog…"
          className="w-full pl-9 pr-4 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-900"
        />
      </div>
      <div className="max-h-64 overflow-y-auto space-y-1.5 pr-1">
        {loading ? (
          <div className="flex justify-center py-8"><Spinner size={20} /></div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-8 text-slate-400 text-sm">No benchmarks found.</div>
        ) : (
          filtered.map(b => (
            <button
              key={b.key}
              onClick={() => onSelect(b.key)}
              className={`w-full text-left p-3 rounded-xl border text-sm transition-colors ${
                selected === b.key
                  ? "border-slate-900 bg-slate-900 text-white"
                  : "border-slate-200 hover:border-slate-300 hover:bg-slate-50 text-slate-800"
              }`}
            >
              <div className="flex items-center gap-2 mb-0.5">
                <span className="font-medium">{b.name}</span>
                {b.is_frontier && <Badge className="bg-red-100 text-red-600 text-[10px]">Frontier</Badge>}
                {b.year && <span className={`text-[10px] ${selected === b.key ? "opacity-60" : "text-slate-400"}`}>{b.year}</span>}
              </div>
              <p className={`text-xs truncate ${selected === b.key ? "opacity-70" : "text-slate-500"}`}>{b.description}</p>
              <div className={`text-[10px] mt-1 ${selected === b.key ? "opacity-60" : "text-slate-400"}`}>
                {b.domain} · metric: {b.metric} · {b.num_samples} items
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-step: HuggingFace browser (for import → HF source)
// ─────────────────────────────────────────────────────────────────────────────

function HFBrowser({
  repoId,
  split,
  subset,
  maxItems,
  onRepoId,
  onSplit,
  onSubset,
  onMaxItems,
}: {
  repoId: string; split: string; subset: string; maxItems: number;
  onRepoId: (v: string) => void; onSplit: (v: string) => void;
  onSubset: (v: string) => void; onMaxItems: (v: number) => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<HFDataset[]>([]);
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState<HFDataset | null>(null);

  const doSearch = useCallback(async (q: string) => {
    if (!q.trim()) { setResults([]); return; }
    setSearching(true);
    try {
      const res = await fetch(`https://huggingface.co/api/datasets?search=${encodeURIComponent(q)}&limit=12&sort=downloads&direction=-1`);
      const data = await res.json();
      setResults(Array.isArray(data) ? data : []);
    } catch { setResults([]); }
    setSearching(false);
  }, []);

  useEffect(() => {
    const t = setTimeout(() => doSearch(query), 400);
    return () => clearTimeout(t);
  }, [query, doSearch]);

  const pickDataset = (ds: HFDataset) => {
    setSelected(ds);
    onRepoId(ds.id);
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search HuggingFace datasets…"
          className="w-full pl-9 pr-4 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-yellow-400"
        />
        {searching && <Spinner size={13} className="absolute right-3 top-1/2 -translate-y-1/2" />}
      </div>

      {results.length > 0 && (
        <div className="grid grid-cols-2 gap-2 max-h-44 overflow-y-auto">
          {results.map((ds: any) => (
            <button
              key={ds.id}
              onClick={() => pickDataset(ds)}
              className={`text-left p-3 rounded-lg border transition-colors text-xs ${
                selected?.id === ds.id ? "border-yellow-400 bg-yellow-50" : "border-slate-200 hover:border-slate-300 hover:bg-slate-50"
              }`}
            >
              <div className="font-medium text-slate-900 truncate">{ds.id}</div>
              <div className="text-slate-400 mt-0.5 flex gap-2">
                {ds.downloads != null && <span>⬇ {(ds.downloads / 1000).toFixed(0)}k</span>}
                {ds.gated && <span className="text-amber-600 font-medium">GATED</span>}
              </div>
            </button>
          ))}
        </div>
      )}

      <div className="border border-slate-200 rounded-xl p-4 bg-slate-50 space-y-3">
        <div>
          <label className="text-xs font-medium text-slate-600 mb-1 block">Repository ID</label>
          <input
            value={repoId}
            onChange={e => onRepoId(e.target.value)}
            placeholder="e.g. EleutherAI/hendrycks_test"
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-yellow-400"
          />
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="text-xs font-medium text-slate-600 mb-1 block">Split</label>
            <select value={split} onChange={e => onSplit(e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-2 py-1.5 text-sm bg-white">
              <option value="test">test</option>
              <option value="train">train</option>
              <option value="validation">validation</option>
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-600 mb-1 block">Subset</label>
            <input value={subset} onChange={e => onSubset(e.target.value)}
              placeholder="optional"
              className="w-full border border-slate-200 rounded-lg px-2 py-1.5 text-sm bg-white" />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-600 mb-1 block">Max items</label>
            <input type="number" value={maxItems} onChange={e => onMaxItems(+e.target.value)}
              min={10} max={5000}
              className="w-full border border-slate-200 rounded-lg px-2 py-1.5 text-sm bg-white" />
          </div>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main wizard
// ─────────────────────────────────────────────────────────────────────────────

interface WizardProps {
  onClose: () => void;
  onCreated: () => void;
}

export function BenchmarkWizard({ onClose, onCreated }: WizardProps) {
  const [mode, setMode] = useState<Mode>("choose");
  const [step, setStep] = useState(1);   // 1=mode, 2=source/meta, 3=browse/items, 4=confirm

  // ── Import state ─────────────────────────────────────────────────────────
  const [importSource, setImportSource] = useState<ImportSource>("catalog");
  const [selectedCatalogKey, setSelectedCatalogKey] = useState<string | null>(null);
  const [hfRepoId, setHfRepoId] = useState("");
  const [hfSplit, setHfSplit] = useState("test");
  const [hfSubset, setHfSubset] = useState("");
  const [hfMaxItems, setHfMaxItems] = useState(200);
  const [fileContent, setFileContent] = useState<File | null>(null);
  const [importName, setImportName] = useState("");
  const [importType, setImportType] = useState<BenchmarkType>("custom");
  const [importMetric, setImportMetric] = useState("accuracy");
  const [importTags, setImportTags] = useState("");

  // ── Create state ─────────────────────────────────────────────────────────
  const [createName, setCreateName] = useState("");
  const [createDescription, setCreateDescription] = useState("");
  const [createType, setCreateType] = useState<BenchmarkType>("custom");
  const [createMetric, setCreateMetric] = useState("accuracy");
  const [manualItems, setManualItems] = useState<ManualItem[]>([{ prompt: "", expected: "" }]);
  const [jsonPaste, setJsonPaste] = useState("");
  const [inputMode, setInputMode] = useState<"manual" | "json">("manual");
  const [riskThreshold, setRiskThreshold] = useState<string>("");
  const [createTags, setCreateTags] = useState("");

  // ── Shared submit state ───────────────────────────────────────────────────
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  // ── Helpers ──────────────────────────────────────────────────────────────
  const totalSteps = mode === "choose" ? 1 : 4;
  const progress = Math.round(((step - 1) / (totalSteps - 1)) * 100);

  const canAdvance = (): boolean => {
    if (step === 1) return mode !== "choose";
    if (mode === "import") {
      if (step === 2) return true; // source always selected
      if (step === 3) {
        if (importSource === "catalog") return !!selectedCatalogKey;
        if (importSource === "huggingface") return !!hfRepoId.trim();
        if (importSource === "file") return !!fileContent;
      }
      if (step === 4) return !!importName.trim();
    }
    if (mode === "create") {
      if (step === 2) return !!createName.trim();
      if (step === 3) {
        if (inputMode === "manual") return manualItems.some(i => i.prompt.trim());
        return !!jsonPaste.trim();
      }
      if (step === 4) return true;
    }
    return true;
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null;
    setFileContent(f);
    if (f && !importName) setImportName(f.name.replace(/\.[^.]+$/, ""));
  };

  const handleSubmitImport = async () => {
    setSubmitting(true);
    setError(null);
    try {
      if (importSource === "catalog" && selectedCatalogKey) {
        const res = await fetch(`${API_BASE}/catalog/benchmarks`);
        const catalog: CatalogBenchmark[] = await res.json();
        const b = catalog.find(x => x.key === selectedCatalogKey);
        if (!b) throw new Error("Benchmark not found in catalog");
        await benchmarksApi.create({
          name: importName || b.name,
          type: importType as any,
          description: b.description,
          tags: importTags ? importTags.split(",").map(t => t.trim()).filter(Boolean) : b.tags,
          metric: importMetric || b.metric,
          num_samples: b.num_samples,
          config: {},
        });
      } else if (importSource === "huggingface") {
        const res = await fetch(`${API_BASE}/benchmarks/import-huggingface`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            repo_id: hfRepoId,
            split: hfSplit,
            subset: hfSubset || undefined,
            max_items: hfMaxItems,
            name_override: importName || undefined,
          }),
        });
        if (!res.ok) { const e = await res.json(); throw new Error(e.detail ?? "Import failed"); }
      } else if (importSource === "file" && fileContent) {
        const b = await benchmarksApi.create({
          name: importName,
          type: importType as any,
          description: "",
          tags: importTags ? importTags.split(",").map(t => t.trim()).filter(Boolean) : [],
          metric: importMetric,
          num_samples: null,
          config: {},
        });
        await benchmarksApi.uploadDataset(b.id, fileContent);
      }
      setDone(true);
      setTimeout(() => { onCreated(); }, 1200);
    } catch (e: any) {
      setError(String(e.message ?? e));
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmitCreate = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const tags = createTags.split(",").map(t => t.trim()).filter(Boolean);
      const b = await benchmarksApi.create({
        name: createName,
        type: createType as any,
        description: createDescription,
        tags,
        metric: createMetric,
        num_samples: null,
        config: {},
        risk_threshold: riskThreshold ? parseFloat(riskThreshold) : undefined,
      });

      // Build dataset file from items
      let items: Record<string, string>[] = [];
      if (inputMode === "json") {
        try { items = JSON.parse(jsonPaste); } catch {}
      } else {
        items = manualItems.filter(i => i.prompt.trim()).map(i => ({ prompt: i.prompt, expected: i.expected }));
      }
      if (items.length > 0) {
        const blob = new Blob([JSON.stringify(items, null, 2)], { type: "application/json" });
        const file = new File([blob], `${createName.replace(/\s+/g, "_").toLowerCase()}.json`, { type: "application/json" });
        await benchmarksApi.uploadDataset(b.id, file);
      }
      setDone(true);
      setTimeout(() => { onCreated(); }, 1200);
    } catch (e: any) {
      setError(String(e.message ?? e));
    } finally {
      setSubmitting(false);
    }
  };

  const handleNext = () => {
    if (step === 1) {
      if (mode === "import" || mode === "create") setStep(2);
      return;
    }
    if (step < 4) { setStep(s => s + 1); return; }
    // step === 4 → submit
    if (mode === "import") handleSubmitImport();
    if (mode === "create") handleSubmitCreate();
  };

  const handleBack = () => {
    if (step > 1) { setStep(s => s - 1); } else { onClose(); }
  };

  // ─────────────────────────────────────────────────────────────────────────
  // Render helpers
  // ─────────────────────────────────────────────────────────────────────────

  const renderStep1 = () => (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-slate-500 mb-2">
        What would you like to do?
      </p>
      <div className="grid grid-cols-2 gap-4">
        <button
          onClick={() => setMode("create")}
          className={`flex flex-col items-center gap-3 p-6 rounded-2xl border-2 transition-all ${
            mode === "create" ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 hover:border-slate-400 text-slate-700"
          }`}
        >
          <Plus size={28} className={mode === "create" ? "text-white" : "text-slate-400"} />
          <div className="text-center">
            <div className="font-semibold mb-1">Créer de zéro</div>
            <p className={`text-xs ${mode === "create" ? "opacity-70" : "text-slate-500"}`}>
              Définissez les métadonnées et saisissez les items manuellement ou en JSON.
            </p>
          </div>
        </button>
        <button
          onClick={() => setMode("import")}
          className={`flex flex-col items-center gap-3 p-6 rounded-2xl border-2 transition-all ${
            mode === "import" ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 hover:border-slate-400 text-slate-700"
          }`}
        >
          <Database size={28} className={mode === "import" ? "text-white" : "text-slate-400"} />
          <div className="text-center">
            <div className="font-semibold mb-1">Importer depuis une source</div>
            <p className={`text-xs ${mode === "import" ? "opacity-70" : "text-slate-500"}`}>
              Catalogue INESIA, HuggingFace, ou fichier local JSON/CSV.
            </p>
          </div>
        </button>
      </div>
    </div>
  );

  const renderImportStep2 = () => (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-slate-500 mb-1">Choisissez la source d'import :</p>
      {(
        [
          { key: "catalog", icon: "📋", label: "Catalogue INESIA", desc: "Benchmarks académiques et sécurité INESIA" },
          { key: "huggingface", icon: "🤗", label: "HuggingFace", desc: "Importez n'importe quel dataset public" },
          { key: "file", icon: "📁", label: "Fichier local", desc: "JSON, JSONL ou CSV depuis votre machine" },
        ] as { key: ImportSource; icon: string; label: string; desc: string }[]
      ).map(opt => (
        <button
          key={opt.key}
          onClick={() => setImportSource(opt.key)}
          className={`flex items-center gap-4 p-4 rounded-xl border-2 text-left transition-all ${
            importSource === opt.key ? "border-slate-900 bg-slate-50" : "border-slate-200 hover:border-slate-300"
          }`}
        >
          <span className="text-2xl">{opt.icon}</span>
          <div>
            <div className="font-medium text-slate-900 text-sm">{opt.label}</div>
            <p className="text-xs text-slate-500">{opt.desc}</p>
          </div>
          {importSource === opt.key && <CheckCircle size={16} className="ml-auto text-slate-900 shrink-0" />}
        </button>
      ))}
    </div>
  );

  const renderImportStep3 = () => {
    if (importSource === "catalog") {
      return <CatalogBrowser selected={selectedCatalogKey} onSelect={setSelectedCatalogKey} />;
    }
    if (importSource === "huggingface") {
      return (
        <HFBrowser
          repoId={hfRepoId} split={hfSplit} subset={hfSubset} maxItems={hfMaxItems}
          onRepoId={setHfRepoId} onSplit={setHfSplit} onSubset={setHfSubset} onMaxItems={setHfMaxItems}
        />
      );
    }
    // file
    return (
      <div className="flex flex-col gap-4">
        <label className="flex flex-col items-center justify-center gap-3 p-8 border-2 border-dashed border-slate-300 rounded-2xl cursor-pointer hover:border-slate-400 hover:bg-slate-50 transition-colors">
          <Upload size={24} className="text-slate-400" />
          <div className="text-center">
            <p className="text-sm font-medium text-slate-700">Cliquez ou glissez un fichier</p>
            <p className="text-xs text-slate-400 mt-0.5">JSON, JSONL ou CSV</p>
          </div>
          <input type="file" accept=".json,.jsonl,.csv" className="hidden" onChange={handleFileChange} />
        </label>
        {fileContent && (
          <div className="flex items-center gap-3 p-3 bg-green-50 border border-green-200 rounded-xl text-sm text-green-700">
            <CheckCircle size={16} />
            <span className="font-medium">{fileContent.name}</span>
            <span className="text-xs text-green-500 ml-auto">{(fileContent.size / 1024).toFixed(1)} KB</span>
          </div>
        )}
      </div>
    );
  };

  const renderImportStep4 = () => (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-slate-500">Confirmez les métadonnées du benchmark :</p>
      <div className="grid grid-cols-2 gap-3">
        <div className="col-span-2">
          <label className="text-xs font-medium text-slate-600 mb-1 block">Nom *</label>
          <input required value={importName} onChange={e => setImportName(e.target.value)}
            placeholder="Nom du benchmark"
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
        </div>
        <div>
          <label className="text-xs font-medium text-slate-600 mb-1 block">Type</label>
          <select value={importType} onChange={e => setImportType(e.target.value as BenchmarkType)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm">
            <option value="custom">Custom</option>
            <option value="academic">Academic</option>
            <option value="safety">Safety</option>
            <option value="coding">Coding</option>
          </select>
        </div>
        <div>
          <label className="text-xs font-medium text-slate-600 mb-1 block">Metric</label>
          <input value={importMetric} onChange={e => setImportMetric(e.target.value)}
            placeholder="accuracy"
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
        </div>
        <div className="col-span-2">
          <label className="text-xs font-medium text-slate-600 mb-1 block">Tags (séparés par virgules)</label>
          <input value={importTags} onChange={e => setImportTags(e.target.value)}
            placeholder="reasoning, academic, french…"
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
        </div>
      </div>
      <div className="bg-slate-50 rounded-xl p-3 text-xs text-slate-500">
        <strong>Source :</strong>{" "}
        {importSource === "catalog" && `INESIA Catalog — ${selectedCatalogKey}`}
        {importSource === "huggingface" && `HuggingFace — ${hfRepoId} (split: ${hfSplit}${hfSubset ? `, subset: ${hfSubset}` : ""})`}
        {importSource === "file" && `Fichier local — ${fileContent?.name}`}
      </div>
    </div>
  );

  const renderCreateStep2 = () => (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-slate-500">Métadonnées du benchmark :</p>
      <div className="grid grid-cols-2 gap-3">
        <div className="col-span-2">
          <label className="text-xs font-medium text-slate-600 mb-1 block">Nom *</label>
          <input required value={createName} onChange={e => setCreateName(e.target.value)}
            placeholder="Mon benchmark custom"
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
        </div>
        <div className="col-span-2">
          <label className="text-xs font-medium text-slate-600 mb-1 block">Description</label>
          <textarea value={createDescription} onChange={e => setCreateDescription(e.target.value)}
            rows={2} placeholder="Ce benchmark évalue…"
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-slate-900" />
        </div>
        <div>
          <label className="text-xs font-medium text-slate-600 mb-1 block">Type</label>
          <select value={createType} onChange={e => setCreateType(e.target.value as BenchmarkType)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm">
            <option value="custom">Custom</option>
            <option value="academic">Academic</option>
            <option value="safety">Safety</option>
            <option value="coding">Coding</option>
          </select>
        </div>
        <div>
          <label className="text-xs font-medium text-slate-600 mb-1 block">Metric</label>
          <input value={createMetric} onChange={e => setCreateMetric(e.target.value)}
            placeholder="accuracy"
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
        </div>
      </div>
    </div>
  );

  const renderCreateStep3 = () => (
    <div className="flex flex-col gap-3">
      <div className="flex gap-2">
        <button onClick={() => setInputMode("manual")}
          className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${inputMode === "manual" ? "bg-slate-900 text-white border-slate-900" : "border-slate-200 text-slate-600 hover:bg-slate-50"}`}>
          Saisie manuelle
        </button>
        <button onClick={() => setInputMode("json")}
          className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${inputMode === "json" ? "bg-slate-900 text-white border-slate-900" : "border-slate-200 text-slate-600 hover:bg-slate-50"}`}>
          Coller du JSON
        </button>
      </div>

      {inputMode === "manual" ? (
        <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
          {manualItems.map((item, idx) => (
            <div key={idx} className="border border-slate-200 rounded-xl p-3 bg-slate-50">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium text-slate-500">Item {idx + 1}</span>
                {manualItems.length > 1 && (
                  <button onClick={() => setManualItems(prev => prev.filter((_, i) => i !== idx))}
                    className="text-slate-400 hover:text-red-500">
                    <Trash2 size={12} />
                  </button>
                )}
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-[10px] font-medium text-slate-400 mb-0.5 block">Prompt</label>
                  <textarea value={item.prompt}
                    onChange={e => setManualItems(prev => prev.map((x, i) => i === idx ? { ...x, prompt: e.target.value } : x))}
                    rows={2} placeholder="Question / instruction…"
                    className="w-full border border-slate-200 rounded-lg px-2 py-1 text-xs resize-none bg-white focus:outline-none focus:ring-1 focus:ring-slate-300" />
                </div>
                <div>
                  <label className="text-[10px] font-medium text-slate-400 mb-0.5 block">Réponse attendue</label>
                  <textarea value={item.expected}
                    onChange={e => setManualItems(prev => prev.map((x, i) => i === idx ? { ...x, expected: e.target.value } : x))}
                    rows={2} placeholder="Réponse correcte…"
                    className="w-full border border-slate-200 rounded-lg px-2 py-1 text-xs resize-none bg-white focus:outline-none focus:ring-1 focus:ring-slate-300" />
                </div>
              </div>
            </div>
          ))}
          <button onClick={() => setManualItems(prev => [...prev, { prompt: "", expected: "" }])}
            className="w-full flex items-center justify-center gap-1.5 text-xs py-2 border border-dashed border-slate-300 rounded-xl text-slate-500 hover:border-slate-400 hover:bg-slate-50 transition-colors">
            <Plus size={12} /> Ajouter un item
          </button>
        </div>
      ) : (
        <div>
          <p className="text-xs text-slate-400 mb-2">
            Format attendu : <code className="bg-slate-100 px-1 rounded">{"[{\"prompt\": \"...\", \"expected\": \"...\"}]"}</code>
          </p>
          <textarea
            value={jsonPaste}
            onChange={e => setJsonPaste(e.target.value)}
            rows={10}
            placeholder={'[\n  {"prompt": "Quelle est la capitale de la France ?", "expected": "Paris"},\n  ...\n]'}
            className="w-full border border-slate-200 rounded-xl px-3 py-2 text-xs font-mono resize-none focus:outline-none focus:ring-2 focus:ring-slate-900"
          />
          {jsonPaste && (() => {
            try { const d = JSON.parse(jsonPaste); return <p className="text-xs text-green-600 mt-1">✓ {Array.isArray(d) ? d.length : "?"} items valides</p>; }
            catch { return <p className="text-xs text-red-500 mt-1">JSON invalide</p>; }
          })()}
        </div>
      )}
    </div>
  );

  const renderCreateStep4 = () => (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-slate-500">Seuils et classification (optionnels) :</p>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs font-medium text-slate-600 mb-1 block">Risk threshold (0–1)</label>
          <input type="number" step="0.01" min="0" max="1"
            value={riskThreshold} onChange={e => setRiskThreshold(e.target.value)}
            placeholder="e.g. 0.85 (leave blank = none)"
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
          <p className="text-[10px] text-slate-400 mt-0.5">Un seuil active la détection frontier (bloquant).</p>
        </div>
        <div>
          <label className="text-xs font-medium text-slate-600 mb-1 block">Tags (séparés par virgules)</label>
          <input value={createTags} onChange={e => setCreateTags(e.target.value)}
            placeholder="custom, safety, french…"
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
        </div>
      </div>
      {/* Summary */}
      <div className="bg-slate-50 rounded-xl p-4 text-xs space-y-1 text-slate-600">
        <div><span className="font-semibold text-slate-800">Nom :</span> {createName}</div>
        <div><span className="font-semibold text-slate-800">Type :</span> {createType} · metric: {createMetric}</div>
        {createDescription && <div><span className="font-semibold text-slate-800">Description :</span> {createDescription}</div>}
        <div>
          <span className="font-semibold text-slate-800">Items :</span>{" "}
          {inputMode === "manual"
            ? `${manualItems.filter(i => i.prompt.trim()).length} items manuels`
            : (() => { try { return `${JSON.parse(jsonPaste).length} items JSON`; } catch { return "JSON (à valider)"; } })()}
        </div>
        {riskThreshold && <div><span className="font-semibold text-slate-800">Risk threshold :</span> {(parseFloat(riskThreshold) * 100).toFixed(0)}%</div>}
      </div>
    </div>
  );

  const stepTitle = (() => {
    if (step === 1) return "Choisir le mode";
    if (mode === "import") {
      const s = ["", "Choisir le mode", "Source d'import", "Configurer la source", "Confirmer les métadonnées"];
      return s[step] ?? "";
    }
    const s = ["", "Choisir le mode", "Métadonnées", "Items du dataset", "Thresholds & Tags"];
    return s[step] ?? "";
  })();

  const submitLabel = mode === "import" ? "Importer" : "Créer";

  // ─────────────────────────────────────────────────────────────────────────
  // Done state
  // ─────────────────────────────────────────────────────────────────────────
  if (done) {
    return (
      <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl w-full max-w-md p-10 flex flex-col items-center gap-4 shadow-2xl">
          <CheckCircle size={48} className="text-green-500" />
          <h3 className="text-lg font-semibold text-slate-900">
            {mode === "import" ? "Benchmark importé !" : "Benchmark créé !"}
          </h3>
          <p className="text-sm text-slate-500 text-center">La bibliothèque va se rafraîchir.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl w-full max-w-2xl flex flex-col shadow-2xl max-h-[90vh]">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div>
            <h2 className="font-semibold text-slate-900">
              {mode === "choose" ? "Nouveau benchmark" : mode === "import" ? "Importer un benchmark" : "Créer un benchmark"}
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Étape {step} / {totalSteps} — {stepTitle}
            </p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-lg"><X size={16} /></button>
        </div>

        {/* Progress bar */}
        {mode !== "choose" && (
          <div className="h-1 bg-slate-100">
            <div
              className="h-full bg-slate-900 transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
        )}

        {/* Step indicator */}
        {mode !== "choose" && (
          <div className="px-6 py-3 border-b border-slate-100 flex gap-2 items-center">
            {[1, 2, 3, 4].map(s => (
              <div key={s} className={`flex items-center gap-1.5 text-xs ${s === step ? "text-slate-900 font-semibold" : s < step ? "text-slate-400" : "text-slate-300"}`}>
                <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ${
                  s < step ? "bg-green-100 text-green-600" : s === step ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-400"
                }`}>
                  {s < step ? "✓" : s}
                </span>
                {s < 4 && <span className="w-6 h-px bg-slate-200" />}
              </div>
            ))}
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-6">
          {step === 1 && renderStep1()}
          {mode === "import" && step === 2 && renderImportStep2()}
          {mode === "import" && step === 3 && renderImportStep3()}
          {mode === "import" && step === 4 && renderImportStep4()}
          {mode === "create" && step === 2 && renderCreateStep2()}
          {mode === "create" && step === 3 && renderCreateStep3()}
          {mode === "create" && step === 4 && renderCreateStep4()}
        </div>

        {/* Error */}
        {error && (
          <div className="mx-6 mb-3 px-4 py-2.5 bg-red-50 border border-red-200 rounded-xl text-sm text-red-600">
            {error}
          </div>
        )}

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-100 flex items-center justify-between">
          <button onClick={handleBack}
            className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 transition-colors">
            <ChevronLeft size={16} />
            {step === 1 ? "Annuler" : "Retour"}
          </button>

          <button
            onClick={handleNext}
            disabled={!canAdvance() || submitting}
            className="flex items-center gap-2 bg-slate-900 text-white px-5 py-2 rounded-xl text-sm font-medium hover:bg-slate-700 transition-colors disabled:opacity-40"
          >
            {submitting ? <Spinner size={14} /> : null}
            {step < 4 ? (
              <><span>{step === 1 ? "Commencer" : "Suivant"}</span><ChevronRight size={16} /></>
            ) : (
              <span>{submitting ? "En cours…" : submitLabel}</span>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
