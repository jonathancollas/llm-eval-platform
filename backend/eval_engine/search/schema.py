"""
Search engine — strict schema contracts.

Every wire response is a Pydantic model. No dict-shaped payloads leak into
the frontend. The intent classifier returns a typed payload so TypeScript
can discriminate cleanly.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field


class SearchIntent(str, Enum):
    NAVIGATE = "navigate"
    ASK = "ask"
    LAUNCH = "launch"
    ATTACK = "attack"
    UNKNOWN = "unknown"


# ── Typeahead ──────────────────────────────────────────────────────────────

class TypeaheadResult(BaseModel):
    """A single suggestion item shown under the search bar."""
    id: str                                           # stable unique id (e.g. "model:42")
    label: str                                        # primary display text
    subtitle: str = ""                                # secondary text
    kind: Literal[
        "model", "benchmark", "campaign", "route",
        "action", "incident", "paper",
    ]
    href: Optional[str] = None                        # navigation target if applicable
    action_hint: Optional[str] = None                 # e.g. "Launch eval" / "Open Red Room"
    icon: str = ""                                    # lucide icon name
    score: float = 0.0                                # ranking score (higher = better)


class TypeaheadGroup(BaseModel):
    """Suggestions grouped by kind for UI display."""
    kind: str
    label: str
    items: list[TypeaheadResult]


class TypeaheadResponse(BaseModel):
    query: str
    groups: list[TypeaheadGroup]
    latency_ms: int = 0


# ── Intent classification ──────────────────────────────────────────────────

class NavigatePayload(BaseModel):
    kind: Literal["navigate"] = "navigate"
    route: str
    label: str = ""


class AskSource(BaseModel):
    id: str
    label: str
    href: Optional[str] = None
    snippet: str = ""


class AskPayload(BaseModel):
    kind: Literal["ask"] = "ask"
    answer: str
    sources: list[AskSource] = Field(default_factory=list)
    # When True, the answer was produced by a static rule (no LLM call).
    deterministic: bool = False


class LaunchSlots(BaseModel):
    model_id: Optional[int] = None
    model_name: Optional[str] = None
    benchmark_ids: list[int] = Field(default_factory=list)
    benchmark_names: list[str] = Field(default_factory=list)
    max_samples: int = 50
    autonomy_level: Literal["L1", "L2", "L3", "L4", "L5"] = "L2"
    temperature: float = 0.0


class LaunchPreview(BaseModel):
    name: str
    description: str = ""
    model_ids: list[int]
    benchmark_ids: list[int]
    max_samples: int
    temperature: float
    run_context_json: str
    # Human-facing estimates
    estimated_cost_usd: float
    estimated_time_minutes: float
    # Anything the user must confirm or supply
    needs_confirmation: list[str] = Field(default_factory=list)


class LaunchPayload(BaseModel):
    kind: Literal["launch"] = "launch"
    slots: LaunchSlots
    preview: Optional[LaunchPreview] = None
    # If set, the frontend surfaces a disambiguation menu.
    clarification: Optional[str] = None


class AttackPayload(BaseModel):
    kind: Literal["attack"] = "attack"
    target_model_id: Optional[int] = None
    target_model_name: Optional[str] = None
    goal: str
    aggressiveness: int = 3                      # 1..5
    engines: list[str] = Field(default_factory=lambda: ["native"])
    autonomy_level: Literal["L1", "L2", "L3", "L4", "L5"] = "L3"
    # Always requires explicit confirmation before /redbox/attack is called.
    requires_role: Literal["evaluator", "admin"] = "evaluator"
    clarification: Optional[str] = None


IntentPayload = Union[NavigatePayload, AskPayload, LaunchPayload, AttackPayload]


class IntentResponse(BaseModel):
    query: str
    intent: SearchIntent
    confidence: float                                 # 0.0 .. 1.0
    payload: IntentPayload = Field(discriminator="kind")
    # If True, the classifier is confident enough to execute directly.
    can_auto_execute: bool = False
    latency_ms: int = 0


# ── Execute ────────────────────────────────────────────────────────────────

class ExecuteRequest(BaseModel):
    query: str
    # Optional: force a specific intent (set by UI when user picks from the
    # disambiguation menu) to skip the classifier.
    forced_intent: Optional[SearchIntent] = None
    # Optional: role context for ATTACK eligibility.
    role: Literal["viewer", "evaluator", "admin"] = "viewer"


class ExecuteResponse(BaseModel):
    intent_response: IntentResponse
    # For LAUNCH: the exact CampaignCreate-shaped body the user should POST.
    # For ATTACK: the AttackCampaignRequest-shaped body.
    # For NAVIGATE / ASK: null.
    submit_body: Optional[dict] = None
    submit_endpoint: Optional[str] = None
