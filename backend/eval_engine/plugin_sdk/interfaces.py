from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class PluginManifest:
    name: str; version: str; author: str; description: str
    capability_tags: list = field(default_factory=list)
    domain: str = ""; license: str = "MIT"; homepage: str = ""
    dependencies: list = field(default_factory=list)
    mercury_min_version: str = "1.0.0"

@dataclass
class MetricResult:
    metric_name: str; value: float
    ci_lower: float = 0.0; ci_upper: float = 1.0
    n_samples: int = 0; metadata: dict = field(default_factory=dict)

@dataclass
class JudgeScore:
    score: float; reasoning: str
    confidence: float = 1.0; criteria: str = ""

@dataclass
class JudgeCalibrationResult:
    judge_name: str; human_agreement: float; bias_score: float
    bias_types: list = field(default_factory=list); n_calibration_items: int = 0

class BenchmarkPlugin(ABC):
    def __init__(self, benchmark=None, bench_library_path: str = ""):
        self.benchmark = benchmark; self.bench_library_path = bench_library_path
    @property
    @abstractmethod
    def plugin_manifest(self) -> PluginManifest: ...
    @property
    @abstractmethod
    def capability_tags(self) -> list: ...
    @property
    @abstractmethod
    def difficulty(self) -> str: ...
    @property
    @abstractmethod
    def domain(self) -> str: ...
    @abstractmethod
    async def run(self, model, n_samples: int = 10) -> dict: ...

class MetricPlugin(ABC):
    @abstractmethod
    def compute(self, items: list) -> MetricResult: ...
    @abstractmethod
    def compute_with_ci(self, items: list, n_bootstrap: int = 1000) -> MetricResult: ...
    @property
    @abstractmethod
    def metric_name(self) -> str: ...
    @property
    @abstractmethod
    def description(self) -> str: ...
    @property
    @abstractmethod
    def range(self) -> tuple: ...

class JudgePlugin(ABC):
    @abstractmethod
    async def judge(self, prompt: str, response: str, expected: Optional[str], criteria: str) -> JudgeScore: ...
    @abstractmethod
    async def calibrate(self, calibration_set: list) -> JudgeCalibrationResult: ...
    @property
    @abstractmethod
    def judge_name(self) -> str: ...
    @property
    @abstractmethod
    def bias_score(self) -> float: ...

class EnvironmentPlugin(ABC):
    @abstractmethod
    def reset(self, seed: Optional[int] = None) -> dict: ...
    @abstractmethod
    def step(self, state: dict, action: str) -> tuple: ...
    @abstractmethod
    def render(self, state: dict) -> str: ...
    @property
    @abstractmethod
    def action_space(self) -> list: ...
    @property
    @abstractmethod
    def max_steps(self) -> int: ...
