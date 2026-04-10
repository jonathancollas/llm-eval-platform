import { API_BASE } from "./config";

async function apiFetch<T>(path: string, init?: RequestInit & { timeoutMs?: number }): Promise<T> {
  const { timeoutMs = 30000, ...fetchInit } = init ?? {};
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json", ...fetchInit?.headers },
      signal: controller.signal,
      ...fetchInit,
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
    if (e.name === "AbortError") {
      throw new Error("Request timeout — backend is taking too long. Please retry.");
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Canonical model identity — separates DB primary key from provider identifier.
 * Never compare model.id (dbId) with model.model_id (providerModelId).
 *
 * dbId          — internal DB integer PK, used for foreign keys / relations
 * model_id      — provider string identifier e.g. "openai/gpt-4o", "llama3:8b"
 */
export interface ModelIdentity {
  dbId: number;           // Internal DB primary key
  model_id: string;       // Provider identifier (OpenRouter format, Ollama name, etc.)
}

export type ModelProvider = "ollama" | "openai" | "anthropic" | "mistral" | "groq" | "custom";
export type BenchmarkType = "academic" | "safety" | "coding" | "custom";

// Ollama API
export const ollamaApi = {
  check: () => apiFetch<{ available: boolean; url: string; models: any[]; total: number }>("/sync/ollama"),
  import: () => apiFetch<{ added: number; available: boolean }>("/sync/ollama/import", { method: "POST" }),
  pull: (modelName: string) => apiFetch<{ status: string; model: string }>(`/sync/ollama/pull?model_name=${encodeURIComponent(modelName)}`, { method: "POST", timeoutMs: 300000 }),
  pullAndRegister: (modelName: string) => apiFetch<{ status: string; model_name: string }>("/sync/ollama/pull-and-register", { method: "POST", body: JSON.stringify({ model_name: modelName }), timeoutMs: 300000 }),
};
export type JobStatus = "pending" | "running" | "completed" | "failed" | "cancelled";

export interface LLMModel {
  id: number; name: string; provider: ModelProvider; model_id: string;
  endpoint: string | null; has_api_key: boolean; context_length: number;
  cost_input_per_1k: number; cost_output_per_1k: number; tags: string[];
  notes: string; is_active: boolean;
  supports_vision: boolean; supports_tools: boolean; supports_reasoning: boolean;
  is_free: boolean; max_output_tokens: number; is_moderated: boolean;
  tokenizer: string; instruct_type: string; hugging_face_id: string;
  model_created_at: number; created_at: string; updated_at: string;
}

export interface Benchmark {
  id: number; name: string; type: BenchmarkType; description: string;
  tags: string[]; metric: string; num_samples: number | null;
  config: Record<string, unknown>; is_builtin: boolean;
  risk_threshold: number | null; has_dataset: boolean;
  source: "inesia" | "public" | "community";
  created_at: string;
}

export interface EvalRunSummary {
  id: number; model_id: number; benchmark_id: number; status: JobStatus;
  score: number | null;
  capability_score: number | null;   // Elicited maximum — what model CAN do
  propensity_score: number | null;   // Operational tendency — what model TENDS to do
  metrics: Record<string, unknown>;
  total_cost_usd: number; total_latency_ms: number; num_items: number;
  error_message?: string | null;
}

export interface Campaign {
  id: number; name: string; description: string; model_ids: number[];
  benchmark_ids: number[]; seed: number; max_samples: number | null;
  temperature: number; status: JobStatus; progress: number;
  error_message: string | null;
  current_item_index: number | null;
  current_item_total: number | null;
  current_item_label: string | null;
  created_at: string; started_at: string | null;
  completed_at: string | null; runs: EvalRunSummary[];
}

export interface HeatmapCell { model_name: string; benchmark_name: string; score: number | null; status: string; }
export interface WinRateRow { model_name: string; wins: number; losses: number; ties: number; win_rate: number; }
export interface DashboardData {
  campaign_id: number; campaign_name: string; status: string;
  heatmap: HeatmapCell[]; radar: Record<string, Record<string, number>>;
  win_rates: WinRateRow[]; total_cost_usd: number; avg_latency_ms: number; alerts: string[];
}
export interface Report {
  id: number; campaign_id: number; title: string;
  content_markdown: string; model_used: string; created_at: string;
}

export interface GenomeData {
  models: Record<string, Record<string, number>>;
  ontology: Record<string, { id: string; label: string; color: string; description: string; severity: number }>;
  computed: boolean;
  genome_version?: string;
}

export interface FailedItem {
  id: number; item_index: number; prompt: string; response: string;
  expected: string | null; score: number; latency_ms: number;
  model_name: string; benchmark_name: string; error_type: string;
}
export interface FailedRun {
  run_id: number; model_name: string; benchmark_name: string;
  error_message: string | null; error_type: string;
}
export interface FailedItemsData {
  items: FailedItem[]; total_failed: number; failed_runs: FailedRun[];
}

export const modelsApi = {
  list: () => apiFetch<LLMModel[]>("/models/"),
  get: (id: number) => apiFetch<LLMModel>(`/models/${id}`),
  create: (data: Record<string, unknown>) => apiFetch<LLMModel>("/models/", { method: "POST", body: JSON.stringify(data) }),
  update: (id: number, data: Record<string, unknown>) => apiFetch<LLMModel>(`/models/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  delete: (id: number) => apiFetch<void>(`/models/${id}`, { method: "DELETE" }),
  test: (id: number) => apiFetch<{ ok: boolean; latency_ms: number; response: string; error: string | null }>(`/models/${id}/test`, { method: "POST" }),
};

export const benchmarksApi = {
  list: (type?: BenchmarkType) => apiFetch<Benchmark[]>(`/benchmarks/${type ? `?type=${type}` : ""}`),
  get: (id: number) => apiFetch<Benchmark>(`/benchmarks/${id}`),
  create: (data: Record<string, unknown>) => apiFetch<Benchmark>("/benchmarks/", { method: "POST", body: JSON.stringify(data) }),
  delete: (id: number) => apiFetch<void>(`/benchmarks/${id}`, { method: "DELETE" }),
  uploadDataset: (id: number, file: File) => {
    const form = new FormData(); form.append("file", file);
    return fetch(`${API_BASE}/benchmarks/${id}/upload-dataset`, { method: "POST", body: form }).then(r => r.json()) as Promise<Benchmark>;
  },
};

export const campaignsApi = {
  list: () => apiFetch<Campaign[]>("/campaigns/"),
  get: (id: number) => apiFetch<Campaign>(`/campaigns/${id}`),
  create: (data: Record<string, unknown>) => apiFetch<Campaign>("/campaigns/", { method: "POST", body: JSON.stringify(data) }),
  run: (id: number) => apiFetch<Campaign>(`/campaigns/${id}/run`, { method: "POST" }),
  cancel: (id: number) => apiFetch<Campaign>(`/campaigns/${id}/cancel`, { method: "POST" }),
  delete: (id: number) => apiFetch<void>(`/campaigns/${id}`, { method: "DELETE" }),
};

export const resultsApi = {
  dashboard: (campaignId: number) => apiFetch<DashboardData>(`/results/campaign/${campaignId}/dashboard`),
  runItems: (runId: number, limit = 50, offset = 0) => apiFetch<{ items: unknown[]; total: number; score: number; metrics: Record<string, unknown> }>(`/results/run/${runId}/items?limit=${limit}&offset=${offset}`),
  failedItems: (campaignId: number) => apiFetch<FailedItemsData>(`/results/campaign/${campaignId}/failed-items`),
  insights: (campaignId: number) => apiFetch<any>(`/results/campaign/${campaignId}/insights`),
  contamination: (campaignId: number) => apiFetch<any>(`/results/campaign/${campaignId}/contamination`),
  exportUrl: (campaignId: number) => `${API_BASE}/results/campaign/${campaignId}/export.csv`,
};

export const reportsApi = {
  generate: (campaignId: number, customInstructions = "", ollamaModel = "") =>
    apiFetch<Report>("/reports/generate", {
      method: "POST",
      body: JSON.stringify({ campaign_id: campaignId, custom_instructions: customInstructions, ollama_model: ollamaModel }),
      timeoutMs: 120000,
    }),
  list: (campaignId: number) => apiFetch<Report[]>(`/reports/campaign/${campaignId}`),
  exportUrl: (reportId: number) => `${API_BASE}/reports/${reportId}/export.md`,
  exportHtmlUrl: (reportId: number) => `${API_BASE}/reports/${reportId}/export.html`,
};

export const genomeApi = {
  campaign: (campaignId: number) => apiFetch<GenomeData>(`/genome/campaigns/${campaignId}`),
  compute: (campaignId: number) => apiFetch<{ profiles_created: number }>(`/genome/campaigns/${campaignId}/compute`, { method: "POST" }),
  computeHybrid: (campaignId: number) => apiFetch<{ profiles_created: number; method: string }>(`/genome/campaigns/${campaignId}/compute-hybrid`, { method: "POST", timeoutMs: 120000 }),
  signals: (runId: number) => apiFetch<{ items: any[] }>(`/genome/signals/${runId}`),
  regressionCompare: (baselineId: number, candidateId: number) => apiFetch<any>(`/genome/regression/compare?baseline_id=${baselineId}&candidate_id=${candidateId}`),
  regressionExplain: (baselineId: number, candidateId: number) => apiFetch<any>(`/genome/regression/explain?baseline_id=${baselineId}&candidate_id=${candidateId}`, { method: "POST", timeoutMs: 60000 }),
};

export const judgeApi = {
  evaluate: (campaignId: number, judgeModels: string[], criteria = "correctness", maxItems = 50) =>
    apiFetch<any>("/judge/evaluate", {
      method: "POST",
      body: JSON.stringify({ campaign_id: campaignId, judge_models: judgeModels, criteria, max_items: maxItems }),
      timeoutMs: 300000, // 5 min — many LLM calls
    }),
  agreement: (campaignId: number) => apiFetch<any>(`/judge/agreement/${campaignId}`),
  calibrate: (campaignId: number, oracleLabels: { result_id: number; score: number }[]) =>
    apiFetch<any>("/judge/calibrate", { method: "POST", body: JSON.stringify({ campaign_id: campaignId, oracle_labels: oracleLabels }) }),
  bias: (campaignId: number) => apiFetch<any>(`/judge/bias/${campaignId}`),
  summary: (campaignId: number) => apiFetch<any>(`/judge/summary/${campaignId}`),
};
