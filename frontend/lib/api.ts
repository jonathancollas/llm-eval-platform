const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "https://llm-eval-backend-kqlh.onrender.com/api";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "API error");
  }
  return res.json() as Promise<T>;
}

export type ModelProvider = "ollama" | "openai" | "anthropic" | "mistral" | "groq" | "custom";
export type BenchmarkType = "academic" | "safety" | "coding" | "custom";
export type JobStatus = "pending" | "running" | "completed" | "failed" | "cancelled";

export interface LLMModel {
  id: number; name: string; provider: ModelProvider; model_id: string;
  endpoint: string | null; has_api_key: boolean; context_length: number;
  cost_input_per_1k: number; cost_output_per_1k: number; tags: string[];
  notes: string; is_active: boolean;
  supports_vision: boolean;
  supports_tools: boolean;
  supports_reasoning: boolean;
  created_at: string; updated_at: string;
}

export interface Benchmark {
  id: number; name: string; type: BenchmarkType; description: string;
  tags: string[]; metric: string; num_samples: number | null;
  config: Record<string, unknown>; is_builtin: boolean;
  risk_threshold: number | null; has_dataset: boolean; created_at: string;
}

export interface EvalRunSummary {
  id: number; model_id: number; benchmark_id: number; status: JobStatus;
  score: number | null; metrics: Record<string, unknown>;
  total_cost_usd: number; total_latency_ms: number; num_items: number;
}

export interface Campaign {
  id: number; name: string; description: string; model_ids: number[];
  benchmark_ids: number[]; seed: number; max_samples: number | null;
  temperature: number; status: JobStatus; progress: number;
  error_message: string | null; created_at: string; started_at: string | null;
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
  exportUrl: (campaignId: number) => `${API_BASE}/results/campaign/${campaignId}/export.csv`,
};

export const reportsApi = {
  generate: (campaignId: number, customInstructions = "") =>
    apiFetch<Report>("/reports/generate", { method: "POST", body: JSON.stringify({ campaign_id: campaignId, custom_instructions: customInstructions }) }),
  list: (campaignId: number) => apiFetch<Report[]>(`/reports/campaign/${campaignId}`),
  exportUrl: (reportId: number) => `${API_BASE}/reports/${reportId}/export.md`,
};
