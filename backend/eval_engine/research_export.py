"""Research Export Formats — JSON-LD, CSV, LaTeX, BibTeX, HELM, eval cards."""
from __future__ import annotations
import json, csv, io
from dataclasses import dataclass, field
from datetime import datetime, UTC

@dataclass
class ExportConfig:
    include_ci: bool = True; include_raw_scores: bool = False
    include_metadata: bool = True; decimal_places: int = 4
    author: str = ""; institution: str = ""
    date: str = field(default_factory=lambda: datetime.now(UTC).strftime("%Y-%m-%d"))

def export_json_ld(run_data: dict, config: ExportConfig) -> str:
    """Export a single run as a W3C PROV-O compatible JSON-LD document."""
    run_uri = f"urn:mercury-retrograde:run:{run_data.get('run_id', 'unknown')}"
    model_uri = f"urn:mercury-retrograde:model:{run_data.get('model_name', 'unknown')}"
    benchmark_uri = f"urn:mercury-retrograde:benchmark:{run_data.get('benchmark_name', 'unknown')}"
    doc = {
        "@context": {
            "@vocab": "https://schema.org/",
            "prov": "http://www.w3.org/ns/prov#",
            "xsd": "http://www.w3.org/2001/XMLSchema#",
            "mr": "https://mercury-retrograde.ai/ns#",
        },
        "@graph": [
            {
                "@id": run_uri,
                "@type": ["prov:Entity", "mr:EvaluationRun"],
                "name": run_data.get("benchmark_name", ""),
                "mr:model": run_data.get("model_name", ""),
                "mr:benchmark": run_data.get("benchmark_name", ""),
                "mr:score": run_data.get("score", 0.0),
                "mr:ciLower": run_data.get("ci_lower", 0.0),
                "mr:ciUpper": run_data.get("ci_upper", 1.0),
                "mr:nItems": run_data.get("n_items", 0),
                "prov:generatedAtTime": {
                    "@value": run_data.get("created_at", config.date),
                    "@type": "xsd:dateTime",
                },
                "prov:wasAttributedTo": {
                    "@id": model_uri,
                    "@type": "prov:Agent",
                    "name": run_data.get("model_name", "unknown"),
                },
                "prov:wasDerivedFrom": {"@id": benchmark_uri},
                "prov:wasGeneratedBy": {
                    "@type": "prov:Activity",
                    "prov:startedAtTime": run_data.get("created_at", config.date),
                    "prov:endedAtTime": config.date,
                    "prov:wasAssociatedWith": {
                        "@type": "prov:Agent",
                        "name": config.author or "unknown",
                        "mr:institution": config.institution or "unknown",
                    },
                },
            },
            {
                "@id": benchmark_uri,
                "@type": ["prov:Entity", "mr:Benchmark"],
                "name": run_data.get("benchmark_name", ""),
            },
        ],
    }
    return json.dumps(doc, indent=2)

def export_csv(runs: list, config: ExportConfig) -> str:
    """Export multiple runs as CSV with confidence intervals and metadata columns."""
    buf = io.StringIO()
    cols = ["model", "benchmark", "score", "ci_lower", "ci_upper", "n_items",
            "contamination_risk", "capability_score", "propensity_score"]
    writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    for r in runs:
        # Accept both model/benchmark and model_name/benchmark_name keys
        row = {c: r.get(c, "") for c in cols}
        if not row["model"]:
            row["model"] = r.get("model_name", "")
        if not row["benchmark"]:
            row["benchmark"] = r.get("benchmark_name", "")
        writer.writerow(row)
    return buf.getvalue()

def export_latex_table(runs: list, config: ExportConfig) -> str:
    """Generate a paper-ready LaTeX table for comparison results."""
    lines = [r"\begin{tabular}{llrr}", r"\hline",
             r"Model & Benchmark & Score & 95\% CI \\ \hline"]
    for r in runs:
        model = r.get("model") or r.get("model_name", "")
        benchmark = r.get("benchmark") or r.get("benchmark_name", "")
        score = round(r.get("score", 0), config.decimal_places)
        ci = f"[{r.get('ci_lower', 0):.3f}, {r.get('ci_upper', 1):.3f}]"
        lines.append(f"{model} & {benchmark} & {score} & {ci} \\\\")
    lines += [r"\hline", r"\end{tabular}"]
    return "\n".join(lines)

def export_bibtex(benchmarks: list) -> str:
    """Generate BibTeX entries for eval suites used in a run."""
    entries = []
    for b in benchmarks:
        key = b.get("name", "unknown").replace(" ", "_")
        entries.append(
            f"@misc{{{key},\n"
            f"  title={{{b.get('title', '')}}},\n"
            f"  author={{{b.get('authors', '')}}},\n"
            f"  year={{{b.get('year', '')}}},\n"
            f"  url={{{b.get('url', '')}}}\n"
            f"}}"
        )
    return "\n\n".join(entries)

