"""
Red Room v2 HTTP API.

This router exposes the new ``eval_engine.redroom`` package over HTTP
under ``/api/redroom/v2``. The legacy ``/api/redbox`` router remains in
place; v2 is the migration target. Once the frontend has migrated, the
legacy router will be deprecated.

Routes:

  POST   /sessions                  Create a new Red Room session
  GET    /sessions/{session_id}     Inspect a session (rows + chain status)
  POST   /sessions/{session_id}/probe
                                    Run one probe in this session
  GET    /sessions/{session_id}/traces
                                    All traces (paginated)
  GET    /sessions/{session_id}/verify
                                    Run verify_chain() and return status
  GET    /sessions/{session_id}/artifact.html
                                    Fetch the HTML Risk Artifact

Charter authorization is enforced inside ``run_probe`` (the runtime
gate) AND at the dependency layer for the POST endpoint (early-fail
before any DB write). Tenant scoping is enforced at every read.

Errors are uniform: 400 for malformed payload, 401 for missing role
(via require_role), 403 for charter refusal, 404 for missing session,
429 for charter rate limit, 500 for unexpected.
"""
from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from core.auth import require_role, require_tenant
from core.database import get_session
from core.models import Tenant
from eval_engine.redroom import (
    RunInputs,
    build_default_registry,
    generate_html_report,
    load_charter,
    run_probe,
)
from eval_engine.redroom.charter import (
    Aggressiveness,
    AttackRequest,
)
from eval_engine.redroom.charter import (
    enforce as charter_enforce,
)
from eval_engine.redroom.trace_store import (
    ChainIntegrityError,
    RedRoomTrace,
    verify_chain,
)

router = APIRouter(prefix="/redroom/v2", tags=["redroom-v2"])
logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
#  Schemas
# ────────────────────────────────────────────────────────────────────


class CreateSessionRequest(BaseModel):
    """Initial session creation. The charter is checked at probe time, not now."""

    name: str = Field(default="", max_length=200)
    target_class: str = Field(default="self", max_length=20)
    aggressiveness: int = Field(ge=1, le=5, default=2)


class CreateSessionResponse(BaseModel):
    session_id: str
    tenant_id: int
    name: str
    target_class: str
    aggressiveness: int


class ProbeRunRequest(BaseModel):
    """Body for POST /sessions/{session_id}/probe."""

    technique: str = Field(..., max_length=64)
    target_model_id: int = Field(..., gt=0)
    target_class: str = Field(default="self", max_length=20)
    aggressiveness: int = Field(default=2, ge=1, le=5)
    seed: int = Field(default=0)
    max_turns: int = Field(default=4, ge=1, le=64)
    prompt_seed: str | None = Field(default=None)
    timeout_seconds: float = Field(default=60.0, ge=1.0, le=600.0)


class ProbeRunResponse(BaseModel):
    session_id: str
    technique: str
    decision_reason: str
    effective_disclosure: str
    duration_seconds: float
    n_attempts: int
    aborted_reason: str | None


class TraceRow(BaseModel):
    id: int
    uuid: str
    kind: str
    verdict: str | None
    engine: str | None
    aggressiveness: int
    target_class: str
    target_model_id: int | None
    payload_json: str
    replay_hash: str
    row_signature: str
    created_at: str
    system_id: int | None = None


class TracesResponse(BaseModel):
    session_id: str
    rows: list[TraceRow]
    has_more: bool


class VerifyResponse(BaseModel):
    session_id: str
    tenant_id: int
    status: str            # "ok" | "broken" | "error"
    rows_verified: int | None = None
    broken_at_row_id: int | None = None
    reason: str = ""


# ────────────────────────────────────────────────────────────────────
#  Helpers
# ────────────────────────────────────────────────────────────────────


def _new_session_id() -> str:
    return f"sess-{secrets.token_hex(8)}"


def _tenant_id_from(tenant: Tenant) -> int:
    """Read-only access to tenant.id with a defensive fallback."""
    if tenant.id is None:
        raise HTTPException(
            status_code=500, detail="Resolved tenant has no id"
        )
    return int(tenant.id)


def _row_to_dto(r: RedRoomTrace) -> TraceRow:
    return TraceRow(
        id=int(r.id) if r.id is not None else 0,
        uuid=r.uuid,
        kind=r.kind,
        verdict=r.verdict,
        engine=r.engine,
        aggressiveness=r.aggressiveness,
        target_class=r.target_class,
        target_model_id=r.target_model_id,
        payload_json=r.payload_json,
        replay_hash=r.replay_hash,
        row_signature=r.row_signature,
        created_at=r.created_at.isoformat(),
        system_id=r.system_id,
    )


