# API Endpoints

74 endpoints across 15 routers.


## Agents

Agent Evaluation Engine — multi-step trajectory scoring on 6 axes.

| Method | Path | Function | Description |
|--------|------|----------|-------------|
| `POST` | `/trajectories` | `create_trajectory` | Upload an agent trajectory for evaluation. |
| `POST` | `/evaluate` | `evaluate_trajectory` | Score a trajectory on 6 axes. |
| `GET` | `/trajectories` | `list_trajectories` | List agent trajectories. |
| `GET` | `/trajectories/{trajectory_id}` | `get_trajectory` | Get full trajectory with steps. |
| `GET` | `/dashboard` | `agent_dashboard` | Aggregate agent eval metrics across trajectories. |


## Benchmarks

Benchmarks — CRUD + dataset upload + HuggingFace import.

| Method | Path | Function | Description |
|--------|------|----------|-------------|
| `GET` | `/{benchmark_id}/items` | `get_benchmark_items` | Browse dataset items for a benchmark (paginated). |
| `POST` | `/import-huggingface` | `import_huggingface_dataset` | Import a dataset from HuggingFace Hub and create a benchmark. |


## Genome

Failure Genome API — GENOME-3, GENOME-4, GENOME-5

| Method | Path | Function | Description |
|--------|------|----------|-------------|
| `POST` | `/campaigns/{campaign_id}/compute` | `compute_campaign_genome` | Compute and store Failure Genome for all runs in a campaign. |
| `GET` | `/campaigns/{campaign_id}` | `get_campaign_genome` | Get aggregated Failure Genome for all models in a campaign. |
| `GET` | `/models/{model_id}` | `get_model_genome` | Get behavioral fingerprint for a specific model. |
| `GET` | `/models` | `list_model_fingerprints` | List all model fingerprints for comparison. |
| `GET` | `/ontology` | `get_ontology` | Safety Heatmap: capability × risk matrix. |
| `GET` | `/regression/compare` | `compare_campaigns` | REGRESSION-2: Compare two campaigns and identify probable causes. |
| `POST` | `/regression/explain` | `explain_regression` | Generate a natural language causal explanation of the regression. |
| `GET` | `/signals/{run_id}` | `get_run_signals` | Extract and return signals for items in an eval run (debugging/analysis). |
| `POST` | `/campaigns/{campaign_id}/compute-hybrid` | `compute_hybrid_genome` | Compute genome with LLM hybrid classification (GENOME-4). |


## Judge

LLM-as-Judge — Multi-judge ensemble, calibration & bias detection.

| Method | Path | Function | Description |
|--------|------|----------|-------------|
| `POST` | `/evaluate` | `evaluate_with_judges` | Run multi-judge evaluation on campaign results. |
| `GET` | `/agreement/{campaign_id}` | `get_judge_agreement` | Compute inter-judge agreement (Cohen's kappa + Pearson correlation). |
| `POST` | `/calibrate` | `calibrate_judges` | Upload oracle (human) labels and compute judge calibration metrics. |
| `GET` | `/bias/{campaign_id}` | `detect_judge_bias` | Detect systematic biases in judge evaluations. |
| `GET` | `/summary/{campaign_id}` | `judge_summary` | Summary of all judge evaluations for a campaign. |


## Leaderboard

Leaderboard endpoints — aggregated scores by domain + Claude narrative reports.

| Method | Path | Function | Description |
|--------|------|----------|-------------|
| `GET` | `/domains` | `list_domains` | List all available leaderboard domains. |


## Models

Model Registry — CRUD + connection testing.

| Method | Path | Function | Description |
|--------|------|----------|-------------|
| `POST` | `/{model_id}/test` | `test_model_connection` | Live connection test — returns latency and a sample response. |


## Policy

Policy Simulation Layer — PROD-1

| Method | Path | Function | Description |
|--------|------|----------|-------------|
| `GET` | `/frameworks` | `list_frameworks` | List available policy frameworks. |
| `POST` | `/evaluate` | `evaluate_campaign_policy` | Evaluate a campaign's results against a policy framework. |


## Redbox

REDBOX — Adversarial Security Lab

| Method | Path | Function | Description |
|--------|------|----------|-------------|
| `POST` | `/forge` | `forge_variants` | Generate adversarial variants from a seed prompt using LLM + rules. |
| `POST` | `/run` | `run_variants` | Run adversarial variants against a model and record exploits. |
| `GET` | `/exploits` | `list_exploits` | List recorded exploits with optional filters. |
| `GET` | `/heatmap` | `attack_surface_heatmap` | Attack surface: model × mutation_type breach rates. |
| `POST` | `/replay/{exploit_id}` | `replay_exploit` | Replay a known exploit against a different model. |
| `POST` | `/smart-forge` | `smart_forge` | GENOME → REDBOX feedback loop. |


## Reports

Report generation: sends campaign results to Claude and returns a structured

| Method | Path | Function | Description |
|--------|------|----------|-------------|
| `GET` | `/{report_id}/export.md` | `export_report_markdown` | Export report as styled HTML. |


## Results

Results endpoints — powers the dashboards.

| Method | Path | Function | Description |
|--------|------|----------|-------------|
| `GET` | `/run/{run_id}/items` | `get_run_items` | Drill-down: per-item results for one EvalRun. |
| `GET` | `/campaign/{campaign_id}/export.csv` | `export_csv` | Export all results for a campaign as CSV. |
| `GET` | `/campaign/{campaign_id}/live` | `get_campaign_live_feed` | Live feed of most recent eval results for a running campaign. |
| `GET` | `/campaign/{campaign_id}/failed-items` | `get_failed_items` | Get all failed/errored items for a campaign with error classification. |
| `GET` | `/campaign/{campaign_id}/insights` | `get_campaign_insights` | Unified view across all modules for one campaign. |
| `GET` | `/campaign/{campaign_id}/contamination` | `check_contamination` | Analyze benchmark results for signs of test data contamination. |


## Sync

Sync — auto-imports benchmarks + all OpenRouter models at startup.

| Method | Path | Function | Description |
|--------|------|----------|-------------|
| `GET` | `/benchmarks` | `sync_benchmarks_check` | Discover and import local Ollama models. |
| `GET` | `/ollama` | `check_ollama` | Check Ollama availability and list local models. |
| `POST` | `/ollama/import` | `import_ollama_models` | Import all local Ollama models into the platform. |


## Tenants

Tenant management — INFRA-3

| Method | Path | Function | Description |
|--------|------|----------|-------------|
| `POST` | `/` | `create_tenant` | Create a new tenant and return its API key (shown only once). |
| `GET` | `/` | `list_tenants` | Rotate tenant API key. |
| `POST` | `/{tenant_id}/users` | `add_user` | Add a user to a tenant. |
