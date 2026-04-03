// ── Enums ──────────────────────────────────────────────────────────────────────

export type ModelProvider =
  | "ollama" | "openai" | "anthropic" | "mistral" | "groq" | "custom";

export type BenchmarkType = "academic" | "safety" | "coding" | "custom";

export type JobStatus =
  | "pending" | "running" | "completed" | "failed" | "cancelled";

// ── Models ─────────────────────────────────────────────────────────────────────

export interface LLMModel {
  id: number;
  name: string;
  provider: ModelProvider;
  model_id: string;
  endpoint: string | null;
  has_api_key: boolean;
  context_length: number;
  cost_input_per_1k: number;
  cost_output_per_1k: number;
  tags: string[];
  notes: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ModelCreate {
  name: string;
  provider: ModelProvider;
  model_id: string;
  endpoint?: string;
  api_key?: string;
  context_length?: number;
  cost_input_per_1k?: number;
  cost_output_per_1k?: number;
  tags?: string[];
  notes?: string;
}

export interface ConnectionTestResult {
  ok: boolean;
  latency_ms: number;
  response: string;
  error: string | null;
}

// ── Benchmarks ─────────────────────────────────────────────────────────────────

export interface Benchmark {
  id: number;
  name: string;
  type: BenchmarkType;
  description: string;
  tags: string[];
  metric: string;
  num_samples: number | null;
  config: Record<string, unknown>;
  is_builtin: boolean;
  risk_threshold: number | null;
  has_dataset: boolean;
  created_at: string;
}

// ── Campaigns ──────────────────────────────────────────────────────────────────

export interface EvalRunSummary {
  id: number;
  model_id: number;
  benchmark_id: number;
  status: JobStatus;
  score: number | null;
  metrics: Record<string, unknown>;
  total_cost_usd: number;
  total_latency_ms: number;
  num_items: number;
}

export interface Campaign {
  id: number;
  name: string;
  description: string;
  model_ids: number[];
  benchmark_ids: number[];
  seed: number;
  max_samples: number | null;
  temperature: number;
  status: JobStatus;
  progress: number;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  runs: EvalRunSummary[];
}

export interface CampaignCreate {
  name: string;
  description?: string;
  model_ids: number[];
  benchmark_ids: number[];
  seed?: number;
  max_samples?: number;
  temperature?: number;
}

// ── Dashboard ──────────────────────────────────────────────────────────────────

export interface HeatmapCell {
  model_name: string;
  benchmark_name: string;
  score: number | null;
  status: JobStatus;
}

export interface WinRateRow {
  model_name: string;
  wins: number;
  losses: number;
  ties: number;
  win_rate: number;
}

export interface DashboardData {
  campaign_id: number;
  campaign_name: string;
  status: JobStatus;
  heatmap: HeatmapCell[];
  radar: Record<string, Record<string, number>>;
  win_rates: WinRateRow[];
  total_cost_usd: number;
  avg_latency_ms: number;
  alerts: string[];
}

// ── Reports ────────────────────────────────────────────────────────────────────

export interface Report {
  id: number;
  campaign_id: number;
  title: string;
  content_markdown: string;
  model_used: string;
  created_at: string;
}
