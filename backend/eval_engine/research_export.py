"""Research Export Formats — JSON-LD, CSV, LaTeX, BibTeX, eval cards."""
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
    doc = {
        "@context": {"@vocab": "https://schema.org/", "prov": "http://www.w3.org/ns/prov#"},
        "@type": "EvaluationResult",
        "name": run_data.get("benchmark_name",""),
        "model": run_data.get("model_name",""),
        "score": run_data.get("score", 0.0),
        "ci_lower": run_data.get("ci_lower", 0.0),
        "ci_upper": run_data.get("ci_upper", 1.0),
        "n_items": run_data.get("n_items", 0),
        "dateCreated": run_data.get("created_at", config.date),
        "prov:generatedAtTime": config.date,
        "prov:wasAttributedTo": config.author or "unknown",
    }
    return json.dumps(doc, indent=2)

def export_csv(runs: list, config: ExportConfig) -> str:
    buf = io.StringIO()
    cols = ["model","benchmark","score","ci_lower","ci_upper","n_items","contamination_risk","capability_score","propensity_score"]
    writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    for r in runs:
        writer.writerow({c: r.get(c,"") for c in cols})
    return buf.getvalue()

def export_latex_table(runs: list, config: ExportConfig) -> str:
    lines = [r"\begin{tabular}{llrr}", r"\hline", r"Model & Benchmark & Score & 95\% CI \\ \hline"]
    for r in runs:
        score = round(r.get("score",0), config.decimal_places)
        ci = f"[{r.get('ci_lower',0):.3f}, {r.get('ci_upper',1):.3f}]"
        lines.append(f"{r.get('model','')} & {r.get('benchmark','')} & {score} & {ci} \\\\")
    lines += [r"\hline", r"\end{tabular}"]
    return "\n".join(lines)

def export_bibtex(benchmarks: list) -> str:
    entries = []
    for b in benchmarks:
        key = b.get("name","unknown").replace(" ","_")
        entries.append(f"@misc{{{key},\n  title={{{b.get('title','')}}},\n  author={{{b.get('authors','')}}},\n  year={{{b.get('year','')}}},\n  url={{{b.get('url','')}}}\n}}")
    return "\n\n".join(entries)

def export_eval_card(run_data: dict, benchmark_data: dict, config: ExportConfig) -> str:
    lines = [
        "# Eval Card",
        f"\nGenerated: {config.date}\n",
        "## Model",
        f"- **Name**: {run_data.get('model_name','')}",
        "\n## Benchmark",
        f"- **Name**: {benchmark_data.get('name','')}",
        f"- **Description**: {benchmark_data.get('description','')}",
        "\n## Results",
        f"- **Score**: {run_data.get('score',0):.4f}",
        f"- **95% CI**: [{run_data.get('ci_lower',0):.3f}, {run_data.get('ci_upper',1):.3f}]",
        f"- **N Items**: {run_data.get('n_items',0)}",
        "\n## Limitations",
        "- Results reflect performance on this benchmark only.",
        "\n## Citation",
        f"```bibtex\n@misc{{eval,author={{{config.author or 'Unknown'}}},year={{{config.date[:4]}}}}}\n```",
    ]
    return "\n".join(lines)
