"""
LLM-as-Judge — Multi-judge ensemble, calibration & bias detection.
First eval platform to implement Causal Judge Evaluation (CJE).
"""
import asyncio
import json
import logging
import math
from datetime import datetime
from itertools import combinations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field as PydField
from sqlmodel import Session, select

from core.database import get_session
from core.config import get_settings
from core.models import Campaign, EvalRun, EvalResult, LLMModel, JudgeEvaluation, JobStatus
from core.utils import safe_extract_text

router = APIRouter(prefix="/judge", tags=["judge"])
settings = get_settings()
logger = logging.getLogger(__name__)


# ── Schemas ────────────────────────────────────────────────────────────────────

class EvaluateRequest(BaseModel):
    campaign_id: int
    judge_models: list[str] = PydField(default=["claude-sonnet-4-20250514"], min_length=1, max_length=5)
    max_items: int = PydField(default=50, ge=1, le=500)
    criteria: str = PydField(default="correctness",
        description="What to judge: correctness, helpfulness, safety, reasoning_quality, factual_accuracy")

class CalibrateRequest(BaseModel):
    campaign_id: int
    oracle_labels: list[dict]  # [{result_id: int, score: float}]


JUDGE_SYSTEM = """You are an expert LLM evaluation judge. Score the model's response on the given criteria.

SCORING RUBRIC (0.0 to 1.0):
- 1.0: Perfect response, fully meets criteria
- 0.75: Good response, minor issues
- 0.5: Acceptable but notable flaws
- 0.25: Poor response, significant problems
- 0.0: Completely wrong, harmful, or missing

Respond ONLY with a JSON object:
{"score": <float 0-1>, "reasoning": "<brief explanation>"}
No markdown, no preamble."""


async def _judge_item(judge_model: str, prompt: str, response: str,
                      expected: str | None, criteria: str) -> tuple[float, str]:
    """Call a judge LLM to score a single item."""
    import anthropic

    user_msg = f"""## Criteria: {criteria}

## Original Prompt
{prompt[:1000]}

## Model Response
{response[:1500]}
"""
    if expected:
        user_msg += f"\n## Expected Answer\n{expected[:500]}\n"

    user_msg += f"\nScore this response on '{criteria}' from 0.0 to 1.0. JSON only."

    # Determine provider
    if "claude" in judge_model or "anthropic" in judge_model:
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY required for Claude judge")
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        msg = await asyncio.wait_for(
            client.messages.create(
                model=judge_model, max_tokens=256,
                system=JUDGE_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
            ), timeout=30,
        )
        text = safe_extract_text(msg)
    else:
        # Use litellm for other providers
        from eval_engine.litellm_client import complete
        dummy_model = LLMModel(
            name=judge_model, model_id=judge_model, provider="custom",
            endpoint="https://openrouter.ai/api/v1",
        )
        result = await complete(model=dummy_model, prompt=f"{JUDGE_SYSTEM}\n\n{user_msg}",
                               temperature=0.0, max_tokens=256)
        text = result.text.strip()

    # Parse response
    try:
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        data = json.loads(text)
        return float(data.get("score", 0.5)), str(data.get("reasoning", ""))
    except (json.JSONDecodeError, TypeError, KeyError):
        # Try to extract score from text
        import re
        m = re.search(r'"?score"?\s*[:=]\s*([0-9.]+)', text)
        if m:
            return float(m.group(1)), text[:200]
        return 0.5, f"Parse error: {text[:200]}"


# ── Agreement Metrics ──────────────────────────────────────────────────────────

