# API Endpoints

161 endpoints across 21 routers. All routes are prefixed with `/api`.


## Agents

Agent Evaluation Engine — multi-step trajectory scoring on 6 axes.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/agents/trajectories` | Upload an agent trajectory for evaluation. |
| `POST` | `/agents/evaluate` | Score a trajectory on 6 axes (task completion, tool precision, planning coherence, error recovery, safety compliance, cost efficiency). |
| `GET` | `/agents/trajectories` | List agent trajectories. |
| `GET` | `/agents/trajectories/{trajectory_id}` | Get full trajectory with steps. |
| `GET` | `/agents/dashboard` | Aggregate agent eval metrics across trajectories. |
| `GET` | `/agents/trajectories/{trajectory_id}/steps` | Get all steps for a trajectory. |
| `GET` | `/agents/trajectories/{trajectory_id}/replay` | Replay a trajectory step-by-step with diffs and safety signals. |
| `POST` | `/agents/trajectories/{trajectory_id}/ingest-steps` | Ingest structured steps into trajectory-native storage. |


## Benchmarks

Benchmarks — CRUD + dataset upload + HuggingFace import + fork/card/versions.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/benchmarks/` | List all benchmarks (optionally filter by type). |
| `GET` | `/benchmarks/{benchmark_id}` | Get a single benchmark. |
| `POST` | `/benchmarks/` | Create a new benchmark. |
| `POST` | `/benchmarks/{benchmark_id}/upload-dataset` | Upload a JSON/CSV dataset file for a benchmark. |
| `PATCH` | `/benchmarks/{benchmark_id}` | Update benchmark metadata. |
| `DELETE` | `/benchmarks/{benchmark_id}` | Delete a benchmark. |
| `GET` | `/benchmarks/{benchmark_id}/items` | Browse dataset items for a benchmark (paginated + search). |
| `POST` | `/benchmarks/import-huggingface` | Import a dataset from HuggingFace Hub and create a benchmark. |
| `GET` | `/benchmarks/sources` | List available benchmark source types. |
| `POST` | `/benchmarks/{benchmark_id}/fork` | Fork a benchmark into a new custom variant. |
| `GET` | `/benchmarks/{benchmark_id}/card` | Get benchmark dataset card metadata. |
| `GET` | `/benchmarks/{benchmark_id}/versions` | Get version history for a benchmark. |


## Campaigns

Campaign lifecycle — CRUD + run/cancel + live tracking + manifest.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/campaigns/` | List all campaigns. |
| `POST` | `/campaigns/` | Create a new campaign (N models × M benchmarks). |
| `GET` | `/campaigns/{campaign_id}` | Get campaign details including all run summaries. |
| `POST` | `/campaigns/{campaign_id}/run` | Start execution of a campaign. |
| `POST` | `/campaigns/{campaign_id}/cancel` | Cancel a running campaign. |
| `DELETE` | `/campaigns/{campaign_id}` | Delete a campaign and all its results. |
| `GET` | `/campaigns/{campaign_id}/manifest` | Download the reproducibility manifest for a campaign. |


## Catalog

Read-only catalog for browsing all registered models and benchmarks.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/catalog/models` | List all models from the catalog. |
| `GET` | `/catalog/benchmarks` | List all benchmarks from the catalog. |


## Deep Analysis

Model introspection — tokenizer info, refusal probing, embedding analysis.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/deep-analysis/models/{model_id}/info` | Get detailed model info and metadata. |
| `GET` | `/deep-analysis/models/{model_id}/tokenizer` | Get tokenizer information for a model. |
| `POST` | `/deep-analysis/models/{model_id}/refusal-probe` | Run a structured refusal probe against a model. |
| `POST` | `/deep-analysis/models/{model_id}/embedding-analysis` | Analyze model response embedding space. |


## Events

Event-sourced campaign state — real-time diff, timeline, and state reconstruction.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/events/campaign/{campaign_id}` | Get all events for a campaign. |
| `GET` | `/events/campaign/{campaign_id}/state` | Reconstruct current campaign state from events. |
| `GET` | `/events/campaign/{campaign_id}/diff` | Get event diff since a given offset. |
| `GET` | `/events/campaign/{campaign_id}/timeline` | Get campaign timeline with key milestones. |
| `GET` | `/events/types` | List all available event types. |


## Evidence

