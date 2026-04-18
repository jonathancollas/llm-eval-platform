"""
Leaderboard endpoints — aggregated scores by domain + Claude narrative reports.
"""
import json
import logging
import threading
import time
from datetime import datetime, UTC
from typing import Optional, NamedTuple

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from core.database import get_session
from core.config import get_settings
from core.models import EvalRun, LLMModel, Benchmark, JobStatus

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])
settings = get_settings()
logger = logging.getLogger(__name__)

# ── In-process TTL cache for leaderboard data ────────────────────────────────
# Leaderboard data is read-heavy but changes only when new eval runs complete.
_leaderboard_cache: dict[str, tuple[float, object]] = {}
_leaderboard_cache_lock = threading.Lock()
_LEADERBOARD_TTL = 300.0  # 5 minutes

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
        "description": "Systemic risk benchmarks — INESIA frontier evaluation.",
        "benchmark_keys": ["mitre_attack_cyber", "disarm_info_manipulation",
                           "harmbench", "wildchat", "salad_bench", "safety_refusals", "autonomy_probe",
                           "agentic_failure_modes", "autonomous_replication"],
        "icon": "🛡️",
        "color": "red",
    },
    "cyber": {
        "label": "Cybersecurity",
        "description": "MITRE ATT&CK full coverage — 14 tactics, 61 techniques. Offensive cyber resistance.",
        "benchmark_keys": ["mitre_attack_cyber", "harmbench", "wildchat", "salad_bench"],
        "icon": "🔒",
        "color": "orange",
    },
    "disinfo": {
        "label": "Info Manipulation",
        "description": "DISARM framework full coverage — 12 phases. Influence operations, disinformation, FIMI.",
        "benchmark_keys": ["disarm_info_manipulation"],
        "icon": "📡",
        "color": "red",
    },
    "propensity": {
        "label": "Propensity",
        "description": "Behavioral tendencies — scheming, sycophancy, shutdown resistance, persuasion risk. What models TEND to do, not what they CAN do.",
        "benchmark_keys": ["scheming_eval", "sycophancy_eval", "shutdown_resistance", "persuasion_risk"],
        "icon": "🧠",
        "color": "purple",
    },
    "academic": {
        "label": "Academic",
        "description": "Standard performance benchmarks — knowledge, reasoning, math.",
        "benchmark_keys": ["mmlu", "mmlu_pro", "gpqa", "hellaswag", "arc_challenge",
                           "winogrande", "gsm8k", "math_subset", "truthfulqa", "bbh"],
        "icon": "🎓",
        "color": "blue",
    },
    "french": {
        "label": "French",
        "description": "French language benchmarks — digital sovereignty.",
        "benchmark_keys": ["mmlu_fr", "frenchbench_raisonnement", "fquad", "piaf",
                           "frenchbench_droit", "frenchbench_institutions", "mgsm"],
        "icon": "🇫🇷",
        "color": "blue",
    },
    "code": {
        "label": "Code",
        "description": "Code generation and reasoning capabilities.",
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

class _RunSlim(NamedTuple):
    """Lightweight projection — only the five columns needed for aggregation."""
    model_id: int
    benchmark_id: int
    score: Optional[float]
    total_cost_usd: float
    total_latency_ms: int


# ── Helpers ────────────────────────────────────────────────────────────────────

def _resolve_domain_benchmark_ids(
    allowed_keys: list[str] | None,
    all_benchmarks: dict[int, Benchmark],
) -> set[int] | None:
    """Return the set of benchmark IDs that belong to this domain, or None (= all)."""
    if allowed_keys is None:
        return None
    filtered: set[int] = set()
    for b_id, bench in all_benchmarks.items():
        bench_key = bench.name.lower().replace(" ", "_").replace("-", "_")
        for key in allowed_keys:
            if key.lower() in bench_key or bench_key.startswith(key.lower()):
                filtered.add(b_id)
                break
    return filtered


def _get_domain_runs(domain: str, session: Session) -> tuple[list[_RunSlim], dict[int, LLMModel], dict[int, Benchmark]]:
    """
    Return slim run projections for *domain*, plus lookup dicts for models and benchmarks.

    Optimisations vs. the original implementation:
    - Only the five columns required for aggregation are fetched (no full ORM hydration).
    - The domain benchmark filter is pushed to SQL (WHERE benchmark_id IN (...)) so the
      database never transfers rows that would be discarded in Python.
    - The benchmarks table is small and always fetched in full to support name-key matching;
      models are fetched only for the IDs that appear in the result set.
    """
    domain_cfg = DOMAINS.get(domain, DOMAINS["global"])
    allowed_keys = domain_cfg["benchmark_keys"]

    # Benchmarks table is small — fetch all once to resolve domain filter.
    all_benchmarks: dict[int, Benchmark] = {
        b.id: b
        for b in session.exec(select(Benchmark)).all()
    }

    domain_bench_ids = _resolve_domain_benchmark_ids(allowed_keys, all_benchmarks)

    # Projected query — only fetch the columns we actually need.
    stmt = select(
        EvalRun.model_id,
        EvalRun.benchmark_id,
        EvalRun.score,
        EvalRun.total_cost_usd,
        EvalRun.total_latency_ms,
    ).where(EvalRun.status == JobStatus.COMPLETED)

    if domain_bench_ids is not None:
        # Apply domain filter at SQL level — avoids transferring irrelevant rows.
        stmt = stmt.where(EvalRun.benchmark_id.in_(domain_bench_ids))

    raw_rows = session.exec(stmt).all()
    if not raw_rows:
        return [], {}, {}

    runs = [_RunSlim(*r) for r in raw_rows]

    # Fetch only models that appear in the result set.
    model_ids = list({r.model_id for r in runs})
    models: dict[int, LLMModel] = {
        m.id: m
        for m in session.exec(select(LLMModel).where(LLMModel.id.in_(model_ids))).all()
    }

    # Restrict benchmarks dict to those actually referenced.
    bench_ids_in_runs = {r.benchmark_id for r in runs}
    benchmarks = {b_id: all_benchmarks[b_id] for b_id in bench_ids_in_runs if b_id in all_benchmarks}

    return runs, models, benchmarks


def _build_leaderboard(
    runs: list[_RunSlim],
    models: dict[int, LLMModel],
    benchmarks: dict[int, Benchmark],
) -> tuple[list[LeaderboardRow], list[str]]:
    """Aggregate slim run projections into leaderboard rows."""
    # Preserve insertion order for benchmark column headers.
    bench_ids_in_runs = list(dict.fromkeys(r.benchmark_id for r in runs))
    bench_names = [benchmarks[bid].name for bid in bench_ids_in_runs if bid in benchmarks]

    # Group by model.
    by_model: dict[int, list[_RunSlim]] = {}
    for r in runs:
        by_model.setdefault(r.model_id, []).append(r)

    rows: list[LeaderboardRow] = []
    for model_id, model_runs in by_model.items():
        model = models.get(model_id)
        if not model:
            continue

        scores: dict[str, float | None] = {}
        for r in model_runs:
            bench = benchmarks.get(r.benchmark_id)
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

    # Sort by avg_score desc; models with no score sink to the bottom.
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
def get_leaderboard(
    domain: str,
    force_refresh: bool = Query(default=False, description="Bypass the in-process cache and recompute."),
    session: Session = Depends(get_session),
):
    if domain not in DOMAINS:
        raise HTTPException(status_code=404, detail=f"Domain '{domain}' not found. Available: {list(DOMAINS.keys())}")

    now = time.monotonic()
    if not force_refresh:
        with _leaderboard_cache_lock:
            cached = _leaderboard_cache.get(domain)
            if cached is not None:
                ts, data = cached
                if now - ts < _LEADERBOARD_TTL:
                    return data

    runs, models, benchmarks = _get_domain_runs(domain, session)
    rows, bench_names = _build_leaderboard(runs, models, benchmarks)

    cfg = DOMAINS[domain]
    result = DomainLeaderboard(
        domain=domain,
        label=cfg["label"],
        description=cfg["description"],
        icon=cfg["icon"],
        benchmarks=bench_names,
        rows=rows,
        last_updated=datetime.now(UTC).isoformat(),
        total_runs=len(runs),
    )
    with _leaderboard_cache_lock:
        _leaderboard_cache[domain] = (now, result)
    return result


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

    if not settings.anthropic_api_key and not settings.ollama_base_url:
        raise HTTPException(status_code=500, detail="No model available. Configure ANTHROPIC_API_KEY or Ollama.")

    runs, models, benchmarks = _get_domain_runs(domain, session)

    if not runs:
        raise HTTPException(status_code=400, detail="No completed evaluation runs found for this domain. Run some campaigns first.")

    rows, bench_names = _build_leaderboard(runs, models, benchmarks)
    cfg = DOMAINS[domain]

    # Build context
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

    today = datetime.now(UTC).strftime("%B %Y")

    system_prompt = """You are an AI evaluation expert specializing in safety and systemic risks.
You write rigorous narrative analyses for INESIA (National Institute for AI Evaluation and Security).
Your reports target regulators, security teams, and decision-makers.
Style: precise, factual, actionable. Cite concrete numbers. Identify patterns.
Write in English. Use Markdown with clear headings."""

    user_prompt = f"""# Leaderboard {cfg['label']} — {today}

## Domain
{cfg['description']}

## Benchmarks covered
{', '.join(bench_names) if bench_names else 'No domain-specific benchmarks'}

## Results
```json
{json.dumps(results_summary, indent=2, ensure_ascii=False)}
```

## Your mission
Write a narrative state-of-the-art analysis for this domain as of {today}.

Required structure:
1. **Executive summary** (3-5 sentences — what a decision-maker needs in 30 seconds)
2. **Commented ranking** (analyze scores, identify leaders and gaps)
3. **Patterns and correlations** (model size vs score? open-source vs proprietary? cost vs performance?)
4. **Warnings** (models that over-refuse legitimate requests? that underperform on specific benchmarks?)
5. **INESIA recommendations** (which models for which use cases?)
6. **Methodological limits** (what these numbers don't tell us)

Be concrete, name models, cite precise scores."""

    from core.utils import generate_text
    content = await generate_text(
        prompt=user_prompt,
        system_prompt=system_prompt,
        max_tokens=2048,
        timeout=120,
    )

    report = DomainReport(
        domain=domain,
        label=cfg["label"],
        content_markdown=content,
        generated_at=datetime.now(UTC).isoformat(),
        model_used=settings.report_model,
    )
    _report_cache[domain] = report
    return report


@router.get("/{domain}/report", response_model=Optional[DomainReport])
def get_cached_report(domain: str):
    """Return the cached report for a domain, or null if not generated yet."""
    return _report_cache.get(domain)
