"""
Leaderboard endpoints — aggregated scores by domain + Claude narrative reports.
"""
import json
import logging
from datetime import datetime
from typing import Optional

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from core.database import get_session
from core.config import get_settings
from core.models import EvalRun, LLMModel, Benchmark, JobStatus
from core.utils import safe_extract_text

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])
settings = get_settings()
logger = logging.getLogger(__name__)

# ── Domain definitions ─────────────────────────────────────────────────────────

DOMAINS = {
    "global": {
        "label": "Global",
        "description": "Tous les benchmarks — vue d'ensemble comparative.",
        "benchmark_keys": None,  # None = all
        "icon": "🌐",
        "color": "slate",
    },
    "frontier": {
        "label": "Frontier",
        "description": "Benchmarks de risques systémiques — évaluation frontier INESIA.",
        "benchmark_keys": ["cyber_uplift", "cbrne_probe", "loss_of_control",
                           "evaluation_awareness", "capability_overhang", "mechanistic_interp",
                           "autonomy_probe", "safety_refusals", "deception_probe", "manipulation_info"],
        "icon": "🛡️",
        "color": "red",
    },
    "cyber": {
        "label": "Cybersécurité",
        "description": "Résistance aux prompts de cybersécurité offensive.",
        "benchmark_keys": ["cyber_uplift", "safety_refusals", "harmbench", "wildchat", "salad_bench"],
        "icon": "🔒",
        "color": "orange",
    },
    "cbrne": {
        "label": "CBRN-E",
        "description": "Uplift chimique, biologique, radiologique, nucléaire et explosif.",
        "benchmark_keys": ["cbrne_probe"],
        "icon": "☢️",
        "color": "red",
    },
    "agentique": {
        "label": "Systèmes Agentiques",
        "description": "Autonomie, désalignement, loss of control.",
        "benchmark_keys": ["loss_of_control", "autonomy_probe", "evaluation_awareness",
                           "capability_overhang", "tau_bench", "agentbench"],
        "icon": "🤖",
        "color": "purple",
    },
    "academique": {
        "label": "Académique",
        "description": "Benchmarks de performance standard — connaissances, raisonnement, maths.",
        "benchmark_keys": ["mmlu", "mmlu_pro", "gpqa", "hellaswag", "arc_challenge",
                           "winogrande", "gsm8k", "math_subset", "truthfulqa", "bbh"],
        "icon": "🎓",
        "color": "blue",
    },
    "francais": {
        "label": "Français",
        "description": "Benchmarks en langue française — souveraineté numérique.",
        "benchmark_keys": ["mmlu_fr", "frenchbench_raisonnement", "fquad", "piaf",
                           "frenchbench_droit", "frenchbench_institutions", "mgsm"],
        "icon": "🇫🇷",
        "color": "blue",
    },
    "code": {
        "label": "Code",
        "description": "Capacités de génération et raisonnement sur le code.",
        "benchmark_keys": ["humaneval_full", "humaneval_plus", "mbpp", "mbpp_plus",
                           "ds1000", "cruxeval", "livecodebench", "swebench"],
        "icon": "💻",
        "color": "violet",
    },
}

# ── Schemas ────────────────────────────────────────────────────────────────────

class LeaderboardRow(BaseModel):
    rank: int
    model_name: str
    model_provider: str
    scores: dict[str, float | None]   # benchmark_name → score
    avg_score: float | None
    num_benchmarks_run: int
    total_cost_usd: float
    avg_latency_ms: float

class DomainLeaderboard(BaseModel):
    domain: str
    label: str
    description: str
    icon: str
    benchmarks: list[str]
    rows: list[LeaderboardRow]
    last_updated: str
    total_runs: int

class DomainReport(BaseModel):
    domain: str
    label: str
    content_markdown: str
    generated_at: str
    model_used: str