Evidence-Based Evaluation — RCT trials + Real World Data + Real World Evidence synthesis.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/evidence/trials` | Design a Randomized Control Trial for AI evaluation. |
| `GET` | `/evidence/trials` | List all trials. |
| `GET` | `/evidence/trials/{trial_id}` | Get full trial details with power analysis. |
| `POST` | `/evidence/trials/{trial_id}/analyze` | Compute statistical analysis (Mann-Whitney U, bootstrap CI) for a completed trial. |
| `POST` | `/evidence/rwd/collect` | Aggregate telemetry into a Real World Dataset. |
| `GET` | `/evidence/rwd` | List all Real World Datasets. |
| `POST` | `/evidence/rwe/synthesize` | Synthesize RCT results with RWD into Real World Evidence (concordance, drift, grade). |
| `GET` | `/evidence/rwe` | List all Real World Evidence records. |
| `GET` | `/evidence/rwe/{rwe_id}` | Get a specific Real World Evidence record. |


## Genome

Failure Genome (Genomia) API — behavioral fingerprints, signals, hybrid classification, regression analysis.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/genome/campaigns/{campaign_id}/compute` | Compute rule-based Failure Genome for all runs in a campaign. |
| `GET` | `/genome/campaigns/{campaign_id}` | Get aggregated Failure Genome for all models in a campaign. |
| `GET` | `/genome/models/{model_id}` | Get behavioral fingerprint for a specific model. |
| `GET` | `/genome/models` | List all model fingerprints for comparison. |
| `GET` | `/genome/ontology` | Get the failure taxonomy ontology (7 types). |
| `GET` | `/genome/safety-heatmap` | Safety capability × risk heatmap across all models. |
| `GET` | `/genome/regression/compare` | Compare two campaigns and identify probable regression causes. |
| `POST` | `/genome/regression/explain` | Generate a natural language causal explanation of a regression. |
| `GET` | `/genome/signals/{run_id}` | Extract and return signals for items in an eval run. |
| `POST` | `/genome/campaigns/{campaign_id}/compute-hybrid` | Compute genome with LLM hybrid classification (GENOME-4). |
| `GET` | `/genome/references` | List scientific references backing the genome taxonomy. |
| `GET` | `/genome/heuristics` | List all heuristic signal definitions. |
| `GET` | `/genome/heuristics/signal/{signal_key}` | Get details for a specific signal. |
| `GET` | `/genome/heuristics/{benchmark_name}` | Get heuristics applicable to a specific benchmark type. |


## Judge

LLM-as-Judge — multi-judge ensemble, calibration & bias detection.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/judge/evaluate` | Run multi-judge evaluation on campaign results. |
| `GET` | `/judge/agreement/{campaign_id}` | Compute inter-judge agreement (Cohen's kappa + Pearson r). |
| `POST` | `/judge/calibrate` | Upload oracle (human) labels and compute judge calibration metrics. |
| `GET` | `/judge/bias/{campaign_id}` | Detect systematic biases in judge evaluations (length, model preference). |
| `GET` | `/judge/summary/{campaign_id}` | Summary of all judge evaluations for a campaign. |


## Leaderboard

Leaderboard — aggregated scores across 7 domains + Claude narrative reports.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/leaderboard/domains` | List all available leaderboard domains. |
| `GET` | `/leaderboard/{domain}` | Get full leaderboard for a domain (global, safety, coding, academic, french, reasoning, frontier). |
| `POST` | `/leaderboard/{domain}/report` | Generate a Claude narrative report for a domain leaderboard. |
| `GET` | `/leaderboard/{domain}/report` | Get the cached domain report. |


## Models

Model Registry — CRUD + connection testing + adapter introspection.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/models/slim` | List all models (lightweight — use for selectors/dropdowns). |
| `GET` | `/models/` | List all models with full metadata. |
| `POST` | `/models/` | Register a new model. |
| `GET` | `/models/{model_id}` | Get full model details. |
| `PATCH` | `/models/{model_id}` | Update model metadata or API key. |
| `DELETE` | `/models/{model_id}` | Delete a model. |
| `POST` | `/models/{model_id}/test` | Live connection test — returns latency and a sample response. |
| `GET` | `/models/inference/adapters` | List available inference adapter types. |
| `GET` | `/models/explorer` | Model explorer view with capability tags and filters. |


## Monitoring

Telemetry ingestion + drift detection + third-party integrations (Langfuse, OTel).

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/monitoring/ingest` | Ingest a single telemetry event. |
| `POST` | `/monitoring/ingest/batch` | Ingest a batch of telemetry events. |
| `GET` | `/monitoring/report` | Get a monitoring report (drift, safety flags, latency). |
| `GET` | `/monitoring/dashboard` | Drift detection dashboard with aggregated telemetry signals. |
| `GET` | `/monitoring/telemetry` | List raw telemetry events. |
| `GET` | `/monitoring/stats` | Aggregate statistics across all telemetry. |
| `POST` | `/monitoring/ingest/langfuse` | Ingest events from Langfuse integration. |
| `POST` | `/monitoring/ingest/otel` | Ingest events from OpenTelemetry integration. |
| `GET` | `/monitoring/integration/setup` | Get integration setup instructions (Langfuse, OTel). |


