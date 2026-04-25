/**
 * OmniBar — wire types.
 *
 * Mirror of backend/eval_engine/search/schema.py. Keep in sync.
 *
 * The key pattern is the discriminated union on `IntentPayload.kind`, which
 * lets TypeScript narrow safely:
 *
 *   if (payload.kind === "launch" && payload.preview) {
 *     // preview is LaunchPreview here
 *   }
 */

export type OmniBarMode = "hero" | "compact" | "overlay";

export type SearchIntent = "navigate" | "ask" | "launch" | "attack" | "unknown";

// ─── Typeahead ──────────────────────────────────────────────────────────────

export type TypeaheadKind =
  | "model" | "benchmark" | "campaign" | "route" | "action" | "incident" | "paper";

export interface TypeaheadResult {
  id: string;
  label: string;
  subtitle: string;
  kind: TypeaheadKind;
  href: string | null;
  action_hint: string | null;
  icon: string;
  score: number;
}

export interface TypeaheadGroup {
  kind: string;
  label: string;
  items: TypeaheadResult[];
}

export interface TypeaheadResponse {
  query: string;
  groups: TypeaheadGroup[];
  latency_ms: number;
}

// ─── Intent payloads (discriminated by `kind`) ─────────────────────────────

export interface NavigatePayload {
  kind: "navigate";
  route: string;
  label: string;
}

export interface AskSource {
  id: string;
  label: string;
  href: string | null;
  snippet: string;
}

export interface AskPayload {
  kind: "ask";
  answer: string;
  sources: AskSource[];
  deterministic: boolean;
}

export type AutonomyLevel = "L1" | "L2" | "L3" | "L4" | "L5";

export interface LaunchSlots {
  model_id: number | null;
  model_name: string | null;
  benchmark_ids: number[];
  benchmark_names: string[];
  max_samples: number;
  autonomy_level: AutonomyLevel;
  temperature: number;
}

export interface LaunchPreview {
  name: string;
  description: string;
  model_ids: number[];
  benchmark_ids: number[];
  max_samples: number;
  temperature: number;
  run_context_json: string;
  estimated_cost_usd: number;
  estimated_time_minutes: number;
  needs_confirmation: string[];
}

export interface LaunchPayload {
  kind: "launch";
  slots: LaunchSlots;
  preview: LaunchPreview | null;
  clarification: string | null;
}

export interface AttackPayload {
  kind: "attack";
  target_model_id: number | null;
  target_model_name: string | null;
  goal: string;
  aggressiveness: number;
  engines: string[];
  autonomy_level: AutonomyLevel;
  requires_role: "evaluator" | "admin";
  clarification: string | null;
}

export type IntentPayload =
  | NavigatePayload
  | AskPayload
  | LaunchPayload
  | AttackPayload;

export interface IntentResponse {
  query: string;
  intent: SearchIntent;
  confidence: number;
  payload: IntentPayload;
  can_auto_execute: boolean;
  latency_ms: number;
}

// ─── Execute ───────────────────────────────────────────────────────────────

export interface ExecuteRequest {
  query: string;
  forced_intent?: SearchIntent;
  role?: "viewer" | "evaluator" | "admin";
}

export interface ExecuteResponse {
  intent_response: IntentResponse;
  submit_body: Record<string, unknown> | null;
  submit_endpoint: string | null;
}
