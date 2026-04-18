"""
Event-Sourced Evaluation Pipeline (#45)
=========================================
Replaces the imperative runner with an event-driven architecture.

Every state transition in a campaign emits a typed, immutable event.
Events are persisted to DB and can be replayed to reconstruct any run state.

Scientific grounding:
  - Enables deterministic replay (#46): reproduce any result exactly
  - Enables multi-agent audit trails (#60): full event log per agent
  - Enables continuous monitoring (#79): subscribe to event stream in production
  - Provides the substrate for mech interp validation (#85):
    correlate internal states with observable event sequences

Architecture:
    EvalEngine
        ↓ emit(event)
    EventBus
        ├─ persist → eval_events table
        ├─ → subscribers (live telemetry, monitoring, alerts)
        └─ replay → reconstruct campaign state from event log

Event taxonomy (append-only):
    CampaignStarted | CampaignCompleted | CampaignFailed | CampaignCancelled
    RunStarted      | RunCompleted      | RunFailed
    ItemStarted     | ItemCompleted     | ItemFailed
    GenomeComputed  | JudgeCompleted    | SandbaggingSignal
    InjectionDetected (multi-agent)
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
from typing import Any, Callable, Coroutine, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


# ── Event types ───────────────────────────────────────────────────────────────

class EventType(str, Enum):
    # Campaign lifecycle
    CAMPAIGN_STARTED    = "campaign.started"
    CAMPAIGN_COMPLETED  = "campaign.completed"
    CAMPAIGN_FAILED     = "campaign.failed"
    CAMPAIGN_CANCELLED  = "campaign.cancelled"
    CAMPAIGN_PROGRESS   = "campaign.progress"

    # Run lifecycle (one model × one benchmark)
    RUN_STARTED         = "run.started"
    RUN_COMPLETED       = "run.completed"
    RUN_FAILED          = "run.failed"

    # Item lifecycle (one prompt → response)
    ITEM_STARTED        = "item.started"
    ITEM_COMPLETED      = "item.completed"
    ITEM_FAILED         = "item.failed"

    # Post-processing
    GENOME_COMPUTED     = "genome.computed"
    JUDGE_COMPLETED     = "judge.completed"
    CONTAMINATION_FLAG  = "contamination.flag"
    SANDBAGGING_SIGNAL  = "sandbagging.signal"

    # Multi-agent specific
    AGENT_STEP          = "agent.step"
    INJECTION_DETECTED  = "injection.detected"
    GOAL_DRIFT_DETECTED = "goal_drift.detected"


@dataclass(frozen=True)
class EvalEvent:
    """
    Immutable event record.

    All events share this schema — payload varies by event_type.
    Frozen to enforce immutability (events are facts, not opinions).
    """
    event_id: str           # UUID — globally unique
    event_type: EventType
    campaign_id: int
    timestamp: str          # ISO 8601 UTC
    sequence: int           # Monotonic per-campaign sequence number
    payload: dict           # Event-specific data

    # Optional foreign keys for efficient querying
    run_id: Optional[int] = None
    model_id: Optional[int] = None
    benchmark_id: Optional[int] = None

    @classmethod
    def create(
        cls,
        event_type: EventType,
        campaign_id: int,
        sequence: int,
        payload: dict,
        run_id: Optional[int] = None,
        model_id: Optional[int] = None,
        benchmark_id: Optional[int] = None,
    ) -> "EvalEvent":
        return cls(
            event_id=str(uuid4()),
            event_type=event_type,
            campaign_id=campaign_id,
            timestamp=datetime.now(UTC).isoformat(),
            sequence=sequence,
            payload=payload,
            run_id=run_id,
            model_id=model_id,
            benchmark_id=benchmark_id,
        )

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "campaign_id": self.campaign_id,
            "timestamp": self.timestamp,
            "sequence": self.sequence,
            "payload": self.payload,
            "run_id": self.run_id,
            "model_id": self.model_id,
            "benchmark_id": self.benchmark_id,
        }


# ── Subscriber protocol ───────────────────────────────────────────────────────

EventHandler = Callable[[EvalEvent], Coroutine[Any, Any, None]]


# ── Event Bus ─────────────────────────────────────────────────────────────────

class EventBus:
    """
    In-process async event bus.

    Responsibilities:
    1. Persist events to DB (primary store, enables replay)
    2. Fan-out to all registered async subscribers
    3. Maintain per-campaign sequence counter

    Thread safety: designed for single asyncio event loop.
    For multi-process deployments, replace _persist with a message broker.
    """

    def __init__(self):
        self._subscribers: dict[Optional[EventType], list[EventHandler]] = {}
        self._sequences: dict[int, int] = {}  # campaign_id → sequence counter
        self._lock = asyncio.Lock()

    def subscribe(
        self,
        handler: EventHandler,
        event_type: Optional[EventType] = None,  # None = subscribe to all
    ) -> None:
        """Register a subscriber. Handlers are called concurrently on emit."""
        self._subscribers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, handler: EventHandler, event_type: Optional[EventType] = None) -> None:
        handlers = self._subscribers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    async def emit(
        self,
        event_type: EventType,
        campaign_id: int,
        payload: dict,
        run_id: Optional[int] = None,
        model_id: Optional[int] = None,
        benchmark_id: Optional[int] = None,
    ) -> EvalEvent:
        """
        Emit an event:
        1. Assign sequence number
        2. Persist to DB
        3. Fan-out to subscribers (non-blocking, errors logged not raised)
        """
        async with self._lock:
            seq = self._sequences.get(campaign_id, 0) + 1
            self._sequences[campaign_id] = seq

        event = EvalEvent.create(
            event_type=event_type,
            campaign_id=campaign_id,
            sequence=seq,
            payload=payload,
            run_id=run_id,
            model_id=model_id,
            benchmark_id=benchmark_id,
        )

        # Persist first — even if subscribers fail, the event is recorded
        await self._persist(event)

        # Fan-out to subscribers (fire-and-forget with error isolation)
        handlers = (
            self._subscribers.get(event_type, [])
            + self._subscribers.get(None, [])  # wildcard subscribers
        )
        if handlers:
            await asyncio.gather(
                *[self._call_safe(h, event) for h in handlers],
                return_exceptions=True,
            )

        return event

    async def _persist(self, event: EvalEvent) -> None:
        """Persist to DB. Import here to avoid circular import at module level."""
        try:
            from sqlmodel import Session
            from core.database import engine
            from core.models import EvalEventRecord

            with Session(engine) as session:
                record = EvalEventRecord(
                    event_id=event.event_id,
                    event_type=event.event_type.value,
                    campaign_id=event.campaign_id,
                    run_id=event.run_id,
                    model_id=event.model_id,
                    benchmark_id=event.benchmark_id,
                    sequence=event.sequence,
                    payload_json=json.dumps(event.payload),
                    timestamp=datetime.fromisoformat(event.timestamp),
                )
                session.add(record)
                session.commit()
        except Exception as e:
            logger.error(f"[EventBus] Failed to persist {event.event_type}: {e}")

    @staticmethod
    async def _call_safe(handler: EventHandler, event: EvalEvent) -> None:
        try:
            await handler(event)
        except Exception as e:
            logger.warning(f"[EventBus] Subscriber {handler.__name__} raised: {e}")


# ── Replay Engine ─────────────────────────────────────────────────────────────

class ReplayEngine:
    """
    Reconstructs campaign state from its event log.

    Usage:
        engine = ReplayEngine()
        state = await engine.replay(campaign_id=42)
        state = await engine.replay(campaign_id=42, up_to_sequence=15)

    The reconstructed state is equivalent to what you'd observe by running
    the campaign again — but built from persisted events, not live execution.
    This enables:
    - Deterministic debugging of past runs
    - A/B comparison of identical conditions
    - Audit trail for safety-critical evaluations
    """

    async def replay(
        self,
        campaign_id: int,
        up_to_sequence: Optional[int] = None,
    ) -> "CampaignState":
        """
        Replay all events for a campaign and return reconstructed state.
        Pass up_to_sequence to replay only a prefix of the event log.
        """
        events = await self._load_events(campaign_id, up_to_sequence)
        state = CampaignState(campaign_id=campaign_id)

        for event in events:
            state.apply(event)

        return state

    async def diff(
        self,
        campaign_id: int,
        sequence_a: int,
        sequence_b: int,
    ) -> dict:
        """
        Compute the state difference between two points in the event log.
        Useful for understanding what changed between two checkpoint states.
        """
        state_a = await self.replay(campaign_id, up_to_sequence=sequence_a)
        state_b = await self.replay(campaign_id, up_to_sequence=sequence_b)
        return state_a.diff(state_b)

    @staticmethod
    async def _load_events(
        campaign_id: int,
        up_to_sequence: Optional[int],
    ) -> list[EvalEvent]:
        try:
            from sqlmodel import Session, select
            from core.database import engine
            from core.models import EvalEventRecord

            with Session(engine) as session:
                query = (
                    select(EvalEventRecord)
                    .where(EvalEventRecord.campaign_id == campaign_id)
                    .order_by(EvalEventRecord.sequence)
                )
                if up_to_sequence is not None:
                    query = query.where(EvalEventRecord.sequence <= up_to_sequence)

                records = session.exec(query).all()

            return [
                EvalEvent(
                    event_id=r.event_id,
                    event_type=EventType(r.event_type),
                    campaign_id=r.campaign_id,
                    timestamp=r.timestamp.isoformat(),
                    sequence=r.sequence,
                    payload=json.loads(r.payload_json),
                    run_id=r.run_id,
                    model_id=r.model_id,
                    benchmark_id=r.benchmark_id,
                )
                for r in records
            ]
        except Exception as e:
            logger.error(f"[ReplayEngine] Failed to load events: {e}")
            return []


@dataclass
class RunState:
    run_id: int
    model_id: int
    benchmark_id: int
    status: str = "pending"
    score: Optional[float] = None
    items_completed: int = 0
    items_failed: int = 0
    total_cost: float = 0.0
    total_latency_ms: int = 0
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


@dataclass
class CampaignState:
    """Reconstructed campaign state from event log."""
    campaign_id: int
    status: str = "pending"
    progress: float = 0.0
    runs: dict[int, RunState] = field(default_factory=dict)  # run_id → RunState
    total_items: int = 0
    completed_items: int = 0
    failed_items: int = 0
    total_cost_usd: float = 0.0
    genome_computed: bool = False
    judge_completed: bool = False
    sandbagging_signals: list[dict] = field(default_factory=list)
    events_applied: int = 0
    last_event_sequence: int = 0
    error: Optional[str] = None

    def apply(self, event: EvalEvent) -> None:
        """Apply one event to mutate state. The heart of event sourcing."""
        self.events_applied += 1
        self.last_event_sequence = event.sequence
        p = event.payload

        if event.event_type == EventType.CAMPAIGN_STARTED:
            self.status = "running"

        elif event.event_type == EventType.CAMPAIGN_COMPLETED:
            self.status = "completed"
            self.progress = 100.0

        elif event.event_type == EventType.CAMPAIGN_FAILED:
            self.status = "failed"
            self.error = p.get("error")

        elif event.event_type == EventType.CAMPAIGN_CANCELLED:
            self.status = "cancelled"

        elif event.event_type == EventType.CAMPAIGN_PROGRESS:
            self.progress = p.get("progress", self.progress)

        elif event.event_type == EventType.RUN_STARTED:
            if event.run_id:
                self.runs[event.run_id] = RunState(
                    run_id=event.run_id,
                    model_id=event.model_id or 0,
                    benchmark_id=event.benchmark_id or 0,
                    status="running",
                    started_at=event.timestamp,
                )

        elif event.event_type == EventType.RUN_COMPLETED:
            if event.run_id and event.run_id in self.runs:
                run = self.runs[event.run_id]
                run.status = "completed"
                run.score = p.get("score")
                run.total_cost = p.get("total_cost_usd", 0.0)
                run.total_latency_ms = p.get("total_latency_ms", 0)
                run.completed_at = event.timestamp
                self.total_cost_usd += run.total_cost

        elif event.event_type == EventType.RUN_FAILED:
            if event.run_id and event.run_id in self.runs:
                self.runs[event.run_id].status = "failed"
                self.runs[event.run_id].error = p.get("error")

        elif event.event_type == EventType.ITEM_COMPLETED:
            self.completed_items += 1
            self.total_items = max(self.total_items, p.get("item_index", 0) + 1)
            if event.run_id and event.run_id in self.runs:
                self.runs[event.run_id].items_completed += 1

        elif event.event_type == EventType.ITEM_FAILED:
            self.failed_items += 1
            if event.run_id and event.run_id in self.runs:
                self.runs[event.run_id].items_failed += 1

        elif event.event_type == EventType.GENOME_COMPUTED:
            self.genome_computed = True

        elif event.event_type == EventType.JUDGE_COMPLETED:
            self.judge_completed = True

        elif event.event_type == EventType.SANDBAGGING_SIGNAL:
            self.sandbagging_signals.append(p)

    def diff(self, other: "CampaignState") -> dict:
        """Return what changed between this state and another."""
        changes = {}
        if self.status != other.status:
            changes["status"] = {"from": self.status, "to": other.status}
        if abs(self.progress - other.progress) > 0.1:
            changes["progress"] = {"from": round(self.progress, 1), "to": round(other.progress, 1)}
        if self.completed_items != other.completed_items:
            changes["completed_items"] = {"from": self.completed_items, "to": other.completed_items}
        # Run-level diffs
        run_changes = {}
        for run_id in set(self.runs) | set(other.runs):
            a = self.runs.get(run_id)
            b = other.runs.get(run_id)
            if a and b and a.status != b.status:
                run_changes[run_id] = {"status": {"from": a.status, "to": b.status}}
            elif not a and b:
                run_changes[run_id] = {"added": True}
        if run_changes:
            changes["runs"] = run_changes
        return changes

    @property
    def summary(self) -> dict:
        completed = sum(1 for r in self.runs.values() if r.status == "completed")
        failed = sum(1 for r in self.runs.values() if r.status == "failed")
        return {
            "campaign_id": self.campaign_id,
            "status": self.status,
            "progress": round(self.progress, 1),
            "runs": {
                "total": len(self.runs),
                "completed": completed,
                "failed": failed,
                "running": len(self.runs) - completed - failed,
            },
            "items": {
                "completed": self.completed_items,
                "failed": self.failed_items,
            },
            "total_cost_usd": round(self.total_cost_usd, 6),
            "events_applied": self.events_applied,
            "last_sequence": self.last_event_sequence,
            "genome_computed": self.genome_computed,
            "judge_completed": self.judge_completed,
            "sandbagging_signals": len(self.sandbagging_signals),
        }


# ── Singleton bus ─────────────────────────────────────────────────────────────

# One global bus per process — all parts of the app share this instance
_bus: Optional[EventBus] = None


def get_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus


def get_replay_engine() -> ReplayEngine:
    return ReplayEngine()


# ── Built-in subscribers ──────────────────────────────────────────────────────

async def _live_telemetry_subscriber(event: EvalEvent) -> None:
    """
    Updates Campaign DB fields on key events for live UI polling.
    This replaces the imperative progress updates in runner.py.
    """
    if event.event_type not in (
        EventType.CAMPAIGN_PROGRESS,
        EventType.CAMPAIGN_COMPLETED,
        EventType.CAMPAIGN_FAILED,
        EventType.ITEM_COMPLETED,
    ):
        return

    try:
        from sqlmodel import Session
        from core.database import engine
        from core.models import Campaign

        with Session(engine) as session:
            campaign = session.get(Campaign, event.campaign_id)
            if not campaign:
                return

            p = event.payload
            if event.event_type == EventType.CAMPAIGN_PROGRESS:
                campaign.progress = p.get("progress", campaign.progress)
                campaign.current_item_index = p.get("current_item_index")
                campaign.current_item_total = p.get("current_item_total")
                campaign.current_item_label = p.get("current_item_label")

            elif event.event_type in (EventType.CAMPAIGN_COMPLETED, EventType.CAMPAIGN_FAILED):
                from datetime import datetime as _dt, UTC
                campaign.completed_at = _dt.utcnow()

            session.add(campaign)
            session.commit()
    except Exception as e:
        logger.debug(f"[telemetry subscriber] {e}")


def register_default_subscribers() -> None:
    """Call once at app startup to wire up built-in subscribers."""
    bus = get_bus()
    bus.subscribe(_live_telemetry_subscriber)
    logger.info("[EventBus] Default subscribers registered.")
