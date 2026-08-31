/**
 * Node test for OmniBar API URL joining.
 * Mirrors frontend/components/OmniBar/api.ts resolveApiEndpoint.
 *
 * Run: node --test frontend/lib/resolveApiEndpoint.test.mjs
 */
import { test } from "node:test";
import assert from "node:assert/strict";

function resolveApiEndpoint(path, apiBase = "http://localhost:8000/api") {
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

test("strips /api prefix from execute submit_endpoint", () => {
  assert.equal(
    resolveApiEndpoint("/api/campaigns/"),
    "http://localhost:8000/api/campaigns/"
  );
  assert.equal(
    resolveApiEndpoint("/api/redbox/attack"),
    "http://localhost:8000/api/redbox/attack"
  );
});

test("joins paths that are already API-relative", () => {
  assert.equal(
    resolveApiEndpoint("/campaigns/"),
    "http://localhost:8000/api/campaigns/"
  );
});

test("passes through absolute URLs", () => {
  assert.equal(
    resolveApiEndpoint("https://eval.example/api/campaigns/"),
    "https://eval.example/api/campaigns/"
  );
});
