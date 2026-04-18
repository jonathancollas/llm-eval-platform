"use client";
import { useEffect, useState, useCallback } from "react";
import { API_BASE } from "@/lib/config";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/Badge";
import { Spinner } from "@/components/Spinner";
import { Search, Filter, X, ChevronDown, ChevronRight, Database, Shield,
         Zap, BookOpen, Bot, Lock, FlaskConical } from "lucide-react";

// ── Types ──────────────────────────────────────────────────────────────────────

interface TaskEntry {
  canonical_id: string;
  name: string;
  description: string;
  domain: string;
  capability_tags: string[];
  difficulty: string;
  benchmark_name: string;
  namespace: string;
  source_url: string;
  paper_url: string;
  year: number | null;
  license: string;
  provenance: string;
  contamination_risk: string;
  known_contamination_notes: string;
  required_environment: string;
  dependencies: string[];
  created_at: string;
  updated_at: string;
}

interface RegistryStats {
  total: number;
  by_domain: Record<string, number>;
  by_difficulty: Record<string, number>;
  by_namespace: Record<string, number>;
  top_capabilities: [string, number][];
}

// ── Constants ─────────────────────────────────────────────────────────────────

const DIFFICULTY_COLORS: Record<string, string> = {
  easy:   "bg-green-100 text-green-700",
  medium: "bg-yellow-100 text-yellow-800",
  hard:   "bg-orange-100 text-orange-700",
  expert: "bg-red-100 text-red-700",
};

const CONTAMINATION_COLORS: Record<string, string> = {
  low:      "bg-green-50 text-green-700",
  medium:   "bg-yellow-50 text-yellow-700",
  high:     "bg-orange-50 text-orange-700",
  critical: "bg-red-50 text-red-700",
};

const NAMESPACE_COLORS: Record<string, string> = {
  public:    "bg-blue-100 text-blue-700",
  inesia:    "bg-purple-100 text-purple-700",
  community: "bg-teal-100 text-teal-700",
};

const DOMAIN_ICONS: Record<string, React.ElementType> = {
  cybersecurity:        Shield,
  reasoning:            Zap,
  knowledge:            BookOpen,
  safety:               Lock,
  agentic:              Bot,
  instruction_following: FlaskConical,
  multimodal:           Database,
};

const ENV_COLORS: Record<string, string> = {
  none:    "text-slate-400",
  sandbox: "text-amber-600",
  docker:  "text-blue-600",
  network: "text-red-600",
};

const DOMAINS = [
  "cybersecurity","reasoning","knowledge","safety","agentic",
  "instruction_following","multimodal",
];
const DIFFICULTIES = ["easy","medium","hard","expert"];
const NAMESPACES = ["public","inesia","community"];

// ── Task card ─────────────────────────────────────────────────────────────────

function TaskCard({ task, onClick }: { task: TaskEntry; onClick: () => void }) {
  const DomainIcon = DOMAIN_ICONS[task.domain] ?? Database;
  return (
    <button
      onClick={onClick}
      className="w-full text-left bg-white rounded-xl border border-slate-200 p-4 hover:border-slate-400 hover:shadow-sm transition-all"
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5 p-2 rounded-lg bg-slate-100 text-slate-600 shrink-0">
          <DomainIcon size={14} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="font-medium text-slate-900 text-sm">{task.name}</span>
            <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${DIFFICULTY_COLORS[task.difficulty] ?? "bg-slate-100 text-slate-500"}`}>
              {task.difficulty}
            </span>
            <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${NAMESPACE_COLORS[task.namespace] ?? "bg-slate-100 text-slate-500"}`}>
              {task.namespace}
            </span>
          </div>
          <p className="text-xs text-slate-500 line-clamp-2 mb-2">{task.description}</p>
          <div className="flex items-center gap-1 flex-wrap">
            <span className="text-xs text-slate-400 font-mono">{task.canonical_id}</span>
          </div>
        </div>
        <ChevronRight size={14} className="text-slate-300 shrink-0 mt-1" />
      </div>

      {/* Capability tags */}
      {task.capability_tags.length > 0 && (
        <div className="flex gap-1 flex-wrap mt-3 pl-11">
          {task.capability_tags.slice(0, 5).map((cap) => (
            <span key={cap} className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">
              {cap}
            </span>
          ))}
        </div>
      )}
    </button>
  );
}

// ── Detail drawer ─────────────────────────────────────────────────────────────