def _cohens_kappa(scores_a: list[float], scores_b: list[float], threshold: float = 0.5) -> float:
    """Cohen's kappa between two binary judge classifications."""
    if len(scores_a) != len(scores_b) or not scores_a:
        return 0.0
    n = len(scores_a)
    a_binary = [1 if s >= threshold else 0 for s in scores_a]
    b_binary = [1 if s >= threshold else 0 for s in scores_b]

    agree = sum(1 for i in range(n) if a_binary[i] == b_binary[i])
    p_o = agree / n

    p_a1 = sum(a_binary) / n
    p_b1 = sum(b_binary) / n
    p_e = p_a1 * p_b1 + (1 - p_a1) * (1 - p_b1)

    if p_e == 1.0:
        return 1.0
    return round((p_o - p_e) / (1 - p_e), 4)


def _correlation(xs: list[float], ys: list[float]) -> float:
    """Pearson correlation."""
    if len(xs) != len(ys) or len(xs) < 3:
        return 0.0
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs) / n) or 1e-10
    sy = math.sqrt(sum((y - my) ** 2 for y in ys) / n) or 1e-10
    cov = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / n
    return round(cov / (sx * sy), 4)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/evaluate")
async def evaluate_with_judges(payload: EvaluateRequest, session: Session = Depends(get_session)):
    """Run multi-judge evaluation on campaign results."""
    campaign = session.get(Campaign, payload.campaign_id)
    if not campaign:
        raise HTTPException(404, detail="Campaign not found.")

    # Get completed runs + their results
    runs = session.exec(
        select(EvalRun).where(EvalRun.campaign_id == payload.campaign_id, EvalRun.status == JobStatus.COMPLETED)
    ).all()

    if not runs:
        raise HTTPException(400, detail="No completed runs to judge.")

    run_ids = [r.id for r in runs]
    results = session.exec(
        select(EvalResult).where(EvalResult.run_id.in_(run_ids)).limit(payload.max_items)
    ).all()

    if not results:
        raise HTTPException(400, detail="No results to judge.")

    # Run each judge on each item
    judge_evals = []
    total = len(results) * len(payload.judge_models)
    completed = 0

    for judge_model in payload.judge_models:
        for result in results:
            try:
                score, reasoning = await _judge_item(
                    judge_model, result.prompt, result.response, result.expected, payload.criteria,
                )
            except Exception as e:
                logger.warning(f"Judge {judge_model} failed on result {result.id}: {e}")
                # Skip — don't persist fake 0.5 scores (#64)
                continue

            je = JudgeEvaluation(
                campaign_id=payload.campaign_id,
                run_id=result.run_id,
                result_id=result.id,
                judge_model=judge_model,
                judge_score=score,
                judge_reasoning=reasoning[:500],
            )
            session.add(je)
            judge_evals.append(je)
            completed += 1

    session.commit()

    return {
        "campaign_id": payload.campaign_id,
        "judges": payload.judge_models,
        "criteria": payload.criteria,
        "items_judged": len(results),
        "evaluations_created": len(judge_evals),
        "avg_scores": {
            jm: round(sum(e.judge_score for e in judge_evals if e.judge_model == jm) / max(sum(1 for e in judge_evals if e.judge_model == jm), 1), 4)
            for jm in payload.judge_models
        },
    }


@router.get("/agreement/{campaign_id}")
def get_judge_agreement(campaign_id: int, session: Session = Depends(get_session)):
    """Compute inter-judge agreement (Cohen's kappa + Pearson correlation)."""
    evals = session.exec(
        select(JudgeEvaluation).where(JudgeEvaluation.campaign_id == campaign_id)
    ).all()

    if not evals:
        return {"agreement": {}, "judges": [], "computed": False}

    # Group by judge
    by_judge: dict[str, dict[int, float]] = {}
    for e in evals:
        by_judge.setdefault(e.judge_model, {})[e.result_id] = e.judge_score

    judges = sorted(by_judge.keys())
    if len(judges) < 2:
        return {
            "agreement": {},
            "judges": judges,
            "computed": True,
            "note": "Need at least 2 judges for agreement metrics.",
            "single_judge_avg": round(sum(e.judge_score for e in evals) / len(evals), 4),
        }

    # Pairwise agreement
    pairwise = {}
    for j1, j2 in combinations(judges, 2):
        common_ids = set(by_judge[j1].keys()) & set(by_judge[j2].keys())
        if len(common_ids) < 3:
            continue
        ids = sorted(common_ids)
        s1 = [by_judge[j1][i] for i in ids]
        s2 = [by_judge[j2][i] for i in ids]

        pairwise[f"{j1} × {j2}"] = {
            "cohens_kappa": _cohens_kappa(s1, s2),
            "pearson_r": _correlation(s1, s2),
            "n_items": len(ids),
            "avg_diff": round(sum(abs(s1[i] - s2[i]) for i in range(len(ids))) / len(ids), 4),
        }

    return {
        "agreement": pairwise,
        "judges": judges,
        "computed": True,
        "interpretation": {
            "kappa > 0.8": "Almost perfect agreement",
            "0.6 < kappa < 0.8": "Substantial agreement",
            "0.4 < kappa < 0.6": "Moderate agreement",
            "kappa < 0.4": "Poor agreement — judges disagree significantly",
        },
    }


