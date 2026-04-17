"""Trajectory Intelligence Engine — analyze agent execution traces."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class LoopDetection:
    detected: bool; loop_type: str
    loop_start_step: int = -1; loop_length: int = 0
    n_repetitions: int = 0; affected_steps: list = field(default_factory=list)
    severity: str = "none"

@dataclass
class RetryPattern:
    detected: bool; n_retries: int = 0
    strategy_unchanged: bool = False; tool_name: str = ""
    error_type: str = ""; steps: list = field(default_factory=list)

@dataclass
class ToolMisuseEvent:
    step_index: int; tool_name: str; misuse_type: str; details: str = ""

@dataclass
class TrajectoryAnalysisResult:
    steps_analyzed: int; loop_detection: LoopDetection
    retry_patterns: list; tool_misuse_events: list
    context_overflow_detected: bool; goal_drift_detected: bool
    failure_types: list; failure_severity: str
    efficiency_score: float; autonomy_score: float
    adaptivity_score: float; overall_quality_score: float
    recommendations: list

class TrajectoryAnalysisEngine:
    def detect_loops(self, steps: list) -> LoopDetection:
        seen = {}
        for i, step in enumerate(steps):
            key = (step.get("input_text","")[:100], step.get("tool_name",""))
            if key in seen:
                length = i - seen[key]
                return LoopDetection(detected=True, loop_type="exact",
                    loop_start_step=seen[key], loop_length=length,
                    n_repetitions=2, affected_steps=[seen[key], i],
                    severity="high" if length <= 2 else "medium")
            seen[key] = i
        return LoopDetection(detected=False, loop_type="none")

    def detect_retry_patterns(self, steps: list) -> list:
        results = []; i = 0
        while i < len(steps):
            if not steps[i].get("tool_success", True):
                tool = steps[i].get("tool_name","")
                error = steps[i].get("error_type","")
                retry_steps = [i]
                j = i+1
                while j < len(steps) and not steps[j].get("tool_success", True) and steps[j].get("tool_name","") == tool:
                    retry_steps.append(j); j += 1
                if len(retry_steps) > 1:
                    results.append(RetryPattern(detected=True, n_retries=len(retry_steps)-1,
                        strategy_unchanged=True, tool_name=tool, error_type=error, steps=retry_steps))
                i = j
            else:
                i += 1
        return results

    def detect_tool_misuse(self, steps: list) -> list:
        events = []
        tool_counts = {}
        for i, step in enumerate(steps):
            tool = step.get("tool_name")
            if step.get("step_type") == "tool_call" and not tool:
                events.append(ToolMisuseEvent(i, "", "hallucinated", "tool_call step with no tool_name"))
            if tool:
                tool_counts[tool] = tool_counts.get(tool, 0) + 1
                if tool_counts[tool] > 3:
                    events.append(ToolMisuseEvent(i, tool, "excessive_calls", f"Called {tool_counts[tool]} times"))
        return events

    def classify_failure(self, steps: list, task_description="") -> list:
        failures = []
        loop = self.detect_loops(steps)
        if loop.detected: failures.append("infinite_loop")
        retries = self.detect_retry_patterns(steps)
        if retries: failures.append("repeated_failures")
        if any(s.get("error_type") for s in steps): failures.append("tool_error")
        if any(s.get("context_window_tokens",0) > 100000 for s in steps): failures.append("context_overflow")
        return failures

    def compute_efficiency_score(self, steps: list, task_completed: bool) -> float:
        if not steps: return 1.0
        completed = sum(1 for s in steps if s.get("tool_success", True))
        base = completed / len(steps)
        return round(base * (1.0 if task_completed else 0.5), 4)

    def compute_adaptivity_score(self, steps: list) -> float:
        n = len(steps)
        if n == 0: return 1.0
        recoveries = 0; errors = 0
        for i in range(n-1):
            if not steps[i].get("tool_success", True):
                errors += 1
                if steps[i+1].get("tool_success", True): recoveries += 1
        return round(recoveries / max(errors, 1), 4) if errors > 0 else 1.0

    def compute_autonomy_score(self, steps: list) -> float:
        if not steps: return 1.0
        error_steps = sum(1 for s in steps if s.get("error_type") or not s.get("tool_success", True))
        return max(0.0, round(1 - error_steps/len(steps), 4))

    def analyze_steps(self, steps: list) -> TrajectoryAnalysisResult:
        loop = self.detect_loops(steps)
        retries = self.detect_retry_patterns(steps)
        misuse = self.detect_tool_misuse(steps)
        failures = self.classify_failure(steps)
        autonomy = self.compute_autonomy_score(steps)
        adaptivity = self.compute_adaptivity_score(steps)
        efficiency = self.compute_efficiency_score(steps, True)
        quality = round((autonomy + adaptivity + efficiency) / 3, 4)
        severity = "high" if loop.detected else "medium" if failures else "low"
        recs = []
        if loop.detected: recs.append("Investigate loop at step " + str(loop.loop_start_step))
        if retries: recs.append("Improve error handling for repeated failures")
        ctx_overflow = any(s.get("context_window_tokens",0)>100000 for s in steps)
        return TrajectoryAnalysisResult(
            steps_analyzed=len(steps), loop_detection=loop,
            retry_patterns=retries, tool_misuse_events=misuse,
            context_overflow_detected=ctx_overflow, goal_drift_detected=False,
            failure_types=failures, failure_severity=severity,
            efficiency_score=efficiency, autonomy_score=autonomy,
            adaptivity_score=adaptivity, overall_quality_score=quality,
            recommendations=recs,
        )