# Simple in-memory cache for reports
_report_cache: dict[str, DomainReport] = {}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_domain_runs(domain: str, session: Session) -> tuple[list[EvalRun], list[LLMModel], list[Benchmark]]:
    """Fetch all completed runs for a domain."""
    runs = session.exec(
        select(EvalRun).where(EvalRun.status == JobStatus.COMPLETED)
    ).all()

    models = {m.id: m for m in session.exec(select(LLMModel)).all()}
    benchmarks = {b.id: b for b in session.exec(select(Benchmark)).all()}

    domain_cfg = DOMAINS.get(domain, DOMAINS["global"])
    allowed_keys = domain_cfg["benchmark_keys"]

    if allowed_keys is not None:
        # Filter runs to only those benchmarks in this domain
        # Match by benchmark name key (partial match on name)
        filtered_bench_ids = set()
        for b_id, bench in benchmarks.items():
            bench_name_lower = bench.name.lower().replace(" ", "_").replace("-", "_")
            bench_key = bench_name_lower.split("(")[0].strip().replace(" ", "_")
            for key in allowed_keys:
                if key.lower() in bench_name_lower or bench_name_lower.startswith(key.lower()):
                    filtered_bench_ids.add(b_id)
                    break
        runs = [r for r in runs if r.benchmark_id in filtered_bench_ids]

    return runs, list(models.values()), list(benchmarks.values())


def _build_leaderboard(runs: list[EvalRun], models_list: list[LLMModel], benchmarks_list: list[Benchmark]) -> tuple[list[LeaderboardRow], list[str]]:
    """Aggregate runs into leaderboard rows."""
    models_map = {m.id: m for m in models_list}
    benches_map = {b.id: b for b in benchmarks_list}

    # Collect benchmark names that appear in runs
    bench_ids_in_runs = list(dict.fromkeys(r.benchmark_id for r in runs))
    bench_names = [benches_map[bid].name for bid in bench_ids_in_runs if bid in benches_map]

    # Group by model
    by_model: dict[int, list[EvalRun]] = {}
    for r in runs:
        by_model.setdefault(r.model_id, []).append(r)

    rows: list[LeaderboardRow] = []
    for model_id, model_runs in by_model.items():
        model = models_map.get(model_id)
        if not model:
            continue

        scores: dict[str, float | None] = {}
        for r in model_runs:
            bench = benches_map.get(r.benchmark_id)
            if bench:
                scores[bench.name] = r.score

        valid_scores = [s for s in scores.values() if s is not None]
        avg = sum(valid_scores) / len(valid_scores) if valid_scores else None
        total_cost = sum(r.total_cost_usd for r in model_runs)
        avg_latency = sum(r.total_latency_ms for r in model_runs) / max(len(model_runs), 1)

        rows.append(LeaderboardRow(
            rank=0,  # set after sorting
            model_name=model.name,
            model_provider=model.provider,
            scores=scores,
            avg_score=round(avg, 4) if avg is not None else None,
            num_benchmarks_run=len(model_runs),
            total_cost_usd=round(total_cost, 6),
            avg_latency_ms=round(avg_latency, 1),
        ))

    # Sort by avg_score desc
    rows.sort(key=lambda r: (r.avg_score is None, -(r.avg_score or 0)))
    for i, row in enumerate(rows):
        row.rank = i + 1

    return rows, bench_names


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/domains")
def list_domains():
    """List all available leaderboard domains."""
    return [
        {"key": k, "label": v["label"], "description": v["description"], "icon": v["icon"]}
        for k, v in DOMAINS.items()
    ]


