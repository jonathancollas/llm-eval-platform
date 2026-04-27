"""Reproducibility Engine — SHA-256 fingerprinting of experiment configurations."""
import hashlib
import json
import platform
import sys
from dataclasses import dataclass, field
from datetime import datetime, UTC


@dataclass
class EnvironmentSnapshot:
    python_version: str
    platform_os: str
    platform_arch: str
    platform_version: str
    timestamp: str


@dataclass
class ExperimentFingerprint:
    fingerprint_hash: str
    config_hash: str
    dataset_hash: str
    prompt_hash: str
    seed: int
    temperature: float
    model_configs_json: str
    benchmark_configs_json: str
    environment: EnvironmentSnapshot
    created_at: str


def capture_environment() -> EnvironmentSnapshot:
    return EnvironmentSnapshot(
        python_version=sys.version,
        platform_os=platform.system(),
        platform_arch=platform.machine(),
        platform_version=platform.version(),
        timestamp=datetime.now(UTC).isoformat(),
    )


def hash_config(config: dict) -> str:
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()


def hash_dataset(items: list) -> str:
    return hashlib.sha256(json.dumps(items, sort_keys=True).encode()).hexdigest()


def generate_fingerprint(
    campaign_config: dict,
    model_configs: list,
    benchmark_configs: list,
    seed: int,
    temperature: float,
) -> ExperimentFingerprint:
    env = capture_environment()
    config_hash = hash_config(campaign_config)
    dataset_hash = hash_dataset(model_configs)
    prompt_hash = hash_dataset(benchmark_configs)
    combined = f"{config_hash}{dataset_hash}{prompt_hash}{seed}{temperature}{env.python_version}"
    fingerprint_hash = hashlib.sha256(combined.encode()).hexdigest()

    return ExperimentFingerprint(
        fingerprint_hash=fingerprint_hash,
        config_hash=config_hash,
        dataset_hash=dataset_hash,
        prompt_hash=prompt_hash,
        seed=seed,
        temperature=temperature,
        model_configs_json=json.dumps(model_configs),
        benchmark_configs_json=json.dumps(benchmark_configs),
        environment=env,
        created_at=datetime.now(UTC).isoformat(),
    )


def validate_reproducibility(
    fp_a: ExperimentFingerprint, fp_b: ExperimentFingerprint
) -> dict:
    differences = []
    for field_name in ["config_hash", "dataset_hash", "prompt_hash", "seed", "temperature"]:
        if getattr(fp_a, field_name) != getattr(fp_b, field_name):
            differences.append(field_name)

    return {
        "identical": len(differences) == 0,
        "differences": differences,
        "reproducible": len(differences) == 0,
    }


def build_provenance_chain(run_config: dict, dataset_hash: str, prompt_hash: str) -> dict:
    """Build a cryptographic provenance chain for a run."""
    import hashlib, json as _json
    chain_data = _json.dumps({
        "run_config": run_config,
        "dataset_hash": dataset_hash,
        "prompt_hash": prompt_hash,
    }, sort_keys=True)
    chain_hash = hashlib.sha256(chain_data.encode()).hexdigest()
    return {"chain_hash": chain_hash, "components": {"dataset": dataset_hash, "prompts": prompt_hash}}


def replay_run_config(run_id: int, session) -> dict:
    """Return the exact config needed to replay a run deterministically."""
    from core.models import EvalRun
    import json
    run = session.get(EvalRun, run_id)
    if not run:
        return {"error": f"Run {run_id} not found"}
    ctx = json.loads(run.run_context_json or "{}")
    return {
        "run_id": run_id,
        "seed": ctx.get("seed", 42),
        "temperature": ctx.get("temperature", 0.0),
        "model_id": run.model_id,
        "benchmark_id": run.benchmark_id,
        "prompt_version": ctx.get("prompt_version", "default"),
        "platform_version": ctx.get("platform_version", "unknown"),
        "replay_command": f"mercury eval replay --run-id {run_id}",
    }