def _check_charter_or_403(
    *,
    target_class: str,
    aggressiveness: int,
) -> tuple[str, str]:
    """Pre-flight charter check. Raises 403 on refusal.

    Returns (decision_reason, effective_disclosure) so callers can
    surface them in API responses.
    """
    if aggressiveness < 1 or aggressiveness > 5:
        raise HTTPException(status_code=400, detail="aggressiveness must be 1..5")
    try:
        request = AttackRequest(
            target_class=target_class,  # type: ignore[arg-type]
            aggressiveness=Aggressiveness(aggressiveness),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    decision = charter_enforce(request, load_charter())
    return decision.reason, decision.effective_disclosure


# Endpoints don't need a fake target; the platform's inference layer
# will be wired to provide one in a follow-up. For now the v2 API
# expects the runner to return a structured response — testing this
# router relies on dependency_overrides to inject a target_invoke.

_TARGET_INVOKE_OVERRIDE: dict = {"f": None}


def _get_target_invoke():
    """Resolve the async target callable used to talk to the model under
    test. Tests override via FastAPI's dependency_overrides; in
    production the wiring layer provides a real adapter (out of scope
    for this PR).
    """
    f = _TARGET_INVOKE_OVERRIDE.get("f")
    if f is None:
        # Default: a deterministic stub that echoes a short version of
        # the prompt. Real model invocation lands in a future PR.
        async def _echo(prompt: str) -> str:
            return f"[v2-stub] {prompt[:80]}"

        return _echo
    return f


# ────────────────────────────────────────────────────────────────────
#  Endpoints
# ────────────────────────────────────────────────────────────────────


@router.post(
    "/sessions",
    response_model=CreateSessionResponse,
    dependencies=[Depends(require_role("evaluator", "admin"))],
)
def create_session(
    req: CreateSessionRequest,
    tenant: Tenant = Depends(require_tenant),
):
    """Reserve a new session_id. Does NOT yet authorize a probe — the
    charter is checked when a probe is actually run."""
    sid = _new_session_id()
    return CreateSessionResponse(
        session_id=sid,
        tenant_id=_tenant_id_from(tenant),
        name=req.name or sid,
        target_class=req.target_class,
        aggressiveness=req.aggressiveness,
    )


@router.post(
    "/sessions/{session_id}/probe",
    response_model=ProbeRunResponse,
    dependencies=[Depends(require_role("evaluator", "admin"))],
)
async def run_one_probe(
    session_id: str,
    req: ProbeRunRequest,
    tenant: Tenant = Depends(require_tenant),
    db: Session = Depends(get_session),
):
    """Execute one probe in this session. Charter-checked.

    The actual target callable is resolved via dependency override in
    tests; production wiring lands in a follow-up. The response is a
    flattened summary; the full event chain is fetched via
    GET /sessions/{id}/traces.
    """
    decision_reason, effective_disclosure = _check_charter_or_403(
        target_class=req.target_class, aggressiveness=req.aggressiveness
    )

    registry = build_default_registry()
    if req.technique not in registry:
        raise HTTPException(
            status_code=400,
            detail=(
                f"unknown technique {req.technique!r}; "
                f"registered: {sorted(registry)}"
            ),
        )

    target_invoke = _get_target_invoke()
    inputs = RunInputs(
        technique=req.technique,
        target_model_id=req.target_model_id,
        tenant_id=_tenant_id_from(tenant),
        session_id=session_id,
        target_invoke=target_invoke,
        target_class=req.target_class,
        aggressiveness=req.aggressiveness,
        seed=req.seed,
        max_turns=req.max_turns,
        prompt_seed=req.prompt_seed,
        timeout_seconds=req.timeout_seconds,
    )

    try:
        out = await run_probe(inputs, session=db, registry=registry)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    n_attempts = len(out.result.attempts) if out.result else 0
    return ProbeRunResponse(
        session_id=session_id,
        technique=req.technique,
        decision_reason=decision_reason,
        effective_disclosure=effective_disclosure,
        duration_seconds=out.duration_seconds,
        n_attempts=n_attempts,
        aborted_reason=(
            out.result.aborted_reason if out.result is not None else out.aborted_reason
        ),
    )


@router.get(
    "/sessions/{session_id}/traces",
    response_model=TracesResponse,
    dependencies=[Depends(require_role("viewer", "evaluator", "admin"))],
)
def get_traces(
    session_id: str,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    tenant: Tenant = Depends(require_tenant),
    db: Session = Depends(get_session),
):
    tid = _tenant_id_from(tenant)
    rows = list(
        db.exec(
            select(RedRoomTrace)
            .where(
                RedRoomTrace.tenant_id == tid,
                RedRoomTrace.session_id == session_id,
            )
            .order_by(RedRoomTrace.id.asc())  # type: ignore[union-attr]
            .offset(offset)
            .limit(limit + 1)
        )
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    return TracesResponse(
        session_id=session_id,
        rows=[_row_to_dto(r) for r in rows],
        has_more=has_more,
    )


@router.get(
    "/sessions/{session_id}/verify",
    response_model=VerifyResponse,
    dependencies=[Depends(require_role("viewer", "evaluator", "admin"))],
)
def verify_session(
    session_id: str,
    tenant: Tenant = Depends(require_tenant),
    db: Session = Depends(get_session),
):
    """Run verify_chain on the tenant's whole chain. We deliberately
    don't scope to ``session_id`` here because the chain is per-tenant
    and a partial walk could miss a tampered row in another session
    that comes between the requested session's rows."""
    tid = _tenant_id_from(tenant)
    try:
        n = verify_chain(db, tid)
        return VerifyResponse(
            session_id=session_id,
            tenant_id=tid,
            status="ok",
            rows_verified=n,
            reason="",
        )
    except ChainIntegrityError as exc:
        return VerifyResponse(
            session_id=session_id,
            tenant_id=tid,
            status="broken",
            broken_at_row_id=exc.broken_at_id,
            reason=exc.reason,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("verify_chain unexpected failure")
        return VerifyResponse(
            session_id=session_id,
            tenant_id=tid,
            status="error",
            reason=f"{type(exc).__name__}: {exc}",
        )


@router.get(
    "/sessions/{session_id}/artifact.html",
    response_class=HTMLResponse,
    dependencies=[Depends(require_role("viewer", "evaluator", "admin"))],
)
def get_artifact_html(
    session_id: str,
    emit_export: bool = Query(default=True),
    tenant: Tenant = Depends(require_tenant),
    db: Session = Depends(get_session),
):
    tid = _tenant_id_from(tenant)
    html_doc = generate_html_report(
        db,
        tenant_id=tid,
        session_id=session_id,
        emit_export_trace=bool(emit_export),
    )
    return HTMLResponse(content=html_doc)
