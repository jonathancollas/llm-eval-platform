"""
EVAL RESEARCH OS — Unified Inference Adapter Layer

Provides a single abstract interface over all model providers:
  - OpenRouter (OpenAI-compatible)
  - Anthropic API
  - Ollama (local)
  - HuggingFace Inference API
  - vLLM (self-hosted)

All evaluation runners should use InferenceAdapter, never call providers directly.
This decouples the evaluation engine from provider specifics and enables:
  - Local-first execution (Ollama) with cloud fallback
  - Consistent error handling across providers
  - Easy addition of new providers
  - Mock adapters for testing
"""
from inference.adapter import InferenceAdapter, AdapterResult, get_adapter

__all__ = ["InferenceAdapter", "AdapterResult", "get_adapter"]
