"""Eval Versioning System — semantic versioning for benchmark suites."""
from __future__ import annotations
import hashlib, json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class SemanticVersion:
    major: int; minor: int; patch: int; pre: Optional[str] = None

    @classmethod
    def parse(cls, s: str) -> "SemanticVersion":
        parts = s.split("-", 1)
        pre = parts[1] if len(parts) > 1 else None
        nums = parts[0].split(".")
        return cls(int(nums[0]), int(nums[1]), int(nums[2]), pre)

    def __str__(self): return f"{self.major}.{self.minor}.{self.patch}" + (f"-{self.pre}" if self.pre else "")
    def _tuple(self): return (self.major, self.minor, self.patch)
    def __lt__(self, other): return self._tuple() < other._tuple()
    def __eq__(self, other): return self._tuple() == other._tuple() and self.pre == other.pre
    def bump_patch(self): return SemanticVersion(self.major, self.minor, self.patch+1)
    def bump_minor(self): return SemanticVersion(self.major, self.minor+1, 0)
    def bump_major(self): return SemanticVersion(self.major+1, 0, 0)

@dataclass
class VersionDiff:
    from_version: str; to_version: str
    added: list = field(default_factory=list)
    modified: list = field(default_factory=list)
    removed: list = field(default_factory=list)
    summary: str = ""; breaking_change: bool = False

@dataclass
class BenchmarkVersion:
    benchmark_name: str; version: str
    dataset_hash: str; prompt_hash: str; scoring_hash: str
    n_items: int
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    changelog: str = ""

def hash_content(content) -> str:
    if isinstance(content, (dict,list)):
        data = json.dumps(content, sort_keys=True)
    else:
        data = str(content)
    return hashlib.sha256(data.encode()).hexdigest()

def compute_diff(items_v1, items_v2, id_field="id") -> VersionDiff:
    ids_v1 = {str(item.get(id_field,"")): hash_content(item) for item in items_v1}
    ids_v2 = {str(item.get(id_field,"")): hash_content(item) for item in items_v2}
    added = [k for k in ids_v2 if k not in ids_v1]
    removed = [k for k in ids_v1 if k not in ids_v2]
    modified = [k for k in ids_v1 if k in ids_v2 and ids_v1[k] != ids_v2[k]]
    return VersionDiff(from_version="v1", to_version="v2",
        added=added, modified=modified, removed=removed,
        summary=f"+{len(added)} -{len(removed)} ~{len(modified)}",
        breaking_change=len(removed)>0)

def create_version(benchmark_name, items, prompts, scoring, version, changelog="") -> BenchmarkVersion:
    return BenchmarkVersion(
        benchmark_name=benchmark_name, version=version,
        dataset_hash=hash_content(items), prompt_hash=hash_content(prompts),
        scoring_hash=hash_content(scoring), n_items=len(items), changelog=changelog,
    )

def diff_versions(v1: BenchmarkVersion, v2: BenchmarkVersion) -> dict:
    return {
        "dataset_changed": v1.dataset_hash != v2.dataset_hash,
        "prompts_changed": v1.prompt_hash != v2.prompt_hash,
        "scoring_changed": v1.scoring_hash != v2.scoring_hash,
        "breaking_change": v1.dataset_hash != v2.dataset_hash,
    }