## Multi-Agent

Multi-agent simulation + sandbagging probe.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/multiagent/simulate/pipeline` | Simulate a multi-agent pipeline with configurable roles. |
| `POST` | `/multiagent/simulate/custom` | Run a custom multi-agent simulation scenario. |
| `GET` | `/multiagent/simulations` | List past simulations. |
| `GET` | `/multiagent/simulations/{sim_id}` | Get full simulation results. |
| `GET` | `/multiagent/payloads` | List available simulation payload templates. |
| `POST` | `/multiagent/sandbagging/probe` | Probe a model for sandbagging behavior across eval vs neutral contexts. |
| `GET` | `/multiagent/sandbagging/reports` | List sandbagging probe reports. |


## Policy

Policy Simulation — EU AI Act, HIPAA, Finance regulatory compliance checks.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/policy/frameworks` | List available policy frameworks. |
| `POST` | `/policy/evaluate` | Evaluate a campaign's results against a policy framework. |


## REDBOX

REDBOX — Adversarial Security Lab. Forge, run, replay, and analyze adversarial attacks.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/redbox/forge` | Generate adversarial variants from a seed prompt using `native` or `garak` engine modes. |
| `POST` | `/redbox/run` | Run adversarial variants against a model and record exploits. |
| `GET` | `/redbox/exploits` | List recorded exploits with optional filters. |
| `GET` | `/redbox/heatmap` | Attack surface heatmap: model × mutation_type breach rates. |
| `POST` | `/redbox/replay/{exploit_id}` | Replay a known exploit against a (different) model. |
| `POST` | `/redbox/smart-forge` | GENOME → REDBOX feedback loop: target weaknesses detected by Genomia. |
| `GET` | `/redbox/live/{model_id}` | Live feed of recent exploit attempts against a model. |
| `GET` | `/redbox/taxonomy` | List the adversarial mutation taxonomy (MITRE ATLAS + OWASP LLM). |
| `GET` | `/redbox/killchain` | Get the attack killchain model. |
| `GET` | `/redbox/tool-registry` | Unified adversarial security tool registry (`tool_name`, `category`, `input_adapter`, `output_schema`, `severity_model`). |
| `GET` | `/redbox/catalog` | List all available adversarial scenario templates. |
| `GET` | `/redbox/garak/coverage` | List Garak probe packs and supported attack classes (jailbreak, prompt injection, exfiltration, multilingual). |
| `POST` | `/redbox/generate-scenarios` | Generate new adversarial scenarios using the LLM forge. |


## Reports

Report generation — send campaign results to Claude and get a structured narrative.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/reports/generate` | Generate a narrative report for a campaign (Claude Sonnet or local Ollama). |
| `GET` | `/reports/campaign/{campaign_id}` | List all reports for a campaign. |
| `GET` | `/reports/{report_id}/export.md` | Export report as Markdown. |
| `GET` | `/reports/{report_id}/export.html` | Export report as styled HTML. |


## Research

