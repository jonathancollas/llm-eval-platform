# Data Models

## Core

| Model | Table | Key Fields |
|-------|-------|------------|
| `LLMModel` | `llm_models` | provider, model_id, endpoint, api_key_enc, is_free |
| `Benchmark` | `benchmarks` | type, dataset_path, metric, is_builtin |
| `Campaign` | `campaigns` | status, progress, model_ids, benchmark_ids |
| `EvalRun` | `eval_runs` | campaign_id, model_id, benchmark_id, score, status |
| `EvalResult` | `eval_results` | run_id, prompt, response, expected, score |

## Analyzers

| Model | Table | Key Fields |
|-------|-------|------------|
| `FailureProfile` | `failure_profiles` | run_id, genome_json, genome_version |
| `ModelFingerprint` | `model_fingerprints` | model_id, fingerprint_json |
| `RedboxExploit` | `redbox_exploits` | model_id, mutation_type, severity, breached |
| `JudgeEvaluation` | `judge_evaluations` | campaign_id, judge_model, scores_json |
| `AgentTrajectory` | `agent_trajectories` | model_id, steps_json, scores_json |

## Infrastructure

| Model | Table | Key Fields |
|-------|-------|------------|
| `Report` | `reports` | campaign_id, content_markdown |
| `Tenant` | `tenants` | slug, api_key_hash, plan |
| `User` | `users` | tenant_id, email, role |

## Enums

- `ModelProvider`: openai, anthropic, mistral, groq, ollama, custom
- `BenchmarkType`: academic, safety, coding, custom
- `JobStatus`: pending, running, completed, failed, cancelled