@router.post("/calibrate")
def calibrate_judges(payload: CalibrateRequest, session: Session = Depends(get_session)):
    """Upload oracle (human) labels and compute judge calibration metrics."""
    # Store oracle labels
    for label in payload.oracle_labels:
        evals = session.exec(
            select(JudgeEvaluation).where(
                JudgeEvaluation.campaign_id == payload.campaign_id,
                JudgeEvaluation.result_id == label["result_id"],
            )
        ).all()
        for e in evals:
            e.oracle_score = label["score"]
            session.add(e)
    session.commit()

    # Compute calibration per judge
    all_evals = session.exec(
        select(JudgeEvaluation).where(
            JudgeEvaluation.campaign_id == payload.campaign_id,
            JudgeEvaluation.oracle_score != None,
        )
    ).all()

    if not all_evals:
        return {"calibration": {}, "computed": False, "note": "No oracle labels found."}

    by_judge: dict[str, list[JudgeEvaluation]] = {}
    for e in all_evals:
        by_judge.setdefault(e.judge_model, []).append(e)

    calibration = {}
    for judge, items in by_judge.items():
        judge_scores = [e.judge_score for e in items]
        oracle_scores = [e.oracle_score for e in items]

        # Calibration metrics
        bias = round(sum(j - o for j, o in zip(judge_scores, oracle_scores)) / len(items), 4)
        mae = round(sum(abs(j - o) for j, o in zip(judge_scores, oracle_scores)) / len(items), 4)
        pearson = _correlation(judge_scores, oracle_scores)
        kappa = _cohens_kappa(judge_scores, oracle_scores)

        # Ranking agreement (Kendall-like)
        concordant = 0
        discordant = 0
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                judge_diff = judge_scores[i] - judge_scores[j]
                oracle_diff = oracle_scores[i] - oracle_scores[j]
                if judge_diff * oracle_diff > 0:
                    concordant += 1
                elif judge_diff * oracle_diff < 0:
                    discordant += 1
        total_pairs = concordant + discordant
        rank_agreement = round(concordant / max(total_pairs, 1), 4)

        calibration[judge] = {
            "n_oracle_labels": len(items),
            "bias": bias,
            "mean_absolute_error": mae,
            "pearson_r": pearson,
            "cohens_kappa": kappa,
            "rank_agreement": rank_agreement,
            "reliability": "high" if pearson > 0.7 and mae < 0.2 else "medium" if pearson > 0.4 else "low",
        }

    return {
        "calibration": calibration,
        "computed": True,
        "interpretation": {
            "bias > 0": "Judge overscores relative to humans",
            "bias < 0": "Judge underscores relative to humans",
            "mae < 0.15": "Excellent calibration",
            "0.15 < mae < 0.3": "Acceptable calibration",
            "mae > 0.3": "Poor calibration — judge scores unreliable",
        },
    }


