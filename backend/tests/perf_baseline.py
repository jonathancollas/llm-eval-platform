"""
Performance baseline script — measures P50/P95/P99 latency for critical endpoints.

Usage:
    cd backend
    python tests/perf_baseline.py [--base-url http://localhost:8000] [--runs 10] [--output /tmp/baseline.json]

Outputs a JSON file with latency percentiles per endpoint that can be compared before/after
a performance fix to quantify improvement.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

try:
    import httpx
except ImportError:
    raise SystemExit("httpx is required: pip install httpx")

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_RUNS = 10

ENDPOINTS = [
    ("GET", "/api/campaigns/", "campaigns_list"),
    ("GET", "/api/leaderboard/global", "leaderboard_global"),
    ("GET", "/api/genome/safety-heatmap", "genome_safety_heatmap"),
    ("GET", "/api/genome/models", "genome_model_fingerprints"),
    ("GET", "/api/catalog/models", "catalog_models"),
    ("GET", "/api/health", "health"),
]

# Optional — filled in dynamically if a campaign/run exists
DYNAMIC_ENDPOINTS: list[tuple[str, str, str]] = []


def _percentile(data: list[float], p: int) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(sorted_data) - 1)
    return round(sorted_data[lo] + (sorted_data[hi] - sorted_data[lo]) * (k - lo), 1)


def measure_endpoint(
    client: httpx.Client,
    method: str,
    url: str,
    runs: int,
) -> dict:
    latencies: list[float] = []
    errors = 0
    status_codes: list[int] = []

    for _ in range(runs):
        t0 = time.perf_counter()
        try:
            resp = client.request(method, url, timeout=30.0)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            latencies.append(elapsed_ms)
            status_codes.append(resp.status_code)
        except Exception:
            errors += 1

    if not latencies:
        return {"error": "all requests failed", "runs": runs, "errors": errors}

    return {
        "runs": runs,
        "errors": errors,
        "success_rate": round(len(latencies) / runs, 3),
        "p50_ms": _percentile(latencies, 50),
        "p95_ms": _percentile(latencies, 95),
        "p99_ms": _percentile(latencies, 99),
        "min_ms": round(min(latencies), 1),
        "max_ms": round(max(latencies), 1),
        "mean_ms": round(statistics.mean(latencies), 1),
        "status_codes": list(set(status_codes)),
    }


def discover_dynamic_endpoints(client: httpx.Client, base_url: str) -> list[tuple[str, str, str]]:
    """Try to discover a campaign ID and run ID to add dynamic endpoints."""
    extra: list[tuple[str, str, str]] = []
    try:
        resp = client.get(f"{base_url}/api/campaigns/", timeout=10.0)
        if resp.status_code == 200:
            campaigns = resp.json()
            if campaigns:
                cid = campaigns[0]["id"]
                extra.append(("GET", f"/api/results/campaign/{cid}/dashboard", f"dashboard_campaign_{cid}"))
                extra.append(("GET", f"/api/results/campaign/{cid}/live", f"live_feed_campaign_{cid}"))
                extra.append(("GET", f"/api/genome/campaigns/{cid}", f"genome_campaign_{cid}"))
    except Exception:
        pass
    return extra


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM Eval Platform — performance baseline")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument("--output", default="/tmp/perf_baseline.json")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    print(f"Measuring against {base_url}  ({args.runs} runs per endpoint)\n")

    results: dict[str, dict] = {}

    with httpx.Client(base_url=base_url) as client:
        dynamic = discover_dynamic_endpoints(client, base_url)
        all_endpoints = ENDPOINTS + dynamic

        for method, path, name in all_endpoints:
            print(f"  {method:4s} {path:<60s} ", end="", flush=True)
            result = measure_endpoint(client, method, path, args.runs)
            results[name] = {"method": method, "path": path, **result}
            if "error" in result:
                print(f"FAILED ({result['error']})")
            else:
                print(
                    f"p50={result['p50_ms']:7.1f}ms  "
                    f"p95={result['p95_ms']:7.1f}ms  "
                    f"p99={result['p99_ms']:7.1f}ms  "
                    f"(errors={result['errors']})"
                )

    output_path = Path(args.output)
    output_path.write_text(json.dumps({"base_url": base_url, "results": results}, indent=2))
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
