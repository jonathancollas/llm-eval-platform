/**
 * OmniBar — server contracts as typed functions.
 */
import { API_BASE, API_KEY } from "@/lib/config";
import type {
  IntentResponse,
  ExecuteRequest,
  ExecuteResponse,
  TypeaheadResponse,
} from "./types";

const INTENT_TIMEOUT_MS = 3000;
const TYPEAHEAD_TIMEOUT_MS = 1500;

function withTimeout(ms: number): AbortSignal {
  const c = new AbortController();
  setTimeout(() => c.abort(), ms);
  return c.signal;
}

export function buildHeaders(extra?: HeadersInit): Headers {
  const h = new Headers(extra);
  if (API_KEY) h.set("X-API-Key", API_KEY);
  return h;
}

/**
 * Join a backend path onto API_BASE.
 *
 * Search /execute returns paths like "/api/campaigns/" (FastAPI's public
 * prefix). API_BASE already includes "/api" (e.g. http://localhost:8000/api),
 * and a raw fetch("/api/campaigns/") hits the Next.js origin — not the
 * backend. Strip a leading "/api" so the POST lands on the API server.
 */
export function resolveApiEndpoint(path: string, apiBase: string = API_BASE): string {
  const raw = (path || "").trim();
  if (!raw) return apiBase.replace(/\/+$/, "");
  if (/^https?:\/\//i.test(raw)) return raw;
  const base = apiBase.replace(/\/+$/, "");
  let suffix = raw.startsWith("/") ? raw : `/${raw}`;
  if (suffix === "/api" || suffix.startsWith("/api/")) {
    suffix = suffix.slice(4) || "/";
  }
  if (!suffix.startsWith("/")) suffix = `/${suffix}`;
  return `${base}${suffix}`;
}

/**
 * Fetch typeahead suggestions. Called on every debounced keystroke.
 * Never throws — returns an empty response on error.
 */
export async function fetchTypeahead(
  query: string,
  limit = 5
): Promise<TypeaheadResponse> {
  const url = `${API_BASE}/search/typeahead?q=${encodeURIComponent(query)}&limit=${limit}`;
  try {
    const res = await fetch(url, {
      headers: buildHeaders(),
      signal: withTimeout(TYPEAHEAD_TIMEOUT_MS),
    });
    if (!res.ok) return { query, groups: [], latency_ms: 0 };
    return (await res.json()) as TypeaheadResponse;
  } catch {
    return { query, groups: [], latency_ms: 0 };
  }
}

/**
 * Classify a query. Returns IntentResponse with a discriminated payload.
 */
export async function classifyIntent(query: string): Promise<IntentResponse> {
  const res = await fetch(`${API_BASE}/search/intent`, {
    method: "POST",
    headers: buildHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ query }),
    signal: withTimeout(INTENT_TIMEOUT_MS),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `intent classifier error ${res.status}`);
  }
  return (await res.json()) as IntentResponse;
}

/**
 * Classify + build a submit body. Used when the user hits ⏎ and we need the
 * exact payload to POST (LAUNCH -> /campaigns, ATTACK -> /redbox/attack).
 */
export async function executeIntent(
  req: ExecuteRequest
): Promise<ExecuteResponse> {
  const res = await fetch(`${API_BASE}/search/execute`, {
    method: "POST",
    headers: buildHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(req),
    signal: withTimeout(INTENT_TIMEOUT_MS),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `execute error ${res.status}`);
  }
  return (await res.json()) as ExecuteResponse;
}