@router.get("/bias/{campaign_id}")
def detect_judge_bias(campaign_id: int, session: Session = Depends(get_session)):
    """Detect systematic biases in judge evaluations."""
    evals = session.exec(
        select(JudgeEvaluation).where(JudgeEvaluation.campaign_id == campaign_id)
    ).all()

    if not evals:
        return {"biases": [], "computed": False}

    # Get result details for analysis
    result_ids = list({e.result_id for e in evals})
    results = {r.id: r for r in session.exec(select(EvalResult).where(EvalResult.id.in_(result_ids))).all()}
    runs = {r.id: r for r in session.exec(select(EvalRun).where(EvalRun.campaign_id == campaign_id)).all()}
    models_db = {m.id: m for m in session.exec(select(LLMModel)).all()}

    by_judge: dict[str, list] = {}
    for e in evals:
        result = results.get(e.result_id)
        run = runs.get(e.run_id) if result else None
        model_name = models_db.get(run.model_id).name if run and run.model_id in models_db else "unknown"
        by_judge.setdefault(e.judge_model, []).append({
            "score": e.judge_score,
            "model_being_judged": model_name,
            "response_length": len(result.response) if result else 0,
        })

    biases = []
    for judge, items in by_judge.items():
        # Length bias: does the judge prefer longer responses?
        short = [i["score"] for i in items if i["response_length"] < 200]
        long = [i["score"] for i in items if i["response_length"] >= 200]
        if short and long:
            length_bias = round(sum(long) / len(long) - sum(short) / len(short), 4)
            if abs(length_bias) > 0.1:
                biases.append({
                    "judge": judge,
                    "bias_type": "length_bias",
                    "direction": "favors_long" if length_bias > 0 else "favors_short",
                    "magnitude": abs(length_bias),
                    "description": f"Judge scores longer responses {'higher' if length_bias > 0 else 'lower'} by {abs(length_bias):.2f} on average",
                })

        # Model bias: does the judge consistently favor one model?
        by_model: dict[str, list[float]] = {}
        for i in items:
            by_model.setdefault(i["model_being_judged"], []).append(i["score"])

        if len(by_model) >= 2:
            model_avgs = {m: sum(s) / len(s) for m, s in by_model.items()}
            global_avg = sum(i["score"] for i in items) / len(items)
            for model_name, avg in model_avgs.items():
                diff = round(avg - global_avg, 4)
                if abs(diff) > 0.15:
                    biases.append({
                        "judge": judge,
                        "bias_type": "model_preference",
                        "target_model": model_name,
                        "direction": "favors" if diff > 0 else "penalizes",
                        "magnitude": abs(diff),
                        "description": f"Judge {'favors' if diff > 0 else 'penalizes'} {model_name} by {abs(diff):.2f} vs global average",
                    })

    return {
        "biases": sorted(biases, key=lambda b: b["magnitude"], reverse=True),
        "computed": True,
        "total_evaluations": len(evals),
        "judges_analyzed": list(by_judge.keys()),
    }


@router.get("/summary/{campaign_id}")
def judge_summary(campaign_id: int, session: Session = Depends(get_session)):
    """Summary of all judge evaluations for a campaign."""
    evals = session.exec(
        select(JudgeEvaluation).where(JudgeEvaluation.campaign_id == campaign_id)
    ).all()

    if not evals:
        return {"judges": {}, "computed": False}

    by_judge: dict[str, list[float]] = {}
    for e in evals:
        by_judge.setdefault(e.judge_model, []).append(e.judge_score)

    return {
        "judges": {
            j: {
                "n_evaluations": len(scores),
                "avg_score": round(sum(scores) / len(scores), 4),
                "min_score": min(scores),
                "max_score": max(scores),
                "std_dev": round(math.sqrt(sum((s - sum(scores)/len(scores))**2 for s in scores) / len(scores)), 4),
            }
            for j, scores in by_judge.items()
        },
        "computed": True,
        "total_evaluations": len(evals),
        "has_oracle": any(e.oracle_score is not None for e in evals),
    }