Research OS — Workspaces, Experiment Manifests, Safety Incident Exchange (SIX), replication workflows.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/research/workspaces` | Create a research workspace. |
| `GET` | `/research/workspaces` | List all workspaces. |
| `GET` | `/research/workspaces/{workspace_id}` | Get workspace details with linked manifests. |
| `PATCH` | `/research/workspaces/{workspace_id}` | Update workspace metadata. |
| `POST` | `/research/workspaces/{workspace_id}/fork` | Fork a workspace (creates a derivative copy). |
| `POST` | `/research/manifests/generate/{campaign_id}` | Auto-generate a reproducibility manifest from a completed campaign. |
| `GET` | `/research/manifests/{manifest_id}` | Get manifest details including config snapshot and experiment hash. |
| `POST` | `/research/incidents` | Create a Safety Incident (SIX) record with MRX-YYYY-NNN ID. |
| `GET` | `/research/incidents` | List safety incidents with optional filters. |
| `GET` | `/research/incidents/{incident_id}` | Get a specific safety incident. |
| `POST` | `/research/telemetry/ingest` | Ingest runtime telemetry events (up to 1000 per batch). |
| `GET` | `/research/telemetry/dashboard` | Drift detection dashboard for ingested telemetry. |
| `GET` | `/research/benchmarks/{benchmark_id}/forks` | Get fork lineage for a benchmark. |
| `POST` | `/research/workspaces/{workspace_id}/replications` | Request an independent replication of a workspace. |
| `POST` | `/research/workspaces/{workspace_id}/replications/submit` | Submit completed replication results. |
| `GET` | `/research/workspaces/{workspace_id}/replications` | Get all replication requests and results for a workspace. |
| `POST` | `/research/workspaces/{workspace_id}/publish` | Publish workspace as an executable paper artifact. |


## Results

Results — powers all dashboards: heatmap, win rate, live feed, failed items, insights, contamination.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/results/campaign/{campaign_id}/dashboard` | Full dashboard data: heatmap, radar, win rates, cost, alerts. |
| `GET` | `/results/run/{run_id}/items` | Drill-down: per-item results for one EvalRun (paginated). |
| `GET` | `/results/campaign/{campaign_id}/export.csv` | Export all results for a campaign as CSV. |
| `GET` | `/results/campaign/{campaign_id}/live` | Live feed of most recent eval results for a running campaign. |
| `GET` | `/results/campaign/{campaign_id}/failed-items` | Get all failed/errored items with error classification. |
| `GET` | `/results/campaign/{campaign_id}/insights` | Unified view across all modules (genome, judge, contamination) for one campaign. |
| `GET` | `/results/campaign/{campaign_id}/contamination` | Analyze benchmark results for signs of test data contamination. |
| `GET` | `/results/run/{run_id}/confidence` | Bootstrap confidence interval and reliability grade for an EvalRun. |
| `GET` | `/results/compare` | Compare two campaigns side-by-side. |


## Science

Scientific tooling — capability/propensity elicitation, mechanistic interpretability validation, benchmark validity, compositional risk, failure clustering.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/science/capability-propensity` | Elicit capability vs propensity scores for a model on a benchmark. |
| `GET` | `/science/capability-propensity/runs` | List past capability/propensity runs. |
| `POST` | `/science/mech-interp/validate` | Validate CoT faithfulness with mechanistic interpretability probes. |
| `GET` | `/science/contamination/run/{run_id}` | Check contamination for a single EvalRun. |
| `GET` | `/science/contamination/campaign/{campaign_id}` | Check contamination across a whole campaign. |
| `GET` | `/science/validity/benchmark/{benchmark_id}` | Assess construct validity of a benchmark. |
| `POST` | `/science/compositional-risk` | Compute system-level threat profile from capability/propensity scores (multiplicative composition). |
| `GET` | `/science/compositional-risk/domains` | List all supported risk domains and their severity weights. |
| `GET` | `/science/failure-clusters/campaign/{campaign_id}` | Cluster failure traces and detect novel failure patterns (TF-IDF + cosine, no LLM). |


## Sync

Sync — catalog import, OpenRouter sync, Ollama discovery and model pulling.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/sync/startup` | Trigger a full startup sync (benchmarks + OpenRouter + Ollama). |
| `GET` | `/sync/startup/status` | Get the current startup sync status. |
| `GET` | `/sync/benchmarks` | Check which catalog benchmarks are missing from the DB. |
| `POST` | `/sync/benchmarks/import-all` | Import all catalog benchmarks into the DB. |
| `GET` | `/sync/ollama` | Check Ollama availability and list local models. |
| `POST` | `/sync/ollama/import` | Import all local Ollama models into the platform. |
| `GET` | `/sync/ollama/suggestions` | Get suggestions for useful Ollama models to pull. |
| `POST` | `/sync/ollama/pull` | Pull a model from the Ollama registry. |
| `POST` | `/sync/ollama/pull-and-register` | Pull a model from Ollama and register it in the platform. |


## Tenants

Tenant management — multi-tenant CRUD, API key rotation, user management.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/tenants/` | Create a new tenant and return its API key (shown only once). |
| `GET` | `/tenants/` | List all tenants. |
| `GET` | `/tenants/{tenant_id}` | Get tenant details. |
| `POST` | `/tenants/{tenant_id}/rotate-key` | Rotate a tenant's API key. |
| `POST` | `/tenants/{tenant_id}/users` | Add a user to a tenant. |