def export_helm(run_data: dict, config: ExportConfig) -> str:
    """Export a run in HELM-compatible JSON format for cross-platform comparison.

    Produces the minimal subset of HELM's run_spec + stats schema so that
    results can be ingested by HELM's leaderboard tooling.
    See: https://crfm.stanford.edu/helm/latest/
    """
    score = run_data.get("score", 0.0)
    n = run_data.get("n_items", 0) or 1
    ci_lower = run_data.get("ci_lower", score)
    ci_upper = run_data.get("ci_upper", score)

    # Compute per-item sum/sum_squared from mean ± CI as a best-effort estimate
    stddev = max((ci_upper - ci_lower) / (2 * 1.96), 0.0)
    variance = stddev ** 2
    total_sum = score * n

    model_name = run_data.get("model_name") or run_data.get("model", "unknown")
    benchmark_name = run_data.get("benchmark_name") or run_data.get("benchmark", "unknown")

    doc = {
        "run_spec": {
            "name": f"{benchmark_name}:model={model_name}",
            "scenario_spec": {
                "class_name": f"helm.benchmark.scenarios.{benchmark_name.lower().replace('-', '_')}_scenario.{benchmark_name.replace('-', '')}Scenario",
                "args": {},
            },
            "adapter_spec": {
                "method": "generation",
                "model": model_name,
                "model_deployment": model_name,
                "temperature": run_data.get("temperature", 0.0),
                "max_tokens": run_data.get("max_tokens", 100),
                "num_outputs": 1,
                "num_train_trials": 1,
                "sample_train": True,
                "instructions": "",
                "input_prefix": "",
                "input_suffix": "",
                "output_prefix": "",
                "output_suffix": "",
                "stop_sequences": [],
            },
            "metric_specs": [{"class_name": "helm.benchmark.metrics.basic_metrics.BasicMetric", "args": {}}],
            "data_augmenter_spec": {"perturbation_specs": [], "should_augment_train_instances": False,
                                    "should_include_original_train": True, "should_augment_eval_instances": False,
                                    "should_include_original_eval": True},
            "groups": [benchmark_name],
        },
        "stats": [
            {
                "name": {"name": "exact_match", "split": "test"},
                "count": n,
                "sum": total_sum,
                "sum_squared": (variance + score ** 2) * n,
                "min": ci_lower,
                "max": ci_upper,
                "mean": score,
                "variance": variance,
                "stddev": stddev,
            }
        ],
        "mercury_retrograde_metadata": {
            "exported_at": config.date,
            "author": config.author or "unknown",
            "institution": config.institution or "unknown",
            "run_id": run_data.get("run_id", ""),
        },
    }
    return json.dumps(doc, indent=2)

def export_eval_card(run_data: dict, benchmark_data: dict, config: ExportConfig) -> str:
    """Generate a standardised eval card in Markdown."""
    model_name = run_data.get("model_name") or run_data.get("model", "")
    lines = [
        "# Eval Card",
        f"\nGenerated: {config.date}\n",
        "## Model",
        f"- **Name**: {model_name}",
        f"- **Institution**: {config.institution or 'Unknown'}",
        "\n## Benchmark",
        f"- **Name**: {benchmark_data.get('name', '')}",
        f"- **Description**: {benchmark_data.get('description', '')}",
        "\n## Methodology",
        f"- **Author**: {config.author or 'Unknown'}",
        "- **Evaluation protocol**: Single-run, greedy decoding (temperature=0.0).",
        "- **Metric**: Exact-match accuracy unless otherwise stated.",
        "\n## Results",
        f"- **Score**: {run_data.get('score', 0):.4f}",
        f"- **95% CI**: [{run_data.get('ci_lower', 0):.3f}, {run_data.get('ci_upper', 1):.3f}]",
        f"- **N Items**: {run_data.get('n_items', 0)}",
        "\n## Limitations",
        "- Results reflect performance on this benchmark only.",
        "- Confidence intervals are bootstrap-estimated and assume i.i.d. items.",
        "\n## Citation",
        f"```bibtex\n@misc{{eval_{config.date[:4]},\n"
        f"  author={{{config.author or 'Unknown'}}},\n"
        f"  title={{LLM Evaluation: {benchmark_data.get('name', 'Unknown Benchmark')}}},\n"
        f"  year={{{config.date[:4]}}},\n"
        f"  note={{Mercury Retrograde Evaluation Platform}}\n"
        f"}}\n```",
    ]
    return "\n".join(lines)
