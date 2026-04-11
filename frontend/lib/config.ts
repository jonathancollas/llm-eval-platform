/**
 * EVAL RESEARCH OS — Central configuration
 * Single source of truth for all runtime constants.
 * Never hardcode API_BASE elsewhere — always import from here.
 *
 * Set NEXT_PUBLIC_API_URL in your .env.local or deployment environment.
 * Example: NEXT_PUBLIC_API_URL=http://localhost:8000/api
 */

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

export const APP_NAME = "EVAL RESEARCH OS";
export const APP_TAGLINE = "made with love by INESIA";
export const APP_VERSION = "v0.6.0";

export const OLLAMA_BASE_URL =
  process.env.NEXT_PUBLIC_OLLAMA_URL ?? "http://localhost:11434";

export const SYNC_TTL_MS = 15 * 60 * 1000; // 15 min