function TaskDetailDrawer({ task, onClose }: { task: TaskEntry; onClose: () => void }) {
  const DomainIcon = DOMAIN_ICONS[task.domain] ?? Database;
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={onClose}>
      <div
        className="w-full max-w-lg h-full bg-white shadow-2xl overflow-y-auto p-6 flex flex-col gap-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-slate-100 text-slate-700">
              <DomainIcon size={16} />
            </div>
            <h2 className="font-semibold text-slate-900">{task.name}</h2>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-lg text-slate-500">
            <X size={16} />
          </button>
        </div>

        {/* Canonical ID */}
        <div className="bg-slate-50 rounded-lg px-3 py-2 font-mono text-xs text-slate-600 break-all">
          {task.canonical_id}
        </div>

        {/* Badges row */}
        <div className="flex gap-2 flex-wrap">
          <span className={`text-xs px-2 py-1 rounded-full font-medium ${DIFFICULTY_COLORS[task.difficulty] ?? ""}`}>
            {task.difficulty}
          </span>
          <span className={`text-xs px-2 py-1 rounded-full font-medium ${NAMESPACE_COLORS[task.namespace] ?? ""}`}>
            {task.namespace}
          </span>
          <span className={`text-xs px-2 py-1 rounded-full font-medium ${CONTAMINATION_COLORS[task.contamination_risk] ?? ""}`}>
            contamination: {task.contamination_risk}
          </span>
          <span className={`text-xs px-2 py-1 rounded-full font-medium bg-slate-100 ${ENV_COLORS[task.required_environment] ?? "text-slate-500"}`}>
            env: {task.required_environment}
          </span>
        </div>

        {/* Description */}
        <div>
          <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Description</h3>
          <p className="text-sm text-slate-700">{task.description || "—"}</p>
        </div>

        {/* Domain / Benchmark */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Domain</h3>
            <p className="text-sm text-slate-800">{task.domain}</p>
          </div>
          <div>
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Benchmark</h3>
            <p className="text-sm text-slate-800">{task.benchmark_name || "—"}</p>
          </div>
        </div>

        {/* Capability tags */}
        {task.capability_tags.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Capability Tags</h3>
            <div className="flex gap-1 flex-wrap">
              {task.capability_tags.map((cap) => (
                <span key={cap} className="text-xs bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded-full">
                  {cap}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* License / Provenance */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">License</h3>
            <p className="text-sm text-slate-800">{task.license || "unknown"}</p>
          </div>
          {task.year && (
            <div>
              <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Year</h3>
              <p className="text-sm text-slate-800">{task.year}</p>
            </div>
          )}
        </div>

        {/* Contamination notes */}
        {task.known_contamination_notes && (
          <div>
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">
              Contamination Notes
            </h3>
            <p className="text-sm text-amber-700 bg-amber-50 px-3 py-2 rounded-lg">
              {task.known_contamination_notes}
            </p>
          </div>
        )}

        {/* Dependencies */}
        {task.dependencies.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Dependencies</h3>
            <div className="flex gap-1 flex-wrap">
              {task.dependencies.map((dep) => (
                <span key={dep} className="text-xs bg-slate-100 text-slate-700 px-2 py-0.5 rounded font-mono">
                  {dep}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Links */}
        {(task.paper_url || task.source_url) && (
          <div className="flex gap-3">
            {task.paper_url && (
              <a href={task.paper_url} target="_blank" rel="noopener noreferrer"
                className="text-xs text-blue-600 hover:underline">
                📄 Paper
              </a>
            )}
            {task.source_url && (
              <a href={task.source_url} target="_blank" rel="noopener noreferrer"
                className="text-xs text-blue-600 hover:underline">
                🔗 Source
              </a>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Stats bar ─────────────────────────────────────────────────────────────────

function StatsBar({ stats }: { stats: RegistryStats }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
      <div className="bg-white rounded-xl border border-slate-200 px-4 py-3">
        <p className="text-xs text-slate-500">Total Tasks</p>
        <p className="text-2xl font-bold text-slate-900">{stats.total}</p>
      </div>
      <div className="bg-white rounded-xl border border-slate-200 px-4 py-3">
        <p className="text-xs text-slate-500">Domains</p>
        <p className="text-2xl font-bold text-slate-900">{Object.keys(stats.by_domain).length}</p>
      </div>
      <div className="bg-white rounded-xl border border-slate-200 px-4 py-3">
        <p className="text-xs text-slate-500">INESIA Tasks</p>
        <p className="text-2xl font-bold text-purple-700">{stats.by_namespace["inesia"] ?? 0}</p>
      </div>
      <div className="bg-white rounded-xl border border-slate-200 px-4 py-3">
        <p className="text-xs text-slate-500">Expert-level</p>
        <p className="text-2xl font-bold text-red-700">{stats.by_difficulty["expert"] ?? 0}</p>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function TasksPage() {
  const [tasks, setTasks] = useState<TaskEntry[]>([]);
  const [stats, setStats] = useState<RegistryStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [filterDomain, setFilterDomain] = useState("");
  const [filterDifficulty, setFilterDifficulty] = useState("");
  const [filterNamespace, setFilterNamespace] = useState("");
  const [showFilters, setShowFilters] = useState(false);

  const [selected, setSelected] = useState<TaskEntry | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (search) params.set("search", search);
    if (filterDomain) params.set("domain", filterDomain);
    if (filterDifficulty) params.set("difficulty", filterDifficulty);
    if (filterNamespace) params.set("namespace", filterNamespace);
    params.set("limit", "200");

    fetch(`${API_BASE}/tasks?${params}`)
      .then((r) => r.json())
      .then((d) => { setTasks(d); setError(null); })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [search, filterDomain, filterDifficulty, filterNamespace]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    fetch(`${API_BASE}/tasks/stats`)
      .then((r) => r.json())
      .then(setStats)
      .catch(() => {});
  }, []);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setSearch(searchInput);
  };

  const clearFilters = () => {
    setSearch("");
    setSearchInput("");
    setFilterDomain("");
    setFilterDifficulty("");
    setFilterNamespace("");
  };

  const hasFilters = search || filterDomain || filterDifficulty || filterNamespace;

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <PageHeader
        title="Task Registry"
        description="Canonical, queryable registry of evaluation tasks — browse by capability, domain, and difficulty."
      />

      {stats && <StatsBar stats={stats} />}

      {/* Search + filter bar */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 mb-4">
        <form onSubmit={handleSearch} className="flex gap-2">
          <div className="relative flex-1">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search tasks by name or description…"
              className="w-full pl-9 pr-4 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-900"
            />
          </div>
          <button type="submit"
            className="px-4 py-2 bg-slate-900 text-white text-sm rounded-lg hover:bg-slate-700">
            Search
          </button>
          <button type="button" onClick={() => setShowFilters(!showFilters)}
            className={`flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg border transition-colors ${
              showFilters ? "bg-slate-900 text-white border-slate-900" : "border-slate-200 text-slate-600 hover:bg-slate-50"
            }`}>
            <Filter size={13} />
            Filters
            <ChevronDown size={12} className={`transition-transform ${showFilters ? "rotate-180" : ""}`} />
          </button>
          {hasFilters && (
            <button type="button" onClick={clearFilters}
              className="flex items-center gap-1 px-3 py-2 text-sm text-slate-500 hover:bg-slate-100 rounded-lg border border-slate-200">
              <X size={13} />
              Clear
            </button>
          )}
        </form>

        {showFilters && (
          <div className="mt-3 pt-3 border-t border-slate-100 grid grid-cols-3 gap-3">
            <div>
              <label className="text-xs font-medium text-slate-500 mb-1 block">Domain</label>
              <select value={filterDomain} onChange={(e) => setFilterDomain(e.target.value)}
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-slate-900">
                <option value="">All domains</option>
                {DOMAINS.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-slate-500 mb-1 block">Difficulty</label>
              <select value={filterDifficulty} onChange={(e) => setFilterDifficulty(e.target.value)}
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-slate-900">
                <option value="">All levels</option>
                {DIFFICULTIES.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-slate-500 mb-1 block">Namespace</label>
              <select value={filterNamespace} onChange={(e) => setFilterNamespace(e.target.value)}
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-slate-900">
                <option value="">All namespaces</option>
                {NAMESPACES.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
          </div>
        )}
      </div>

      {/* Active filter badges */}
      {hasFilters && (
        <div className="flex gap-2 flex-wrap mb-3">
          {search && (
            <span className="flex items-center gap-1 text-xs bg-slate-900 text-white px-2.5 py-1 rounded-full">
              search: {search}
              <button onClick={() => { setSearch(""); setSearchInput(""); }}><X size={10} /></button>
            </span>
          )}
          {filterDomain && (
            <span className="flex items-center gap-1 text-xs bg-indigo-100 text-indigo-700 px-2.5 py-1 rounded-full">
              domain: {filterDomain}
              <button onClick={() => setFilterDomain("")}><X size={10} /></button>
            </span>
          )}
          {filterDifficulty && (
            <span className="flex items-center gap-1 text-xs bg-orange-100 text-orange-700 px-2.5 py-1 rounded-full">
              difficulty: {filterDifficulty}
              <button onClick={() => setFilterDifficulty("")}><X size={10} /></button>
            </span>
          )}
          {filterNamespace && (
            <span className="flex items-center gap-1 text-xs bg-purple-100 text-purple-700 px-2.5 py-1 rounded-full">
              namespace: {filterNamespace}
              <button onClick={() => setFilterNamespace("")}><X size={10} /></button>
            </span>
          )}
        </div>
      )}

      {/* Task list */}
      {loading ? (
        <div className="flex justify-center py-20"><Spinner size={28} /></div>
      ) : error ? (
        <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">{error}</div>
      ) : tasks.length === 0 ? (
        <div className="text-center py-20 text-slate-400">
          <Database size={32} className="mx-auto mb-3 opacity-30" />
          <p>No tasks match the current filters.</p>
        </div>
      ) : (
        <>
          <p className="text-xs text-slate-400 mb-3">{tasks.length} task{tasks.length !== 1 ? "s" : ""}</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {tasks.map((task) => (
              <TaskCard key={task.canonical_id} task={task} onClick={() => setSelected(task)} />
            ))}
          </div>
        </>
      )}

      {/* Detail drawer */}
      {selected && (
        <TaskDetailDrawer task={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
