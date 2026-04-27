"""
Strategy memory for the coevolution engine.

A "strategy" is a named template the attacker can select and instantiate.
Each strategy carries running statistics: number of times it was tried,
sum of judge scores, last_used. The engine ranks strategies by their
posterior success rate using a Beta-Binomial model with weak priors so
new strategies aren't immediately drowned out by long-running ones.

The memory is intentionally a plain Python dataclass — persistence is
the caller's responsibility (e.g. JSON dump, DB row). We keep this
module free of I/O so it's trivially testable.
"""
from __future__ import annotations

import dataclasses
import math
from typing import Optional


@dataclasses.dataclass
class Strategy:
    """One named adversarial strategy with running stats.

    Fields:
        name:           short stable identifier ("role_play", "many_shot", ...)
        template:       free-form prompt template; engine asks the
                        attacker to instantiate this for a given objective.
        n_tried:        number of times this strategy has been used.
        sum_score:      sum of judge scores (in [0,1]) over those uses.
        last_used:      monotonic counter — newest used has the highest value.
        notes:          operator commentary, never used for ranking.
    """

    name: str
    template: str
    n_tried: int = 0
    sum_score: float = 0.0
    last_used: int = 0
    notes: str = ""

    @property
    def empirical_score(self) -> float:
        """Mean judge score; 0.0 if never tried."""
        if self.n_tried == 0:
            return 0.0
        return self.sum_score / self.n_tried

    def posterior_score(self, prior_a: float = 1.0, prior_b: float = 1.0) -> float:
        """Beta-Binomial posterior mean of success rate.

        With prior_a=prior_b=1 (uniform Beta(1,1)), we get the standard
        Laplace-smoothed estimate (sum + 1) / (n + 2). Larger priors make
        the estimate slower to react to new data — useful when a few
        early lucky/unlucky pulls would otherwise dominate.
        """
        return (self.sum_score + prior_a) / (self.n_tried + prior_a + prior_b)

    def record(self, score: float, *, clock: int) -> "Strategy":
        """Return a new Strategy with this round's outcome merged in.

        Score is clamped to [0, 1] defensively.
        """
        s = max(0.0, min(1.0, float(score)))
        return dataclasses.replace(
            self,
            n_tried=self.n_tried + 1,
            sum_score=self.sum_score + s,
            last_used=clock,
        )


class StrategyMemory:
    """Mutable container of strategies with rank-by-score selection.

    The memory is per-attacker (not per-tenant). Callers who need to
    isolate memories across tenants instantiate one StrategyMemory each
    and persist them independently.

    The class is intentionally small — selection logic is exposed for
    tests; persistence is left to the caller.
    """

    def __init__(self, strategies: Optional[list[Strategy]] = None):
        self._strategies: dict[str, Strategy] = {}
        self._clock = 0
        for s in strategies or ():
            self.add(s)

    # ── Construction ────────────────────────────────────────────────

    def add(self, strategy: Strategy) -> None:
        """Add a new strategy; raises if the name is already taken."""
        if not strategy.name or not isinstance(strategy.name, str):
            raise ValueError("strategy.name must be a non-empty string")
        if strategy.name in self._strategies:
            raise ValueError(f"strategy {strategy.name!r} already in memory")
        self._strategies[strategy.name] = strategy

    def names(self) -> tuple[str, ...]:
        """Stable, sorted list of strategy names."""
        return tuple(sorted(self._strategies.keys()))

    def get(self, name: str) -> Strategy:
        return self._strategies[name]

    def __contains__(self, name: str) -> bool:
        return name in self._strategies

    def __len__(self) -> int:
        return len(self._strategies)

    # ── Selection ───────────────────────────────────────────────────

    def select(
        self,
        *,
        epsilon: float = 0.1,
        recency_bias: float = 0.0,
        rng=None,
    ) -> Strategy:
        """Pick a strategy: ε-greedy with optional recency bias.

        With probability ε, picks uniformly at random (exploration). The
        rest of the time (exploitation), picks the strategy with the
        highest ``posterior_score + recency_bias * normalized_recency``.

        recency_bias gives a small bonus to recently-used strategies, so
        a long-stale "winner" doesn't suppress newer ones forever.

        Raises if no strategies are present.
        """
        import random
        if not self._strategies:
            raise LookupError("StrategyMemory is empty")
        if epsilon < 0.0 or epsilon > 1.0:
            raise ValueError("epsilon must be in [0,1]")

        rng = rng or random.Random()

        if rng.random() < epsilon:
            names = sorted(self._strategies.keys())
            return self._strategies[rng.choice(names)]

        # Exploit: highest posterior + recency bonus.
        clock = max(s.last_used for s in self._strategies.values())
        denom = max(1, clock)
        ranked = sorted(
            self._strategies.values(),
            key=lambda s: (
                -(s.posterior_score() + recency_bias * (s.last_used / denom)),
                s.name,  # stable tiebreaker
            ),
        )
        return ranked[0]

    # ── Updates ─────────────────────────────────────────────────────

    def record(self, name: str, score: float) -> None:
        """Record one round's outcome for a strategy.

        Increments the internal clock so subsequent ``last_used`` values
        are monotonically increasing.
        """
        if name not in self._strategies:
            raise KeyError(f"unknown strategy {name!r}")
        self._clock += 1
        self._strategies[name] = self._strategies[name].record(
            score, clock=self._clock
        )

    # ── Inspection ──────────────────────────────────────────────────

    def top_n(self, n: int = 3) -> tuple[Strategy, ...]:
        """The N strategies with the highest posterior_score().

        Used to brief the attacker LLM ("here are the top-3 working
        techniques so far").
        """
        if n <= 0:
            return ()
        ranked = sorted(
            self._strategies.values(),
            key=lambda s: (-s.posterior_score(), s.name),
        )
        return tuple(ranked[:n])

    def to_dict(self) -> dict:
        """JSON-friendly dump for persistence."""
        return {
            "clock": self._clock,
            "strategies": [
                dataclasses.asdict(s) for s in self._strategies.values()
            ],
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "StrategyMemory":
        m = cls()
        m._clock = int(payload.get("clock", 0))
        for raw in payload.get("strategies", ()):
            m.add(Strategy(**raw))
        return m


def _safe_log(x: float) -> float:
    """log with a tiny floor — used by exploration heuristics."""
    return math.log(max(x, 1e-12))