@router.get("/{domain}", response_model=DomainLeaderboard)
def get_leaderboard(domain: str, session: Session = Depends(get_session)):
    if domain not in DOMAINS:
        raise HTTPException(status_code=404, detail=f"Domain '{domain}' not found. Available: {list(DOMAINS.keys())}")

    runs, models_list, benchmarks_list = _get_domain_runs(domain, session)
    rows, bench_names = _build_leaderboard(runs, models_list, benchmarks_list)

    cfg = DOMAINS[domain]
    return DomainLeaderboard(
        domain=domain,
        label=cfg["label"],
        description=cfg["description"],
        icon=cfg["icon"],
        benchmarks=bench_names,
        rows=rows,
        last_updated=datetime.utcnow().isoformat(),
        total_runs=len(runs),
    )


@router.post("/{domain}/report", response_model=DomainReport)
async def generate_domain_report(
    domain: str,
    force_refresh: bool = False,
    session: Session = Depends(get_session),
):
    """Generate a Claude narrative report for a leaderboard domain."""
    if domain not in DOMAINS:
        raise HTTPException(status_code=404, detail=f"Domain '{domain}' not found.")

    # Return cached report if available and not forcing refresh
    if not force_refresh and domain in _report_cache:
        return _report_cache[domain]

    if not settings.anthropic_api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured.")

    runs, models_list, benchmarks_list = _get_domain_runs(domain, session)

    if not runs:
        raise HTTPException(status_code=400, detail="No completed evaluation runs found for this domain. Run some campaigns first.")

    rows, bench_names = _build_leaderboard(runs, models_list, benchmarks_list)
    cfg = DOMAINS[domain]

    # Build context for Claude
    results_summary = []
    for row in rows:
        results_summary.append({
            "rank": row.rank,
            "model": row.model_name,
            "provider": row.model_provider,
            "avg_score": row.avg_score,
            "scores_by_benchmark": row.scores,
            "cost_usd": row.total_cost_usd,
            "avg_latency_ms": row.avg_latency_ms,
        })

    today = datetime.utcnow().strftime("%B %Y")

    system_prompt = """Tu es un expert en évaluation de modèles d'IA, spécialiste de la sécurité et des risques systémiques.
Tu rédiges des analyses narratives rigoureuses pour l'INESIA (Institut national pour l'évaluation et la sécurité de l'IA).
Tes rapports sont destinés aux régulateurs, aux équipes de sécurité et aux décideurs.
Ton style : précis, factuel, actionnable. Tu cites les chiffres concrets. Tu identifies les patterns.
Tu écris en français. Tu utilises le Markdown avec des titres clairs."""

    user_prompt = f"""# Leaderboard {cfg['label']} — {today}

## Domaine évalué
{cfg['description']}

## Benchmarks couverts
{', '.join(bench_names) if bench_names else 'Aucun benchmark spécifique au domaine'}

## Résultats
```json
{json.dumps(results_summary, indent=2, ensure_ascii=False)}
```

## Ta mission
Rédige une analyse narrative de l'état de l'art pour ce domaine en {today}.

Structure imposée :
1. **Synthèse exécutive** (3-5 phrases max — ce que doit retenir un décideur en 30 secondes)
2. **Classement commenté** (analyse les scores, identifie les leaders et les écarts)
3. **Patterns et corrélations** (taille du modèle vs score ? open-source vs propriétaire ? coût vs performance ?)
4. **Points de vigilance** (modèles qui sur-refusent les requêtes légitimes ? qui sous-performent sur certains benchmarks ?)
5. **Recommandations INESIA** (quels modèles privilégier pour quels usages ?)
6. **Limites méthodologiques** (ce que ces chiffres ne disent pas)

Sois concret, cite les modèles par nom, donne les scores précis."""

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model=settings.report_model,
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    content = safe_extract_text(message)

    report = DomainReport(
        domain=domain,
        label=cfg["label"],
        content_markdown=content,
        generated_at=datetime.utcnow().isoformat(),
        model_used=settings.report_model,
    )
    _report_cache[domain] = report
    return report


@router.get("/{domain}/report", response_model=Optional[DomainReport])
def get_cached_report(domain: str):
    """Return the cached report for a domain, or null if not generated yet."""
    return _report_cache.get(domain)
